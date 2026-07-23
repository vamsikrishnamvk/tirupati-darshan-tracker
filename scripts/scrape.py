#!/usr/bin/env python3
"""
Cloud (GitHub Actions) scraper for the TTD SRIVANI airport token live-status page.

Appends one row to a daily CSV (one file per IST day) under data/srivani_airport/,
then regenerates data/index.json (the manifest the web dashboard reads). The
GitHub Actions workflow commits+pushes whatever files this changes.

Target: https://webapps.tirumala.org/SrivaniTokenLiveTV/AirportLiveStatus.aspx
Public, no login, plain server-rendered HTML - no separate API found.

Timestamps are ALWAYS IST (Asia/Kolkata) via now_ist(), independent of the
runner's own clock (GitHub runners are UTC). This matches the local launchd
scraper's schema exactly, so the two data sources merge cleanly (dedupe on
scraped_at). Column meanings: `scraped_at` is OUR fetch time; the `ttd_*` columns
are TTD's own published "Reporting Date & Time" label copied verbatim.

Self-gating so it's cheap to run on a coarse cron:
  - Skips outside a soft IST window (the Actions cron already narrows this).
  - Skips once the day's quota is already sold out (reads today's last row),
    so it stops hitting the temple site for the rest of that IST day.
Never raises on network/parse errors - logs to stderr and exits non-zero so a
failed run is visible in Actions without corrupting data.
"""

import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

URL = "https://webapps.tirumala.org/SrivaniTokenLiveTV/AirportLiveStatus.aspx"
TIMEOUT_SECONDS = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) TirupatiDarshanTracker/1.0 (+github.com/vamsikrishnamvk/tirupati-darshan-tracker)"}

IST = ZoneInfo("Asia/Kolkata")
# Soft window guard (the workflow cron is the primary limiter). Wide enough to
# catch an early open and a late sell-out, tight enough to avoid overnight runs.
START_HOUR_IST = 6
HARD_STOP_HOUR_IST = 12

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "srivani_airport"
INDEX_PATH = REPO_ROOT / "data" / "index.json"

REPORTING_RE = re.compile(
    r"(\d{2}-\d{2}-\d{4})\s*\(([A-Za-z]+)\)\s*::\s*(\d{1,2}:\d{2}\s*[AP]M)"
)

CSV_COLUMNS = [
    "scraped_at",                  # ISO 8601, IST - when THIS SCRIPT fetched the page
    "quota",
    "issued",
    "available",
    # ttd_* = TTD's own "Reporting Date & Time" label, copied verbatim off the
    # page (lblReportingDtls). Already IST, usually fixed for the day - NOT our
    # scrape clock, so it does not tick with scraped_at.
    "ttd_reporting_datetime_raw",
    "ttd_reporting_date",
    "ttd_reporting_weekday",
    "ttd_reporting_time",
]


def now_ist() -> datetime:
    """Single source of the timestamp: capture the instant in UTC, convert to
    IST. Guarantees India time regardless of the runner's timezone."""
    return datetime.now(timezone.utc).astimezone(IST)


def log(msg: str) -> None:
    print(f"{now_ist().isoformat(timespec='seconds')}  {msg}", file=sys.stderr)


def last_available_today(csv_path: Path):
    """Return the `available` int from the last row of today's CSV, or None if
    the file doesn't exist / can't be read. Used to detect a same-day sell-out
    without a sentinel file (keeps the git tree clean)."""
    if not csv_path.exists():
        return None
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return None
        return int(rows[-1]["available"])
    except Exception:  # noqa: BLE001
        return None


def fetch_and_parse() -> dict:
    resp = requests.get(URL, headers=HEADERS, timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    def text_of(element_id):
        el = soup.find(id=element_id)
        if el is None:
            raise ValueError(f"missing #{element_id} - site layout may have changed")
        return el.get_text(strip=True)

    reporting_raw = text_of("lblReportingDtls")
    m = REPORTING_RE.search(reporting_raw)
    reporting_date, reporting_weekday, reporting_time = m.groups() if m else ("", "", "")

    return {
        "scraped_at": now_ist().isoformat(timespec="seconds"),
        "quota": text_of("lblQuota"),
        "issued": text_of("lblIssued"),
        "available": text_of("lblAvailableQuota"),
        "ttd_reporting_datetime_raw": reporting_raw,
        "ttd_reporting_date": reporting_date,
        "ttd_reporting_weekday": reporting_weekday,
        "ttd_reporting_time": reporting_time,
    }


def append_row(row: dict) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = DATA_DIR / f"{now_ist().strftime('%Y-%m-%d')}.csv"
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return csv_path


def rebuild_index() -> None:
    """Manifest the dashboard reads to know which day-files exist (GitHub Pages
    has no directory listing). Each entry summarizes one day so the page can show
    a history list without downloading every CSV up front."""
    days = []
    for p in sorted(DATA_DIR.glob("*.csv")):
        date = p.stem
        try:
            with open(p, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        except Exception:  # noqa: BLE001
            rows = []
        if not rows:
            continue
        weekday = rows[-1].get("ttd_reporting_weekday", "")
        first, last = rows[0], rows[-1]

        def to_int(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        avails = [to_int(r["available"]) for r in rows if to_int(r["available"]) is not None]
        sold_out = bool(avails) and avails[-1] <= 0
        days.append({
            "date": date,
            "weekday": weekday,
            "file": f"srivani_airport/{p.name}",
            "samples": len(rows),
            "first_scraped_at": first["scraped_at"],
            "last_scraped_at": last["scraped_at"],
            "quota": to_int(last.get("quota")),
            "last_issued": to_int(last.get("issued")),
            "last_available": to_int(last.get("available")),
            "sold_out": sold_out,
        })
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps({"generated_at": now_ist().isoformat(timespec="seconds"),
                    "source": "srivani_airport", "days": days}, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    now = now_ist()

    if now.hour < START_HOUR_IST or now.hour >= HARD_STOP_HOUR_IST:
        log(f"skip: outside IST window {START_HOUR_IST:02d}:00-{HARD_STOP_HOUR_IST:02d}:00 (now {now:%H:%M} IST)")
        return 0

    today_csv = DATA_DIR / f"{now.strftime('%Y-%m-%d')}.csv"
    prev_avail = last_available_today(today_csv)
    if prev_avail is not None and prev_avail <= 0:
        log(f"skip: already sold out today (last available={prev_avail})")
        return 0

    try:
        row = fetch_and_parse()
    except Exception as exc:  # noqa: BLE001
        log(f"ERROR fetch/parse: {exc!r}")
        return 1

    try:
        csv_path = append_row(row)
        rebuild_index()
    except Exception as exc:  # noqa: BLE001
        log(f"ERROR write: {exc!r}")
        return 1

    latched = ""
    try:
        if int(row["available"]) <= 0:
            latched = "  [SOLD OUT - no more scrapes today]"
    except ValueError:
        pass
    log(f"OK quota={row['quota']} issued={row['issued']} available={row['available']} "
        f"-> {csv_path.name}{latched}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
