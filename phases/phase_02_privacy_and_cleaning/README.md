# Phase 02 - Privacy And Cleaning

Purpose: clean review text and redact PII before any LLM call.

Input:
- `data/raw/reviews_15w.csv`

Output:
- `data/processed/reviews_15w_redacted.csv`
- `data/processed/reviews_15w_redacted_meta.json`

Run:
- `python phases/phase_02_privacy_and_cleaning/clean_and_redact.py`
- `python phases/phase_02_privacy_and_cleaning/clean_and_redact.py --input data/raw/reviews_15w.csv --output data/processed/reviews_15w_redacted.csv --meta-output data/processed/reviews_15w_redacted_meta.json --min-words 6`

PII Patterns:
- Email IDs
- Phone numbers
- Long numeric identifiers

Defensive filters (re-applied):
- Ignore reviews with <= 6 words
- Ignore reviews with emoji
- Ignore repetitive and duplicate text

Quality checks:
- Keep only `rating`, `text`, `date`
- Keep rating in range 1-5
- Drop invalid dates
- Write processing stats for auditability
