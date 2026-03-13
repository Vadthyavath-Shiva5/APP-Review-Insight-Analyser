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

## Run Locally

- `pip install -r requirements.txt`
- `python backend/render_backend.py`
- Backend starts at `http://localhost:8000`
