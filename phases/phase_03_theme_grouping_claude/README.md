# Phase 03 - Theme Grouping With Claude

Purpose: classify sampled redacted reviews into 5 fixed themes and produce top-priority review sets for downstream action planning.

Input:
- `data/processed/reviews_15w_redacted.csv`

Output:
- `data/processed/themes_weekly.json`
- `data/processed/theme_assignments_sample_400.csv`
- `data/processed/themes_weekly_meta.json`

Prerequisites:
- Ensure `.env` has valid keys:
  - `ANTHROPIC_API_KEY`
  - `CLAUDE_MODEL` (optional override, recommended: `claude-haiku-4-5`)
- Script auto-loads `.env` using `python-dotenv`.

Fixed themes:
1. App Performance
2. Trading Charges/Pricing
3. Customer Support
4. Features Performance
5. KYC/Statements/Withdrawals

Sampling and batching:
- Random sample size: 400 reviews
- Batch strategy: 2 batches x 200 reviews
- Claude categorizes each batch into the fixed 5 themes

Top review projection:
- For each theme, generate top 10 reviews ranked by priority score
- Priority score uses:
  - rating severity (lower rating = higher priority)
  - recency (newer date = higher priority)

Run:
- `python phases/phase_03_theme_grouping_claude/theme_grouping.py`
- `python phases/phase_03_theme_grouping_claude/theme_grouping.py --sample-size 400 --batch-size 200 --seed 42`

Notes:
- If Claude API is unavailable, deterministic local fallback is used.
- Output includes actionable insight candidates for later phases.

