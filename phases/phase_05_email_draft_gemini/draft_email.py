from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import smtplib
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

BASE_SUBJECT = "Weekly Review Insights - GROWW"


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^\s*```(?:json|html|markdown|md|text)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    return cleaned.strip()


def _required_blocks_present(text: str) -> bool:
    required = [
        "TOP 5 THEMES THIS WEEK",
        "3 ACTION IDEAS",
        "TOP 5 REVIEW HIGHLIGHTS",
        "DATA and APPLICATION",
    ]
    return all(block in text for block in required)


def _strip_html_to_text(html_text: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", html_text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"(?i)</h[1-6]\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_llm_json(raw_text: str) -> dict:
    cleaned = _strip_code_fences(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise
        return json.loads(match.group(0))


def _gemini_bodies(note_text: str, model: str, app_link: str, attachment_line: str) -> tuple[str, str]:
    from google import genai

    prompt_path = Path("phases/phase_05_email_draft_gemini/prompts/email_prompt.md")
    prompt = prompt_path.read_text(encoding="utf-8")

    combined_prompt = (
        f"{prompt}\n\n"
        f"Application link: {app_link}\n"
        f"Attachment filenames: {attachment_line}\n\n"
        "Weekly note input:\n"
        f"{note_text}"
    )

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(model=model, contents=combined_prompt)
    raw = (getattr(response, "text", "") or str(response)).strip()

    payload = _parse_llm_json(raw)
    plain_body = str(payload.get("plain_body", "")).strip()
    html_body = str(payload.get("html_body", "")).strip()

    if not plain_body and html_body:
        plain_body = _strip_html_to_text(html_body)

    if not plain_body or not html_body:
        raise ValueError("LLM output missing plain_body or html_body")

    if not _required_blocks_present(plain_body):
        raise ValueError("LLM plain_body missing required sections")

    return plain_body, html_body


def _fallback_bodies(note_text: str, app_link: str, attachment_line: str) -> tuple[str, str]:
    snapshot_lines = [line.strip() for line in note_text.splitlines() if line.strip()][:10]
    snapshot = "\n".join(snapshot_lines)

    plain_body = (
        "Hello Team,\n\n"
        "This is your weekly one-page pulse from Groww Play Store reviews. "
        "PDF and CSV are attached for reference.\n\n"
        "TOP 5 THEMES THIS WEEK\n"
        "Refer to the attached weekly note for theme summaries.\n\n"
        "3 ACTION IDEAS\n"
        "Refer to the attached weekly note for prioritized actions.\n\n"
        "TOP 5 REVIEW HIGHLIGHTS\n"
        "Refer to the attached weekly note for top review highlights by theme.\n\n"
        "DATA and APPLICATION\n"
        f"Application link: {app_link}\n"
        f"Attachments: {attachment_line}\n\n"
        + (f"Quick note snapshot:\n{snapshot}\n\n" if snapshot else "")
        + "Best regards,\nVadthyavath Shiva\n\n"
        "*This is an auto-generated mail.*"
    )

    html_body = (
        "<p>Hello Team,</p>"
        "<p>This is your weekly one-page pulse from Groww Play Store reviews. "
        "PDF and CSV are attached for reference.</p>"
        "<p><strong>TOP 5 THEMES THIS WEEK</strong><br/>Refer to the attached weekly note for theme summaries.</p>"
        "<p><strong>3 ACTION IDEAS</strong><br/>Refer to the attached weekly note for prioritized actions.</p>"
        "<p><strong>TOP 5 REVIEW HIGHLIGHTS</strong><br/>Refer to the attached weekly note for top review highlights by theme.</p>"
        f"<p><strong>DATA and APPLICATION</strong><br/>Application link: {app_link}<br/>Attachments: {attachment_line}</p>"
        + (f"<p><strong>Quick note snapshot</strong><br/>{snapshot.replace(chr(10), '<br/>')}</p>" if snapshot else "")
        + "<p>Best regards,<br/>Vadthyavath Shiva</p>"
        "<p><em>This is an auto-generated mail.</em></p>"
    )

    return plain_body, html_body


def _guess_mime_type(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application", "pdf"
    if suffix == ".csv":
        return "text", "csv"
    return "application", "octet-stream"


def _build_message(
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str,
    attachment_paths: list[Path],
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

    for path in attachment_paths:
        if not path.exists():
            raise FileNotFoundError(f"Attachment not found: {path}")

        maintype, subtype = _guess_mime_type(path)
        data = path.read_bytes()
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)

    return msg


def _smtp_send(msg: EmailMessage, host: str, port: int, username: str, password: str, use_tls: bool) -> None:
    with smtplib.SMTP(host, port, timeout=30) as server:
        if use_tls:
            server.starttls()
        server.login(username, password)
        server.send_message(msg)


def _send_via_resend(
    api_key: str,
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str,
    attachment_paths: list[Path],
) -> str | None:
    attachments = []
    for path in attachment_paths:
        if not path.exists():
            raise FileNotFoundError(f"Attachment not found: {path}")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        attachments.append({"filename": path.name, "content": encoded})

    payload = {
        "from": f"{from_name} <{from_email}>",
        "to": [to_email],
        "subject": subject,
        "text": body_text,
        "html": body_html,
        "attachments": attachments,
    }

    req = urllib.request.Request(
        url="https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw else {}
            return parsed.get("id")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Resend request failed: {exc.reason}") from exc


def _as_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _extract_week_end(themes_json_path: Path) -> str | None:
    if not themes_json_path.exists():
        return None

    try:
        payload = json.loads(themes_json_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None

    week_end = payload.get("analysis_window_end") or payload.get("week_end")
    if not week_end:
        return None

    return str(week_end)


def _prepare_dated_attachments(
    pdf_path: Path,
    csv_path: Path,
    week_end: str | None,
    attachments_output_dir: Path,
) -> tuple[Path, Path]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF attachment not found: {pdf_path}")
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV attachment not found: {csv_path}")

    attachments_output_dir.mkdir(parents=True, exist_ok=True)

    date_tag = week_end or datetime.now().date().isoformat()
    date_tag = re.sub(r"[^0-9-]", "-", date_tag)

    pdf_target = attachments_output_dir / f"groww_weekly_insights_{date_tag}.pdf"
    csv_target = attachments_output_dir / f"groww_reviews_redacted_{date_tag}.csv"

    if pdf_path.resolve() != pdf_target.resolve():
        shutil.copy2(pdf_path, pdf_target)
    if csv_path.resolve() != csv_target.resolve():
        shutil.copy2(csv_path, csv_target)

    return pdf_target, csv_target


def run(
    note_input_path: Path,
    themes_json_path: Path,
    output_path: Path,
    to_alias: str,
    pdf_path: Path,
    csv_path: Path,
    attachments_output_dir: Path,
    app_link: str,
    model: str,
    delivery_mode: str,
    dry_run: bool,
) -> None:
    load_dotenv()

    note = note_input_path.read_text(encoding="utf-8")
    week_end = _extract_week_end(themes_json_path)
    subject = f"{BASE_SUBJECT} | {week_end}" if week_end else BASE_SUBJECT

    dated_pdf, dated_csv = _prepare_dated_attachments(
        pdf_path=pdf_path,
        csv_path=csv_path,
        week_end=week_end,
        attachments_output_dir=attachments_output_dir,
    )
    attachment_line = f"{dated_pdf.name}, {dated_csv.name}"

    used_gemini = False
    generation_mode = "fallback_template"
    if os.getenv("GEMINI_API_KEY"):
        try:
            body_text, body_html = _gemini_bodies(
                note_text=note,
                model=model,
                app_link=app_link,
                attachment_line=attachment_line,
            )
            used_gemini = True
            generation_mode = "strict_llm_only"
        except Exception as exc:  # noqa: BLE001
            print(f"Gemini email generation failed, using fallback: {exc}")
            body_text, body_html = _fallback_bodies(
                note_text=note,
                app_link=app_link,
                attachment_line=attachment_line,
            )
    else:
        print("GEMINI_API_KEY not set, using fallback email body.")
        body_text, body_html = _fallback_bodies(
            note_text=note,
            app_link=app_link,
            attachment_line=attachment_line,
        )

    draft = f"Subject: {subject}\nTo: {to_alias}\n\n{body_text}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(draft, encoding="utf-8")
    print(f"Saved email draft to {output_path}")

    email_provider = os.getenv("EMAIL_PROVIDER", "resend").strip().lower()
    from_name = os.getenv("EMAIL_FROM_NAME", "Vadthyavath Shiva").strip() or "Vadthyavath Shiva"
    from_email = (
        os.getenv("EMAIL_FROM_ADDRESS", "").strip()
        or os.getenv("RESEND_FROM_EMAIL", "").strip()
        or os.getenv("SMTP_USERNAME", "").strip()
    )

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_use_tls = _as_bool(os.getenv("SMTP_USE_TLS", "true"), default=True)

    resend_api_key = os.getenv("RESEND_API_KEY", "").strip()

    if dry_run:
        print("Dry run enabled. Email not sent.")
        transport_used = "none"
        transport_status = "dry_run"
    else:
        if not to_alias:
            raise ValueError("Recipient email missing. Set EMAIL_TO_ALIAS or pass --to")
        if not from_email:
            raise ValueError("Sender email missing. Set EMAIL_FROM_ADDRESS or RESEND_FROM_EMAIL or SMTP_USERNAME")

        if email_provider == "resend":
            if not resend_api_key:
                raise ValueError("RESEND_API_KEY is required when EMAIL_PROVIDER=resend")
            message_id = _send_via_resend(
                api_key=resend_api_key,
                from_email=from_email,
                from_name=from_name,
                to_email=to_alias,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                attachment_paths=[dated_pdf, dated_csv],
            )
            print(f"Email sent via Resend to {to_alias}. message_id={message_id}")
            transport_used = "resend"
            transport_status = "sent"
        elif email_provider == "smtp":
            missing = []
            if not smtp_username:
                missing.append("SMTP_USERNAME")
            if not smtp_password:
                missing.append("SMTP_PASSWORD")
            if missing:
                raise ValueError("Missing required SMTP settings: " + ", ".join(missing))

            msg = _build_message(
                from_email=from_email,
                from_name=from_name,
                to_email=to_alias,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                attachment_paths=[dated_pdf, dated_csv],
            )
            _smtp_send(
                msg=msg,
                host=smtp_host,
                port=smtp_port,
                username=smtp_username,
                password=smtp_password,
                use_tls=smtp_use_tls,
            )
            print(f"Email sent via SMTP to {to_alias}")
            transport_used = "smtp"
            transport_status = "sent"
        else:
            raise ValueError("EMAIL_PROVIDER must be either 'resend' or 'smtp'")

    meta = {
        "subject": subject,
        "week_end": week_end,
        "to": to_alias,
        "from": from_email,
        "used_gemini": used_gemini,
        "model": model,
        "delivery_mode": delivery_mode,
        "dry_run": dry_run,
        "attachments": [str(dated_pdf), str(dated_csv)],
        "app_link": app_link,
        "generation_mode": generation_mode,
        "email_provider": email_provider,
        "transport_used": transport_used,
        "transport_status": transport_status,
    }
    meta_path = output_path.with_name("email_draft_meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Saved email metadata to {meta_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and auto-send structured email from weekly note")
    parser.add_argument("--input", default="data/outputs/weekly_note.md")
    parser.add_argument("--themes-json", default="data/processed/themes_weekly.json")
    parser.add_argument("--output", default="data/outputs/email_draft.txt")
    parser.add_argument("--to", default=os.getenv("EMAIL_TO_ALIAS", ""))
    parser.add_argument("--pdf-path", default="data/outputs/weekly_note.pdf")
    parser.add_argument("--csv-path", default="data/processed/reviews_15w_redacted.csv")
    parser.add_argument("--attachments-output-dir", default="data/outputs")
    parser.add_argument("--app-link", default=os.getenv("PHASE7_APP_LINK", "https://groww-review-insight-analyser.vercel.app"))
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"))
    parser.add_argument(
        "--delivery-mode",
        choices=["manual_cli", "scheduled_weekly", "instant_frontend"],
        default="manual_cli",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run(
        note_input_path=Path(args.input),
        themes_json_path=Path(args.themes_json),
        output_path=Path(args.output),
        to_alias=args.to,
        pdf_path=Path(args.pdf_path),
        csv_path=Path(args.csv_path),
        attachments_output_dir=Path(args.attachments_output_dir),
        app_link=args.app_link,
        model=args.model,
        delivery_mode=args.delivery_mode,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
