from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def _fix_text(text: str) -> str:
    if not text:
        return ""

    fixed = text
    # Try to recover mojibake text such as mis-decoded smart quotes.
    try:
        repaired = fixed.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
        if repaired:
            fixed = repaired
    except Exception:  # noqa: BLE001
        pass

    fixed = re.sub(r"\s+", " ", fixed).strip()
    return fixed


def _section_text(lines: list[str], start: str, end: str | None) -> list[str]:
    try:
        sidx = lines.index(start)
    except ValueError:
        return []

    if end is None:
        return lines[sidx + 1 :]

    try:
        eidx = lines.index(end)
    except ValueError:
        eidx = len(lines)

    return lines[sidx + 1 : eidx]


def _parse_theme_one_liners(section_lines: list[str]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for raw in section_lines:
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s+", "", line)

        m = re.match(r"^\*\*(.+?)\*\*:\s*(.+)$", line)
        if m:
            items.append((_fix_text(m.group(1)), _fix_text(m.group(2))))
            continue

        if ":" in line:
            name, desc = line.split(":", 1)
            items.append((_fix_text(name.strip("* ")), _fix_text(desc)))

    return items


def _parse_quick_summary(section_lines: list[str]) -> str:
    text = " ".join(line.strip() for line in section_lines if line.strip())
    return _fix_text(text)


def _parse_action_items(section_lines: list[str]) -> list[str]:
    items: list[str] = []
    for raw in section_lines:
        line = raw.strip()
        if not line:
            continue

        m = re.match(r"^\d+\.\s+(.+)$", line)
        if m:
            items.append(_fix_text(m.group(1)))
            continue

        m = re.match(r"^[-*]\s+(.+)$", line)
        if m:
            items.append(_fix_text(m.group(1)))

    return items[:3]


def _parse_top_reviews(section_lines: list[str]) -> dict[str, list[str]]:
    data: dict[str, list[str]] = {}
    current_theme: str | None = None

    for raw in section_lines:
        line = raw.rstrip()
        if not line.strip():
            continue

        if line.startswith("### "):
            current_theme = _fix_text(line.replace("### ", "", 1).strip())
            data[current_theme] = []
            continue

        if current_theme and re.match(r"^\s*[-*]\s+", line):
            text = re.sub(r"^\s*[-*]\s+", "", line).strip()
            data[current_theme].append(_fix_text(text))

    for theme in list(data.keys()):
        data[theme] = data[theme][:5]

    return data


def _extract_week_range(themes_json_path: Path) -> tuple[str, str]:
    if not themes_json_path.exists():
        return "N/A", "N/A"

    payload = json.loads(themes_json_path.read_text(encoding="utf-8"))
    start = payload.get("analysis_window_start") or payload.get("week_start") or "N/A"
    end = payload.get("analysis_window_end") or payload.get("week_end") or "N/A"
    return str(start), str(end)


def _build_pdf(
    output_path: Path,
    week_start: str,
    week_end: str,
    one_liners: list[tuple[str, str]],
    quick_summary: str,
    action_items: list[str],
    theme_reviews: dict[str, list[str]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
        title="Weekly Insights",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        fontSize=20,
        leading=24,
        alignment=1,
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "SubtitleStyle",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        alignment=1,
        textColor=colors.grey,
        spaceAfter=14,
    )
    h2_style = ParagraphStyle(
        "H2Style",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        spaceBefore=8,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodyStyle",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=14,
        spaceAfter=4,
    )
    theme_style = ParagraphStyle(
        "ThemeStyle",
        parent=styles["Heading3"],
        fontSize=11,
        leading=14,
        spaceBefore=6,
        spaceAfter=4,
    )

    story = [
        Paragraph("<b>Weekly Insights</b>", title_style),
        Paragraph(f"Week: {html.escape(week_start)} to {html.escape(week_end)}", subtitle_style),
    ]

    story.append(Paragraph("<b>1. Themes</b>", h2_style))
    for name, desc in one_liners:
        story.append(Paragraph(f"- <b>{html.escape(name)}</b>: {html.escape(desc)}", body_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>2. Report Summary</b>", h2_style))
    story.append(Paragraph(html.escape(quick_summary), body_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>3. Actionable Insights</b>", h2_style))
    for idx, item in enumerate(action_items, start=1):
        story.append(Paragraph(f"{idx}. {html.escape(item)}", body_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>4. Top 5 Reviews Of Each Theme</b>", h2_style))

    for theme, reviews in theme_reviews.items():
        story.append(Paragraph(f"<b>{html.escape(theme)}</b>", theme_style))
        if not reviews:
            story.append(Paragraph("- No review available", body_style))
            continue

        for review in reviews[:5]:
            story.append(Paragraph(f"- {html.escape(review)}", body_style))

    doc.build(story)


def run(weekly_note_path: Path, themes_json_path: Path, output_pdf_path: Path) -> None:
    lines = weekly_note_path.read_text(encoding="utf-8").splitlines()

    one_liner_lines = _section_text(lines, "## Theme One-Liners", "## Quick Summary")
    summary_lines = _section_text(lines, "## Quick Summary", "## 3 Actionable Insights and Advice")
    action_lines = _section_text(lines, "## 3 Actionable Insights and Advice", "## Top 5 User Reviews By Theme")
    reviews_lines = _section_text(lines, "## Top 5 User Reviews By Theme", None)

    one_liners = _parse_theme_one_liners(one_liner_lines)
    quick_summary = _parse_quick_summary(summary_lines)
    action_items = _parse_action_items(action_lines)
    theme_reviews = _parse_top_reviews(reviews_lines)

    week_start, week_end = _extract_week_range(themes_json_path)

    _build_pdf(
        output_path=output_pdf_path,
        week_start=week_start,
        week_end=week_end,
        one_liners=one_liners,
        quick_summary=quick_summary,
        action_items=action_items,
        theme_reviews=theme_reviews,
    )

    print(f"Saved weekly insights PDF to {output_pdf_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate structured weekly insights PDF from phase 4 markdown")
    parser.add_argument("--input", default="data/outputs/weekly_note.md")
    parser.add_argument("--themes-json", default="data/processed/themes_weekly.json")
    parser.add_argument("--output", default="data/outputs/weekly_note.pdf")
    args = parser.parse_args()

    run(
        weekly_note_path=Path(args.input),
        themes_json_path=Path(args.themes_json),
        output_pdf_path=Path(args.output),
    )


if __name__ == "__main__":
    main()
