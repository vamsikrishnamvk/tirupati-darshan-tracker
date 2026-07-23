# Endpoint Discovery Plan (DevTools) - to run tomorrow

Goal: find every live-status / current-booking endpoint in the same family as the SRIVANI airport
token page - both sibling `.aspx` pages and the hidden backend calls that feed them (those are the
actual scrape targets, if they exist separately from the rendered HTML). Uses Chrome DevTools to
*discover* real endpoints instead of guessing URLs, which sidesteps the guessing-hidden-routes
concern raised when `AccommodationLiveTV`/`DarshanLiveTV`/`RoomLiveTV` were checked (see main
README's "Sources considered and rejected") - watching your own browser's normal traffic is just
using the site, not probing it.

**Note on the "robots disallows automated fetching" claim below**: my own `curl` testing against
`webapps.tirumala.org` (2026-07-19) didn't hit any blocking - got clean 200/403/404/500 responses
across several paths tried, including on the actual SRIVANI page. `robots.txt` itself returned 404
(no file present at all - not a disallow rule, just nothing declared either way). So take "I hit
that wall myself" with a grain of salt; it doesn't match what I directly observed. The underlying
advice (go gently, don't hammer a temple public-service site) stands regardless of whether a formal
robots rule exists.

## Setup (2 min)
1. Open Chrome. Press **F12** (or right-click -> Inspect) to open DevTools.
2. Click the **Network** tab.
3. Check **Preserve log** (so navigations don't wipe the list) and **Disable cache**.
4. Confirm the red record dot is on. Network only logs while DevTools is open, so keep it open the
   whole time.

## Step 1 - Map the page you already have
1. With Network recording, load `https://webapps.tirumala.org/SrivaniTokenLiveTV/AirportLiveStatus.aspx`.
2. Click the **Fetch/XHR** filter button. This hides images/CSS/fonts and shows only the API-style
   calls JavaScript makes - the data feeds.
3. Look at each row's **Name**. Watch for:
   - A call that returns just the numbers/status (not the whole page) -> that's the real scrape
     target. Its **Response** tab will show clean data (JSON, or an ASP.NET fragment).
   - If the page auto-refreshes, the same call repeats on a timer -> confirms it's a polling
     endpoint and tells you the refresh interval.
4. For each promising row: open the **Headers** tab (note the full URL, method GET/POST, and any
   parameters) and the **Response** tab (confirm it contains the data). Right-click the row ->
   **Copy -> Copy as cURL** to save a working, replayable version of the request.

   Prior finding to sanity-check against: source research (2026-07-19) already concluded the
   Airport token page appears to be pure server-rendered HTML with **no separate XHR/API call** -
   the JS only does a full `window.location.reload()` every 15s, not a partial data fetch. If Step
   1 confirms that (empty/irrelevant Fetch/XHR tab), that's expected, not a failure - it just means
   this page's scrape target stays the whole `.aspx` HTML, as already planned. Worth confirming
   directly though, since this was inferred from viewing raw HTML rather than watching actual
   browser network traffic.

## Step 2 - Find sibling pages in the same app
The endpoints often share the `/SrivaniTokenLiveTV/` folder, so:
1. Press **Ctrl+F** inside the Network panel (opens a search box that searches *across all
   captured requests and responses*, not just names).
2. Search for strings likely to appear in links to other status pages: `LiveStatus`, `.aspx`,
   `SrivaniToken`, `Nivasam`, `Srinivasam`, `Bhudevi`, `Accommodation`, `SSD`, `Token`.
3. Any hit points to a request or response body that references another page/endpoint. Click
   through to the source.
4. Also check the **Initiator** column/tab on your data call - clicking it jumps to the exact
   JavaScript line that built the URL. Reading a few lines around it often reveals a base path or a
   list of endpoint names the script constructs, exposing siblings you'd never guess.

## Step 3 - Repeat on the known cousins
Do Steps 1-2 again, fresh recording each time, on:
- `https://webapps.tirumala.org/SrivaniTokenLiveTV/LiveStatus.aspx` (Srivani VIP token status -
  not yet checked; wasn't in the original URL-guessing pass)
- `https://tirumala.org/Home.aspx` - the homepage reportedly embeds a live SSD "Running Slot /
  Balance tickets" widget, so its Fetch/XHR calls should reveal the **SSD live-status backend
  endpoint** - potentially the single most useful one, since SSD (free Sarva Darshan token) status
  wasn't found as a clean public source in the earlier research pass.
- `https://tirumala.org/Current_Booking.aspx` (current accommodation booking) - note the earlier
  research pass found `tirumala.org/Advancebooking.aspx` (different path) rendering as an empty
  JS-shell via plain `curl`; worth checking whether `Current_Booking.aspx` is the same SPA or
  something more directly scrapable, and whether DevTools reveals the JSON it's actually fetching
  underneath (even a login-gated SPA sometimes has a public read-only status call before the
  login-required parts kick in - worth checking, though anything that clearly requires an
  authenticated session stays out of scope per the "no automating login/OTP" line already drawn in
  the main README).

Each page's XHR feeds are candidates. Collect them the same way as Step 1.

## Step 4 - Log what you find

Use `endpoint_tracker.md` in this same folder - one row per endpoint discovered.

## Two practical notes
- **Automated access**: see the robots.txt correction above. Regardless, go gently - respect rate
  limits, don't hammer it. It's a temple public-service site; light, infrequent polling is the
  courteous and safe approach, independent of what any robots file does or doesn't say.
- **If a page shows data but Fetch/XHR is empty**: the numbers are baked into the server-rendered
  `.aspx` HTML itself (no separate API). In that case the scrape target *is* the `.aspx` page, and
  you'd parse the HTML - check the **Doc** filter and look at that document's Response to confirm
  the values are in the raw HTML. (This is the expected outcome for the Airport token page itself,
  per the note under Step 1.)
