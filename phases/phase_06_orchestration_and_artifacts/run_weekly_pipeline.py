from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv


@dataclass(frozen=True)
class Step:
    step_id: str
    name: str
    cmd: list[str]


STEP_ORDER = [
    "phase_01_ingest",
    "phase_01_week_filter",
    "phase_02_clean",
    "phase_03_theme_grouping",
    "phase_04_weekly_note",
    "phase_05_pdf",
    "phase_05_email",
    "phase_06_artifacts",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run(cmd: list[str]) -> None:
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _validate_week_range(weeks_from: int, weeks_to: int) -> None:
    if weeks_from < 1 or weeks_from > 15:
        raise ValueError("--weeks-from must be between 1 and 15")
    if weeks_to < 1 or weeks_to > 15:
        raise ValueError("--weeks-to must be between 1 and 15")
    if weeks_from > weeks_to:
        raise ValueError("--weeks-from must be <= --weeks-to")


def _resolve_recipient(explicit_email: str | None, delivery_mode: str) -> str:
    if explicit_email and explicit_email.strip():
        return explicit_email.strip()

    if delivery_mode == "scheduled_weekly":
        weekly_email = os.getenv("WEEKLY_SCHEDULED_RECIPIENT", "").strip()
        if weekly_email:
            return weekly_email
        raise ValueError("WEEKLY_SCHEDULED_RECIPIENT is required for scheduled_weekly mode")

    alias_email = os.getenv("EMAIL_TO_ALIAS", "").strip()
    if alias_email:
        return alias_email

    raise ValueError("Recipient email missing. Set EMAIL_TO_ALIAS or pass --email-to")


def _base_steps(
    py: str,
    app_id: str,
    recipient_email: str,
    delivery_mode: str,
    email_dry_run: bool,
    weeks_from: int,
    weeks_to: int,
) -> list[Step]:
    return [
        Step(
            step_id="phase_01_ingest",
            name="Fetch reviews from Play Store",
            cmd=[
                py,
                "phases/phase_01_ingest/fetch_reviews.py",
                "--app-id",
                app_id,
                "--weeks",
                str(weeks_to),
                "--output",
                "data/raw/reviews_15w.csv",
                "--meta-output",
                "data/raw/reviews_15w_meta.json",
            ],
        ),
        Step(
            step_id="phase_01_week_filter",
            name="Apply selected week-range filter",
            cmd=[
                py,
                "phases/phase_06_orchestration_and_artifacts/apply_week_range_filter.py",
                "--input",
                "data/raw/reviews_15w.csv",
                "--meta",
                "data/raw/reviews_15w_meta.json",
                "--weeks-from",
                str(weeks_from),
                "--weeks-to",
                str(weeks_to),
            ],
        ),
        Step(
            step_id="phase_02_clean",
            name="Redact and clean reviews",
            cmd=[
                py,
                "phases/phase_02_privacy_and_cleaning/clean_and_redact.py",
                "--input",
                "data/raw/reviews_15w.csv",
                "--output",
                "data/processed/reviews_15w_redacted.csv",
                "--meta-output",
                "data/processed/reviews_15w_redacted_meta.json",
            ],
        ),
        Step(
            step_id="phase_03_theme_grouping",
            name="Theme grouping with Claude",
            cmd=[
                py,
                "phases/phase_03_theme_grouping_claude/theme_grouping.py",
                "--input",
                "data/processed/reviews_15w_redacted.csv",
                "--output",
                "data/processed/themes_weekly.json",
            ],
        ),
        Step(
            step_id="phase_04_weekly_note",
            name="Generate weekly note",
            cmd=[
                py,
                "phases/phase_04_weekly_note_gemini/generate_weekly_note.py",
                "--input",
                "data/processed/themes_weekly.json",
                "--assignments-input",
                "data/processed/theme_assignments_sample_400.csv",
                "--output",
                "data/outputs/weekly_note.md",
                "--meta-output",
                "data/outputs/weekly_note_meta.json",
            ],
        ),
        Step(
            step_id="phase_05_pdf",
            name="Render weekly PDF",
            cmd=[
                py,
                "phases/phase_05_email_draft_gemini/generate_weekly_pdf.py",
                "--input",
                "data/outputs/weekly_note.md",
                "--themes-json",
                "data/processed/themes_weekly.json",
                "--output",
                "data/outputs/weekly_note.pdf",
            ],
        ),
        Step(
            step_id="phase_05_email",
            name="Generate and send email",
            cmd=[
                py,
                "phases/phase_05_email_draft_gemini/draft_email.py",
                "--input",
                "data/outputs/weekly_note.md",
                "--themes-json",
                "data/processed/themes_weekly.json",
                "--output",
                "data/outputs/email_draft.txt",
                "--pdf-path",
                "data/outputs/weekly_note.pdf",
                "--csv-path",
                "data/processed/reviews_15w_redacted.csv",
                "--to",
                recipient_email,
                "--delivery-mode",
                delivery_mode,
            ] + (["--dry-run"] if email_dry_run else []),
        ),
        Step(
            step_id="phase_06_artifacts",
            name="Package latest artifacts",
            cmd=[py, "phases/phase_06_orchestration_and_artifacts/make_artifacts.py"],
        ),
    ]


def _filter_steps(
    steps: list[Step],
    from_step: str | None,
    to_step: str | None,
    skip_email: bool,
    skip_artifacts: bool,
) -> list[Step]:
    step_ids = [s.step_id for s in steps]

    start_idx = 0
    if from_step:
        start_idx = step_ids.index(from_step)

    end_idx = len(steps) - 1
    if to_step:
        end_idx = step_ids.index(to_step)

    if start_idx > end_idx:
        raise ValueError("--from-step must be before or equal to --to-step")

    selected = steps[start_idx : end_idx + 1]

    if skip_email:
        selected = [s for s in selected if s.step_id != "phase_05_email"]

    if skip_artifacts:
        selected = [s for s in selected if s.step_id != "phase_06_artifacts"]

    return selected


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run weekly GROWW review pipeline")
    parser.add_argument("--app-id", default="com.nextbillion.groww")
    parser.add_argument("--email-to", default=None)
    parser.add_argument(
        "--delivery-mode",
        choices=["manual_cli", "scheduled_weekly", "instant_frontend"],
        default="manual_cli",
    )
    parser.add_argument("--email-dry-run", action="store_true")
    parser.add_argument("--from-step", choices=STEP_ORDER, default=None)
    parser.add_argument("--to-step", choices=STEP_ORDER, default=None)
    parser.add_argument("--skip-email", action="store_true")
    parser.add_argument("--skip-artifacts", action="store_true")
    parser.add_argument("--weeks-from", type=int, default=1)
    parser.add_argument("--weeks-to", type=int, default=15)
    parser.add_argument("--meta-output", default="data/outputs/pipeline_run_meta.json")
    args = parser.parse_args()

    _validate_week_range(args.weeks_from, args.weeks_to)
    py = sys.executable

    # First pass: identify whether email step is in the selected plan.
    steps_probe = _base_steps(
        py=py,
        app_id=args.app_id,
        recipient_email="",
        delivery_mode=args.delivery_mode,
        email_dry_run=args.email_dry_run,
        weeks_from=args.weeks_from,
        weeks_to=args.weeks_to,
    )
    selected_probe = _filter_steps(
        steps=steps_probe,
        from_step=args.from_step,
        to_step=args.to_step,
        skip_email=args.skip_email,
        skip_artifacts=args.skip_artifacts,
    )

    needs_email = any(step.step_id == "phase_05_email" for step in selected_probe)
    recipient_email = _resolve_recipient(args.email_to, args.delivery_mode) if needs_email else ""

    steps = _base_steps(
        py=py,
        app_id=args.app_id,
        recipient_email=recipient_email,
        delivery_mode=args.delivery_mode,
        email_dry_run=args.email_dry_run,
        weeks_from=args.weeks_from,
        weeks_to=args.weeks_to,
    )
    selected_steps = _filter_steps(
        steps=steps,
        from_step=args.from_step,
        to_step=args.to_step,
        skip_email=args.skip_email,
        skip_artifacts=args.skip_artifacts,
    )

    run_summary: dict = {
        "started_at_utc": _utc_now_iso(),
        "ended_at_utc": None,
        "status": "running",
        "app_id": args.app_id,
        "delivery_mode": args.delivery_mode,
        "recipient_email": recipient_email if needs_email else None,
        "email_dry_run": args.email_dry_run,
        "week_range": {"from": args.weeks_from, "to": args.weeks_to},
        "selected_steps": [s.step_id for s in selected_steps],
        "steps": [],
    }

    meta_path = Path(args.meta_output)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        for step in selected_steps:
            t0 = perf_counter()
            step_started = _utc_now_iso()
            try:
                _run(step.cmd)
                status = "success"
                error = None
            except subprocess.CalledProcessError as exc:
                status = "failed"
                error = f"exit_code={exc.returncode}"
                run_summary["steps"].append(
                    {
                        "step_id": step.step_id,
                        "name": step.name,
                        "status": status,
                        "started_at_utc": step_started,
                        "ended_at_utc": _utc_now_iso(),
                        "duration_sec": round(perf_counter() - t0, 3),
                        "command": step.cmd,
                        "error": error,
                    }
                )
                raise

            run_summary["steps"].append(
                {
                    "step_id": step.step_id,
                    "name": step.name,
                    "status": status,
                    "started_at_utc": step_started,
                    "ended_at_utc": _utc_now_iso(),
                    "duration_sec": round(perf_counter() - t0, 3),
                    "command": step.cmd,
                    "error": error,
                }
            )

        run_summary["status"] = "success"
    except Exception as exc:  # noqa: BLE001
        run_summary["status"] = "failed"
        run_summary["error"] = str(exc)
        raise
    finally:
        run_summary["ended_at_utc"] = _utc_now_iso()
        meta_path.write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
        print(f"Pipeline run metadata written to {meta_path}")

    print("Pipeline completed. Check artifacts/latest/ for deliverables.")


if __name__ == "__main__":
    main()
