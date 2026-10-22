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
- **M3.4** `GET /api/v1/market-data` and the symbol and trades routes. Status: `todo`. Exit: a scripted FIX order is visible through REST, with sequence and `received_at`.
- **M3.5** Audit middleware. Status: `todo`. Exit: each protected call has one row and the request id, and the token is not in the row.

## Milestone 4 — HTMX dashboard and login

- **M4.1** Keycloak Authorization Code with PKCE, cookie session, CSRF on posts. Status: `todo`. Exit: the browser has no access token in local storage.
- **M4.2** Market page and book fragment. Status: `todo`. Exit: the fragment shows the last book, its age, and its status.
- **M4.3** Alerts page. Status: `todo`. Exit: an analyst can filter alerts and a market-data client cannot open the page.
- **M4.4** Audit search page. Status: `todo`. Exit: a 403 or 429 can be found by request id.
- **M4.5** Swagger UI on the live OpenAPI document. Status: `todo`. Exit: an evaluator can send an authorized request from the browser docs.

## Milestone 5 — Surveillance and scenario harness

- **M5.1** Price, spread, and volume rules. Status: `todo`. Exit: each alert stores the rule, observed value, threshold, and time.
- **M5.2** Private `CLIENT3` harness with named scenarios only. Status: `todo`. Exit: there is no request field that carries a free-form order.
- **M5.3** Scenario lab page. Status: `todo`. Exit: an admin run produces an alert on the alerts page.
- **M5.4** Unauthorized-access and rate-limit scenarios. Status: `todo`. Exit: both leave audit rows that point at the same request id.

## Milestone 6 — Evidence

- **M6.1** Automated checks for 401, 403, and 429. Status: `todo`. Exit: they pass in the API test run.
- **M6.2** API latency p50, p95, and p99 under a stated concurrency, separate from feed age. Status: `todo`. Exit: numbers and the method are written in this file.
- **M6.3** Legacy order-book tests still pass unchanged. Status: `todo`. Exit: `pytest tests -v` or `docker run --rm pytradesim test` is green.
- **M6.4** Deployment and limitation notes brought in line with the running Compose file. Status: `todo`. Exit: a new checkout can follow the doc and reach the definition of done in `docs/ARCHITECTURE.md`.

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
