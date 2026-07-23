# Tirupati SRIVANI Airport Token Tracker

Tracks how fast the **200 daily SRIVANI airport-counter darshan tokens** at Tirupati (TIR)
deplete each morning, to inform the airport-counter vs. online-booking decision for a
Sep 9–10, 2026 Tirupati trip. Live page:

**→ https://vamsikrishnamvk.github.io/tirupati-darshan-tracker/**

## How it works

- **Scraper** (`scripts/scrape.py`) — fetches the TTD public live-status page
  ([`AirportLiveStatus.aspx`](https://webapps.tirumala.org/SrivaniTokenLiveTV/AirportLiveStatus.aspx)),
  parses `quota / issued / available` + TTD's published "Reporting Date & Time", and appends one
  row to `data/srivani_airport/YYYY-MM-DD.csv` (one file per **IST** day). All `scraped_at`
  timestamps are IST regardless of where the code runs.
- **Cloud capture** — `.github/workflows/scrape.yml` runs the scraper every ~5 min during the IST
  morning window (via `cron` in UTC), commits new rows back to the repo. This is the **always-on**
  source: it runs even when my Mac is asleep (the India morning window is US late-night).
  > GitHub Actions `cron` is best-effort — runs can be delayed a few minutes or skipped under load,
  > and 5 min is the floor. That's why there's also a local job for finer detail.
- **Local capture (hybrid)** — a macOS `launchd` job scrapes every **2 min** when the Mac is awake,
  for a higher-resolution curve. Its rows are merged into this repo (deduped on `scraped_at`) by
  `scripts/sync_local.sh`. See that script's header for usage.
- **Dashboard** (`index.html`, served by GitHub Pages) — reads `data/index.json` + the daily CSVs
  and draws the depletion curves (tokens remaining vs. time-of-day IST), with Wednesdays — the
  Sep 9 flight weekday — emphasized. No build step, no external libraries.

## Data schema (`data/srivani_airport/*.csv`)

| column | meaning |
|---|---|
| `scraped_at` | ISO 8601 **IST** — when the scraper fetched the page (**our** clock) |
| `quota` / `issued` / `available` | token counts off the page (`available = quota − issued`) |
| `ttd_reporting_datetime_raw` | TTD's own "Reporting Date & Time" label, verbatim |
| `ttd_reporting_date` / `ttd_reporting_weekday` / `ttd_reporting_time` | parsed from that label — TTD's operational time, **not** a scrape clock |

`data/index.json` is a generated manifest (one summary row per day) the dashboard reads first so it
knows which day-files exist (GitHub Pages has no directory listing).

## Notes

- Unofficial personal project. The counts are already public on TTD's own live-TV page; always
  confirm with TTD before travel.
- Polite cadence, no login, plain `GET`. The scraper self-throttles once a day sells out.
