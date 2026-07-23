#!/usr/bin/env python3
"""
Merge the LOCAL launchd scraper's high-resolution CSVs into this repo's data,
deduped on `scraped_at`, then rebuild data/index.json. Idempotent: running it
repeatedly with no new local rows changes nothing.

Usage:
  python scripts/merge_local.py [LOCAL_DATA_DIR]
  LOCAL_DATA_DIR defaults to ~/tirupati-scraper-data/srivani_airport

Both sources share the same schema and IST `scraped_at`, so the union is just
"all rows, unique by scraped_at, sorted". The local job samples every 2 min; the
cloud job every ~5 min - overlapping-but-distinct timestamps, both kept.
"""

import csv
import sys
from pathlib import Path

# reuse the canonical column list + index builder from the scraper
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scrape  # noqa: E402

REPO_DATA = scrape.DATA_DIR  # repo/data/srivani_airport
DEFAULT_LOCAL = Path.home() / "tirupati-scraper-data" / "srivani_airport"


def read_rows(path: Path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def merge_file(local_csv: Path) -> bool:
    """Merge one day's local CSV into the repo. Returns True if repo changed."""
    repo_csv = REPO_DATA / local_csv.name
    by_ts = {}
    for r in read_rows(repo_csv):      # repo rows first
        by_ts[r["scraped_at"]] = r
    added = 0
    for r in read_rows(local_csv):     # then local rows (fill gaps)
        if r["scraped_at"] not in by_ts:
            by_ts[r["scraped_at"]] = r
            added += 1
    if added == 0 and repo_csv.exists():
        return False
    ordered = [by_ts[k] for k in sorted(by_ts)]
    REPO_DATA.mkdir(parents=True, exist_ok=True)
    with open(repo_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=scrape.CSV_COLUMNS)
        w.writeheader()
        for row in ordered:
            w.writerow({k: row.get(k, "") for k in scrape.CSV_COLUMNS})
    print(f"  {local_csv.name}: +{added} rows (total {len(ordered)})")
    return True


def main() -> int:
    local_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOCAL
    if not local_dir.exists():
        print(f"local data dir not found: {local_dir}")
        return 0
    changed = False
    for local_csv in sorted(local_dir.glob("*.csv")):
        if merge_file(local_csv):
            changed = True
    if changed:
        scrape.rebuild_index()
        print("index.json rebuilt")
    else:
        print("no new local rows to merge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
