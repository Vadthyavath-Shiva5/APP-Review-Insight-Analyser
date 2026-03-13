# Phase 01 - Ingest Play Store Reviews

Purpose: pull public GROWW Play Store reviews for last 15 weeks and store only allowed fields.

Input:
- App ID (default: `com.nextbillion.groww`) or Play Store URL

Output:
- `data/raw/reviews_15w.csv`
- `data/raw/reviews_15w_meta.json` (filtering and volume stats)

Run:
- `python phases/phase_01_ingest/fetch_reviews.py --app-id com.nextbillion.groww`
- `python phases/phase_01_ingest/fetch_reviews.py --playstore-url "https://play.google.com/store/apps/details?id=com.nextbillion.groww&hl=en-US"`

Notes:
- Uses `google-play-scraper`
- Keeps only `rating`, `text`, `date`
- Ignores reviews with <= 6 words
- Ignores reviews containing emoji characters
- Ignores repetitive and duplicate review text
- No username/email/profile ID fields are persisted
