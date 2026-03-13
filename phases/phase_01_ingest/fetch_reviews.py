from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
from google_play_scraper import Sort, reviews

WORD_PATTERN = re.compile(r"[A-Za-z0-9']+")
NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9\s]")
MULTISPACE_PATTERN = re.compile(r"\s+")
REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{5,}")
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"  # flags
    "\U0001F300-\U0001FAFF"  # symbols and pictographs
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats
    "]",
    flags=re.UNICODE,
)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_text(text: str) -> str:
    lowered = text.lower().strip()
    lowered = NON_ALNUM_PATTERN.sub(" ", lowered)
    lowered = MULTISPACE_PATTERN.sub(" ", lowered)
    return lowered.strip()


def _word_count(text: str) -> int:
    return len(WORD_PATTERN.findall(text))


def _contains_emoji(text: str) -> bool:
    return EMOJI_PATTERN.search(text) is not None


def _is_repetitive(text: str) -> bool:
    tokens = [token.lower() for token in WORD_PATTERN.findall(text)]
    if not tokens:
        return True

    unique_ratio = len(set(tokens)) / len(tokens)
    if unique_ratio < 0.4:
        return True

    streak = 1
    for i in range(1, len(tokens)):
        if tokens[i] == tokens[i - 1]:
            streak += 1
            if streak >= 3:
                return True
        else:
            streak = 1

    if REPEATED_CHAR_PATTERN.search(text.lower()):
        return True

    return False


def _extract_app_id(playstore_url: str) -> str:
    query = parse_qs(urlparse(playstore_url).query)
    app_id = query.get("id", [""])[0].strip()
    if not app_id:
        raise ValueError("Could not extract app id from Play Store URL. Expected query param 'id'.")
    return app_id


def fetch_recent_reviews(
    app_id: str,
    weeks: int = 15,
    lang: str = "en",
    country: str = "in",
    batch_size: int = 200,
    max_reviews: int = 5000,
    min_words: int = 6,
) -> tuple[pd.DataFrame, dict[str, int]]:
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    continuation_token = None
    rows: list[dict] = []
    seen_normalized_text: set[str] = set()

    stats = {
        "seen_total": 0,
        "dropped_older_than_cutoff": 0,
        "dropped_empty_text": 0,
        "dropped_short_text": 0,
        "dropped_emoji": 0,
        "dropped_repetitive": 0,
        "dropped_duplicate": 0,
        "kept": 0,
    }

    while len(rows) < max_reviews:
        result, continuation_token = reviews(
            app_id,
            lang=lang,
            country=country,
            sort=Sort.NEWEST,
            count=batch_size,
            continuation_token=continuation_token,
        )

        if not result:
            break

        hit_cutoff = False
        for item in result:
            stats["seen_total"] += 1

            raw_date = item.get("at")
            if not raw_date:
                stats["dropped_older_than_cutoff"] += 1
                continue

            created_at = _to_utc(raw_date)
            if created_at < cutoff:
                hit_cutoff = True
                stats["dropped_older_than_cutoff"] += 1
                continue

            text = (item.get("content") or "").strip()
            if not text:
                stats["dropped_empty_text"] += 1
                continue

            if _word_count(text) <= min_words:
                stats["dropped_short_text"] += 1
                continue

            if _contains_emoji(text):
                stats["dropped_emoji"] += 1
                continue

            if _is_repetitive(text):
                stats["dropped_repetitive"] += 1
                continue

            normalized_text = _normalize_text(text)
            if not normalized_text:
                stats["dropped_empty_text"] += 1
                continue

            if normalized_text in seen_normalized_text:
                stats["dropped_duplicate"] += 1
                continue
            seen_normalized_text.add(normalized_text)

            rows.append(
                {
                    "rating": int(item.get("score", 0) or 0),
                    "text": text,
                    "date": created_at.date().isoformat(),
                }
            )
            stats["kept"] += 1

            if len(rows) >= max_reviews:
                break

        if hit_cutoff or continuation_token is None:
            break

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[["rating", "text", "date"]].copy()
        df = df.drop_duplicates(subset=["text", "date"]).reset_index(drop=True)

    return df, stats


def _write_meta(meta_output: Path, meta_payload: dict) -> None:
    meta_output.parent.mkdir(parents=True, exist_ok=True)
    meta_output.write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Play Store reviews for the last N weeks")
    parser.add_argument("--app-id", default="com.nextbillion.groww")
    parser.add_argument("--playstore-url", default="")
    parser.add_argument("--weeks", type=int, default=15)
    parser.add_argument("--country", default="in")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--min-words", type=int, default=6)
    parser.add_argument("--output", default="data/raw/reviews_15w.csv")
    parser.add_argument("--meta-output", default="data/raw/reviews_15w_meta.json")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    app_id = _extract_app_id(args.playstore_url) if args.playstore_url else args.app_id

    df, stats = fetch_recent_reviews(
        app_id=app_id,
        weeks=args.weeks,
        country=args.country,
        lang=args.lang,
        min_words=args.min_words,
    )

    df.to_csv(output_path, index=False)

    date_min = df["date"].min() if not df.empty else None
    date_max = df["date"].max() if not df.empty else None
    meta_payload = {
        "app_id": app_id,
        "weeks": args.weeks,
        "country": args.country,
        "lang": args.lang,
        "min_words": args.min_words,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_csv": str(output_path),
        "total_reviews_written": int(len(df)),
        "date_range": {"min": date_min, "max": date_max},
        "stats": stats,
    }

    _write_meta(Path(args.meta_output), meta_payload)

    print(f"Saved {len(df)} reviews to {output_path} for app_id={app_id}")
    print(f"Saved ingest metadata to {args.meta_output}")


if __name__ == "__main__":
    main()
