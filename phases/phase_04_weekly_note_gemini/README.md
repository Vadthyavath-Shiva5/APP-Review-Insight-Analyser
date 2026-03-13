# Phase 04 - Weekly Note Generation With Gemini

Purpose: generate a weekly pulse with actionable insights derived from the full Phase 3 sample.

Input:
- `data/processed/themes_weekly.json`
- `data/processed/theme_assignments_sample_400.csv`

Output format (required):
1. Theme One-Liners (one line per theme)
2. Quick Summary
3. 3 Actionable Insights and Advice
4. Top 5 User Reviews By Theme

Actionable insight rule:
- Insights must be based on the 400 sampled reviews from Phase 3 (2 batches x 200), analyzed under each of the 5 fixed themes.
- Use per-theme evidence (counts, top reviews, low-rating share, assigned reviews) before drafting action ideas.

Word count policy:
- No word-count limit is applied in Phase 4 output.

Model guidance:
- Recommended low-cost model: `gemini-2.5-flash-lite`
- Configure via `.env` using `GEMINI_MODEL` and `GEMINI_API_KEY`.

Output files:
- `data/outputs/weekly_note.md`
- `data/outputs/weekly_note_meta.json`

Run:
- `python phases/phase_04_weekly_note_gemini/generate_weekly_note.py`
- `python phases/phase_04_weekly_note_gemini/generate_weekly_note.py --input data/processed/themes_weekly.json --assignments-input data/processed/theme_assignments_sample_400.csv --output data/outputs/weekly_note.md --meta-output data/outputs/weekly_note_meta.json`
