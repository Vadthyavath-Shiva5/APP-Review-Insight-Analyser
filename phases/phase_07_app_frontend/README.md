# Phase 07 - Frontend Dashboard And Send Flow (Vercel-ready)

Purpose: provide a Next.js dashboard UI for themes, insights, review evidence, and user-triggered email workflows.

## Stack
- Frontend: Next.js (App Router)
- API routes: Node.js runtime (`/app/api/*`)
- Deploy target: Vercel

## Dashboard Sections
- Heading: `GROWW Reviews - Analyser`
- Themes list with click-to-expand one-liner under each theme
- Actionable Insights section
- Top 5 Reviews of each theme
- Right-side status card:
  - Latest Updated timestamp
  - Process Loaded timestamp
  - Current analysis window and sample size

## Side Panel Controls
- Recipient email input
- Week range selection:
  - `From week` (1 = latest)
  - `To week` (max 15)
- Buttons:
  - `Send Current Generated Email`
  - `Reprocess Selected Weeks and Send`

## API Behavior
- `/api/dashboard`: reads latest processed files and serves UI data.
- `/api/send-email`: sends current generated email with latest PDF/CSV attachments (Brevo / Resend / SMTP).
- `/api/reprocess-and-send`:
  - On Vercel, calls external backend webhook (`PIPELINE_TRIGGER_URL`) to run Python pipeline and send mail.
  - Returns clear error if webhook is not configured.

## Run Locally
- `npm install`
- `npm run dev`
- Open `http://localhost:3000`

## Deploy on Vercel
Set env vars in Vercel project settings:
- `EMAIL_PROVIDER` (`brevo` recommended for Render free tier)
- `EMAIL_FROM_NAME`
- `EMAIL_FROM_ADDRESS`
- `BREVO_API_KEY`, `BREVO_FROM_EMAIL` or `EMAIL_FROM_ADDRESS` (when using Brevo)
- `RESEND_API_KEY`, `RESEND_FROM_EMAIL` (when using Resend)
- `EMAIL_TO_ALIAS` (optional default)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_TLS`, `SMTP_USERNAME`, `SMTP_PASSWORD` (only if EMAIL_PROVIDER=smtp)
- `PIPELINE_TRIGGER_URL` (required for week-range reprocess on Vercel)
- `PIPELINE_TRIGGER_TOKEN` (optional auth for webhook)

## Notes
- The Python pipeline remains the processing engine for ingestion/grouping/note generation.
- Next.js frontend is the Vercel-compatible presentation + trigger layer.

