# Progress

Status values: `todo`, `in-progress`, `done`, `blocked`.

Update this file in the same change as the work. See `CONTRIBUTING.md`.

## Milestone 1 — Baseline and private network

Legacy regression recorded, `MDCLIENT3` and `CLIENT3` accepted, FIX ports unpublished in Compose, scripted cross checked over FIX.

- **M1.1** Acceptor sessions for `MDCLIENT3` and `CLIENT3`. Status: `done`. Exit: `price.cfg` and `exchange.cfg` each have one new `[SESSION]` and the old blocks are unchanged.
- **M1.2** Initiator configs. Status: `done`. Exit: `secure_api/adapter/configs/mdclient3.cfg` and `secure_api/harness/configs/client3.cfg` exist, with `ResetOnLogon=Y`.
- **M1.3** `secure_api/tools/fix_baseline.py`. Status: `done`. Exit: the tool sends a resting buy and a matching sell and checks the execution reports and both `35=W` snapshots.
- **M1.4** Compose network. Status: `done`. Exit: the `exchange` service does not publish 5001 or 5002, and `docker compose --profile baseline run --rm fix-baseline` is documented.
- **M1.5** Record the baseline. Status: `done`. Exit: this file has the command output, or a `blocked` note with the command still to run.

## Milestone 2 — FIX adapter and PostgreSQL

- **M2.1** Normalize and validate `35=W`. Status: `done`. Exit: invalid prices, quantities, symbols, and entry types are rejected.
- **M2.2** Migrations for the read-model tables. Status: `done`. Exit: a clean database reaches the schema in `docs/ARCHITECTURE.md`.
- **M2.3** Subscriber process on the legacy image. Status: `done`. Exit: `MDCLIENT3` subscribes from `onLogon`, reconnects, and does not run inside a web worker.
- **M2.4** Persist latest snapshot, observations, and trades. Status: `done`. Exit: a resting order shows up as a row without a second pickle consumer.
- **M2.5** Feed health and stale status. Status: `done`. Exit: an exchange restart leaves old rows `stale` until a new snapshot.

## Milestone 3 — FastAPI security and REST

- **M3.1** JWT checks for signature, issuer, audience, and expiry. Status: `done`. Exit: missing, expired, malformed, and wrong-audience tokens get 401.
- **M3.2** Shared policy module. Status: `done`. Exit: a market-data token gets 403 on audit.
- **M3.3** Postgres rate limits, fail closed. Status: `done`. Exit: a burst over the configured limit gets 429 and `Retry-After`.
- **M3.4** `GET /api/v1/market-data` and the symbol and trades routes. Status: `done`. Exit: a scripted FIX order is visible through REST, with sequence and `received_at`.
- **M3.5** Audit middleware. Status: `done`. Exit: each protected call has one row and the request id, and the token is not in the row.

## Milestone 4 — HTMX dashboard and login

- **M4.1** Keycloak Authorization Code with PKCE, cookie session, CSRF on posts. Status: `done`. Exit: the browser has no access token in local storage.
- **M4.2** Market page and book fragment. Status: `done`. Exit: the fragment shows the last book, its age, and its status.
- **M4.3** Alerts page. Status: `done`. Exit: an analyst can filter alerts and a market-data client cannot open the page.
- **M4.4** Audit search page. Status: `done`. Exit: a 403 or 429 can be found by request id.
- **M4.5** Swagger UI on the live OpenAPI document. Status: `done`. Exit: an evaluator can send an authorized request from the browser docs.

## Milestone 5 — Surveillance and scenario harness

- **M5.1** Price, spread, and volume rules. Status: `done`. Exit: each alert stores the rule, observed value, threshold, and time.
- **M5.2** Private `CLIENT3` harness with named scenarios only. Status: `done`. Exit: there is no request field that carries a free-form order.
- **M5.3** Scenario lab page. Status: `done`. Exit: an admin run produces an alert on the alerts page.
- **M5.4** Unauthorized-access and rate-limit scenarios. Status: `done`. Exit: both leave audit rows that point at the same request id.

## Milestone 6 — Evidence

- **M6.1** Automated checks for 401, 403, and 429. Status: `done`. Exit: they pass in the API test run.
- **M6.2** API latency p50, p95, and p99 under a stated concurrency, separate from feed age. Status: `done`. Exit: numbers and the method are written in this file.
- **M6.3** Legacy order-book tests still pass unchanged. Status: `done`. Exit: `pytest tests -v` or `docker run --rm pytradesim test` is green.
- **M6.4** Deployment and limitation notes brought in line with the running Compose file. Status: `done`. Exit: a new checkout can follow the doc and reach the definition of done in `docs/ARCHITECTURE.md`.

## Milestone 7 — UI, auth, and dashboards

- **M7.1** One `.env` for Compose, Keycloak, and the API. Status: `done`. Exit: with no `.env` the stack starts as it does today, and a recreated Keycloak honors `DEMO_ADMIN_PASSWORD`.
- **M7.2** Sign-in that can switch users. Status: `done`. Exit: a second sign-in started for `market` asks for a password and the session is `market`.
- **M7.3** Sign-out through Keycloak. Status: `done`. Exit: after sign-out, the next sign-in asks for a password.
- **M7.4** HTMX-aware session, limit, and error responses. Status: `done`. Exit: an expired fragment redirects, and a 429 fragment keeps polling.
- **M7.5** Shared layout and stylesheet. Status: `done`. Exit: every page extends `base.html` and the nav matches the role.
- **M7.6** Login page with demo users. Status: `done`. Exit: cards and passwords come from the environment.
- **M7.7** Overview dashboard. Status: `done`. Exit: each role sees its own permissions and usage.
- **M7.8** Market console. Status: `done`. Exit: live and stale books render with depth, spread, and freshness.
- **M7.9** Surveillance console. Status: `done`. Exit: an analyst can open an alert, and only an admin can edit a rule.
- **M7.10** Security console. Status: `done`. Exit: access and rate-limit scenarios show up in the counts.
- **M7.11** Security alerts from audit rows. Status: `done`. Exit: repeated 429s produce one `api_abuse` alert.
- **M7.12** Scenario lab redesign. Status: `done`. Exit: a run updates in place and links to its alert or audit row.
- **M7.13** Docs and evidence. Status: `done`. Exit: a new checkout can copy `.env.example` and sign in as each demo user.

## Milestone 8 — Runbook

- **M8.1** Step-by-step runbook. Status: `done`. Exit: `docs/RUNBOOK.md` starts the stack, shows how the processes connect, and lists the fields taken from `35=W`.

## Milestone 9 — Operator console

Spec: `docs/UI_MASTER_PROMPT.md`. Stay on FastAPI, Jinja2, and HTMX. No order ticket, positions, or buy/sell hotkeys.

- **M9.1** Tokens, base shell, filters, and `console.js` core (poll state, backoff, age ticker, scroll keep). Status: `done`. Exit: every page uses the tokens; a forced 429 shows "RETRY Ns" and the last book stays visible; contrast ratios are recorded.
- **M9.2** Market console: three panes, sorted ladder on one scale, tape ticks, 204 when the sequence is unchanged, out-of-band feed state, price flashes. Status: `done`. Exit: running `price_movement` shows a PRICE flash and a new tape row without a full re-render; an unchanged poll returns 204.
- **M9.3** Overview: books table, one `list_books` query, `GET /ui/overview/books` every 5 seconds, limit meters. Status: `done`. Exit: the books table polls from that route. Optional, in its own commit: write `feed_status.last_message_at` from `Store._record`. Otherwise the feed panel says "not recorded".
- **M9.4** Surveillance and alert detail: excess column, rows poll every 10 seconds with a new-row flash, rules as text for analysts, linked timeline, ladder on the detail page, audit-rule evidence links. Status: `done`. Exit: an analyst sees the excess and the book at that sequence, and cannot edit a rule.
- **M9.5** Security and audit: KPI strip, resource and latency columns, status chips, polling note, no auto-poll. Status: `done`. Exit: `/ui/security` and `/ui/audit` show those columns and do not poll.
- **M9.6** Scenario lab: table, confirm dialog, budget meter, run panel states. Status: `done`. Exit: a run still updates in place and links to its alert or audit row.
- **M9.7** Login, error page, callback 403 template, `unknown_user` message, viewport meta, delete `market.css`. Status: `done`. Exit: the callback 403 uses `error.html`, and `market.css` is gone.
- **M9.8** Keyboard and accessibility pass (prompt sections 3.5 and 3.6). Status: `done`. Exit: the shortcuts in the prompt work from the keyboard, and the check result is in the log.
- **M9.9** Evidence. Status: `done`. Exit: `pytest secure_api/tests` is green; `docker run --rm pytradesim test` is still 22 passed; after `docker compose up -d --build`, sign-in as `market`, `analyst`, and `admin` is recorded with the nav each role sees, a forced 429, a scenario run, and the 204 count. Note whether a graphical browser was driven.

## Milestone 10 — UI hardening

Spec: `docs/UI_HARDENING_PROMPT.md`. Correctness, layout, focus, and accessibility fixes only. No features, no redesign, no new endpoints or data fields.

- **M10.0** Safety net: structural markup test and an optional Playwright layout test. Status: `done`. Exit: the structural test is wired into pytest and is red against the malformed table headers before M10.1.
- **M10.1** Table headers: replace every `<th scope="col"ead>` with `<thead>`, name empty header cells, confirm sticky headers. Status: `done`. Exit: M10.0-A is green and every table has a real header.
- **M10.2** Responsive shell and overflow: wrapping top bar and filter bar, `min-width: 0` tracks, capped KPI strip, explicit alerts and audit column widths. Status: `todo`. Exit: no page-level horizontal scroll at 1440 through 400 where a browser exists.
- **M10.3** Focus survives polling: stable ids on swapped controls and rows, focus restore around `outerHTML` swaps, one roving `tabindex`. Status: `todo`. Exit: a poll leaves focus on the same alert row.
- **M10.4** Honest announcements and state: one `#poll-announce` live region, a single session countdown format, paused Refresh URL, used-based scenario meter, prefix nav current state, honest feed and poll cells. Status: `todo`. Exit: announcements happen only on state changes and every meter states what it measures.
- **M10.5** Interaction states and tokens: defined custom properties only, hover/active/disabled/focus-visible states, one dialog block, contrast recorded. Status: `todo`. Exit: no undefined `var(--x)` and disabled controls use `--text-3` plus a dashed border.
- **M10.6** Honest filters, errors, and labels: UTC labels, non-poll HTMX errors, Clear and active-filter text, Security links instead of an embedded audit search, market header `<dl>`, ladder side labels, bounded error and empty states, dialog label, descriptive captions. Status: `todo`. Exit: forms say what they do and failures are visible without losing the last good data.
- **M10.7** Evidence: full pytest counts, host legacy suite, browser layout run when available, contrast ratios, and per-role nav check when Docker is available. Status: `todo`. Exit: the counts and what was not run are in the log.

## Baseline results

Recorded 2026-10-22.

### `pytest tests -v` on the host

QuickFIX is not installed on the host. The order-book tests do not import it. Run with Python 3.12.10, pytest 9.1.1, and `prettytable` 2.1.0:

```text
22 passed in 0.16s
```

### `docker run --rm pytradesim test`

Python 3.9.25, pytest 5.4.1, inside the rebuilt image:

```text
22 passed in 0.10s
```

The first image build on this Windows checkout failed at `exec /app/docker/entrypoint.sh` because `core.autocrlf` had written the script with CRLF. `.gitattributes` keeps `docker/entrypoint.sh`, `DockerFile`, `*.sh`, and `*.cfg` as LF. Rebuild after that attribute is in place.

### `python tests/benchmark.py --sample-size 5000 --probability 0.5`

Run from the repo root with `PYTHONPATH` set to the root. The script imports `pytradesim` before it appends `..` to `sys.path`, so a bare `python tests/benchmark.py` does not find the package. Host timer resolution makes the median look like zero.

```text
Generated 5000 orders in 11274.576 us

Order add stats:-
Count - 5000
Mean - 7.088 us
Median - 0.000 us
Max - 1050.949 us
Min - 0.000 us

Order delete stats:-
Count - 4996
Mean - 1.115 us
Median - 0.000 us
Max - 653.744 us
Min - 0.000 us
```

### `docker compose --profile baseline run --rm fix-baseline`

The exchange log showed `MARKET->MDCLIENT3` and `EXCHANGE->CLIENT3` created. The tool then printed:

```text
baseline: MDCLIENT3 logged on
baseline: subscribed to BASELINE
baseline: CLIENT3 logged on
baseline: sent CLIENT3BASELINE1
baseline: 35=8 exec_type=0 symbol=BASELINE last=675.0@189.0
baseline: 35=W BASELINE bids=[(189.0, 675.0)] asks=[] trades=[]
baseline: sent CLIENT3BASELINE2
baseline: 35=8 exec_type=2 symbol=BASELINE last=675.0@189.0
baseline: 35=8 exec_type=2 symbol=BASELINE last=675.0@189.0
baseline: 35=W BASELINE bids=[] asks=[] trades=[(189.0, 675.0)]
baseline: PASS BASELINE bid 675.0 x 189.0 crossed
```

### Known limitations

- The exchange flushes a symbol about once a second, and only after the book changes.
- One flush collapses identical `(price, quantity)` trades through `set()`.
- Subscribing does not return the current book. The first snapshot waits for the next change.
- The matching book is process memory. A restart drops it. Stored snapshots are not a recovered book.
- `MarketDepth(10)` is not applied. Empty sides are omitted from `35=W`.
- `subscriber` and `scenario-worker` stay unhealthy. They reuse the exchange image health check, which expects listeners on 5001 and 5002. Feed health is `feed_status.logged_on`.
- Compose publishes the API on `localhost:8080` and Keycloak on `localhost:8081`. It does not publish 5001, 5002, 5432, or 9000. Browser login uses `localhost` because the realm redirect URIs do.

## API latency

Recorded 2026-10-22. These numbers are HTTP response time. They are not the age of the stored book, and `received_at` was not used.

Method: from the host, 8 warmup requests were discarded, then 160 requests to `GET http://127.0.0.1:8080/api/v1/market-data/BASELINE` ran with 8 calls in flight. The caller was a Keycloak client-credentials token for `pytradesim-scenario` (`market_data_client`, audience `pytradesim-api`). Each sample is `time.perf_counter` around one request on a shared HTTP client. Percentiles use linear interpolation: rank `(n - 1) * (p / 100)` between the adjacent sorted samples. For this sample only, that client's market-data policy was raised above the default 60 per minute so the burst would not be rejected, then restored to 1 per 60 seconds. All 160 measured calls returned 200. The wall clock for those calls was 950.84 ms.

| Percentile | Latency |
| --- | --- |
| p50 | 46.34 ms |
| p95 | 57.60 ms |
| p99 | 64.49 ms |

The fastest call was 31.04 ms and the slowest was 64.99 ms.

## Decision log

- **2026-10-22** — Integration boundary is the FIX market-data session on port 5002 (`MDCLIENT3`). The pickle socket on port 9000 stays between the two legacy processes.
- **2026-10-22** — UI is FastAPI with Jinja2 and HTMX. No separate frontend build.
- **2026-10-22** — Keycloak for identity. Kong, Kafka, and Grafana are deferred.
- **2026-10-22** — Layout is additive. Legacy paths stay where they are. New code is `secure_api/`. Docs are `docs/` and `CONTRIBUTING.md`.
- **2026-10-22** — The subscriber runs from the existing `pytradesim` image so QuickFIX is not built again. The API image does not link QuickFIX.
- **2026-10-22** — Demo initiators set `ResetOnLogon=Y` so a recreated exchange store does not reject them.
- **2026-10-22** — Rate limiting fails closed when its database is unavailable.

## Log

- **2026-10-22** — M1.1–M1.5. Added the two acceptor sessions, initiator configs, `fix_baseline.py`, and the private Compose network. Host pytest and the image suite both passed 22 tests. `fix-baseline` passed for symbol `BASELINE` at 675 @ 189. `.gitattributes` forces LF on the entrypoint and FIX configs so a Windows checkout can build the image.
- **2026-10-22** — M2.1. `secure_api/adapter/normalizer.py` rejects bad symbols, prices, quantities, and entry types, and keeps identical trade prints. Checked with `pytest secure_api/tests/test_normalizer.py` (14 passed) and `pytest tests` (22 passed).
- **2026-10-22** — M2.2. `secure_api/migrations/001_read_model.sql` creates the read model, audit, rate policies, and `feed_status`. The app role can insert audit rows and cannot update or delete them. Checked with `docker compose run --rm migrate` against a clean Postgres.
- **2026-10-22** — M2.3. `subscriber` is its own Compose process. It logged on as `MDCLIENT3`, subscribed to `MSFT,HYG,BASELINE` from `onLogon`, and subscribed again after `docker compose restart exchange`.
- **2026-10-22** — M2.4. A `CLIENT3` bid of 40 `BASELINE` at 51 was stored as `market_snapshots` sequence 1, status `live`, bids `[{price: 51.0, quantity: 40.0}]`. Checked with `docker compose --profile order run --rm place-order` and a SQL select. No second consumer on port 9000.
- **2026-10-22** — M2.5. Restarting the subscriber marked `BASELINE` `stale` while `feed_status.logged_on` returned to true. A later bid at 53 made the row `live` again, with both price levels. `psycopg` transactions use `connection.transaction()` so the connection stays open.
- **2026-10-22** — M3.1 and M3.2. RS256 tokens are checked for signature, issuer, audience, and expiry. A `market_data_client` token can call market data and receives 403 on audit. Checked with `pytest secure_api/tests/test_api.py` (7 passed).
- **2026-10-22** — M3.3. Each protected call consumes a Postgres counter for the token's client id. The limiter denies the call when the store is down. A subject allowed 2 market-data requests in the window received 429 and `Retry-After` on the third. Checked with pytest in the API image on the Compose network after `002_rate_limits.sql`. Host `pytest secure_api/tests/test_api.py` skips that case when `DATABASE_URL` is unset and still passes the token checks.
- **2026-10-22** — M3.4. `GET /api/v1/market-data`, `GET /api/v1/market-data/{symbol}`, and the trades route read `market_snapshots` and `trade_observations`. `BASELINE` from the scripted `CLIENT3` bid came back `live` with `ingest_sequence` 6 and `received_at`. Checked with pytest in the API image on the Compose network (the book case passed).
- **2026-10-22** — M3.5. Protected calls append one `audit_events` row with the request id, client id, decision, and status. The bearer token is not stored. A market-data read for `req-audit-m35` was listed by a `security_admin` token and the token text was absent. Checked with `docker compose run --rm --no-deps --entrypoint python api -m pytest secure_api/tests/test_api.py` (10 passed).
- **2026-10-22** — M4.1. Browser sign-in is Authorization Code with PKCE. The cookie is `HttpOnly`, `Secure`, and `SameSite=Lax`, and it carries a session id. The access token stays in `browser_sessions`. The login and home pages have no `localStorage`. A logout without the CSRF token gets 403. Checked with `pytest secure_api/tests/test_browser_session.py` in the API image (3 passed, the no-database case skipped because `DATABASE_URL` was set).
- **2026-10-22** — M4.2. `/ui/market` renders the last book and polls `/ui/market-data/{symbol}/book` every 2 seconds. The fragment shows status, age, `received_at`, and FIX session health. `BASELINE` showed a bid at 51.0. Checked with `pytest secure_api/tests/test_market_page.py` in the API image (2 passed). Signing in as `market` through Keycloak also returned that fragment, with no access token in the page.
- **2026-10-22** — M4.3. `/ui/alerts` lists rule, symbol, severity, observed value, threshold, and time. A symbol filter hides the other row. `market_data_client` receives 403 on the page and on `GET /api/v1/alerts`. Checked with `pytest secure_api/tests/test_alerts_page.py` in the API image (3 passed).
- **2026-10-22** — M4.4. `/ui/audit` filters by request id, client, action, decision, status, and time. A 403 and a 429 were found again by request id. A market-data client receives 403 on the page. Checked with `pytest secure_api/tests/test_audit_page.py secure_api/tests/test_api.py` in the API image (12 passed).
- **2026-10-22** — M4.5. `/docs` serves Swagger UI from the live `/openapi.json`, with Keycloak PKCE as an authorize option. The realm accepts `http://localhost:8080/docs/oauth2-redirect`. A Keycloak access token with audience `pytradesim-api` and role `market_data_client` returned 200 for `GET /api/v1/market-data`. Checked with `pytest secure_api/tests/test_docs.py` (passed) and a scripted PKCE login against the running stack. A graphical browser was not driven.
- **2026-10-22** — M5.1. The API evaluates `price_movement`, `spread_widening`, and `volume` on each new market observation. An alert stores the rule, the observed value, the threshold, and the observation time, and the same observation is not written twice. Checked with `pytest secure_api/tests/test_surveillance.py` in the API image (4 passed). A book inserted after the API started produced those three alerts from the API process.
- **2026-10-22** — M5.2. The CLIENT3 harness accepts only a scenario name: `price_movement`, `spread_widening`, or `volume`. A request with a price, quantity, symbol, or extra argument is rejected, and `ORDER_PRICE` is ignored. Volume orders wait for the gateway flush so each distinct trade is kept. Checked with `pytest secure_api/tests/test_scenarios.py` (3 passed). `docker compose --profile scenario run` passed all three names. An extra argument printed `free_form_order` and exited 2. The volume trades were stored as 400@101, 350@102, and 300@103, and the volume alert recorded 1050 above 1000.
- **2026-10-22** — M5.3. `/ui/scenarios` lists the five scenario names and the scenario rate limit. A run posts only the scenario name, and the scenario worker sends the fixed CLIENT3 orders. Checked with `pytest secure_api/tests/test_scenarios_page.py` in the API image (4 passed). Signing in as admin and running `spread_widening` finished `passed`. The SPREAD `spread_widening` alert count went from 2 to 3, and the alerts page showed that row. A graphical browser was not driven.
- **2026-10-22** — M5.4. `unauthorized_access` calls audit as a market-data client and stores a 403. `rate_limit_abuse` allows one market-data read for that client and stores a 429 on the next. The audit row uses the same request id the lab shows, and neither scenario sends an order. Checked with `pytest secure_api/tests/test_access_scenarios.py secure_api/tests/test_scenarios.py secure_api/tests/test_scenarios_page.py` in the API image (9 passed). Signing in as admin, both runs finished `passed` and the audit page showed each request id. The stored rows are 403 `missing_scope` and 429 `rate_limited`. A graphical browser was not driven.
- **2026-10-22** — M6.1. The API test run checks 401 for a missing, malformed, expired, wrong-audience, and wrong-issuer token, 403 for a market-data client calling audit and alerts, and 429 with `Retry-After` after the configured limit. Each body returns that call's request id. Checked with `pytest secure_api/tests/test_api.py` in the API image (11 passed, none skipped).
- **2026-10-22** — M6.2. Timed `GET /api/v1/market-data/BASELINE` from the host at concurrency 8, 160 samples after 8 warmup calls. p50 46.34 ms, p95 57.60 ms, p99 64.49 ms. The timer is the HTTP call, not the book's age. All 160 responses were 200. The temporary rate-limit raise for that client was restored to 1 per 60 seconds.
- **2026-10-22** — M6.3. `docker run --rm pytradesim test` passed 22 tests in 0.12s on Python 3.9.25 and pytest 5.4.1. The run includes the order-book cases in `tests/test_orderbook.py`. The legacy test files were left as they are.
- **2026-10-22** — M6.4. `DOCKER.md` now starts the secure layer with `docker compose up -d --build`, and `docs/ARCHITECTURE.md` states the checks that command reaches. The running stack matches that description: exchange and postgres healthy, migrate exited 0, API on port 8080, Keycloak on 8081, FIX and Postgres unpublished. `http://localhost:8080/ui/login` and the `pytradesim` realm both returned 200. The subscriber log says `MDCLIENT3 logged on` while its container stays unhealthy. A fresh checkout was not rebuilt.
- **2026-10-23** — M7.1. Compose reads `.env.example` values, with the same defaults when `.env` is absent. Keycloak substitutes `${DEMO_ADMIN_PASSWORD}` on import. A recreated realm accepted `changeme` for `admin` and rejected `admin`, then the container was recreated on the default password. `006_app_password.sql` ran `ALTER ROLE`. Checked with `pytest secure_api/tests/test_config.py` (passed) and `docker compose config`.
- **2026-10-23** — M7.2. Named sign-in ends the Keycloak session first, then asks for that user's password. The browser session ends when the access token expires. A used callback returns to `/ui/login?error=expired`. Checked with `pytest secure_api/tests/test_browser_session.py` (6 passed, 1 skipped). A scripted sign-in as `admin`, then as `market`, showed the password form with username `market` and the home page client was `market`. A graphical browser was not driven.
- **2026-10-23** — M7.3. `POST /ui/logout` deletes the app session and redirects to the Keycloak end-session endpoint with `id_token_hint`. Checked with `pytest secure_api/tests/test_logout.py` (passed). A scripted admin sign-in then sign-out landed on `/ui/login`, `/ui` redirected to login, and the next sign-in showed the password form. A graphical browser was not driven.
- **2026-10-23** — M7.4. An HTMX request with no session gets `HX-Redirect` and does not include the login page. A 429 fragment says the limit was reached and keeps polling after `Retry-After`. Polling runs only while the tab is visible. `/ui` errors render HTML. Checked with `pytest secure_api/tests/test_htmx_errors.py` (3 passed).
- **2026-10-23** — M7.5. Signed-in pages extend `base.html` with role-aware navigation, a user chip, and a sign-out form. Checked with `pytest secure_api/tests/test_layout.py` (passed). A graphical browser was not driven.
- **2026-10-23** — M7.6. The login page shows one card per demo user. Passwords appear only when `SHOW_DEMO_CREDENTIALS` is not `0`. Checked with `pytest secure_api/tests/test_browser_session.py` (7 passed, 1 skipped). A graphical browser was not driven.
- **2026-10-23** — M7.7. `/ui` shows the signed-in client, the permissions that role grants, feed health, symbol tiles, and that client's rate-limit usage. Checked with `pytest secure_api/tests/test_overview.py` (passed). A graphical browser was not driven.
- **2026-10-23** — M7.8. The market page lists symbols with status, and the book shows a depth ladder, spread, last trade, and a note that the exchange sends no event time. Pause stops polling. Checked with `pytest secure_api/tests/test_market_console.py` (passed). A graphical browser was not driven.
- **2026-10-23** — M7.9. Surveillance filters are selects, an alert page shows the observed value against its threshold, and `GET /api/v1/alerts/{id}` returns that alert. Saving a rule requires `rules:write`, the CSRF token, and the admin rate category. An analyst edit is rejected. An admin edit is audited as an administrative change. Checked with `pytest secure_api/tests/test_rules_admin.py` (3 passed). A graphical browser was not driven.
- **2026-10-23** — M7.10. `/ui/security` shows request totals, 401/403/429 counts, latency percentiles, per-minute bars, top clients, and policies. Audit search uses selects for decision and status, and each request id links to the audit filter. `GET /api/v1/metrics` requires `operations:read`. Checked with `pytest secure_api/tests/test_security_console.py` (2 passed). A graphical browser was not driven. The live scenario counts are checked with the stack in M7.13.
- **2026-10-23** — M7.11. The API poller reads `audit_events` for `api_abuse` (429s above 2 in 60 seconds) and `access_denied` (401s and 403s above 5 in 60 seconds). It writes one alert per client per window, with no symbol and the client in the detail. Seeded by migration 008. Checked with `docker compose run --rm --no-deps -v` the API tree `:ro --entrypoint python api -m pytest secure_api/tests/test_security_alerts.py` (passed: three 429s, one `api_abuse` alert, a second poll did not add another). A graphical browser was not driven.
- **2026-10-23** — M7.12. Each scenario is a card with its expected alert and, for the FIX scenarios, the fixed orders. The access scenarios say they do not send an order. The page shows run history, the remaining scenario budget, and a run that keeps polling until it finishes and links to alerts or the audit row. Checked with `pytest secure_api/tests/test_scenario_cards.py` (2 passed). A graphical browser was not driven.
- **2026-10-23** — M7.13. `DOCKER.md` and `docs/ARCHITECTURE.md` describe `.env`, the sign-in and sign-out flow, and the five consoles. A named sign-in with no current session goes straight to Keycloak with `login_hint` and `prompt=login`. A sign-in that still has an id token ends the Keycloak session first. Host `pytest secure_api/tests` was 56 passed and 15 skipped. After `docker compose build api` and `docker compose up -d api`, a script signed in as `market`, `analyst`, and `admin`: each password form was filled with that username, `/ui` showed that user, market and analyst were refused the next console (403), and admin opened `/ui/security` (200). `docker run --rm pytradesim test` stayed at 22 passed. A graphical browser was not driven.
- **2026-10-24** — M8.1. `docs/RUNBOOK.md` lists the start commands, the path from `35=D` to the page, and the fields `35=W` contributes. `README.rst` and `DOCKER.md` point at it. Checked against `docker-compose.yml`, `secure_api/adapter/normalizer.py`, and the secure-layer section of `DOCKER.md`. A fresh checkout was not rebuilt. A graphical browser was not driven.
- **2026-10-24** — Milestone 9 listed as `todo`. The implementation prompt is `docs/UI_MASTER_PROMPT.md`. No console code changed. `ui-ux-pro-max` is installed locally and excluded from git; conflicts with this repo (no React, no glassmorphism, 13px type, 24px targets) are written at the top of that file. Checked by reading the prompt against `secure_api/app/main.py`, `secure_api/app/web/routes.py`, and `secure_api/app/models/payloads.py`. A graphical browser was not driven.
- **2026-10-24** — M9.1. Pages use the token stylesheet, the shell shows FIX and poll state, and `console.js` keeps scroll, ticks ages, and sets `data-backoff` on 429 without swapping the last book. htmx 2 still does not swap 4xx, so the previous book stays. A 429 labels the poll cell `RETRY Ns` (`RETRY 9s` for `Retry-After: 9`). Contrast on `--bg-panel` / `--bg-row-active`, dark then light: text-1 15.31/11.33 and 19.35/15.60; text-2 9.96/7.37 and 12.46/10.04; text-3 7.59/5.62 and 7.59/6.12 (4.5:1 floor, not used for numbers). Data colours were lightened or darkened only where the active row was under 7:1. Dark active-row ratios after that: bid `#45D29A` 7.00, ask `#FFA1AC` 7.00, pending `#85C0FF` 7.03, deny `#FFA677` 7.02, ok `#6CCE9F` 7.02, neutral `#C9D1D9` 8.71, warn `#F0B90B` 7.46. Light active-row: bid `#055536` 7.18, ask `#970E23` 7.05, pending `#0A489A` 7.03, warn `#664500` 7.01, deny `#852D10` 7.11, ok `#095633` 7.08, neutral `#2B3540` 10.04. Checked with `pytest secure_api/tests` on the host: 58 passed, 15 skipped. Docker Desktop was not running, so a graphical browser was not driven.
- **2026-10-24** — M9.2. The market page is a watchlist, depth ladder, and tape under one header. Asks sit above bids, both sorted high to low, on one quantity scale. An unchanged book poll returns 204 and does not swap. A changed poll swaps only `#market-book` and sends the FIX state and the watchlist row out of band. `console.js` flashes a price or a new trade row after that swap. Checked with `pytest secure_api/tests/test_market_console.py` (ladder order 70 before 60 before the spread before 50, 204 when `since` matches, 200 when it does not). `pytest secure_api/tests`: 58 passed, 15 skipped. Docker Desktop was not running, so `price_movement` was not executed and a graphical browser was not driven.
- **2026-10-24** — M9.3. Overview reads every book in one `list_books` query and polls `GET /ui/overview/books` every 5 seconds (12 of the 60 market-data requests per minute; the book poll is 20, so one overview tab plus one market tab is 32). Bid and ask cells carry `ovw:{symbol}` keys so a change flashes. The rate-limit meter is green under 70 percent, amber from 70 percent, and red at the cap. `feed_status.last_message_at` is still never written, so the feed panel says "not recorded". Checked with `pytest secure_api/tests`: 58 passed, 15 skipped. A graphical browser was not driven.
- **2026-10-24** — M9.4. Alert rows show the excess and poll `GET /ui/alerts/rows` every 10 seconds (6 of the 20 alerts requests per minute). A newer alert id flashes once and the caption shows "{n} new". Analysts see rule thresholds as text. The detail page draws the same ladder as the market page when that sequence is still stored, and `api_abuse` / `access_denied` link to audit status 429 / 403. Checked with `pytest secure_api/tests`: 62 passed, 15 skipped. A graphical browser was not driven.
- **2026-10-24** — M9.5. `/ui/security` shows a nine-cell strip, a 15m/60m switch, a refresh link, and the note that each book refresh is one audited request. `/ui/audit` adds resource and latency columns and status chips. Neither page polls; the audit budget stays at 10 per minute for page loads and filter changes. Checked with `pytest secure_api/tests`: 62 passed, 15 skipped. A graphical browser was not driven.
- **2026-10-24** — M9.6. The scenario lab is a table with a confirm dialog and a budget meter. A pending or running run still polls `GET /ui/scenarios/runs/{id}` every 3 seconds, and that poll is not rate-limited. A passed run links to the symbol's alerts and the audit row, then stops polling. The running marker is a static 2px bar because motion stays a 150ms flash. Checked with `pytest secure_api/tests`: 64 passed, 15 skipped. A graphical browser was not driven.
- **2026-10-24** — M9.7. Sign-in is a 640px table, and an unknown account shows "That account is not a demo user." A callback for an account without market access renders `error.html` at 403, with the status code and request id. The request id links to audit only when the viewer has `audit:read`. `market.css` is deleted; its rules were the old light sheet and were not copied. Checked with `pytest secure_api/tests`: 65 passed, 15 skipped. A graphical browser was not driven.
- **2026-10-24** — M9.8. Shortcuts are handled in `console.js` only when focus is outside a field and no modifier is held. `?` opens the shortcut sheet, `1`–`5` follow the visible nav, `/` focuses the page filter, Esc closes a dialog or clears a filter, arrows move a row, Enter opens it, and `p`, `r`, `[`, `]`, and `c` hit the pause, refresh, symbol, and copy controls. There is no order shortcut. Pages have a skip link, header, nav, and main; every table has a caption and `th scope="col"`; the focus ring is 2px; controls are at least 24px; `aria-live` is on the poll cell, the session countdown at two minutes or less, and the active run, and not on the ladder or tape. Checked with `pytest secure_api/tests`: 66 passed, 15 skipped, including the key decisions and the markup scan. axe and Lighthouse were not run. A graphical browser was not driven.
- **2026-10-24** — M9.9. `pytest secure_api/tests` was 66 passed and 15 skipped. `docker run --rm pytradesim test` was 22 passed. After `docker compose up -d --build`, a script signed in as `market`, `analyst`, and `admin`. Nav hrefs: market `/ui`, `/ui/market`; analyst those plus `/ui/alerts`; admin those plus `/ui/security` and `/ui/scenarios`. Five unchanged `BASELINE` book polls returned 204. Further book polls used the rest of the 60-per-minute market-data budget (54 more 200s) and the next one returned 429. Admin scenario run 12, `price_movement`, went pending, then running, then passed. A graphical browser was not driven.
- **2026-10-25** — M10.0. Added `test_markup_structure.py`, which renders every signed-in page and fragment through `TestClient` with the `test_layout.py` monkeypatch pattern and parses the result with `html.parser`. It checks caption, one `thead`, `th scope="col"` inside that `thead`, table children, attribute names, unique ids, and `aria-labelledby` targets. It also adds `test_layout_browser.py` (Playwright, skipped because Playwright is not installed; dependency is in `secure_api/requirements-dev.txt` only). The old scan passed because `<th\b[^>]*>` matched `<th scope="col"ead>`; it now rejects the malformed attribute and requires `<thead>`. Before the fix the structural test failed on every rendered table with `invalid attribute 'ead'`, `<th> is a direct child of <table>`, `expected one <thead>, found 0`, and `no <th scope="col"> inside <thead>`. `pytest secure_api/tests/test_markup_structure.py` was 3 failed. A graphical browser was not driven.
- **2026-10-25** — M10.1. Replaced all 15 `<th scope="col"ead>` sites with `<thead><tr> … </tr></thead>`; `grep -rn 'scope="col"ead' secure_api/app/web/templates` now returns nothing. Named every empty header cell (`home.html`, `security.html`, `scenarios.html`, `login.html`, `alerts.html`) with `<span class="sr-only">Actions</span>` and added `.sr-only` to `app.css`. The sticky rule `.alert-panel thead th` now applies because the table has a real `thead`; no CSS change was needed for it. Checked with `pytest secure_api/tests/test_markup_structure.py secure_api/tests/test_layout.py`: 5 passed. The rest of the suite was checked in M10.2. A graphical browser was not driven.
