# Tirupati SRIVANI Airport Token Tracker

Tracks how fast the **200 daily SRIVANI airport-counter darshan tokens** at Tirupati (TIR) deplete
each morning, to inform the airport-counter vs. online-booking decision for a Sep 9-10, 2026
Tirupati trip. Live page:

**https://vamsikrishnamvk.github.io/tirupati-darshan-tracker/**

## Architecture: local capture, GitHub publish

The TTD site ([`AirportLiveStatus.aspx`](https://webapps.tirumala.org/SrivaniTokenLiveTV/AirportLiveStatus.aspx))
**blocks non-India / datacenter IPs at the firewall.** A GitHub Actions runner (US Azure) gets a
connection timeout; a home Mac on a residential IP reaches it fine (verified 2026-07-23). So capture
cannot run in the cloud. The split is:

- **Capture (local Mac):** a macOS `launchd` job runs the scraper every 2 min during the IST morning
  window, writing daily CSVs to `~/tirupati-scraper-data/srivani_airport/`. Timestamps are always
  IST regardless of the Mac's own timezone.
- **Publish + backup (GitHub):** `scripts/sync_local.sh` merges those local CSVs into this repo
  (deduped on `scraped_at`), rebuilds `data/index.json`, and pushes. GitHub Pages serves the
  dashboard from the committed data. A second `launchd` job runs the sync every ~10 min while the
  Mac is awake, so the live page stays current.

> Note on coverage: the India window (07:00-09:30 IST) is 21:30 EDT to midnight, i.e. US
> late-evening. Capture happens whenever the Mac is awake then. On nights the Mac is fully asleep or
> closed, that day is missed. Keep the Mac awake on the Wednesdays before Sep 9 (the flight weekday)
> for the data that matters most.

## Files

- `scripts/scrape.py`: the scraper (parse + IST timestamps + `ttd_*` schema + `rebuild_index`).
  Also used as a library by `merge_local.py`. It carries a self-gating morning window and a
  sold-out skip. (Runs locally; the cloud path is dead per the firewall block above.)
- `scripts/merge_local.py`: merge the local scraper's CSVs into this repo, deduped on `scraped_at`.
- `scripts/sync_local.sh`: pull, merge, rebuild index, commit, push. Safe to run on a timer.
- `index.html`: the GitHub Pages dashboard. Reads `data/index.json` + the daily CSVs, draws the
  depletion curves (tokens remaining vs. time-of-day IST), Wednesdays emphasized. No build step, no
  external libraries.
- `data/srivani_airport/YYYY-MM-DD.csv`: one file per IST day. `data/index.json`: generated manifest
  (one summary row per day) the dashboard reads first, since GitHub Pages has no directory listing.
- `data/flights.json`: approximate scheduled TIR morning arrival times. Used twice: the dashboard
  overlays them as landing markers, and the scraper starts polling `start_buffer_min` before the
  earliest arrival so it is already running when the first flight lands (then stops at `available=0`).
  These are scheduled, not live wheels-down times; the real "first flight landed" signal is the first
  drop in the token curve (200 -> 198), which the dashboard rings and reports as "first drop".

## Data schema (`data/srivani_airport/*.csv`)

| column | meaning |
|---|---|
| `scraped_at` | ISO 8601 **IST**, when the scraper fetched the page (**our** clock) |
| `quota` / `issued` / `available` | token counts off the page (`available = quota - issued`) |
| `ttd_reporting_datetime_raw` | TTD's own "Reporting Date & Time" label, verbatim |
| `ttd_reporting_date` / `ttd_reporting_weekday` / `ttd_reporting_time` | parsed from that label. TTD's operational time, **not** a scrape clock |

## Notes

- Unofficial personal project. The counts are already public on TTD's own live-TV page. Always
  confirm with TTD before travel.
- Polite cadence, no login, plain `GET`. The scraper self-throttles once a day sells out.
