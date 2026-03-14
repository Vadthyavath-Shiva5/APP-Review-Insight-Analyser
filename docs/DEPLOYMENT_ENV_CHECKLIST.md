# Deployment & environment variables checklist

Use this after deploying the Brevo (HTTPS email API) changes. No SMTP is used; everything uses HTTPS so Render free tier works.

**Redeploy frontend (Vercel):** After pushing to GitHub, Vercel usually auto-deploys. If the live site still shows the old “resend or smtp” error:

1. **Redeploy with cache clear:** Vercel Dashboard → your project → Deployments → ⋮ on latest → **Redeploy** → **uncheck** “Use existing Build Cache” → Redeploy.
2. **If the error still appears – fresh deploy:** Vercel Dashboard → your project → Settings → scroll down → **Delete Project**. Then create a new project: **Add New** → **Project** → Import `Vadthyavath-Shiva5/APP-Review-Insight-Analyser` from GitHub → leave framework/build settings as auto → add Environment Variables (BREVO_API_KEY, EMAIL_FROM_ADDRESS, PIPELINE_TRIGGER_URL, PIPELINE_TRIGGER_TOKEN) → Deploy. Your app URL may change unless you use the same project name.

---

## 1. Vercel (frontend)

**Where:** Project → Settings → Environment Variables

| Variable | Value | Required |
|----------|--------|----------|
| `EMAIL_PROVIDER` | `brevo` | Yes |
| `EMAIL_FROM_NAME` | `Groww Pulse Bot` (or any name) | Yes |
| `EMAIL_FROM_ADDRESS` | `shivavadthyavtah5@gmail.com` | Yes |
| `BREVO_API_KEY` | Your Brevo API key | Yes (for Send Email) |
| `PIPELINE_TRIGGER_URL` | `https://<your-render-service>.onrender.com/trigger` | Yes (for Reprocess & Send) |
| `PIPELINE_TRIGGER_TOKEN` | Same secret token you set on Render | Yes (for Reprocess & Send) |
| `EMAIL_TO_ALIAS` | Optional default recipient | No |

**Remove or leave empty (not used with Brevo):** `RESEND_API_KEY`, `RESEND_FROM_EMAIL`  
**Redeploy** after changing env vars.

---

## 2. Render (backend)

**Where:** Web Service → Environment tab

| Variable | Value | Required |
|----------|--------|----------|
| `EMAIL_PROVIDER` | `brevo` | Yes |
| `EMAIL_FROM_NAME` | `Groww Pulse Bot` | Yes |
| `EMAIL_FROM_ADDRESS` | `shivavadthyavtah5@gmail.com` | Yes |
| `BREVO_API_KEY` | Your Brevo API key | Yes |
| `PIPELINE_TRIGGER_TOKEN` | Same token as in Vercel & GitHub Actions | Yes |
| `WEEKLY_SCHEDULED_RECIPIENT` | Email that receives weekly scheduled run | Yes (for cron) |
| `PHASE7_APP_LINK` | `https://groww-review-insight-analyser.vercel.app` | Yes (for email body) |
| `GEMINI_API_KEY` | Your Gemini API key | Yes (pipeline) |
| `ANTHROPIC_API_KEY` | Your Claude API key | Yes (pipeline) |
| `GEMINI_MODEL` | e.g. `gemini-2.5-flash-lite` | Optional |
| `CLAUDE_MODEL` | e.g. `claude-haiku-4-5` | Optional |
| `WEEKLY_SCHEDULE_DAY` | `MON` | Optional |
| `WEEKLY_SCHEDULE_TIME` | `10:00` | Optional |
| `WEEKLY_WEEKS_FROM` | `1` | Optional |
| `WEEKLY_WEEKS_TO` | `15` | Optional |

**Remove or leave empty (not used with Brevo):** `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, SMTP_*  
Render auto-redeploys when you save environment.

---

## 3. GitHub Actions (weekly trigger)

**Where:** Repo → Settings → Secrets and variables → Actions

| Secret | Value | Required |
|-------|--------|----------|
| `PIPELINE_TRIGGER_URL` | `https://<your-render-service>.onrender.com/trigger` | Yes |
| `PIPELINE_TRIGGER_TOKEN` | Same token as Render & Vercel | Yes |

**No other secrets needed for the workflow.** The workflow only POSTs to Render; Render has all API keys and Brevo.

**No changes needed** to the workflow file itself. Only ensure these two secrets are set and match Render.

---

## Quick check (no errors expected if)

1. **Vercel**  
   - `EMAIL_PROVIDER=brevo`, `BREVO_API_KEY` and `EMAIL_FROM_ADDRESS` set.  
   - “Send Current Generated Email” uses Brevo.  
   - `PIPELINE_TRIGGER_URL` and `PIPELINE_TRIGGER_TOKEN` set.  
   - “Reprocess Selected Weeks and Send” calls Render.

2. **Render**  
   - `EMAIL_PROVIDER=brevo`, `BREVO_API_KEY`, `EMAIL_FROM_ADDRESS` set.  
   - Pipeline (including `draft_email.py`) sends via Brevo HTTPS API only (no SMTP).  
   - `PIPELINE_TRIGGER_TOKEN` matches Vercel and GitHub.  
   - `WEEKLY_SCHEDULED_RECIPIENT` set for scheduled runs.

3. **GitHub Actions**  
   - `PIPELINE_TRIGGER_URL` = your Render `/trigger` URL.  
   - `PIPELINE_TRIGGER_TOKEN` = same as Render.  
   - Weekly run (or manual “Run workflow”) triggers Render; Render sends email via Brevo.

4. **Brevo**  
   - Sender `shivavadthyavtah5@gmail.com` is verified in Brevo (Senders & IP).  
   - API key is valid and has transactional send permission.

---

## What you changed for this deployment

- **Backend (Render):** Switched from Resend/SMTP to **Brevo HTTPS API** only → set `EMAIL_PROVIDER=brevo`, `BREVO_API_KEY`, `EMAIL_FROM_ADDRESS` on Render.
- **Frontend (Vercel):** Same → set `EMAIL_PROVIDER=brevo`, `BREVO_API_KEY`, `EMAIL_FROM_ADDRESS` on Vercel.
- **GitHub Actions:** No env/secret changes for Brevo; only `PIPELINE_TRIGGER_URL` and `PIPELINE_TRIGGER_TOKEN` (unchanged).
