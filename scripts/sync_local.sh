#!/usr/bin/env bash
# Push the LOCAL launchd scraper's high-res rows into this repo (hybrid capture).
#
#   scripts/sync_local.sh
#
# Run it from anywhere with the Mac awake. It pulls the latest cloud commits,
# merges the local CSVs (deduped on scraped_at), rebuilds index.json, and pushes.
# Safe to run repeatedly / on a schedule - a no-op when there are no new rows.
#
# Optional: wire it to a daily launchd job so the local detail syncs itself.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${TDT_PYTHON:-$HOME/tirupati-darshan-scraper-run/.venv/bin/python}"   # a python with requests+bs4 (bs4 only needed for scrape import; merge itself is stdlib)
LOCAL_DATA="${1:-$HOME/tirupati-scraper-data/srivani_airport}"

cd "$REPO_DIR"
git pull --rebase --autostash origin "$(git rev-parse --abbrev-ref HEAD)" || true
"$PY" scripts/merge_local.py "$LOCAL_DATA"

if git diff --quiet -- data/; then
  echo "sync_local: nothing to push."
  exit 0
fi
git add data/
git commit -m "data: merge local 2-min samples ($(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M IST'))"
git push
echo "sync_local: pushed."
