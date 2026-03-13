from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


def _validate_range(weeks_from: int, weeks_to: int) -> None:
    if weeks_from < 1 or weeks_from > 15:
        raise ValueError("weeks_from must be between 1 and 15")
    if weeks_to < 1 or weeks_to > 15:
        raise ValueError("weeks_to must be between 1 and 15")
    if weeks_from > weeks_to:
        raise ValueError("weeks_from must be <= weeks_to")


def run(input_csv: Path, meta_json: Path, weeks_from: int, weeks_to: int) -> dict:
    _validate_range(weeks_from, weeks_to)

    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    df = pd.read_csv(input_csv)
    if "date" not in df.columns:
        raise ValueError("Input CSV must include 'date' column")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_bound = now - timedelta(weeks=weeks_to)
    end_bound = now - timedelta(weeks=weeks_from - 1)

    filtered = df[(df["date"] >= start_bound) & (df["date"] < end_bound)].copy()
    filtered["date"] = filtered["date"].dt.strftime("%Y-%m-%d")
    filtered = filtered.reset_index(drop=True)

    filtered.to_csv(input_csv, index=False)

    meta_payload = {}
    if meta_json.exists():
        try:
            meta_payload = json.loads(meta_json.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            meta_payload = {}

    meta_payload["week_filter"] = {
        "weeks_from": weeks_from,
        "weeks_to": weeks_to,
        "applied_at_utc": datetime.now(timezone.utc).isoformat(),
        "date_range_inclusive_start": start_bound.date().isoformat(),
        "date_range_exclusive_end": end_bound.date().isoformat(),
        "rows_after_filter": int(len(filtered)),
    }
    meta_json.parent.mkdir(parents=True, exist_ok=True)
    meta_json.write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")

    return {
        "rows_after_filter": int(len(filtered)),
        "start": start_bound.date().isoformat(),
        "end_exclusive": end_bound.date().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter raw reviews CSV by selected week range")
    parser.add_argument("--input", default="data/raw/reviews_15w.csv")
    parser.add_argument("--meta", default="data/raw/reviews_15w_meta.json")
    parser.add_argument("--weeks-from", type=int, required=True)
    parser.add_argument("--weeks-to", type=int, required=True)
    args = parser.parse_args()

    result = run(
        input_csv=Path(args.input),
        meta_json=Path(args.meta),
        weeks_from=args.weeks_from,
        weeks_to=args.weeks_to,
    )

    print(
        "Applied week filter:",
        f"from={args.weeks_from}",
        f"to={args.weeks_to}",
        f"rows={result['rows_after_filter']}",
        f"start={result['start']}",
        f"end_exclusive={result['end_exclusive']}",
    )


if __name__ == "__main__":
    main()
