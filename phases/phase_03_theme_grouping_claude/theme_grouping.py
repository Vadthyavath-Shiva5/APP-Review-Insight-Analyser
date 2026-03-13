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

THEMES = [
    "App Performance",
    "Trading Charges/Pricing",
    "Customer Support",
    "Features Performance",
    "KYC/Statements/Withdrawals",
]

THEME_HINTS = {
    "App Performance": [
        "crash",
        "slow",
        "lag",
        "hang",
        "freeze",
        "loading",
        "performance",
        "stuck",
        "error",
    ],
    "Trading Charges/Pricing": [
        "charge",
        "charges",
        "pricing",
        "price",
        "brokerage",
        "fee",
        "fees",
        "cost",
        "expensive",
        "hidden",
    ],
    "Customer Support": [
        "support",
        "customer care",
        "help",
        "ticket",
        "response",
        "resolved",
        "service",
        "agent",
    ],
    "Features Performance": [
        "feature",
        "option",
        "chart",
        "watchlist",
        "portfolio",
        "ui",
        "ux",
        "function",
        "update",
        "notification",
    ],
    "KYC/Statements/Withdrawals": [
        "kyc",
        "verify",
        "verification",
        "statement",
        "withdraw",
        "withdrawal",
        "bank",
        "payout",
        "redeem",
        "account",
    ],
}

INSIGHT_TEMPLATES = {
    "App Performance": "Prioritize crash/latency fixes on critical journeys and add release-level performance telemetry.",
    "Trading Charges/Pricing": "Audit brokerage/charges communication and add transparent fee breakdowns before order confirmation.",
    "Customer Support": "Improve first-response SLA and reduce repeat-information loops with better ticket context carryover.",
    "Features Performance": "Stabilize high-usage features and add targeted QA checks for recurring functional regressions.",
    "KYC/Statements/Withdrawals": "Shorten KYC and withdrawal turnaround with proactive status updates and clearer failure reasons.",
}

THEME_NORMALIZATION = {
    "app performance": "App Performance",
    "performance": "App Performance",
    "stability": "App Performance",
    "trading charges/pricing": "Trading Charges/Pricing",
    "trading pricing": "Trading Charges/Pricing",
    "pricing": "Trading Charges/Pricing",
    "charges": "Trading Charges/Pricing",
    "customer support": "Customer Support",
    "support": "Customer Support",
    "features performance": "Features Performance",
    "feature performance": "Features Performance",
    "features": "Features Performance",
    "kyc/statements/withdrawals": "KYC/Statements/Withdrawals",
    "kyc": "KYC/Statements/Withdrawals",
    "withdrawals": "KYC/Statements/Withdrawals",
    "statements": "KYC/Statements/Withdrawals",
}


def _normalize_theme(raw_theme: str) -> str:
    value = (raw_theme or "").strip().lower()
    if value in THEME_NORMALIZATION:
        return THEME_NORMALIZATION[value]

    for key, canonical in THEME_NORMALIZATION.items():
        if key in value:
            return canonical

    return "Features Performance"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return default


def _safe_date(value: Any) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.Timestamp.now(tz="UTC").tz_localize(None)
    if getattr(parsed, "tzinfo", None) is not None:
        return parsed.tz_convert(None)
    return parsed


def _sample_reviews(df: pd.DataFrame, sample_size: int, seed: int) -> pd.DataFrame:
    n = min(sample_size, len(df))
    sampled = df.sample(n=n, random_state=seed).copy().reset_index(drop=True)
    sampled["sample_id"] = sampled.index.map(lambda i: f"R{i + 1:03d}")
    sampled["rating"] = sampled["rating"].map(lambda x: _safe_int(x, 3)).clip(lower=1, upper=5)
    sampled["date"] = sampled["date"].map(_safe_date)
    sampled["text"] = sampled["text"].fillna("").astype(str).str.strip()
    sampled = sampled[sampled["text"].str.len() > 0].reset_index(drop=True)
    return sampled


def _split_batches(sampled_df: pd.DataFrame, batch_size: int) -> list[pd.DataFrame]:
    batches: list[pd.DataFrame] = []
    for start in range(0, len(sampled_df), batch_size):
        batch = sampled_df.iloc[start : start + batch_size].copy()
        if not batch.empty:
            batches.append(batch)
    return batches


def _local_classify_text(text: str) -> str:
    lower = text.lower()
    scores = {theme: 0 for theme in THEMES}
    for theme, hints in THEME_HINTS.items():
        for hint in hints:
            if hint in lower:
                scores[theme] += 1

    best_theme = max(scores, key=scores.get)
    if scores[best_theme] == 0:
        return "Features Performance"
    return best_theme


def _local_batch_classification(batch_df: pd.DataFrame) -> dict[str, str]:
    return {
        row["sample_id"]: _local_classify_text(str(row["text"]))
        for _, row in batch_df.iterrows()
    }


def _extract_json(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Model output does not contain JSON object")
    return json.loads(text[start : end + 1])


def _parse_assignments_payload(parsed: dict[str, Any]) -> dict[str, str]:
    assignments = parsed.get("assignments", {})
    mapped: dict[str, str] = {}

    if isinstance(assignments, dict):
        for review_id, theme in assignments.items():
            rid = str(review_id).strip()
            if rid:
                mapped[rid] = _normalize_theme(str(theme))
        return mapped

    if isinstance(assignments, list):
        for item in assignments:
            if not isinstance(item, dict):
                continue
            review_id = str(item.get("review_id", "")).strip()
            theme = _normalize_theme(str(item.get("theme", "")))
            if review_id:
                mapped[review_id] = theme

    return mapped


def _claude_message(client: Any, model: str, system_prompt: str, user_prompt: str, max_tokens: int = 6000) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in response.content if hasattr(block, "text"))


def _claude_batch_classification(batch_df: pd.DataFrame, model: str) -> dict[str, str]:
    from anthropic import Anthropic

    prompt_path = Path("phases/phase_03_theme_grouping_claude/prompts/theme_grouping_prompt.md")
    system_prompt = prompt_path.read_text(encoding="utf-8")

    records: list[dict[str, Any]] = []
    for _, row in batch_df.iterrows():
        records.append(
            {
                "review_id": row["sample_id"],
                "rating": int(row["rating"]),
                "date": row["date"].strftime("%Y-%m-%d"),
                "text": str(row["text"])[:450],
            }
        )

    user_prompt = (
        "Classify each review_id into exactly one of the five fixed themes.\n"
        "Return compact JSON only in this shape:"
        " {\"assignments\": {\"R001\": \"App Performance\", ...}}\n"
        "Include every review_id exactly once. No prose.\n\n"
        f"Themes: {THEMES}\n\n"
        "Input records:\n"
        f"{json.dumps(records, ensure_ascii=True)}"
    )

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    first_text = _claude_message(client, model, system_prompt, user_prompt, max_tokens=6000)
    try:
        parsed = _extract_json(first_text)
        mapped = _parse_assignments_payload(parsed)
        if mapped:
            return mapped
    except Exception:  # noqa: BLE001
        pass

    repair_prompt = (
        "Convert the following content into VALID JSON ONLY with this shape:"
        " {\"assignments\": {\"R001\": \"App Performance\"}}."
        " Keep only allowed theme values and do not omit any IDs.\n\n"
        f"Raw content:\n{first_text}"
    )
    repaired_text = _claude_message(client, model, system_prompt, repair_prompt, max_tokens=6000)
    repaired = _extract_json(repaired_text)
    mapped = _parse_assignments_payload(repaired)
    if not mapped:
        raise ValueError("Claude response could not be parsed into assignments")
    return mapped


def _priority_score(rating: int, date_value: pd.Timestamp, min_date: pd.Timestamp, max_date: pd.Timestamp) -> float:
    rating_score = (6 - rating) / 5
    if max_date <= min_date:
        recency_score = 1.0
    else:
        recency_score = (date_value - min_date).days / max((max_date - min_date).days, 1)
    return round((0.7 * rating_score + 0.3 * recency_score) * 100, 2)


def _build_theme_summary(sampled_df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    min_date = sampled_df["date"].min()
    max_date = sampled_df["date"].max()

    sampled_df["priority_score"] = sampled_df.apply(
        lambda row: _priority_score(int(row["rating"]), row["date"], min_date, max_date),
        axis=1,
    )

    themes_payload: list[dict[str, Any]] = []
    quotes: list[str] = []
    insight_candidates: list[dict[str, Any]] = []

    for theme in THEMES:
        subset = sampled_df[sampled_df["theme"] == theme].copy()
        subset = subset.sort_values(by=["priority_score", "date", "rating"], ascending=[False, False, True])

        top_reviews = subset.head(10)
        count = int(len(subset))
        avg_rating = round(float(subset["rating"].mean()), 2) if count else None

        top_payload: list[dict[str, Any]] = []
        for rank, (_, row) in enumerate(top_reviews.iterrows(), start=1):
            top_payload.append(
                {
                    "rank": rank,
                    "review_id": row["sample_id"],
                    "rating": int(row["rating"]),
                    "date": row["date"].strftime("%Y-%m-%d"),
                    "priority_score": float(row["priority_score"]),
                    "text": str(row["text"]),
                }
            )

        if count:
            quotes.append(str(top_payload[0]["text"])[:180])

        insight_candidates.append(
            {
                "theme": theme,
                "insight": INSIGHT_TEMPLATES[theme],
                "supporting_review_ids": [item["review_id"] for item in top_payload[:3]],
            }
        )

        themes_payload.append(
            {
                "name": theme,
                "count": count,
                "avg_rating": avg_rating,
                "summary": (
                    f"{count} sampled reviews mapped here"
                    + (f" (avg rating {avg_rating})." if avg_rating is not None else ".")
                ),
                "top_reviews": top_payload,
            }
        )

    unique_quotes: list[str] = []
    seen = set()
    for quote in quotes:
        normalized = re.sub(r"\s+", " ", quote.strip())
        if normalized and normalized not in seen:
            unique_quotes.append(normalized)
            seen.add(normalized)
        if len(unique_quotes) == 5:
            break

    while len(unique_quotes) < 5:
        unique_quotes.append("Users highlighted recurring friction in this theme bucket.")

    return themes_payload, unique_quotes[:5], insight_candidates


def _write_assignments_csv(sampled_df: pd.DataFrame, assignments_output: Path) -> None:
    payload = sampled_df[["sample_id", "theme", "rating", "date", "text"]].copy()
    payload["date"] = payload["date"].dt.strftime("%Y-%m-%d")
    assignments_output.parent.mkdir(parents=True, exist_ok=True)
    payload.to_csv(assignments_output, index=False)


def run(
    input_path: Path,
    output_path: Path,
    model: str,
    sample_size: int,
    batch_size: int,
    seed: int,
    assignments_output: Path,
    meta_output: Path,
) -> None:
    load_dotenv()
    df = pd.read_csv(input_path)

    required = {"rating", "text", "date"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    sampled_df = _sample_reviews(df, sample_size=sample_size, seed=seed)
    batches = _split_batches(sampled_df, batch_size=batch_size)

    all_assignments: dict[str, str] = {}
    used_claude = False

    for batch in batches[:2]:
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                batch_assignments = _claude_batch_classification(batch, model=model)
                used_claude = True
            except Exception as exc:  # noqa: BLE001
                print(f"Claude batch failed, using local fallback for this batch: {exc}")
                batch_assignments = _local_batch_classification(batch)
        else:
            batch_assignments = _local_batch_classification(batch)

        for review_id in batch["sample_id"].tolist():
            all_assignments[review_id] = _normalize_theme(batch_assignments.get(review_id, "Features Performance"))

    for batch in batches[2:]:
        local_assignments = _local_batch_classification(batch)
        for review_id in batch["sample_id"].tolist():
            all_assignments[review_id] = _normalize_theme(local_assignments.get(review_id, "Features Performance"))

    sampled_df["theme"] = sampled_df["sample_id"].map(all_assignments).fillna("Features Performance")

    themes_payload, quotes, insight_candidates = _build_theme_summary(sampled_df)

    period_start = sampled_df["date"].min().strftime("%Y-%m-%d") if not sampled_df.empty else None
    period_end = sampled_df["date"].max().strftime("%Y-%m-%d") if not sampled_df.empty else None

    payload = {
        "week_start": period_start,
        "week_end": period_end,
        "analysis_window_start": period_start,
        "analysis_window_end": period_end,
        "sampling": {
            "input_rows": int(len(df)),
            "sample_size_requested": sample_size,
            "sample_size_used": int(len(sampled_df)),
            "batch_size": batch_size,
            "batches_used_for_claude": min(2, len(batches)),
            "seed": seed,
            "used_claude": used_claude,
        },
        "fixed_themes": THEMES,
        "themes": themes_payload,
        "quotes": quotes,
        "actionable_insight_candidates": insight_candidates,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    _write_assignments_csv(sampled_df, assignments_output)

    meta_payload = {
        "phase": "phase_03_theme_grouping_claude",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_csv": str(input_path),
        "output_json": str(output_path),
        "assignments_csv": str(assignments_output),
        "config": {
            "model": model,
            "sample_size": sample_size,
            "batch_size": batch_size,
            "seed": seed,
        },
        "sampling": payload["sampling"],
        "theme_counts": {item["name"]: item["count"] for item in themes_payload},
    }
    meta_output.parent.mkdir(parents=True, exist_ok=True)
    meta_output.write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")

    print(f"Saved theme summary to {output_path}")
    print(f"Saved per-review assignments to {assignments_output}")
    print(f"Saved phase metadata to {meta_output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Group redacted reviews into fixed themes with Claude")
    parser.add_argument("--input", default="data/processed/reviews_15w_redacted.csv")
    parser.add_argument("--output", default="data/processed/themes_weekly.json")
    parser.add_argument("--assignments-output", default="data/processed/theme_assignments_sample_400.csv")
    parser.add_argument("--meta-output", default="data/processed/themes_weekly_meta.json")
    parser.add_argument("--model", default=os.getenv("CLAUDE_MODEL", "claude-haiku-4-5"))
    parser.add_argument("--sample-size", type=int, default=400)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    run(
        input_path=Path(args.input),
        output_path=Path(args.output),
        model=args.model,
        sample_size=args.sample_size,
        batch_size=args.batch_size,
        seed=args.seed,
        assignments_output=Path(args.assignments_output),
        meta_output=Path(args.meta_output),
    )


if __name__ == "__main__":
    main()
