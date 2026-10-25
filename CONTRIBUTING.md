# Contributing

Work is tracked in [docs/PROGRESS.md](docs/PROGRESS.md). The design is [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Pick a task

1. Take the lowest milestone that still has a `todo` item, unless you were asked for a specific id.
2. Set that item to `in-progress` in `docs/PROGRESS.md` before editing code.
3. Branch from the current line as `m<milestone>/<task-id>-<slug>`. Example: `m2/m2-3-fix-subscriber`.
4. Commit subjects start with the task id in brackets: `[M2.3] Subscribe from onLogon`.

One task per branch. A change that finishes the task also updates `docs/PROGRESS.md`: status `done` or `blocked`, and a dated line in the log saying what changed and how it was checked.

## Legacy freeze

Do not change matching, execution reports, or the pickle channel.

Frozen:

- `pytradesim/**/*.py`
- `pytradesim/server.py`, `market_data.py`, `client.py`, `market_client.py`
- `docker/`, `DockerFile`
- `tests/`

Allowed legacy edit: a new `[SESSION]` block in `pytradesim/configs/exchange.cfg` or `pytradesim/configs/price.cfg`. Do not edit the existing `CLIENT1`, `CLIENT2`, `MDCLIENT1`, or `MDCLIENT2` blocks.

New application code goes under `secure_api/`. The order harness stays in `secure_api/harness/` and is not imported by the read API.

Do not connect anything new to `localhost:9000`. Do not publish 5001, 5002, or 9000 on the Compose `exchange` service.

## Checks

Legacy unit tests, from the repo root when QuickFIX is installed:

```bash
pytest tests -v
```

The same suite inside the image:

```bash
docker build -f DockerFile -t pytradesim .
docker run --rm pytradesim test
```

FIX baseline (rebuild first so the image contains the `CLIENT3` and `MDCLIENT3` sessions):

```bash
docker compose build exchange
docker compose --profile baseline run --rm fix-baseline
```

Order-book tests in `tests/test_orderbook.py` are the regression net. Do not edit them to match a new API. If they fail, the matching code was changed and that change should be reverted.

## Security review before `done`

- Logs and audit rows contain a client id and a request id, not a bearer token, password, cookie, or key.
- SQL uses bound parameters.
- Symbols, pagination, thresholds, and scenario names are validated on the server. The scenario action does not accept an order payload.
- `/ui` handlers call the same policy module as `/api/v1`.
- State-changing browser forms send a CSRF token.
- Rate limiting rejects the request when its store is unavailable.
- A stale snapshot is labeled `stale` or `uninitialized`, including after an exchange restart.

## Done means

- The task's exit condition in `docs/PROGRESS.md` is true.
- The checks above that the task can affect were run, and the log names the command.
- No frozen file changed, other than an allowed session block.
- Docs that the task makes wrong are updated in the same change (`DOCKER.md`, `docs/ARCHITECTURE.md`, or this guide).
