from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _copy_if_exists(source: Path, target: Path, copied: list[str], missing: list[str]) -> None:
    if source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(str(target))
    else:
        missing.append(str(source))


def _export_review_sample(source_csv: Path, target_csv: Path, rows: int = 50) -> int:
    if not source_csv.exists():
        return 0

    df = pd.read_csv(source_csv)
    sample = df.head(rows)
    target_csv.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(target_csv, index=False)
    return len(sample)


def _copy_latest_matching(pattern: str, target_name: str, copied: list[str], missing: list[str]) -> None:
    candidates = sorted(Path("data/outputs").glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        missing.append(f"data/outputs/{pattern}")
        return

    source = candidates[0]
    target = Path("artifacts/latest") / target_name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    copied.append(str(target))


def main() -> None:
    artifacts = Path("artifacts/latest")
    artifacts.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    missing: list[str] = []

    fixed_copies = [
        (Path("data/outputs/weekly_note.md"), artifacts / "weekly_note.md"),
        (Path("data/outputs/weekly_note.pdf"), artifacts / "weekly_note.pdf"),
        (Path("data/outputs/weekly_note_meta.json"), artifacts / "weekly_note_meta.json"),
        (Path("data/outputs/email_draft.txt"), artifacts / "email_draft.txt"),
        (Path("data/outputs/email_draft_meta.json"), artifacts / "email_draft_meta.json"),
        (Path("data/outputs/pipeline_run_meta.json"), artifacts / "pipeline_run_meta.json"),
        (Path("data/outputs/pipeline_run_meta_scheduled.json"), artifacts / "pipeline_run_meta_scheduled.json"),
        (Path("data/processed/themes_weekly.json"), artifacts / "themes_weekly.json"),
        (Path("data/processed/themes_weekly_meta.json"), artifacts / "themes_weekly_meta.json"),
        (Path("data/processed/theme_assignments_sample_400.csv"), artifacts / "theme_assignments_sample_400.csv"),
    ]

    for source, target in fixed_copies:
        _copy_if_exists(source, target, copied=copied, missing=missing)

    sample_rows = _export_review_sample(
        source_csv=Path("data/processed/reviews_15w_redacted.csv"),
        target_csv=artifacts / "reviews_sample_redacted.csv",
        rows=50,
    )
    if sample_rows > 0:
        copied.append(str(artifacts / "reviews_sample_redacted.csv"))
    else:
        missing.append("data/processed/reviews_15w_redacted.csv")

    _copy_latest_matching(
        pattern="groww_weekly_insights_*.pdf",
        target_name="latest_weekly_insights.pdf",
        copied=copied,
        missing=missing,
    )
    _copy_latest_matching(
        pattern="groww_reviews_redacted_*.csv",
        target_name="latest_reviews_redacted.csv",
        copied=copied,
        missing=missing,
    )

    manifest = {
        "created_at_utc": _utc_now_iso(),
        "artifact_root": str(artifacts),
        "files_copied": copied,
        "missing_sources": missing,
        "review_sample_rows": sample_rows,
    }
    manifest_path = artifacts / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Artifacts prepared at {artifacts}")
    print(f"Manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
