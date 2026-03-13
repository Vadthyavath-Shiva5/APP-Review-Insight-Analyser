from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:\d[\s-]?){10,12}\b")
LONG_ID_PATTERN = re.compile(r"\b\d{9,18}\b")
WORD_PATTERN = re.compile(r"[A-Za-z0-9']+")
NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9\s]")
MULTISPACE_PATTERN = re.compile(r"\s+")
REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{5,}")
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "]",
    flags=re.UNICODE,
)


def _redact_pii_with_counts(text: str) -> tuple[str, dict[str, int]]:
    email_matches = len(EMAIL_PATTERN.findall(text))
    phone_matches = len(PHONE_PATTERN.findall(text))
    id_matches = len(LONG_ID_PATTERN.findall(text))

    clean = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    clean = PHONE_PATTERN.sub("[REDACTED_PHONE]", clean)
    clean = LONG_ID_PATTERN.sub("[REDACTED_ID]", clean)
    clean = MULTISPACE_PATTERN.sub(" ", clean).strip()

    return clean, {
        "email_matches": email_matches,
        "phone_matches": phone_matches,
        "id_matches": id_matches,
    }


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


def _write_meta(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run(input_path: Path, output_path: Path, min_words: int = 6, meta_output: Path | None = None) -> None:
    df = pd.read_csv(input_path)

    required = {"rating", "text", "date"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    stats = {
        "rows_input": int(len(df)),
        "rows_after_required_projection": 0,
        "dropped_empty_text": 0,
        "dropped_short_text": 0,
        "dropped_emoji": 0,
        "dropped_repetitive": 0,
        "dropped_invalid_date": 0,
        "dropped_invalid_rating": 0,
        "dropped_duplicates": 0,
        "rows_output": 0,
        "pii_email_matches": 0,
        "pii_phone_matches": 0,
        "pii_id_matches": 0,
    }

    cleaned = df[["rating", "text", "date"]].copy()
    stats["rows_after_required_projection"] = int(len(cleaned))

    cleaned["text"] = cleaned["text"].fillna("").astype(str)
    cleaned["date"] = cleaned["date"].fillna("").astype(str).str.strip()

    redacted_texts: list[str] = []
    for text in cleaned["text"]:
        redacted, pii_counts = _redact_pii_with_counts(text)
        redacted_texts.append(redacted)
        stats["pii_email_matches"] += pii_counts["email_matches"]
        stats["pii_phone_matches"] += pii_counts["phone_matches"]
        stats["pii_id_matches"] += pii_counts["id_matches"]
    cleaned["text"] = redacted_texts

    before = len(cleaned)
    cleaned = cleaned[cleaned["text"].str.len() > 0].copy()
    stats["dropped_empty_text"] += int(before - len(cleaned))

    before = len(cleaned)
    cleaned = cleaned[cleaned["text"].map(_word_count) > min_words].copy()
    stats["dropped_short_text"] += int(before - len(cleaned))

    before = len(cleaned)
    cleaned = cleaned[~cleaned["text"].map(_contains_emoji)].copy()
    stats["dropped_emoji"] += int(before - len(cleaned))

    before = len(cleaned)
    cleaned = cleaned[~cleaned["text"].map(_is_repetitive)].copy()
    stats["dropped_repetitive"] += int(before - len(cleaned))

    cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce")
    before = len(cleaned)
    cleaned = cleaned.dropna(subset=["date"]).copy()
    stats["dropped_invalid_date"] += int(before - len(cleaned))
    cleaned["date"] = cleaned["date"].dt.strftime("%Y-%m-%d")

    cleaned["rating"] = pd.to_numeric(cleaned["rating"], errors="coerce")
    before = len(cleaned)
    cleaned = cleaned[cleaned["rating"].between(1, 5, inclusive="both")].copy()
    stats["dropped_invalid_rating"] += int(before - len(cleaned))
    cleaned["rating"] = cleaned["rating"].astype(int)

    cleaned["_normalized_text"] = cleaned["text"].map(_normalize_text)
    cleaned = cleaned[cleaned["_normalized_text"].str.len() > 0].copy()

    before = len(cleaned)
    cleaned = cleaned.drop_duplicates(subset=["_normalized_text"]).reset_index(drop=True)
    stats["dropped_duplicates"] += int(before - len(cleaned))

    cleaned = cleaned[["rating", "text", "date"]]
    stats["rows_output"] = int(len(cleaned))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(output_path, index=False)

    if meta_output is not None:
        payload = {
            "phase": "phase_02_privacy_and_cleaning",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_csv": str(input_path),
            "output_csv": str(output_path),
            "min_words": min_words,
            "stats": stats,
        }
        _write_meta(meta_output, payload)
        print(f"Saved cleaning metadata to {meta_output}")

    print(f"Saved {len(cleaned)} redacted reviews to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean reviews and redact PII")
    parser.add_argument("--input", default="data/raw/reviews_15w.csv")
    parser.add_argument("--output", default="data/processed/reviews_15w_redacted.csv")
    parser.add_argument("--meta-output", default="data/processed/reviews_15w_redacted_meta.json")
    parser.add_argument("--min-words", type=int, default=6)
    args = parser.parse_args()

    run(
        input_path=Path(args.input),
        output_path=Path(args.output),
        min_words=args.min_words,
        meta_output=Path(args.meta_output) if args.meta_output else None,
    )


if __name__ == "__main__":
    main()
