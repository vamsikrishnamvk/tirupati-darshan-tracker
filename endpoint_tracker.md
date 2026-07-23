# Endpoint Tracker

One row per endpoint found while running `DISCOVERY_PLAN.md`. Add rows as you go tomorrow - doesn't
need to be tidy while you're actively discovering, just capture enough to reconstruct/replay each
call later (the "Copy as cURL" from DevTools is the fastest way to do that - paste the cURL into
the Notes/cURL column or a linked file).

| # | Source page | Full URL | Method | Parameters | Data returned | Response format | Refresh interval | Needs cookies/session? | Notes / cURL |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Airport token page | `https://webapps.tirumala.org/SrivaniTokenLiveTV/AirportLiveStatus.aspx` | GET | none | Quota/Issued/Available/Reporting Date&Time | HTML (whole page, server-rendered) | 15s client-side full reload | No | Already confirmed via raw `curl` (2026-07-19) - no separate XHR found in that pass; DISCOVERY_PLAN Step 1 re-checks this via actual browser network traffic to be sure. This is the baseline/known-good row - format for new entries below. |
| 2 | | | | | | | | | |
| 3 | | | | | | | | | |
| 4 | | | | | | | | | |
| 5 | | | | | | | | | |

## Column guide
- **Method**: GET or POST (Headers tab in DevTools)
- **Parameters**: querystring or POST body fields - note which ones look like they'd need to be
  supplied by the scraper (date, counter ID, etc.) vs. fixed
- **Response format**: JSON / HTML fragment / whole HTML page - determines whether you'll parse
  with `BeautifulSoup`, `json.loads`, or something else
- **Refresh interval**: only fill in if you watched it repeat on a timer in Step 1
- **Needs cookies/session?**: check the Headers tab for a `Cookie` request header. If yes, flag it
  and don't build a scraper against it without discussing first - matches the "no automating
  login/OTP flows" line already drawn in the main README for the accommodation/current-booking SPAs.

## After filling this in
Bring it back to `README.md`'s "Sources" section - each confirmed, cookie-free, GET-able endpoint
becomes a new numbered source there (following the pattern of source #1/#2 already documented),
with its own `data/raw/<source_name>/` output folder and a poll-interval recommendation based on
what was observed here.
