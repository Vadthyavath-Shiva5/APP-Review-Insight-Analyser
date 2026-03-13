# GROWW Review Insight Analyzer

Phase-wise architecture and implementation scaffold to convert recent GROWW Play Store reviews into a weekly one-page pulse for Product, Growth, Support, and Leadership teams.

## Objective
Build an AI workflow that:
- Imports public Play Store reviews from the last 15 weeks (`rating`, `text`, `date`)
- Groups feedback into maximum 5 themes
- Produces a scannable weekly one-page note (<= 250 words)
- Includes 5 real user quotes (PII-safe)
- Suggests 3-5 action ideas
- Creates an email draft to self/alias with the weekly note

## Key Constraints
- Use public review exports only (no login-only scraping)
- Use Play Store scraper library (`google-play-scraper`)
- Maximum 5 themes
- Weekly note must be scannable and <= 250 words
- Ignore reviews with 6 words or fewer, emoji content, repetitive content, and duplicates
- No usernames, emails, IDs, contact numbers, or personal identifiers in any artifact

## Model Split (as requested)
- Claude: theme categorization + review understanding
- Gemini: action recommendations + weekly note shaping + email draft generation

## Phase-Wise Architecture

| Phase | Goal | Primary Tech | Input | Output |
|---|---|---|---|---|
| Phase 01 | Import Play Store reviews (15 weeks) | `google-play-scraper`, `pandas` | App ID (`com.nextbillion.groww`) | `data/raw/reviews_15w.csv` |
| Phase 02 | Cleaning + PII redaction | `pandas`, regex validators | Raw CSV | `data/processed/reviews_15w_redacted.csv` |
| Phase 03 | Fixed 5-theme grouping + top-10 reviews/theme | Claude API | Redacted CSV sample (400) | `data/processed/themes_weekly.json` + assignments/meta |
| Phase 04 | Weekly one-page note + action ideas | Gemini API | Themes JSON | `data/outputs/weekly_note.md` |
| Phase 05 | Email draft generation | Gemini API (+ optional Gmail Draft API later) | Weekly note | `data/outputs/email_draft.txt` |
| Phase 06 | Orchestration + artifact packaging | Python runner | All phase outputs | `artifacts/latest/*` |
| Phase 07 | Frontend dashboard + send option | Next.js (Vercel) + Node API routes | Latest weekly outputs | User-entered recipient email send flow |

## Detailed Phase Plan

### Phase 01 - Ingest Play Store Reviews (Last 15 Weeks)
What we do:
- Use `google-play-scraper` to fetch public GROWW reviews ordered by newest.
- Stop when reviews are older than 15 weeks from run date.
- Keep only allowed fields: `rating`, `text`, `date`.
- Exclude reviews with <= 6 words, emoji content, repetitive content, or duplicate text.

Why this matters:
- Creates a reliable source dataset for all downstream AI tasks.
- Enforces "public data only" constraint from day one.

Checks:
- File exists: `data/raw/reviews_15w.csv`
- Date range spans recent 15 weeks only
- No extra identity fields persisted

Exit criteria:
- Clean raw dataset ready for redaction and analysis.

### Phase 02 - Privacy Cleaning and Redaction
What we do:
- Normalize missing text fields and apply defensive quality filters.
- Redact potential PII using regex:
  - email addresses
  - phone numbers
  - long numeric IDs
- Remove duplicates and empty reviews.

Why this matters:
- Prevents personal data from entering prompts, notes, or email artifacts.

Checks:
- File exists: `data/processed/reviews_15w_redacted.csv`
- Random sample contains no visible email/phone/ID patterns
- Row count after cleaning is reasonable (not near zero unexpectedly)

Exit criteria:
- PII-safe review dataset for model processing.

### Phase 03 - Fixed Theme Grouping and Top Review Projection (Claude)
What we do:
- Randomly sample 400 reviews from data/processed/reviews_15w_redacted.csv.
- Split into 2 batches of 200 reviews each.
- Send each batch to Claude for classification into exactly 5 fixed themes:
  - App Performance
  - Trading Charges/Pricing
  - Customer Support
  - Features Performance
  - KYC/Statements/Withdrawals
- Build top 10 reviews per theme using priority score based on:
  - rating severity (lower rating = higher priority)
  - recency (newer date = higher priority)
- Emit actionable insight candidates for later action-generation phase.

Why this matters:
- Keeps categorization consistent week to week with stable business themes.
- Surfaces the highest-priority evidence under each theme before recommendation drafting.

Checks:
- Files exist:
  - data/processed/themes_weekly.json
  - data/processed/theme_assignments_sample_400.csv
  - data/processed/themes_weekly_meta.json
- sample_size_used <= 400
- batches_used_for_claude == 2 when enough data exists
- Exactly 5 fixed themes are present in output
- Each theme has up to 10 prioritized reviews

Exit criteria:
- Theme JSON contains fixed-theme counts, top reviews, quotes, and insight candidates.

### Phase 04 - One-Page Weekly Pulse Generation (Gemini)
What we do:
- Send theme JSON to Gemini with formatting and tone constraints.
- Generate markdown note with sections:
  - Top Themes
  - Real User Quotes (5)
  - Action Ideas (3-5)
- Enforce output length <= 250 words.

Why this matters:
- Produces leadership-ready summary that is fast to scan and action.
- Keeps requested Gemini role for actionable recommendation generation.

Checks:
- File exists: `data/outputs/weekly_note.md`
- Word count <= 250
- Contains all required sections and list sizes

Exit criteria:
- Shareable weekly pulse ready for internal communication.

### Phase 05 - Email Draft Creation (Gemini)
What we do:
- Use note content to generate concise internal email draft.
- Include subject, recipient, action ideas, and top review highlights.
- Attach date-stamped files:
  - `groww_weekly_insights_<week_end>.pdf`
  - `groww_reviews_redacted_<week_end>.csv`
- Auto-send by SMTP (or `--dry-run` for draft-only mode).

Why this matters:
- Completes end-to-end "insights to communication" workflow.
- Supports both direct send and review-before-send.

Checks:
- File exists: `data/outputs/email_draft.txt`
- File exists: `data/outputs/email_draft_meta.json`
- No PII in draft
- Tone is clear for Product/Growth/Support/Leadership readers

Exit criteria:
- Ready-to-send draft email available for approval.

### Phase 06 - Orchestration and Artifact Packaging
What we do:
- Run all phases in sequence with one command.
- Package latest outputs into `artifacts/latest/`.
- Keep a sample redacted CSV for audit/demo.

Why this matters:
- Enables repeatable weekly operation.
- Supports demo and handover requirements.

Checks:
- `artifacts/latest/weekly_note.md`
- `artifacts/latest/email_draft.txt`
- `artifacts/latest/reviews_sample_redacted.csv`

Exit criteria:
- Weekly run completes end-to-end with deliverables bundled.

### Phase 07 - Frontend Dashboard And Recipient Email Send
What we do:
- Provide a Next.js dashboard page for themes, insights, and top reviews.
- Add API routes for current-email send and reprocess trigger.
- Send current weekly report directly to entered recipient email.
- Trigger week-range reprocess via backend webhook when deployed on Vercel.

Why this matters:
- Enables non-technical users to trigger weekly report delivery from UI.

## Repository Layout

```text
.
|-- README.md
|-- requirements.txt
|-- package.json
|-- next.config.mjs
|-- .env.example
|-- app/
|-- lib/
|-- data/
|   |-- raw/
|   |-- processed/
|   `-- outputs/
|-- artifacts/
|   `-- latest/
|-- docs/
|   |-- theme_legend.md
|   `-- one_page_note_template.md
`-- phases/
    |-- phase_01_ingest/
    |-- phase_02_privacy_and_cleaning/
    |-- phase_03_theme_grouping_claude/
    |-- phase_04_weekly_note_gemini/
    |-- phase_05_email_draft_gemini/
    |-- phase_06_orchestration_and_artifacts/
    `-- phase_07_app_frontend/
```

## End-to-End Flow

1. Fetch latest 15-week GROWW reviews from Play Store (public endpoint only).
2. Retain allowed columns only: `rating`, `text`, `date`.
3. Run PII redaction and text normalization.
4. Randomly sample 400 redacted reviews (2 batches x 200) and send to Claude for fixed-theme categorization.
5. Send theme summary to Gemini for:
   - concise weekly note (<= 250 words),
   - top themes section,
   - 5 user quotes,
   - 3-5 action ideas.
6. Generate date-stamped email draft and attachments, then send via SMTP.
7. Optionally use frontend to enter recipient email and trigger send.
8. Package artifacts to `artifacts/latest/`.

## Data Contract

Required review schema:

| field | type | notes |
|---|---|---|
| `rating` | int | 1-5 |
| `text` | string | review body |
| `date` | ISO date | UTC recommended |

## Privacy Guardrails

- Drop all non-required fields from source payload immediately.
- Redact PII patterns from review text:
  - emails
  - phone numbers
  - long numeric IDs (possible account/order IDs)
- Never persist usernames or profile identifiers.
- Ensure quotes in note and email are redacted and short.

## How To Re-Run For A New Week

1. Setup environment:
   - `python -m venv .venv`
   - `.venv\Scripts\Activate.ps1`
   - `pip install -r requirements.txt`
2. Configure keys in `.env` (Claude + Gemini).
3. Run orchestrator:
   - `python phases/phase_06_orchestration_and_artifacts/run_weekly_pipeline.py --app-id com.nextbillion.groww`
4. Send weekly report by CLI:
   - `python phases/phase_05_email_draft_gemini/draft_email.py --to receiver@example.com`
5. Or run Vercel-compatible frontend:
   - `npm install`
   - `npm run dev`
6. Collect outputs from:
   - `data/outputs/weekly_note.md`
   - `data/outputs/email_draft.txt`
   - `artifacts/latest/`

## Theme Legend

See `docs/theme_legend.md` for default categories and definitions.

## Deliverables Mapping

- Working prototype / demo video: create after running pipeline once with sample data.
- Latest one-page weekly note: `data/outputs/weekly_note.md` (export to PDF/Doc as needed).
- Email draft: `data/outputs/email_draft.txt`.
- Reviews CSV used: `artifacts/latest/reviews_sample_redacted.csv`.
- README: includes rerun steps + architecture + theme legend.

## Deployment Later (Not in Current Scope)

Planned upgrades for production deployment:
- REST API wrapper over orchestration pipeline
- Weekly scheduler (GitHub Actions / Cloud Scheduler / cron)
- Secret manager for API keys
- Storage for historical weekly pulses
- Monitoring for token usage, failures, and output quality checks
## Recipient Delivery Rules

- Weekly triggered mail uses only WEEKLY_SCHEDULED_RECIPIENT from .env.
- Frontend-entered recipient emails are sent instantly and are not stored for weekly triggers.
- Sender is fixed by SMTP config: SMTP_USERNAME=shivavadthyavath5@gmail.com.

## Weekly Schedule Setup (Monday 10:00)

1. Set these in .env:
   - WEEKLY_SCHEDULED_RECIPIENT=your_primary_recipient@example.com
   - WEEKLY_SCHEDULE_DAY=MON
   - WEEKLY_SCHEDULE_TIME=10:00
2. Test scheduled entrypoint once:
   - python phases/phase_06_orchestration_and_artifacts/send_weekly_scheduled.py --force --email-dry-run
3. Use Windows Task Scheduler to run every Monday at 10:00 AM:
   - Program/script: Python executable path
   - Arguments: phases/phase_06_orchestration_and_artifacts/send_weekly_scheduled.py
   - Start in: project root path

## Vercel Frontend

- Frontend stack is now Next.js (App Router) in root `app/` with Node API routes under `app/api/`.
- Local run:
  - `npm install`
  - `npm run dev`
- Deploy to Vercel from repository root.
- Required Vercel env vars:
  - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_TLS`
  - `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM_NAME`
  - `EMAIL_TO_ALIAS` (optional default recipient)
  - `PIPELINE_TRIGGER_URL` (required for week-range reprocess from Vercel frontend)
  - `PIPELINE_TRIGGER_TOKEN` (optional)

## Render Backend + GitHub Actions Scheduler (Implemented)

### 1. Deploy Backend on Render

This repo now includes a Render-ready backend trigger service:
- `backend/render_backend.py`
- `render.yaml`

Render Web Service settings:
- Build command: `pip install -r requirements.txt`
- Start command: `python backend/render_backend.py`
- Health endpoint: `GET /health`

Backend endpoints:
- `GET /health`
- `POST /trigger`
- `GET /status/<run_id>`

Auth:
- Set `PIPELINE_TRIGGER_TOKEN` in Render.
- Call `POST /trigger` with header:
  - `Authorization: Bearer <PIPELINE_TRIGGER_TOKEN>`

### 2. Configure GitHub Actions Weekly Trigger

Workflow file:
- `.github/workflows/weekly_backend_trigger.yml`

Schedule:
- Monday 10:00 AM IST (`30 4 * * 1` UTC)

Required GitHub repository secrets:
- `PIPELINE_TRIGGER_URL` = `https://<your-render-service>/trigger`
- `PIPELINE_TRIGGER_TOKEN` = same token set in Render

Optional manual run:
- `Actions -> Weekly Backend Trigger -> Run workflow`
- Inputs: `weeks_from`, `weeks_to`, `recipient_email`, `email_dry_run`

### 3. Keep Frontend on Vercel

Frontend remains on Vercel (`app/` + `app/api/*`).
Set these Vercel env vars for backend trigger:
- `PIPELINE_TRIGGER_URL` = `https://<your-render-service>/trigger`
- `PIPELINE_TRIGGER_TOKEN` = same shared token

This enables the "Reprocess Selected Weeks and Send" button to trigger backend runs.

### 4. Security Checklist

- Do not commit `.env`.
- Store all secrets only in Render, GitHub Secrets, and Vercel env vars.
- Rotate any tokens/keys that were previously shared in chat.
