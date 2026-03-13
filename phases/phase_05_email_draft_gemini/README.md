# Phase 05 - LLM Email Draft And Auto-Send

Purpose: generate and send a weekly insights email with strict LLM-only body generation.

Inputs:
- `data/outputs/weekly_note.md`
- `data/outputs/weekly_note.pdf`
- `data/processed/reviews_15w_redacted.csv`

Outputs:
- `data/outputs/email_draft.txt`
- `data/outputs/email_draft_meta.json`
- Date-stamped attachments:
  - `data/outputs/groww_weekly_insights_<week_end>.pdf`
  - `data/outputs/groww_reviews_redacted_<week_end>.csv`

Email behavior:
- Subject format: `Weekly Review Insights - GROWW | <week_end_date>`
- Body generation mode: `strict_llm_only`
- LLM returns both `plain_body` and `html_body` in JSON
- No manual fallback formatting path
- Sends multipart email (HTML + plain text)

Recipient modes:
- `manual_cli`: direct send from CLI
- `scheduled_weekly`: weekly trigger recipient flow
- `instant_frontend`: immediate send for frontend-entered recipient

Required env for auto-send:
- `GEMINI_API_KEY` (mandatory)
- `SMTP_HOST` (default: `smtp.gmail.com`)
- `SMTP_PORT` (default: `587`)
- `SMTP_USE_TLS` (default: `true`)
- `SMTP_USERNAME`
- `SMTP_PASSWORD` (App Password for Gmail)
- `EMAIL_FROM_NAME` (default: `Vadthyavath Shiva`)
- `PHASE7_APP_LINK`

Run:
- Auto-send:
  - `python phases/phase_05_email_draft_gemini/draft_email.py --to your_alias@example.com --delivery-mode manual_cli`
- Dry run:
  - `python phases/phase_05_email_draft_gemini/draft_email.py --to your_alias@example.com --delivery-mode manual_cli --dry-run`

Notes:
- If LLM output is invalid JSON or missing required sections, the script raises an error.
- Frontend send option is available in `phases/phase_07_app_frontend/app.py`.
