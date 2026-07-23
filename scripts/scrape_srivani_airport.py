#!/usr/bin/env python3
"""
Scrapes the TTD SRIVANI airport token live-status page and appends one row to a
daily CSV (one file per IST day) in the Drive project folder. See ../README.md
(Source #1) and ../DISCOVERY_PLAN.md for the research behind this.

Target: https://webapps.tirumala.org/SrivaniTokenLiveTV/AirportLiveStatus.aspx
Public, no login, plain server-rendered HTML - no separate API found.

Daily behaviour (per request):
  - Quota resets each morning to 200 and depletes as flights land, typically
    gone by the 3rd/4th landing.
  - Scrape only during the daily window: from START_HOUR_IST (07:00) until the
    day's `available` hits 0 (then a sentinel file stops further polling for
    that IST day), with a HARD_STOP_HOUR_IST safety cutoff so it never runs
    overnight even on a low-demand day that never sells out.
  - One CSV per IST calendar day: data/raw/srivani_airport/YYYY-MM-DD.csv

Designed to run every 2 min via launchd. Runs unattended, so it never raises on
network/parse errors - it logs and exits 0/1 without crashing the scheduler.

  Exit 0 = handled (row written, or intentionally skipped).
  Exit 1 = a fetch/parse/write error occurred (logged to logs/error.log).
"""

import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

URL = "https://webapps.tirumala.org/SrivaniTokenLiveTV/AirportLiveStatus.aspx"
TIMEOUT_SECONDS = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) TirupatiDarshanScraper/1.0"}

IST = ZoneInfo("Asia/Kolkata")
HARD_STOP_HOUR_IST = 23   # safety: never scrape at/after 23:00 IST, sold out or not

# Start polling shortly BEFORE the first flight is due, so we are already running
# when it lands and can catch the exact first drop (200 -> 198). The schedule
# lives in the tracker repo; we start (earliest scheduled arrival - buffer). If
# that file is missing/unreadable, fall back to a safe fixed start well before any
# plausible first arrival (~07:00). Tokens can't deplete before a flight lands, so
# an early start just records a flat 200 baseline until the real first drop.
# This script lives in the repo (the Drive folder). Everything is repo-relative.
REPO_ROOT = Path(__file__).resolve().parent.parent
# .git is kept OUTSIDE the Drive-synced folder so Drive never syncs git internals.
GIT_DIR = Path.home() / "tirupati-tracker.git"
FLIGHTS_JSON = REPO_ROOT / "data" / "flights.json"
FALLBACK_START_MIN = 6 * 60 + 30   # 06:30 IST


def start_minute_ist() -> int:
    """Minute-of-day (IST) at which polling should begin today: the earliest
    scheduled TIR arrival minus start_buffer_min, floored at 05:00. Falls back to
    FALLBACK_START_MIN if the schedule file is missing or malformed."""
    try:
        data = json.loads(FLIGHTS_JSON.read_text(encoding="utf-8"))
        buf = int(data.get("start_buffer_min", 20))
        mins = []
        for a in data.get("arrivals", []):
            hm = a.get("sched_arr", "")
            if len(hm) >= 5 and hm[2] == ":":
                mins.append(int(hm[:2]) * 60 + int(hm[3:5]))
        if mins:
            return max(5 * 60, min(mins) - buf)
    except Exception:  # noqa: BLE001 - any problem => safe fallback
        pass
    return FALLBACK_START_MIN


def now_ist() -> datetime:
    """The single source of the timestamp: capture the current instant in UTC,
    then convert to IST. Every timestamp this script writes (CSV scraped_at, CSV
    filename date, status/error logs, the scrape-window checks) goes through here,
    so they are ALWAYS India time regardless of the machine's own timezone -
    whether this Mac is on America/New_York now, or switches to IST later while
    traveling. There is no path by which a non-IST time reaches the CSV."""
    return datetime.now(timezone.utc).astimezone(IST)

# CSV output goes straight into this repo (the Drive folder), so the data lives
# in Drive AND is committed to GitHub. This requires the launchd job's python to
# have Full Disk Access (macOS gates background writes into the Drive File
# Provider mount). The venv itself stays LOCAL (launchd can't exec a venv inside
# Drive), and .git stays local too (GIT_DIR above) so Drive never syncs it.
DATA_DIR = REPO_ROOT / "data" / "srivani_airport"
LOG_DIR = REPO_ROOT / "logs"

REPORTING_RE = re.compile(
    r"(\d{2}-\d{2}-\d{4})\s*\(([A-Za-z]+)\)\s*::\s*(\d{1,2}:\d{2}\s*[AP]M)"
)

CSV_COLUMNS = [
    "scraped_at",                  # ISO 8601, IST - when THIS SCRIPT fetched the page
    "quota",
    "issued",
    "available",
    # The `ttd_*` fields are TTD's own "Reporting Date & Time" label, copied
    # verbatim off the page (element lblReportingDtls) - NOT our scrape clock.
    # It's an operational time the temple publishes (already IST), typically a
    # fixed value for the day, so it does not tick with scraped_at.
    "ttd_reporting_datetime_raw",  # full raw label, e.g. "...:22-07-2026(WEDNESDAY) :: 04:00 PM"
    "ttd_reporting_date",          # DD-MM-YYYY
    "ttd_reporting_weekday",
    "ttd_reporting_time",          # HH:MM AM/PM, as published by TTD
]


def write_status(msg: str) -> None:
    """Overwrite a single-line status file so the latest state is always visible
    at a glance without the log growing unbounded over weeks of running."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        (LOG_DIR / "last_run.txt").write_text(
            f"{now_ist().isoformat(timespec='seconds')}  {msg}\n", encoding="utf-8"
        )
    except Exception:  # noqa: BLE001 - status logging must never crash the run
        pass


def log_error(msg: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / "error.log", "a", encoding="utf-8") as f:
            f.write(f"{now_ist().isoformat(timespec='seconds')}  {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def sentinel_path(today_str: str) -> Path:
    """Marker meaning 'available hit 0 for this IST day - stop polling until
    tomorrow'. One-way latch; delete by hand if the quota is ever seen to reset
    back up mid-day."""
    return DATA_DIR / f".sold_out_{today_str}"


def data_dir_writable() -> bool:
    """Courtesy pre-check: confirm we can actually store a result BEFORE hitting
    the temple site. Under launchd without Full Disk Access, writing into the
    Drive folder raises PermissionError - in that case we skip the fetch entirely
    rather than poll a public-service site every 2 min and throw the data away."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = DATA_DIR / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:  # noqa: BLE001
        return False


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
    """Regenerate data/index.json, the per-day manifest the dashboard reads first
    (GitHub Pages has no directory listing)."""
    index_path = REPO_ROOT / "data" / "index.json"

    def to_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    days = []
    for p in sorted(DATA_DIR.glob("*.csv")):
        try:
            with open(p, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        except Exception:  # noqa: BLE001
            rows = []
        if not rows:
            continue
        first, last = rows[0], rows[-1]
        avails = [to_int(r["available"]) for r in rows if to_int(r["available"]) is not None]
        days.append({
            "date": p.stem,
            "weekday": last.get("ttd_reporting_weekday", ""),
            "file": f"srivani_airport/{p.name}",
            "samples": len(rows),
            "first_scraped_at": first["scraped_at"],
            "last_scraped_at": last["scraped_at"],
            "quota": to_int(last.get("quota")),
            "last_issued": to_int(last.get("issued")),
            "last_available": to_int(last.get("available")),
            "sold_out": bool(avails) and avails[-1] <= 0,
        })
    index_path.write_text(
        json.dumps({"generated_at": now_ist().isoformat(timespec="seconds"),
                    "source": "srivani_airport", "days": days}, indent=2) + "\n",
        encoding="utf-8",
    )


def git_publish() -> str:
    """Commit data/ into the repo and push to GitHub. The repo work tree is this
    Drive folder; .git lives locally (GIT_DIR). Needs Full Disk Access on this
    python to read/stage the Drive work tree. Never raises - logs and returns a
    short status tag for the run line."""
    env = {**os.environ, "GIT_DIR": str(GIT_DIR), "GIT_WORK_TREE": str(REPO_ROOT),
           "GIT_TERMINAL_PROMPT": "0"}

    def git(*args):
        return subprocess.run(["git", *args], cwd=str(REPO_ROOT), env=env,
                              capture_output=True, text=True, timeout=120)

    try:
        git("add", "data/")
        if git("diff", "--cached", "--quiet").returncode == 0:
            return ""  # nothing new to publish
        if git("commit", "-m", f"data: srivani airport {now_ist():%Y-%m-%d %H:%M IST}").returncode != 0:
            return "  [commit failed]"
        git("pull", "--rebase", "--autostash", "origin", "main")
        if git("push", "origin", "main").returncode != 0:
            log_error("git push failed")
            return "  [committed, push failed]"
        return "  [pushed]"
    except Exception as exc:  # noqa: BLE001
        log_error(f"git publish failed: {exc!r}")
        return "  [git error]"


def main() -> int:
    now = now_ist()
    today_str = now.strftime("%Y-%m-%d")

    # 1. Already sold out today? Stop until tomorrow.
    if sentinel_path(today_str).exists():
        write_status(f"skip: sold out earlier today ({today_str}); waiting for tomorrow")
        return 0

    # 2. Outside the daily scraping window? Skip quietly. Start is tied to the
    #    first scheduled flight arrival (so we're polling before it lands).
    start_min = start_minute_ist()
    now_min = now.hour * 60 + now.minute
    if now_min < start_min:
        write_status(f"skip: before {start_min // 60:02d}:{start_min % 60:02d} IST start "
                     f"(~20m before first scheduled TIR arrival)")
        return 0
    if now.hour >= HARD_STOP_HOUR_IST:
        write_status(f"skip: after {HARD_STOP_HOUR_IST:02d}:00 IST safety cutoff")
        return 0

    # 3. Can we store a result at all? If not (no Full Disk Access / Drive
    #    unmounted), don't bother the site - just surface the reason.
    if not data_dir_writable():
        write_status(
            "BLOCKED: cannot write to Drive data folder - grant Full Disk Access "
            "to the scraper python (see README), or check Google Drive is mounted. "
            "Not fetching until this is fixed."
        )
        return 0

    # 4. Fetch + parse.
    try:
        row = fetch_and_parse()
    except Exception as exc:  # noqa: BLE001
        log_error(f"fetch/parse failed: {exc!r}")
        write_status(f"ERROR fetching: {exc}")
        return 1

    # 5. Store.
    try:
        csv_path = append_row(row)
    except Exception as exc:  # noqa: BLE001
        log_error(f"write failed: {exc!r}")
        write_status(f"ERROR writing: {exc}")
        return 1

    # 6. Latch if sold out.
    latched = ""
    try:
        if int(row["available"]) <= 0:
            sentinel_path(today_str).touch()
            latched = "  [SOLD OUT - latched, stopping for today]"
    except ValueError:
        pass  # non-numeric 'available' - don't latch on bad data

    # 7. Update the dashboard manifest, then commit + push to GitHub.
    try:
        rebuild_index()
    except Exception as exc:  # noqa: BLE001
        log_error(f"index rebuild failed: {exc!r}")
    published = git_publish()

    msg = (f"OK quota={row['quota']} issued={row['issued']} "
           f"available={row['available']} -> {csv_path.name}{latched}{published}")
    write_status(msg)
    print(f"{row['scraped_at']}  {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
