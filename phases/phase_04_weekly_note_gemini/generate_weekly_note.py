from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:\d[\s-]?){10,12}\b")
LONG_ID_PATTERN = re.compile(r"\b\d{9,18}\b")


REQUIRED_SECTIONS = [
    "## Theme One-Liners",
    "## Quick Summary",
    "## 3 Actionable Insights and Advice",
    "## Top 5 User Reviews By Theme",
]


def _sanitize_text(text: str, max_chars: int = 220) -> str:
    clean = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    clean = PHONE_PATTERN.sub("[REDACTED_PHONE]", clean)
    clean = LONG_ID_PATTERN.sub("[REDACTED_ID]", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_chars]


def _build_evidence(themes_payload: dict[str, Any], assignments_df: pd.DataFrame) -> dict[str, Any]:
    assignments = assignments_df.copy()
    assignments["rating"] = pd.to_numeric(assignments["rating"], errors="coerce").fillna(3).astype(int)
    assignments["date"] = pd.to_datetime(assignments["date"], errors="coerce")
    assignments = assignments.dropna(subset=["date"]).copy()

    fixed_themes = themes_payload.get("fixed_themes") or sorted(assignments["theme"].dropna().unique().tolist())

    theme_rows = []
    for theme_name in fixed_themes:
        subset = assignments[assignments["theme"] == theme_name].copy()
        subset = subset.sort_values(["rating", "date"], ascending=[True, False])

        count = int(len(subset))
        avg_rating = round(float(subset["rating"].mean()), 2) if count else None
        low_rating_count = int((subset["rating"] <= 2).sum()) if count else 0
        low_rating_pct = round((low_rating_count / count) * 100, 2) if count else 0.0

        top_reviews = []
        for theme_obj in themes_payload.get("themes", []):
            if theme_obj.get("name") == theme_name:
                top_reviews = theme_obj.get("top_reviews", [])[:5]
                break

        top_review_evidence = [
            {
                "review_id": item.get("review_id"),
                "rating": item.get("rating"),
                "date": item.get("date"),
                "priority_score": item.get("priority_score"),
                "text": _sanitize_text(str(item.get("text", ""))),
            }
            for item in top_reviews
        ]

        # If top reviews are missing, backfill from assignments for the same theme.
        if len(top_review_evidence) < 5 and count:
            backfill_needed = 5 - len(top_review_evidence)
            for _, row in subset.head(backfill_needed).iterrows():
                top_review_evidence.append(
                    {
                        "review_id": str(row.get("sample_id", "N/A")),
                        "rating": int(row["rating"]),
                        "date": row["date"].strftime("%Y-%m-%d"),
                        "priority_score": None,
                        "text": _sanitize_text(str(row.get("text", ""))),
                    }
                )

        theme_rows.append(
            {
                "theme": theme_name,
                "count": count,
                "avg_rating": avg_rating,
                "low_rating_count": low_rating_count,
                "low_rating_pct": low_rating_pct,
                "top5_reviews": top_review_evidence[:5],
            }
        )

    theme_rows = sorted(theme_rows, key=lambda x: x["count"], reverse=True)

    return {
        "analysis_window_start": themes_payload.get("analysis_window_start") or themes_payload.get("week_start"),
        "analysis_window_end": themes_payload.get("analysis_window_end") or themes_payload.get("week_end"),
        "sample_size": int(len(assignments)),
        "themes": theme_rows,
        "seeded_insight_candidates": themes_payload.get("actionable_insight_candidates", []),
    }


def _theme_one_liner(theme: dict[str, Any]) -> str:
    name = theme["theme"]
    count = theme["count"]
    low_pct = theme["low_rating_pct"]
    avg = theme["avg_rating"]

    if low_pct >= 60:
        severity = "very high user pain"
    elif low_pct >= 40:
        severity = "high user pain"
    elif low_pct >= 20:
        severity = "moderate user pain"
    else:
        severity = "lower-severity but recurring feedback"

    return f"{name}: {count} reviews, avg rating {avg}, {low_pct}% low-rated indicating {severity}."


def _quick_summary(themes: list[dict[str, Any]]) -> str:
    if not themes:
        return "No theme evidence available for this run."

    top_volume = themes[0]
    top_severity = sorted(themes, key=lambda t: t["low_rating_pct"], reverse=True)[0]

    return (
        f"Across 400 categorized reviews, the highest feedback volume is in {top_volume['theme']} "
        f"({top_volume['count']} reviews). The most severe sentiment appears in {top_severity['theme']} "
        f"with {top_severity['low_rating_pct']}% low-rated reviews. Prioritizing reliability, support speed, "
        "and pricing/feature clarity should reduce repeated complaints fastest."
    )


def _actionable_insights(themes: list[dict[str, Any]]) -> list[str]:
    if not themes:
        return [
            "Create a weekly issue triage and map incoming reviews to fixed themes before planning fixes.",
            "Track low-rating share and review volume per theme to prioritize the next sprint.",
            "Publish weekly improvements to users to close feedback loops faster.",
        ]

    top_severity = sorted(themes, key=lambda t: t["low_rating_pct"], reverse=True)
    top_volume = sorted(themes, key=lambda t: t["count"], reverse=True)

    action_1_theme = top_severity[0]["theme"]
    action_2_theme = top_volume[0]["theme"]
    action_3_theme = top_severity[1]["theme"] if len(top_severity) > 1 else top_volume[0]["theme"]

    return [
        f"Fix highest-severity issue paths in {action_1_theme} first and set a weekly target to reduce low-rating share by at least 10%.",
        f"Run a focused reliability/UX sprint for {action_2_theme} (largest volume theme) and monitor complaint recurrence week-over-week.",
        f"For {action_3_theme}, add proactive in-app messaging and clearer status/fee/support explanations to reduce confusion-driven tickets.",
    ]


def _fallback_note(evidence: dict[str, Any]) -> str:
    themes = evidence.get("themes", [])

    lines = [
        "# GROWW Weekly Review Pulse",
        (
            f"Period: {evidence.get('analysis_window_start', 'N/A')} to {evidence.get('analysis_window_end', 'N/A')} | "
            f"Evidence base: {evidence.get('sample_size', 0)} categorized reviews (2 batches x 200)"
        ),
        "",
        "## Theme One-Liners",
    ]

    for theme in themes:
        lines.append(f"- { _theme_one_liner(theme) }")

    lines.append("")
    lines.append("## Quick Summary")
    lines.append(_quick_summary(themes))

    lines.append("")
    lines.append("## 3 Actionable Insights and Advice")
    for idx, action in enumerate(_actionable_insights(themes), start=1):
        lines.append(f"{idx}. {action}")

    lines.append("")
    lines.append("## Top 5 User Reviews By Theme")
    for theme in themes:
        lines.append("")
        lines.append(f"### {theme['theme']}")
        for review in theme.get("top5_reviews", [])[:5]:
            lines.append(
                f"- (Rating {review.get('rating')}, Date {review.get('date')}) {review.get('text', '')}"
            )

    return "\n".join(lines).strip() + "\n"


def _has_required_sections(note: str) -> bool:
    return all(section in note for section in REQUIRED_SECTIONS)


def _gemini_note(evidence: dict[str, Any], model: str) -> str:
    from google import genai

    prompt_path = Path("phases/phase_04_weekly_note_gemini/prompts/weekly_note_prompt.md")
    prompt = prompt_path.read_text(encoding="utf-8")

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    combined_prompt = (
        f"{prompt}\n\n"
        "Evidence JSON (derived from all 400 categorized reviews):\n"
        f"{json.dumps(evidence, ensure_ascii=True, indent=2)}"
    )

    response = client.models.generate_content(model=model, contents=combined_prompt)
    text = (getattr(response, "text", "") or str(response)).strip()
    if _has_required_sections(text):
        return text + "\n"

    repair_prompt = (
        "Reformat the following draft into Markdown with EXACT sections:\n"
        "## Theme One-Liners\n"
        "## Quick Summary\n"
        "## 3 Actionable Insights and Advice\n"
        "## Top 5 User Reviews By Theme\n"
        "Keep top 5 reviews for EACH theme, no PII, and no word limit.\n\n"
        f"Draft:\n{text}"
    )
    repair_response = client.models.generate_content(model=model, contents=repair_prompt)
    repaired = (getattr(repair_response, "text", "") or str(repair_response)).strip()

    if _has_required_sections(repaired):
        return repaired + "\n"

    raise ValueError("Gemini response missing required sections")


def run(
    themes_input_path: Path,
    assignments_input_path: Path,
    output_path: Path,
    model: str,
    meta_output_path: Path,
) -> None:
    load_dotenv()

    themes_payload = json.loads(themes_input_path.read_text(encoding="utf-8"))
    assignments_df = pd.read_csv(assignments_input_path)
    evidence = _build_evidence(themes_payload, assignments_df)

    used_gemini = False
    if os.getenv("GEMINI_API_KEY"):
        try:
            note = _gemini_note(evidence, model=model)
            used_gemini = True
        except Exception as exc:  # noqa: BLE001
            print(f"Gemini note generation failed, using fallback: {exc}")
            note = _fallback_note(evidence)
    else:
        note = _fallback_note(evidence)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(note, encoding="utf-8")

    meta_payload = {
        "phase": "phase_04_weekly_note_gemini",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "themes_input": str(themes_input_path),
        "assignments_input": str(assignments_input_path),
        "output_note": str(output_path),
        "model": model,
        "used_gemini": used_gemini,
        "sample_size": evidence.get("sample_size"),
        "word_count": len(note.split()),
        "word_limit_applied": False,
    }
    meta_output_path.parent.mkdir(parents=True, exist_ok=True)
    meta_output_path.write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")

    print(f"Saved weekly note to {output_path}")
    print(f"Saved note metadata to {meta_output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one-page weekly note from themes + assignments")
    parser.add_argument("--input", default="data/processed/themes_weekly.json")
    parser.add_argument("--assignments-input", default="data/processed/theme_assignments_sample_400.csv")
    parser.add_argument("--output", default="data/outputs/weekly_note.md")
    parser.add_argument("--meta-output", default="data/outputs/weekly_note_meta.json")
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"))
    args = parser.parse_args()

    run(
        themes_input_path=Path(args.input),
        assignments_input_path=Path(args.assignments_input),
        output_path=Path(args.output),
        model=args.model,
        meta_output_path=Path(args.meta_output),
    )


if __name__ == "__main__":
    main()
