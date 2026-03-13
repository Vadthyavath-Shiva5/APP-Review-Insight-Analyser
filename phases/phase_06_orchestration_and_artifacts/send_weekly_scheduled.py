from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

DAY_INDEX = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
    "SUN": 6,
}


def _parse_time_hhmm(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("Time must be HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Invalid HH:MM time range")
    return hour, minute


def _within_schedule_window(now: datetime, day: str, hhmm: str, window_minutes: int) -> bool:
    day_key = day.strip().upper()
    if day_key not in DAY_INDEX:
        raise ValueError(f"Invalid day: {day}")

    if now.weekday() != DAY_INDEX[day_key]:
        return False

    hour, minute = _parse_time_hhmm(hhmm)
    now_total = now.hour * 60 + now.minute
    target_total = hour * 60 + minute
    return abs(now_total - target_total) <= window_minutes


def _iso_week_key(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Scheduled weekly trigger for GROWW pipeline email")
    parser.add_argument("--app-id", default="com.nextbillion.groww")
    parser.add_argument("--day", default=os.getenv("WEEKLY_SCHEDULE_DAY", "MON"))
    parser.add_argument("--time", default=os.getenv("WEEKLY_SCHEDULE_TIME", "10:00"))
    parser.add_argument("--window-minutes", type=int, default=30)
    parser.add_argument("--weeks-from", type=int, default=int(os.getenv("WEEKLY_WEEKS_FROM", "1")))
    parser.add_argument("--weeks-to", type=int, default=int(os.getenv("WEEKLY_WEEKS_TO", "15")))
    parser.add_argument("--state-file", default="data/outputs/scheduled_state.json")
    parser.add_argument("--email-dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-dedupe", action="store_true")
    args = parser.parse_args()

    recipient = os.getenv("WEEKLY_SCHEDULED_RECIPIENT", "").strip()
    if not recipient:
        raise ValueError("Set WEEKLY_SCHEDULED_RECIPIENT in .env for scheduled sends")

    now = datetime.now()
    state_path = Path(args.state_file)
    state = _load_state(state_path)

    if not args.force and not _within_schedule_window(now, args.day, args.time, args.window_minutes):
        print(
            f"Current local time {now.strftime('%Y-%m-%d %H:%M')} is outside scheduled window "
            f"{args.day} {args.time} (+/-{args.window_minutes} min). Skipping run."
        )
        return

    run_key = _iso_week_key(now)
    last_sent_key = str(state.get("last_success_iso_week", "")).strip()
    if not args.no_dedupe and not args.email_dry_run and last_sent_key == run_key:
        print(f"Weekly send already completed for {run_key}. Skipping duplicate run.")
        return

    cmd = [
        sys.executable,
        "phases/phase_06_orchestration_and_artifacts/run_weekly_pipeline.py",
        "--app-id",
        args.app_id,
        "--weeks-from",
        str(args.weeks_from),
        "--weeks-to",
        str(args.weeks_to),
        "--email-to",
        recipient,
        "--delivery-mode",
        "scheduled_weekly",
        "--meta-output",
        "data/outputs/pipeline_run_meta_scheduled.json",
    ]
    if args.email_dry_run:
        cmd.append("--email-dry-run")

    print("Running scheduled weekly pipeline for recipient:", recipient)
    subprocess.run(cmd, check=True)

    if not args.email_dry_run:
        state.update(
            {
                "last_success_iso_week": run_key,
                "last_sent_at_local": now.replace(microsecond=0).isoformat(),
                "recipient": recipient,
                "weeks_from": args.weeks_from,
                "weeks_to": args.weeks_to,
            }
        )
        _save_state(state_path, state)
        print(f"Scheduled state updated at {state_path}")


if __name__ == "__main__":
    main()
