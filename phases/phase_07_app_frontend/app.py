from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from phases.phase_05_email_draft_gemini.draft_email import run as run_email_draft


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NOTE_PATH = ROOT / "data/outputs/weekly_note.md"
DEFAULT_NOTE_META_PATH = ROOT / "data/outputs/weekly_note_meta.json"
DEFAULT_THEMES_JSON_PATH = ROOT / "data/processed/themes_weekly.json"
DEFAULT_PIPELINE_META_PATH = ROOT / "data/outputs/pipeline_run_meta.json"
DEFAULT_OUTPUT_PATH = ROOT / "data/outputs/email_draft.txt"
DEFAULT_PDF_PATH = ROOT / "data/outputs/weekly_note.pdf"
DEFAULT_CSV_PATH = ROOT / "data/processed/reviews_15w_redacted.csv"
DEFAULT_ATTACHMENTS_DIR = ROOT / "data/outputs"


def _is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _extract_section(lines: list[str], start: str, end: str | None) -> list[str]:
    try:
        sidx = lines.index(start)
    except ValueError:
        return []

    if end is None:
        return lines[sidx + 1 :]

    try:
        eidx = lines.index(end)
    except ValueError:
        eidx = len(lines)

    return lines[sidx + 1 : eidx]


def _parse_theme_oneliners(note_text: str) -> dict[str, str]:
    lines = note_text.splitlines()
    section = _extract_section(lines, "## Theme One-Liners", "## Quick Summary")

    items: dict[str, str] = {}
    for raw in section:
        line = raw.strip().strip("- ")
        if not line:
            continue

        line = re.sub(r"^\*\*", "", line)
        line = re.sub(r"\*\*$", "", line)
        line = line.replace("**", "")

        if ":" in line:
            key, value = line.split(":", 1)
            items[key.strip()] = value.strip()

    return items


def _parse_actionable_insights(note_text: str) -> list[str]:
    lines = note_text.splitlines()
    section = _extract_section(lines, "## 3 Actionable Insights and Advice", "## Top 5 User Reviews By Theme")

    actions: list[str] = []
    for raw in section:
        line = raw.strip()
        m = re.match(r"^\d+\.\s+(.+)$", line)
        if m:
            actions.append(m.group(1).strip())

    return actions


def _format_dt(value: str) -> str:
    if not value:
        return "N/A"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return value


def _latest_updated() -> str:
    note_meta = _read_json(DEFAULT_NOTE_META_PATH)
    pipeline_meta = _read_json(DEFAULT_PIPELINE_META_PATH)

    if note_meta.get("generated_at_utc"):
        return _format_dt(str(note_meta.get("generated_at_utc")))
    if pipeline_meta.get("ended_at_utc"):
        return _format_dt(str(pipeline_meta.get("ended_at_utc")))
    return "N/A"


def _run_pipeline_and_send(recipient: str, weeks_from: int, weeks_to: int, dry_run: bool) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        "phases/phase_06_orchestration_and_artifacts/run_weekly_pipeline.py",
        "--app-id",
        "com.nextbillion.groww",
        "--weeks-from",
        str(weeks_from),
        "--weeks-to",
        str(weeks_to),
        "--email-to",
        recipient,
        "--delivery-mode",
        "instant_frontend",
    ]
    if dry_run:
        cmd.append("--email-dry-run")

    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    return result.returncode == 0, output.strip()


def _send_current_email(recipient: str, dry_run: bool) -> None:
    run_email_draft(
        note_input_path=DEFAULT_NOTE_PATH,
        themes_json_path=DEFAULT_THEMES_JSON_PATH,
        output_path=DEFAULT_OUTPUT_PATH,
        to_alias=recipient,
        pdf_path=DEFAULT_PDF_PATH,
        csv_path=DEFAULT_CSV_PATH,
        attachments_output_dir=DEFAULT_ATTACHMENTS_DIR,
        app_link=os.getenv("PHASE7_APP_LINK", "[Dashboard link to be added in Phase 7]"),
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
        delivery_mode="instant_frontend",
        dry_run=dry_run,
    )


def main() -> None:
    load_dotenv(ROOT / ".env")
    st.set_page_config(page_title="GROWW Reviews - Analyser", layout="wide")

    note_text = _read_text(DEFAULT_NOTE_PATH)
    themes_payload = _read_json(DEFAULT_THEMES_JSON_PATH)
    themes = themes_payload.get("themes", [])
    one_liners = _parse_theme_oneliners(note_text)
    actions = _parse_actionable_insights(note_text)

    header_left, header_right = st.columns([4, 1])
    with header_left:
        st.title("GROWW Reviews - Analyser")
    with header_right:
        st.caption(f"Latest Updated: {_latest_updated()}")
        st.caption(f"Process Loaded: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    st.sidebar.header("Run & Send")
    default_email = os.getenv("EMAIL_TO_ALIAS", "")
    recipient = st.sidebar.text_input("Recipient email", value=default_email)
    weeks_from = st.sidebar.number_input("From week (1=latest)", min_value=1, max_value=15, value=1, step=1)
    weeks_to = st.sidebar.number_input("To week (<=15)", min_value=1, max_value=15, value=15, step=1)
    dry_run = st.sidebar.checkbox("Dry run (do not send email)", value=False)

    send_now = st.sidebar.button("Send Current Generated Email")
    rerun_send = st.sidebar.button("Reprocess Selected Weeks and Send Email")

    if send_now:
        if not _is_valid_email(recipient.strip()):
            st.sidebar.error("Enter a valid recipient email.")
        else:
            with st.spinner("Sending current generated email..."):
                try:
                    _send_current_email(recipient=recipient.strip(), dry_run=dry_run)
                    if dry_run:
                        st.sidebar.success("Draft generated (dry run).")
                    else:
                        st.sidebar.success("Email sent successfully.")
                except Exception as exc:  # noqa: BLE001
                    st.sidebar.error(f"Send failed: {exc}")

    if rerun_send:
        if not _is_valid_email(recipient.strip()):
            st.sidebar.error("Enter a valid recipient email.")
        elif int(weeks_from) > int(weeks_to):
            st.sidebar.error("From week must be <= To week.")
        else:
            with st.spinner("Running full process for selected week range and sending email..."):
                ok, logs = _run_pipeline_and_send(
                    recipient=recipient.strip(),
                    weeks_from=int(weeks_from),
                    weeks_to=int(weeks_to),
                    dry_run=dry_run,
                )
                if ok:
                    if dry_run:
                        st.sidebar.success("Pipeline completed (email dry run).")
                    else:
                        st.sidebar.success("Pipeline completed and email sent.")
                    st.sidebar.info("Refreshing dashboard with latest outputs...")
                    st.rerun()
                else:
                    st.sidebar.error("Pipeline failed. See logs below.")
                    st.sidebar.text_area("Run logs", value=logs, height=250)

    col_main, col_side = st.columns([3, 1])

    with col_main:
        st.subheader("Themes")
        if not themes:
            st.info("Theme data not found. Run the pipeline first.")
        else:
            for theme in themes:
                name = str(theme.get("name", "Unnamed Theme"))
                one_line = one_liners.get(name) or str(theme.get("summary", "No summary available."))
                with st.expander(name, expanded=False):
                    st.write(one_line)

        st.subheader("Actionable Insights")
        if actions:
            for i, action in enumerate(actions, start=1):
                st.write(f"{i}. {action}")
        else:
            fallback_actions = themes_payload.get("actionable_insight_candidates", [])
            if fallback_actions:
                for i, item in enumerate(fallback_actions[:5], start=1):
                    st.write(f"{i}. {item.get('insight', 'No insight')} ({item.get('theme', 'N/A')})")
            else:
                st.info("No actionable insights available.")

        st.subheader("Top 5 Reviews of Each Theme")
        if themes:
            for theme in themes:
                name = str(theme.get("name", "Unnamed Theme"))
                st.markdown(f"**{name}**")
                top_reviews = theme.get("top_reviews", [])[:5]
                if not top_reviews:
                    st.write("- No reviews available.")
                    continue
                for idx, review in enumerate(top_reviews, start=1):
                    rating = review.get("rating", "N/A")
                    date = review.get("date", "N/A")
                    text = str(review.get("text", "")).strip()
                    st.write(f"{idx}. ({rating}★, {date}) {text}")
                st.write("")

    with col_side:
        st.subheader("Current Window")
        st.write(f"From: {themes_payload.get('analysis_window_start', 'N/A')}")
        st.write(f"To: {themes_payload.get('analysis_window_end', 'N/A')}")
        st.write(f"Sample Size: {themes_payload.get('sampling', {}).get('sample_size_used', 'N/A')}")


if __name__ == "__main__":
    main()
