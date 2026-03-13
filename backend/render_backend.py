from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "data" / "outputs" / "backend_trigger_runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")

STATE_LOCK = threading.Lock()
RUN_STATES: dict[str, dict] = {}
ACTIVE_RUN_ID: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, indent=2).encode("utf-8")


def _write_state(run_id: str, payload: dict) -> None:
    out_path = RUNS_DIR / f"{run_id}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    raw_len = handler.headers.get("Content-Length", "0").strip()
    try:
        content_len = int(raw_len)
    except ValueError:
        content_len = 0

    if content_len <= 0:
        return {}

    raw_body = handler.rfile.read(content_len)
    if not raw_body:
        return {}

    try:
        return json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc


def _validate_week_range(weeks_from: int, weeks_to: int) -> None:
    if weeks_from < 1 or weeks_from > 15:
        raise ValueError("weeksFrom must be between 1 and 15")
    if weeks_to < 1 or weeks_to > 15:
        raise ValueError("weeksTo must be between 1 and 15")
    if weeks_from > weeks_to:
        raise ValueError("weeksFrom must be <= weeksTo")


def _resolve_delivery_mode(payload: dict) -> str:
    requested = str(payload.get("deliveryMode", "")).strip()
    recipient = str(payload.get("recipientEmail", "")).strip()
    if requested in {"manual_cli", "scheduled_weekly", "instant_frontend"}:
        return requested
    return "instant_frontend" if recipient else "scheduled_weekly"


def _is_authorized(handler: BaseHTTPRequestHandler) -> bool:
    shared_token = os.getenv("PIPELINE_TRIGGER_TOKEN", "").strip()
    if not shared_token:
        return True

    auth_header = handler.headers.get("Authorization", "")
    expected = f"Bearer {shared_token}"
    return secrets.compare_digest(auth_header.strip(), expected)


def _run_pipeline_worker(run_id: str, command: list[str], context: dict) -> None:
    global ACTIVE_RUN_ID

    started_at = _utc_now_iso()
    base_state = {
        "run_id": run_id,
        "status": "running",
        "started_at_utc": started_at,
        "ended_at_utc": None,
        "context": context,
        "command": command,
        "return_code": None,
        "stdout": "",
        "stderr": "",
        "error": None,
    }

    with STATE_LOCK:
        RUN_STATES[run_id] = base_state
        _write_state(run_id, base_state)

    try:
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        status = "success" if proc.returncode == 0 else "failed"
        err = None if status == "success" else f"Pipeline exited with code {proc.returncode}"

        final_state = {
            **base_state,
            "status": status,
            "ended_at_utc": _utc_now_iso(),
            "return_code": proc.returncode,
            "stdout": (proc.stdout or "")[-20000:],
            "stderr": (proc.stderr or "")[-20000:],
            "error": err,
        }
    except Exception as exc:  # noqa: BLE001
        final_state = {
            **base_state,
            "status": "failed",
            "ended_at_utc": _utc_now_iso(),
            "return_code": -1,
            "stdout": "",
            "stderr": "",
            "error": str(exc),
        }

    with STATE_LOCK:
        RUN_STATES[run_id] = final_state
        _write_state(run_id, final_state)
        if ACTIVE_RUN_ID == run_id:
            ACTIVE_RUN_ID = None


class TriggerHandler(BaseHTTPRequestHandler):
    server_version = "GrowwPulseBackend/1.0"

    def _send_json(self, status_code: int, payload: dict) -> None:
        body = _json_bytes(payload)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self) -> None:
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Endpoint not found"})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            with STATE_LOCK:
                active = ACTIVE_RUN_ID
                latest = RUN_STATES.get(active) if active else None
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "status": "healthy",
                    "active_run_id": active,
                    "active_run_status": latest["status"] if latest else None,
                    "timestamp_utc": _utc_now_iso(),
                },
            )
            return

        if path.startswith("/status/"):
            run_id = path.split("/status/", 1)[1].strip()
            if not run_id:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Run ID is required"})
                return

            with STATE_LOCK:
                state = RUN_STATES.get(run_id)

            if not state:
                state_file = RUNS_DIR / f"{run_id}.json"
                if state_file.exists():
                    state = json.loads(state_file.read_text(encoding="utf-8"))

            if not state:
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": f"Run not found: {run_id}"})
                return

            self._send_json(HTTPStatus.OK, {"ok": True, "run": state})
            return

        self._not_found()

    def do_POST(self) -> None:  # noqa: N802
        global ACTIVE_RUN_ID

        parsed = urlparse(self.path)
        if parsed.path != "/trigger":
            self._not_found()
            return

        if not _is_authorized(self):
            self._send_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Unauthorized"})
            return

        try:
            payload = _read_json_body(self)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        app_id = str(payload.get("appId") or "com.nextbillion.groww").strip()
        recipient_email = str(payload.get("recipientEmail") or "").strip()
        weeks_from = int(payload.get("weeksFrom", 1))
        weeks_to = int(payload.get("weeksTo", 15))
        email_dry_run = bool(payload.get("emailDryRun", False))

        try:
            _validate_week_range(weeks_from, weeks_to)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        with STATE_LOCK:
            if ACTIVE_RUN_ID:
                self._send_json(
                    HTTPStatus.CONFLICT,
                    {
                        "ok": False,
                        "error": "A pipeline run is already active",
                        "active_run_id": ACTIVE_RUN_ID,
                    },
                )
                return

            run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
            delivery_mode = _resolve_delivery_mode(payload)

            command = [
                sys.executable,
                "phases/phase_06_orchestration_and_artifacts/run_weekly_pipeline.py",
                "--app-id",
                app_id,
                "--weeks-from",
                str(weeks_from),
                "--weeks-to",
                str(weeks_to),
                "--delivery-mode",
                delivery_mode,
                "--meta-output",
                f"data/outputs/backend_trigger_runs/{run_id}_pipeline_meta.json",
            ]

            if recipient_email:
                command.extend(["--email-to", recipient_email])
            if email_dry_run:
                command.append("--email-dry-run")

            context = {
                "app_id": app_id,
                "recipient_email": recipient_email or None,
                "weeks_from": weeks_from,
                "weeks_to": weeks_to,
                "delivery_mode": delivery_mode,
                "email_dry_run": email_dry_run,
                "requested_at_utc": _utc_now_iso(),
            }

            ACTIVE_RUN_ID = run_id

        worker = threading.Thread(
            target=_run_pipeline_worker,
            args=(run_id, command, context),
            daemon=True,
            name=f"pipeline-{run_id}",
        )
        worker.start()

        self._send_json(
            HTTPStatus.ACCEPTED,
            {
                "ok": True,
                "message": "Pipeline accepted",
                "run_id": run_id,
                "status_url": f"/status/{run_id}",
                "context": context,
            },
        )

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        # Keep Render logs concise and still informative.
        print(f"[{self.log_date_time_string()}] {self.address_string()} - {fmt % args}")


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    host = "0.0.0.0"
    server = ThreadingHTTPServer((host, port), TriggerHandler)

    print(f"Groww backend listening on http://{host}:{port}")
    print("Endpoints: GET /health, POST /trigger, GET /status/<run_id>")
    server.serve_forever()


if __name__ == "__main__":
    main()
