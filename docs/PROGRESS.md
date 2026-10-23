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
- **M7.8** Market console. Status: `todo`. Exit: live and stale books render with depth, spread, and freshness.
- **M7.9** Surveillance console. Status: `todo`. Exit: an analyst can open an alert, and only an admin can edit a rule.
- **M7.10** Security console. Status: `todo`. Exit: access and rate-limit scenarios show up in the counts.
- **M7.11** Security alerts from audit rows. Status: `todo`. Exit: repeated 429s produce one `api_abuse` alert.
- **M7.12** Scenario lab redesign. Status: `todo`. Exit: a run updates in place and links to its alert or audit row.
- **M7.13** Docs and evidence. Status: `todo`. Exit: a new checkout can copy `.env.example` and sign in as each demo user.

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
