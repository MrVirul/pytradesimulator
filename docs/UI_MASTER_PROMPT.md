# Master UI/UX Design and Frontend Architecture Prompt

Standalone instructions for the next implementation agent. Source of truth for screens, tokens, and data mappings. Do not invent endpoints or fields.

## Skill reconciliation

`npx skills add nextlevelbuilder/ui-ux-pro-max-skill` installed seven skills under `.agents/skills/` and `.claude/skills/` (local only; both directories stay out of git). The skill this console follows is `ui-ux-pro-max`. Ignore `banner-design`, `brand`, `design`, `design-system`, `slides`, and `ui-styling`.

`ui-ux-pro-max` says its search results never override repository rules. Where it conflicts with this prompt, this prompt wins:

- Do not detect a stack from `package.json`. There is no React, Next.js, Tailwind, or shadcn app. Do not pass `--stack` for those, and do not add Tailwind, GSAP, Google Fonts, a CDN, or a persisted `design-system/` directory.
- Do not query or apply Glassmorphism, Liquid Glass, Aurora, Neumorphism, or any style that uses `backdrop-filter`, blur, gradients, glow, or radius above 2px. The catalog rows closest to this product are Data-Dense Dashboard and Real-Time Monitoring. Ignore their chart libraries (recharts, chart.js, d3), pulse, and glow.
- Touch targets in the skill are 44px. This is a desktop operator console. The minimum here is 24px. Do not grow ladder or table rows to 44px.
- The skill wants a 16px body and forbids text under 12px. This console uses 13px UI text and an 11px floor. Keep 13px.
- Motion is a 150ms background flash only. No GSAP, no scroll choreography, no width or height animation.
- Colour is never the only signal. That part of the skill agrees with this prompt. Keep the status word on every chip.

ROLE
You are implementing the next UI phase of the pytradesim secure layer: a FastAPI + Jinja2 + HTMX operator console for a FIX 4.2 exchange simulator. Plan first, then implement milestone by milestone.

HARD CONSTRAINTS (do not violate)
- Stack stays FastAPI + Jinja2 + HTMX 2.0.4 (vendored at secure_api/app/web/static/htmx.min.js). No React, no Next.js, no build step, no CDN assets, no new JS dependencies unless vendored under secure_api/app/web/static/.
- No localStorage, sessionStorage, or IndexedDB anywhere. Tokens stay server-side in browser_sessions. Tests assert the login and home pages contain no localStorage.
- Every new or changed /ui route calls _guard(request, permission) or _open_session(request, permission) with the same permission as its /api/v1 twin. auth/policies.py is the only role-to-permission map. Every state-changing POST checks csrf_token with secrets.compare_digest.
- Do not edit frozen legacy code: pytradesim/server.py, market_data.py, market_client.py, client.py, pytradesim/modules/*, docker/, DockerFile, tests/.
- There is no order-entry, position, portfolio, or P&L API. Do not design or stub an order ticket, blotter, or buy/sell hotkeys. The only action that sends orders is a named scenario run (POST /ui/scenarios with {csrf_token, scenario}), admin-only, budget 3 per 60s.
- Never describe a stale row as live. exchange_event_time is always null. Age is measured from received_at, which the subscriber sets.
- Banned visuals: backdrop-filter or blur, glassmorphism, gradients, neon colours, glow shadows, rounded marketing cards (border-radius above 2px on panels), low-contrast grey text, emoji, decorative illustrations.
- Follow .claude/skills/progress-tracking. Milestone 9 is already listed in docs/PROGRESS.md as todo. Do not add it again. Set the task you are doing to in-progress before coding, branch m9/<task-id>-<slug>, commit subjects start with [M9.x], and add a dated log line with how it was checked.
- Keep pytest secure_api/tests green. Tests assert visible strings (examples: "Status stale", "Spread", "10.0", "no event time", "Paused", "Resume", the absence of "every 3s" when paused, "Limit reached, retrying in 9 s", 'hx-trigger="every 9s"', "Missing permission", '<!DOCTYPE html>'). Keep them. If a markup change truly requires a different assertion, update that test in the same commit and list it in the PROGRESS log.

DATA YOU MAY USE (exact fields; nothing else exists)
- Book (services.market_data.get_symbol): symbol, status (live|stale|uninitialized), received_at (ISO), ingest_sequence (int), exchange_event_time (null), bids [{price, quantity}], asks [{price, quantity}]. Levels are not sorted by the service.
- Symbol list (list_symbols): symbol, status, received_at, ingest_sequence, exchange_event_time.
- Trades (recent_trades(symbol, limit 1..100)): ingestion_id, price, quantity, received_at, ingest_sequence. No aggressor side, no exchange trade id.
- Feed (feed_health): logged_on (bool), last_message_at (always null today; see M9.3).
- Limits (rate_limit.snapshot(client_id, roles)): [{category, used, allowed, resets_at|null}]. Categories: market_data 60/60s, alerts 20/60s, audit 10/60s (shared by audit:read and operations:read), scenario 3/60s, admin 20/60s.
- Alerts (list_alerts, max 100): id, rule_name, symbol|null, severity (always "warning" today), observed_value, threshold, created_at, detail. get_alert adds ingest_sequence. alert_context returns {book (only if the snapshot at that sequence is still current) | null, current_sequence, trades:[{ingestion_id, price, quantity, received_at}]}.
- Rules (list_rules): name, enabled, threshold, window_seconds. Names: price_movement, spread_widening, volume, api_abuse, access_denied.
- Filter choices (filter_choices): symbols, rules, severities. Timeline (timeline, max 20): at, kind (alert|scenario), label, ref (alert id or run id).
- Audit (list_events, max 50): request_id, client_id, action, resource, decision (allowed|denied), reason, status_code, latency_ms, recorded_at.
- Metrics (security_metrics(15|60)): minutes, requests, allowed, denied, status_401, status_403, status_429, p50, p95, p99 (ms, nullable), per_minute [{minute, count, width 0..100}], clients (top 5) [{client_id, count}], policies [{subject, category, allowed, used, window_seconds}].
- Scenarios (scenario_choices): name, about, expects, sends_order, orders (strings like "buy 10 @ 150"), runnable. scenario_policy: requests_allowed, window_seconds. recent_runs(12): id, scenario, status, request_id, created_at. get_run: id, scenario, status (pending|running|passed|failed), symbol, request_id.
- Session shell (routes.shell): signed_in, client_id, roles, csrf_token, minutes_left, nav, path. Session row has expires_at.
- Fixed scenario orders: price_movement on PRICE (buy 10 @ 150, sell 10 @ 150); spread_widening on SPREAD (buy 10 @ 50, sell 10 @ 60); volume on VOLUME (sell/buy 400 @ 101, 350 @ 102, 300 @ 103). unauthorized_access and rate_limit_abuse send no order.
- Exchange facts to surface in the UI: at most one flush per symbol per second, only on change; subscribing returns no book until the next change; identical prints in one flush are collapsed; empty sides are omitted.

=====================================================================
SECTION 1. DESIGN SYSTEM AND TOKENS
=====================================================================
Put every token as a CSS custom property in secure_api/app/web/static/app.css. Delete the unlinked market.css after moving anything still needed. Dark is the default. Light applies under @media (prefers-color-scheme: light), with no JS toggle and no storage.

1.1 Surfaces (dark / light)
- --bg-app        #0B0E11 / #EEF0F3   page background
- --bg-panel      #12161B / #FFFFFF   panels, tables
- --bg-panel-head #161B21 / #F6F7F9   panel title bars, sticky table heads
- --bg-elevated   #1A2027 / #FFFFFF   <dialog>, shortcut sheet (with 1px --line-strong border; one shadow 0 8px 24px rgba(0,0,0,.45) in dark only)
- --bg-row-hover  #1C232B / #F0F3F7
- --bg-row-active #22303F / #DCE8F7   selected symbol, focused row
- --line          #262E37 / #D3D9E0   1px structural borders between every panel
- --line-strong   #36414D / #AEB8C3   table head bottom border, dialog border

1.2 Text
- --text-1 #E8ECF1 / #0B0E11   data and primary labels
- --text-2 #B7C1CC / #2B3540   secondary labels, zero values
- --text-3 #9DA9B5 / #4A5562   smallest allowed label tone; never for data
Contrast target: at least 7:1 for any number, price, quantity, or timestamp on --bg-panel and --bg-row-active, and at least 4.5:1 for other UI text. Check every pair with a contrast checker, adjust lightness only, and record the measured ratios in the M9.1 log line.

1.3 Semantic financial colours (text / depth-bar fill / 150ms flash fill)
- Bid, bull, uptick:     --bid  #2EBD85 / --bid-bar #0F2E23 / --bid-flash #145C40   (light: #055C3B / #D6EFE4 / #A8DDC4)
- Ask, bear, downtick:   --ask  #FF6B7D / --ask-bar #3A1A20 / --ask-flash #6E2230   (light: #A30F26 / #F8DDE1 / #F0B3BC)
- Neutral, spread, mid, unchanged: --neutral #C9D1D9 (light #2B3540)
- Pending, in flight, running: --pending #5AA9FF (light #0B4FA8)
- Warning, stale, 429, alert severity warning: --warn #F0B90B, bg #3A2E07 (light #7A5300, bg #FFF1C2)
- Denied, 401, 403, failed: --deny #FF8A4C, bg #3A2111 (light #9A3412, bg #FDE3D3)
- OK, live, allowed, passed: --ok #4CC38A (light #0B6B3F)
- Focus ring: --focus #5AA9FF (light #0B4FA8), 2px solid, offset 1px
Colour is never the only signal. Every status chip carries its word. Price ticks also get a ▲ or ▼ glyph when prefers-reduced-motion is set.

1.4 Typography
- UI font: "Segoe UI", system-ui, -apple-system, Roboto, sans-serif.
- Data font: "Cascadia Mono", "JetBrains Mono", Consolas, ui-monospace, monospace, with font-variant-numeric: tabular-nums slashed-zero.
- Sizes: page title 16px/600; panel title 12px/600 uppercase, letter-spacing .04em, --text-2; table and UI text 13px; data cells 13px mono; minimum 11px.
- Apply the data font to every price, quantity, spread, percentage, count, latency, sequence, id, request id, and timestamp. Right-align numbers and left-align text. Size numeric columns in ch units so polling never changes their width.
- Formatting, done on the server only through Jinja filters registered once on templates.env in routes.py:
  price(v): 2 decimals, thousands separator, "—" for None.
  qty(v): integer with thousands separator if v.is_integer(), else 2 decimals.
  signed(v): leading + or −, 2 decimals.
  ts(v): HH:MM:SS.mmm in UTC for cells; full ISO in the title attribute and in <time datetime>.
  tsd(v): MM-DD HH:MM:SS UTC, for tables that can span days (alerts, audit, runs).
  age(seconds): "Ns" under 60, "M:SS" under 3600, "H:MM:SS" above.
  Column headers say "UTC".

1.5 Spacing and shape
- Scale: --s1 4px, --s2 8px, --s3 12px, --s4 16px, --s6 24px. Table cell padding 4px 8px. Row height 24px. Panel padding 8px. Gap between panels 1px (the border).
- Radius: 0 on panels and tables, 2px on inputs, buttons, and chips.
- Layout: remove main {max-width:1100px}. Pages use the full viewport width. Add <meta name="viewport" content="width=device-width, initial-scale=1">.
- Motion: only background-color and opacity transitions. No layout animation. Everything is disabled under prefers-reduced-motion.

=====================================================================
SECTION 2. SCREEN-BY-SCREEN BLUEPRINT
=====================================================================
Every page has: purpose (the decision made in under 2 seconds), layout, API-to-UI mapping, and real-time behaviour.

2.0 GLOBAL SHELL (base.html)
Purpose: who am I, is the feed up, is my polling healthy, how long until my session ends.
Layout: sticky top bar, 36px tall: brand | nav (shell.nav, aria-current on the active page) | link status cell | identity cell | Sign out. Below it, a 0-or-28px message strip (the .banner class, defined in app.css) for flash and error messages. Then <main> with the full-height page grid (height: calc(100dvh - 36px)); each panel scrolls on its own.
Mapping:
- Identity cell: client_id (mono) · roles joined · session countdown. Render data-expires="{{expires_at ISO}}" and data-server-now. console.js counts down every second and turns --warn at 2 minutes or less. At 0 the next fragment request receives HX-Redirect, which already exists.
- Link status cell has two parts:
  FIX: "FIX on" (--ok) or "FIX off" (--deny), from feed_health().logged_on. Render it at page load, and refresh it out-of-band from the book fragment (hx-swap-oob on #feed-state) so it costs no extra request.
  POLL: driven by console.js from htmx events on any element with data-poll. States: "OK HH:MM:SS" (last 2xx or 204), "RETRY Ns" (429; N from the Retry-After header, counting down), "DENIED" (403), "DOWN" (5xx or htmx:sendError), "PAUSED" (market paused). aria-live="polite".
- Sign out: the existing POST /ui/logout form with csrf_token.
Real-time: this fixes silent failures without changing server status codes. Keep htmx's default no-swap on 4xx/5xx so the last good data stays on screen, and surface the failure in the POLL cell. Add data-backoff to <body> while a 429 is active. Every poller's trigger includes [document.visibilityState === 'visible' && !document.body.dataset.backoff], so the page stops calling until Retry-After passes. The existing 429 fragment body stays as it is (tests).

2.1 LOGIN (/ui/login, login.html)
Purpose: pick a demo identity.
Layout: one centred 640px panel. Title "Sign in". A message strip for notice=signed_out and error=expired|failed|unknown_user (unknown_user is redirected to today but never rendered; add it).
Mapping: a table with one row per demo_users() entry: username (mono) | role | opens | password (only when show_passwords) | "Sign in as {username}" link to /ui/login/start?user={username}. The password cell is mono with a copy button, which uses navigator.clipboard and stores nothing.
Real-time: none. Enter on a focused row follows its sign-in link.

2.2 OVERVIEW (/ui, home.html)
Purpose: which books are live, is the feed up, how much of my rate budget is left.
Layout: grid-template-columns: 1fr 320px. Left: the Books table panel. Right rail, stacked: Feed panel, Rate limits panel, Identity panel (a <details> element, closed by default).
Mapping:
- Books table, one row per list_symbols() entry: Symbol (link to /ui/market?symbol=) | Status chip | Bid price(max bid) | Ask price(min ask) | Spread price(ask−bid, or "—" if either side is missing) | Last change age(received_at) | Seq ingest_sequence. Add ingest_sequence to the tile dict in routes._overview.
- Feed panel: FIX state, and Last message ts(last_message_at) or "not recorded" until M9.3 adds the write.
- Rate limits panel: one row per snapshot entry: category | a used/allowed meter (1px-bordered track; fill --ok under 70%, --warn from 70%, --deny at 100%) | "resets HH:MM:SS" from resets_at.
- Identity panel: client_id, roles, the permissions list.
Real-time: NEW fragment route GET /ui/overview/books, guarded by _market_guard and rendering only the Books table, polled every 5s (12 of the 60 per minute market_data budget). Replace the N+1 queries in _overview with one new service function market_data.list_books() that selects symbol, status, received_at, ingest_sequence, bids, asks in a single query. Changed cells flash (Section 3.4).

2.3 MARKET (/ui/market?symbol=, market.html + book.html)
Purpose: where is the inside market, how wide is it, did it just trade, is this book current.
Layout at 1280px and wider: grid-template-columns: 240px minmax(420px, 1fr) 380px. Watchlist | Ladder | Tape. Above them, a sticky 40px symbol header strip that spans all three columns. From 1024 to 1279px: 240px 1fr, with Tape below Ladder. Below 1024px: the watchlist becomes the existing <select> form and everything stacks in one column.
Fragment boundary: one poll returns one fragment, #market-book. It contains the header strip, the ladder, and the tape, plus out-of-band updates for #feed-state and for this symbol's watchlist row. One request per tick means one rate token per tick.
Mapping:
- Header strip: symbol (16px mono) | Status chip ("Status {status}" text kept for tests) | Bid price(best_bid) in --bid | Ask price(best_ask) in --ask | Spread price(spread) in --neutral | Last price(last_trade.price) × qty(last_trade.quantity) | Last change age(age_seconds), ticking on the client | Seq ingest_sequence | FIX on/off | Pause/Resume and Refresh buttons (existing hx-get links kept as buttons).
- Watchlist: list_symbols() rows: symbol | status chip | age(received_at). The current symbol uses --bg-row-active with a 2px left border in --pending. Arrow keys move through it and Enter opens a symbol. Unknown but valid query symbols render as uninitialized (existing behaviour).
- Ladder: sort in routes._book_context, bids by price descending and asks by price descending, so asks sit on top. Rows, top to bottom: asks (highest to lowest), then the spread row "Spread {price(spread)}", then bids (highest to lowest). Columns: Cum qty | Qty | Price | Depth bar. Cumulative quantity is computed outward from the inside on each side. Bar width = quantity / max(quantity across both sides) × 100, so both sides use one scale. Bars sit next to the price column, filled --bid-bar or --ask-bar. Price text is --bid or --ask. An empty side shows one row "No bids" or "No asks" in --text-2.
- Tape: recent_trades(symbol, 20). Columns: Time ts | Price | Qty | Seq. ingestion_id goes in the row's title. Colour each price by its tick against the next older trade: higher --bid ▲, lower --ask ▼, equal --neutral. Do not label trades as buys or sells; aggressor side is not in the data. Footer: "Identical prints in one exchange flush are collapsed."
- Keep this footnote text: "The exchange sends no event time. Age is measured from the time this service stored the book."
- Uninitialized: the ladder shows "No snapshot yet. The exchange sends the first one after the next book change."
- Stale: the header strip gets a 2px --warn top border, the chip reads "Status stale", and ladder prices use --text-2 instead of bid/ask colours. Stale must never look live.
Real-time:
- Poll every 3s, using the trigger rule from 2.0. Add hx-vals with since=<ingest_sequence>, st=<status>, lo=<0|1>. When get_symbol returns the same ingest_sequence and status and feed_health has the same logged_on, return 204. htmx does not swap a 204, so nothing re-renders. The rate token and audit row are still spent; that is intended.
- Age ticks on the client: <time data-age-from="{received_at}"> is updated every 1s by console.js using (Date.now() + serverOffset) − Date.parse(received_at). serverOffset comes from data-server-now on each fragment. The server still renders the initial value, so the page reads correctly without JS.
- Price flash: Section 3.4. New trade rows (ingestion_id greater than the previous maximum) get the row-new flash.
- Paused: an amber "PAUSED" chip shows in the header and in the POLL cell, the age keeps ticking, and "every 3s" is absent from the markup (test).

2.4 SURVEILLANCE (/ui/alerts, alerts.html + alert_rows.html)
Purpose: which rule fired, on what, by how much, and is it new.
Layout: sticky 40px filter bar (the existing #alert-filters form). Below it, a column flex: the Alerts table panel (flex 1, sticky thead, scrolls internally), then a 280px bottom split, 1fr 1fr: Rules | Timeline. Each half collapses with a <details> summary bar.
Mapping:
- Filters: symbol select (choices.symbols), rule select (choices.rules), severity select (choices.severities), from/to inputs type=datetime-local (alerts._parse_time accepts that format; validate on the server as today).
- Alerts table: Time tsd(created_at) | Rule (link to /ui/alerts/{id}) | Symbol (or "—") | Severity chip (warning uses --warn) | Observed | Threshold | Excess signed(observed − threshold), computed in the route | Detail (truncated with ellipsis, full text in title). Footer: "Latest 100 matching."
- Rules: rows of name | window "over Ns" when window_seconds is set | threshold | enabled. If can_write_rules: an input type=number step=any min=0.0001 for the threshold, an enabled checkbox, and Save (the existing POST /ui/rules with csrf_token; it stays a full form post with a 303). If not: plain text values, not disabled inputs.
- Timeline: tsd(at) | kind chip | label. Link alert rows to /ui/alerts/{ref} and scenario rows to /ui/scenarios?run={ref}.
Real-time: #alert-rows polls GET /ui/alerts/rows every 10s with hx-include="#alert-filters" and the trigger rule from 2.0 (6 of the 20 per minute alerts budget). Before each swap console.js records the highest data-id. After the swap, rows with a higher id flash once, and the caption shows "{n} new". Filter changes keep hx-trigger="change, submit".

2.5 ALERT DETAIL (/ui/alerts/{id}, alert_detail.html)
Purpose: was this crossing real, and what did the book look like at that sequence.
Layout: grid-template-columns: 360px 1fr. Left: Facts panel. Right: Evidence panel.
Mapping:
- Facts: rule_name | symbol | severity chip | observed_value | threshold | excess signed(observed − threshold) | ratio (observed / threshold, 2 decimals, "×") | created_at as full ISO | ingest_sequence | detail. Threshold bar: a track from 0 to max(observed, threshold) × 1.1, a 1px --text-1 tick at the threshold, and a --warn marker at the observed value.
- Evidence: if stored.book exists, render the same ladder macro as Market (not the Python list repr). If not: "That book is no longer the stored snapshot. The current sequence is {current_sequence}." plus a link to /ui/market?symbol={symbol}. Then "Trades at sequence {ingest_sequence}": a table of ts(received_at) | price | qty | ingestion_id.
- Audit-based rules (api_abuse, access_denied; symbol and ingest_sequence are null): Evidence reads "Rule computed from audit events; no book." with a link to /ui/audit?status_code=429 for api_abuse or /ui/audit?status_code=403 for access_denied. Do not parse the client id out of detail.
- Back link to /ui/alerts.
Real-time: none; this is a static record.

2.6 SECURITY (/ui/security?minutes=15|60, security.html)
Purpose: is anyone being denied or throttled right now, and is latency normal.
Layout: a 56px KPI strip of 9 equal cells. Then a segmented control: 15m | 60m (links; any value other than 60 is treated as 15). Then grid 1fr 1fr: left the Requests/min panel; right, stacked, Top clients and Policies. Below, full width: the Audit search filters and rows.
Mapping:
- KPI cells: Requests | Allowed | Denied | 401 | 403 | 429 | p50 ms | p95 ms | p99 ms. 401/403 are --deny when above 0; 429 is --warn when above 0; zeros are --text-2; null percentiles show "—".
- Requests/min: one row per per_minute entry: minute as HH:MM | CSS bar (width from width) | count.
- Top clients: client_id | count | share bar (count / requests).
- Policies: subject | category | used/allowed meter | window_seconds "s".
- Audit search: the same filter and row partials as 2.7.
- Note under the KPI strip: "Counts include console polling; each book refresh is one audited request."
Real-time: no auto-polling. The audit budget is 10 per minute and is shared by page loads and filter changes. Show a Refresh button and "as of HH:MM:SS".

2.7 AUDIT (/ui/audit, audit.html + audit_filters.html + audit_rows.html)
Purpose: find this request id and see why it was allowed or denied.
Layout: sticky filter bar, then a full-height table panel with a sticky thead.
Mapping:
- Filters: request_id (type=search, maxlength 80) | client_id (maxlength 80) | action (maxlength 64) | decision select (allowed, denied) | status select (401, 403, 429) | from/to type=datetime-local.
- Table: Time tsd(recorded_at) | Request id (mono, link to ?request_id=, plus a copy button) | Client | Action | Resource (new column) | Decision chip (allowed --ok, denied --deny) | Status chip (2xx --ok, 401/403 --deny, 429 --warn, 5xx --deny bold) | Reason | Latency ms (new column, right-aligned). Footer: "Latest 50 matching."
Real-time: filter-driven only (the existing change/submit trigger). No polling.

2.8 SCENARIO LAB (/ui/scenarios?run=, scenarios.html + scenario_run.html)
Purpose: which scenario to trigger, what it will send, and whether it produced the expected evidence.
Layout: a 40px header strip: "Budget {remaining} of {policy.requests_allowed} per {policy.window_seconds}s" as a meter. Then grid 1fr 380px. Left: the Scenarios table. Right, stacked: Active run panel, Run history panel.
Mapping:
- Scenarios table: Name (mono) | What it does (about) | Orders (mono lines from orders, or "No order") | Expects | Last status chip (last_status, or "not run") | Run button.
- Run: the button opens a native <dialog> on --bg-elevated with the scenario name, symbol, and fixed order lines, and Confirm and Cancel buttons. Confirm submits the existing form (csrf_token, scenario) to POST /ui/scenarios. While it submits, disable the button and show "Submitting…". When remaining is 0, disable the buttons and show the reset time in the title.
- Active run (scenario_run.html): "Run {id} {scenario}" | status chip (pending: --pending outline; running: --pending fill plus a 2px indeterminate bar, static under reduced motion; passed: --ok; failed: --deny) | "Alerts for {symbol}" link when passed with a symbol | "Request {request_id}" link to the audit filter | "The scenario did not complete." when failed.
- Run history: tsd(created_at) | scenario | status chip | request_id link.
Real-time: the active run polls GET /ui/scenarios/runs/{id} every 3s while pending or running (existing; no rate cost). aria-live="polite" on the active run panel. When the status changes, the chip flashes once.

2.9 ERRORS (error.html, error_fragment.html, the callback 403)
- error.html: status code as 16px mono, message, "Request {request_id}" (from request.state.request_id) linking to /ui/audit?request_id= when the user has audit:read, and a Back link. Keep "Missing permission" and the <!DOCTYPE html> start (tests).
- routes.callback: replace the inline "This account cannot open the app" HTML with error.html at status 403.
- error_fragment.html stays a valid fragment; the POLL cell is what surfaces the failure (2.0).

=====================================================================
SECTION 3. CLEAN CODE AND FRONTEND PRACTICES (HTMX TRANSLATION)
=====================================================================
3.1 Composition
- templates/macros/ui.html holds the pure presentational macros: panel(title, id), kpi(label, value, tone), chip(word, tone), num(value, kind, key), ts_cell(value), meter(used, allowed), ladder(bids, asks, max_qty), empty_row(colspan, text).
- Routes build plain dict contexts in helper functions (_book_context, _overview, _alert_filters, _audit_context, _scenario_page_context). Templates only format and loop. No queries, policy checks, or arithmetic beyond formatting in templates. Excess, ratio, cumulative quantity, tick direction, sorting, and the shared maximum quantity are computed in Python.
- Data access lives only in app/services. New: market_data.list_books(). Do not import QuickFIX into the API.
- Static assets: app.css (tokens, layout, components) and console.js (vanilla, about 200 lines, no globals except window.pts, no storage APIs). No inline <script>.

3.2 Polling budget (per client_id, per 60s; the budget is shared across tabs)
- Market book: 3s, which is 20 of 60 market_data. Overview books: 5s, 12 of 60. Never poll market data faster than 2s; the exchange flushes at most about once a second.
- Alerts rows: 10s, 6 of 20 alerts. Audit and security: no polling (budget 10). Scenario run: 3s while active (not rate-limited).
- Every poller: data-poll attribute, visibility guard, backoff guard.
- Two market tabs together must stay under 60 per minute. Document the arithmetic in the PROGRESS log.

3.3 Render cost
- Return 204 on an unchanged ingest_sequence (2.3), so no swap and no DOM churn happen.
- One fragment per tick. Use hx-swap-oob for the small outside cells (#feed-state, the watchlist row) instead of a second request.
- Never put inputs, selects, or open dialogs inside a polled region, so polling can't take focus away.
- console.js keeps scrollTop for [data-keep-scroll] elements across htmx:beforeSwap and htmx:afterSwap.
- Tables are capped at 100 alerts, 50 audit rows, 20 trades, and 12 runs. Do not add virtualization. Use table-layout: fixed and contain: content on panels.
- The API has one Postgres connection behind an RLock (app/db.py). Add no query-per-row patterns. One query per fragment per tick at most.

3.4 Tick feedback (console.js)
- Every changing value is rendered as <span data-k="{stable key}" data-v="{raw number}">. Keys: best-bid, best-ask, spread, last-px, ladder:{side}:{price}:qty, ladder:{side}:{price}:cum, ovw:{symbol}:bid, ovw:{symbol}:ask.
- On htmx:beforeSwap, snapshot a map of key to value for the target. On htmx:afterSettle, compare. For prices: higher adds .tick-up (background --bid-flash), lower adds .tick-down (--ask-flash). For quantities: any change adds .tick-chg (--bg-row-active), never green or red, so a quantity change doesn't imply direction. Hold 150ms, fade over 300ms (background-color only), then remove the class.
- New rows (a data-id above the previous maximum) get .row-new with the same timing.
- prefers-reduced-motion: no animation; append ▲/▼ to price cells for one poll cycle.
- A key that is new or removed (a level appears or disappears) gets no flash; its presence is the signal.

3.5 Keyboard (console.js, handled only when focus is not in input, select, or textarea and no Ctrl/Alt/Meta is held; every shortcut also has a visible control and aria-keyshortcuts)
- ? opens the shortcut sheet (<dialog>). Esc closes any open dialog, cancels a scenario confirmation, or blurs and clears the focused filter input.
- 1–5 go to the nav items in shell order (only those the role can see).
- / focuses the page's primary input: the symbol select on Market, the first filter on Surveillance and Audit.
- Market: ArrowUp/ArrowDown move through the watchlist, Enter opens the focused symbol, [ and ] go to the previous/next symbol, p pauses or resumes, r refreshes now.
- Tables (alerts, audit, runs, overview books): ArrowUp/ArrowDown move row focus (roving tabindex), Enter opens the row link, c copies the request id on audit rows.
- Scenario lab: Enter on a focused scenario row opens its confirm dialog. Enter confirms. Esc cancels.
- No order shortcuts exist.

3.6 Accessibility
- A skip link to <main>. Landmarks: header, nav, main. <th scope="col">, and captions on every table.
- Visible 2px --focus ring on every interactive element. Targets at least 24×24px.
- aria-live="polite" only on the POLL cell, the session countdown at 2 minutes or less, and the active run panel. Never on the ladder or tape.
- Status always as text plus colour. Run axe or Lighthouse accessibility on each page and record the result.

=====================================================================
SECTION 4. DELIVERY PLAN
=====================================================================
Milestone 9 is already listed in docs/PROGRESS.md. Implement these tasks in order. Do not add them again. Exit conditions:
- M9.1 Tokens, base shell, filters, console.js core (POLL state, backoff, age ticker, scroll keep). Exit: every page uses the tokens; a forced 429 shows "RETRY Ns" and the last book stays visible; contrast ratios recorded.
- M9.2 Market console (3-pane layout, sorted ladder with shared scale, tape ticks, 204 on unchanged sequence, OOB feed state, price flashes). Exit: running price_movement shows PRICE flash and a new tape row without a full re-render; an unchanged poll returns 204.
- M9.3 Overview (books table, list_books single query, /ui/overview/books 5s fragment, limit meters). Optional and separately committed: write feed_status.last_message_at = received_at inside Store._record in secure_api/adapter/persistence.py (not frozen), so "Last message" is true. Otherwise label it "not recorded".
- M9.4 Surveillance and alert detail (excess column, 10s rows poll with new-row flash, rules as text for analysts, linked timeline, ladder macro on detail, audit-rule evidence links).
- M9.5 Security and audit (KPI strip, resource and latency columns, status chips, polling note, no auto-poll).
- M9.6 Scenario lab (table, confirm dialog, budget meter, run panel states).
- M9.7 Login, error page, callback 403 template, unknown_user message, viewport meta, delete market.css.
- M9.8 Keyboard and accessibility pass (3.5, 3.6).
- M9.9 Evidence: pytest secure_api/tests green; docker run --rm pytradesim test still 22 passed; docker compose up -d --build; sign in as market, analyst, and admin; record per role which nav items appear, a forced 429, a scenario run, and the 204 count. Note whether a graphical browser was driven.
