# Render Backend

This backend runs the weekly pipeline and exposes HTTP endpoints for Vercel + GitHub Actions.

## Endpoints

- `GET /health`
- `POST /trigger`
- `GET /status/<run_id>`

## Trigger Payload

```json
{
  "appId": "com.nextbillion.groww",
  "weeksFrom": 1,
  "weeksTo": 15,
  "recipientEmail": "optional@example.com",
  "deliveryMode": "scheduled_weekly",
  "emailDryRun": false
}
```

Rules:
- `weeksFrom` and `weeksTo` must be in `1..15` and `weeksFrom <= weeksTo`.
- If `deliveryMode` is omitted, backend auto-uses:
  - `instant_frontend` when `recipientEmail` is provided
  - `scheduled_weekly` otherwise

## Security

Set `PIPELINE_TRIGGER_TOKEN` in Render env vars.
Then call `POST /trigger` with:

`Authorization: Bearer <PIPELINE_TRIGGER_TOKEN>`

## Email Transport on Render

Use HTTPS email API for Render free tier.
Recommended:
- `EMAIL_PROVIDER=resend`
- `RESEND_API_KEY=...`
- `RESEND_FROM_EMAIL=verified@yourdomain.com`
- `EMAIL_FROM_NAME=Groww Pulse Bot`
- `EMAIL_FROM_ADDRESS=verified@yourdomain.com`

SMTP is optional fallback (`EMAIL_PROVIDER=smtp`) but may fail on Render free due to outbound SMTP restrictions.

## Run Locally

- `pip install -r requirements.txt`
- `python backend/render_backend.py`
- Backend starts at `http://localhost:8000`
