# Phase 05 - LLM Email Draft And Auto-Send

Purpose: generate and send a weekly insights email with LLM-first body generation.

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
- Body generation mode:
  - preferred: `strict_llm_only` (Gemini)
  - fallback: `fallback_template` when Gemini quota/errors occur
- LLM returns both `plain_body` and `html_body` in JSON.
- Sends multipart email with attachments.

Recipient modes:
- `manual_cli`: direct send from CLI
- `scheduled_weekly`: weekly trigger recipient flow
- `instant_frontend`: immediate send for frontend-entered recipient

Required env for auto-send:
- `EMAIL_PROVIDER` (`brevo` recommended for Render free tier, or `resend`, or `smtp`)
- `EMAIL_FROM_NAME`
- `EMAIL_FROM_ADDRESS` (or `BREVO_FROM_EMAIL` / `RESEND_FROM_EMAIL` / `SMTP_USERNAME`)
- `PHASE7_APP_LINK`

For Brevo (recommended: HTTPS API, works on Render free tier; personal mail OK):
- `BREVO_API_KEY`
- `EMAIL_FROM_ADDRESS` or `BREVO_FROM_EMAIL` (verified sender in Brevo)

For Resend (requires verified domain):
- `RESEND_API_KEY`
- `RESEND_FROM_EMAIL`

For SMTP fallback:
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USE_TLS`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`

Optional for LLM body generation:
- `GEMINI_API_KEY`
- `GEMINI_MODEL`

Run:
- Auto-send:
  - `python phases/phase_05_email_draft_gemini/draft_email.py --to your_alias@example.com --delivery-mode manual_cli`
- Dry run:
  - `python phases/phase_05_email_draft_gemini/draft_email.py --to your_alias@example.com --delivery-mode manual_cli --dry-run`

Notes:
- If Gemini output fails, script falls back to a template body and still attempts send.
- Frontend send option is available in `app/api/send-email/route.js`.
