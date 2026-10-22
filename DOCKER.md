# Running pytradesim with Docker

A guide to build the image, start the exchange, run the clients and walk
through a full trading demonstration.

- [What runs where](#what-runs-where)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Starting the exchange](#starting-the-exchange)
- [Running the clients](#running-the-clients)
- [Demonstration](#demonstration)
- [Image modes](#image-modes)
- [Environment variables](#environment-variables)
- [Useful commands](#useful-commands)
- [Troubleshooting](#troubleshooting)
- [Notes](#notes)

---

## What runs where

The project is a FIX 4.2 exchange simulator made of four processes. The
Docker image runs them in three different ways:

| Process | Role | Port | Runs in |
|---|---|---|---|
| `server.py` | Exchange gateway, accepts FIX orders | `5001` | `exchange` container |
| `market_data.py` | Market data gateway, accepts FIX subscriptions | `5002` | `exchange` container |
| `client.py` | Interactive trading client | - | client container |
| `market_client.py` | Interactive market data client | - | market data client container |

The two gateways run **together in one container** because they pass order
books to each other over a `multiprocessing` channel bound to
`localhost:9000`. They therefore have to share a network namespace. That
internal port is not published.

The clients are interactive, so they run in their own short lived
containers with a terminal attached.

```
                        ┌───────────────────────────────┐
   trading client  ───► │  exchange container            │
   (container)     5001 │  ┌─────────────────────────┐  │
                        │  │ server.py  (FIX :5001)  │  │
                        │  │        ▲                │  │
                        │  │        │ order books    │  │
                        │  │        ▼                │  │
                        │  │ market_data.py          │  │
                        │  │   (FIX :5002,  ──:9000) │  │
                        │  └─────────────────────────┘  │
                        └───────────────────────────────┘
                                      ▲
                        ┌─────────────┴─────────────┐
   market data      ───►│  market data client      │
   client (container)  │  (container)              │
                        └───────────────────────────┘
```

## Prerequisites

- Docker with the Compose plugin (`docker compose`, not `docker-compose`)
- Nothing else, the image carries the Python 3.9 runtime and every
  dependency, `quickfix` included

## Quick start

```bash
# 1. Build the image
docker build -f DockerFile -t pytradesim:latest .

# 2. Start the exchange. FIX ports stay on the Compose network.
docker compose up -d exchange

# 3. Follow the logs
docker compose logs -f exchange
```

The exchange is ready when the log shows:

```
[supervisor] exchange gateway accepting FIX orders on 5001, market data gateway on 5002
[supervisor] ready
```

## Starting the exchange

### With Docker Compose (recommended)

```bash
docker compose up -d exchange
docker compose ps          # STATUS should read "healthy"
```

Compose does not publish FIX to the host. Other Compose services reach the
exchange at `exchange:5001` and `exchange:5002`. To publish those ports for
a client that runs on the host, use the `docker run -p` example below.

| Compose service port | Who can connect |
|---|---|
| `5001` | Containers on the Compose network (FIX order entry) |
| `5002` | Containers on the Compose network (FIX market data) |

### Without Compose

```bash
docker build -f DockerFile -t pytradesim:latest .

docker network create pytradesim
docker run -d \
    --name pytradesim-exchange \
    --network pytradesim \
    -p 5001:5001 \
    -p 5002:5002 \
    pytradesim:latest
```

The client containers talk to the exchange over the `pytradesim` network, so
`EXCHANGE_HOST` has to point at the exchange container.

## Running the clients

Both clients are interactive, they need `-it` for a terminal and `-i` so
stdin stays open.

### Trading client

```bash
docker run -it \
    --network pytradesim \
    -e EXCHANGE_HOST=pytradesim-exchange \
    pytradesim:latest client configs/client1.cfg
```

With Compose:

```bash
docker compose --profile client run --rm client
```

### Market data client

```bash
docker run -it \
    --network pytradesim \
    -e EXCHANGE_HOST=pytradesim-exchange \
    pytradesim:latest market-client configs/mdclient1.cfg
```

With Compose:

```bash
docker compose --profile market-client run --rm market-client
```

The market data client asks for a symbol right after it logs on:

```
Enter symbol to subscribe: MSFT
```

Use `configs/client2.cfg` and `configs/mdclient2.cfg` for the second
session. The exchange accepts `CLIENT1`, `CLIENT2`, `MDCLIENT1` and
`MDCLIENT2`.

## Demonstration

This walk through places a resting bid, matches it with a sell order and
watches the market data feed react.

### 1. Start the exchange

```bash
docker compose up -d exchange
docker compose logs -f exchange
```

Leave that terminal open, or use a second one for the steps below.

### 2. Subscribe to market data

In a second terminal:

```bash
docker compose --profile market-client run --rm market-client
```

The client logs on and waits for a symbol:

```
2026-10-22 07:42:06.001742 [INFO   ] (onLogon  ) FIX.4.2:MDCLIENT1->MARKET session successfully logged in.
Enter symbol to subscribe:
```

Type `MSFT` and press enter. Nothing is printed yet, the feed only sends a
snapshot when the book changes.

### 3. Place a resting bid

In a third terminal:

```bash
docker compose --profile client run --rm client
```

The trading client logs on and shows its menu:

```
2026-10-22 07:42:13.963125 [INFO   ] (onLogon  ) FIX.4.2:CLIENT1->EXCHANGE session successfully logged in.
Enter choice :-
1. New order
2. Replace order
3. Delete order
>
```

Choose **1** (new order) and enter:

```
Symbol: MSFT
Price: 189
Quantity: 675
Side: buy
Type: limit
```

The exchange acknowledges the order:

```
Sending new order...
2026-10-22 07:42:15.966225 [INFO   ] (fromApp  ) Got message 8=FIX.4.2|9=180|35=8|34=2|49=EXCHANGE|...|54=1|55=MSFT|... for FIX.4.2:CLIENT1->EXCHANGE.
2026-10-22 07:42:15.966366 [INFO   ] (process  ) Order placed successfully.
2026-10-22 07:42:15.966472 [INFO   ] (process  ) Order: 17=MSFT_E_000001, 11=CLIENT1MSFT1 55=MSFT 32=675@31=189 54=1
```

The market data client now prints the book:

```
Symbol: MSFT
+------------------+--------------------+
| bid_prc, bid_qty |  ask_prc, ask_qty  |
+------------------+--------------------+
|  (189.0, 675.0)  | ('Empty', 'Empty') |
+------------------+--------------------+
```

The bid is resting at 189.0 for 675 shares.

### 4. Match the bid with a sell order

In the trading client, choose **1** again and enter:

```
Symbol: MSFT
Price: 189
Quantity: 675
Side: sell
Type: limit
```

The sell order crosses the resting bid, so both sides get an execution
report:

```
Sending new order...
2026-10-22 07:42:16.970283 [INFO   ] (process  ) Trade received.
2026-10-22 07:42:16.970488 [INFO   ] (process  ) Trade: 17=MSFT_E_000002, 11=CLIENT1MSFT1 55=MSFT 32=675@31=189 54=1
2026-10-22 07:42:16.970843 [INFO   ] (process  ) Trade received.
2026-10-22 07:42:16.971032 [INFO   ] (process  ) Trade: 17=MSFT_E_000003, 11=CLIENT1MSFT2 55=MSFT 32=675@31=189 54=2
```

The market data feed shows the book is empty again and reports the trade:

```
Symbol: MSFT
+------------------+------------------+
| bid_prc, bid_qty | ask_prc, ask_qty |
+------------------+------------------+
+------------------+------------------+
Trade MSFT, 675.0@189.0.
```

### 5. Clean up

```bash
docker compose down --remove-orphans
```

## Image modes

The entry point selects what to run from the first argument.

| Command | What it does |
|---|---|
| `server` | Runs both gateways under the supervisor (default) |
| `client [config]` | Runs the interactive trading client, default `configs/client1.cfg` |
| `market-client [config]` | Runs the interactive market data client, default `configs/mdclient1.cfg` |
| `test` | Runs the test suite with `pytest` |
| `shell` | Opens a shell in `/app/pytradesim` |
| anything else | Executed verbatim, for example `python -m pytradesim.modules.orderbook` |

The `-d` / `--debug` flag of the clients is passed straight through:

```bash
docker run -it --network pytradesim -e EXCHANGE_HOST=pytradesim-exchange \
    pytradesim:latest client configs/client1.cfg -d
```

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `EXCHANGE_HOST` | `127.0.0.1` | Host the client connects to, substituted into `SocketConnectHost` |
| `RESET_ON_LOGON` | `Y` | Adds `ResetOnLogon=Y` to the rendered client config, see [Notes](#notes) |
| `RUNTIME_CONFIG_DIR` | `/tmp/pytradesim-configs` | Where the rendered FIX configs are written |
| `PYTRADESIM_INTERNAL_PORT` | `9000` | Order book channel between the two gateways |
| `PYTRADESIM_FIX_PORT` | `5001` | FIX order entry port |
| `PYTRADESIM_MD_FIX_PORT` | `5002` | FIX market data port |
| `PYTRADESIM_HEALTH_PORTS` | `5001,5002` | Ports the health check requires |

## Useful commands

```bash
# Follow the exchange log
docker compose logs -f exchange

# Check the health of the container
docker inspect --format '{{.State.Health.Status}}' pytradesim-exchange

# Run the scripted FIX baseline. Rebuild first so the image contains the
# CLIENT3 and MDCLIENT3 acceptor sessions.
docker compose build exchange
docker compose --profile baseline run --rm fix-baseline

# Create the read-model database and apply every file in secure_api/migrations.
docker compose up -d postgres
docker compose run --rm migrate

# Start Keycloak and the read API. Browser login is http://127.0.0.1:8080/ui/login.
# After sign-in, the market book is http://127.0.0.1:8080/ui/market.
# Alerts are http://127.0.0.1:8080/ui/alerts for analyst and admin.
# The API applies price_movement, spread_widening, and volume to each new book.
# Audit search is http://127.0.0.1:8080/ui/audit for admin.
# Swagger UI is http://127.0.0.1:8080/docs and uses the live OpenAPI document.
# Authorize there with Keycloak (PKCE). The redirect is /docs/oauth2-redirect.
# Demo users are market/market, analyst/analyst, and admin/admin.
# The session cookie is HttpOnly. The access token is not sent to the page.
docker compose up -d keycloak api

# Follow the FIX subscriber. It is a separate process from any web worker.
docker compose up -d subscriber
docker compose logs -f subscriber

# Place one resting bid and read it from the read model.
docker compose --profile order run --rm place-order

# Run one named scenario as CLIENT3. The only input is SCENARIO.
# price_movement, spread_widening, or volume. There is no price or quantity field.
docker compose --profile scenario run --rm -e SCENARIO=price_movement run-scenario
docker compose exec postgres psql -U pytradesim_app -d pytradesim -c "SELECT symbol, status, bids FROM market_snapshots"

# Run the test suite
docker run --rm pytradesim:latest test

# Open a shell inside the running exchange, it starts in /app
docker compose exec exchange bash

# Look at the FIX logs and the message store
docker compose exec exchange ls -l /app/pytradesim/logs /app/pytradesim/store

# Stop the exchange, the gateways are shut down gracefully
docker compose down
```

## Troubleshooting

**`exec /app/docker/entrypoint.sh: no such file or directory`.**
The script was copied into the image with Windows CRLF line endings.
`.gitattributes` keeps `docker/entrypoint.sh` and the FIX configs as LF.
Rebuild the image after pulling that attribute.

**The client hangs on "Enter choice" and never logs on.**
The exchange is not reachable. Check that it is healthy and that
`EXCHANGE_HOST` matches the exchange container name on the shared network.

**The client logs on, then logs out and retries.**
The FIX sequence numbers do not line up. The rendered client config sets
`ResetOnLogon=Y` to avoid this. If you replaced the config yourself, either
add `ResetOnLogon=Y` back or start the exchange with a fresh store.

**"address already in use" in the logs.**
The internal port `9000` or one of the FIX ports is taken, usually by
another exchange container. Stop the other one, or change
`PYTRADESIM_INTERNAL_PORT` and the matching `SocketConnectHost` /
`SocketConnectPort` entries.

**The market data client logs on but prints no snapshot.**
It only prints when the book for the subscribed symbol changes. Place an
order first, see the [demonstration](#demonstration).

**The build fails with "unknown mnemonic `xadd'" on an ARM machine.**
The `quickfix` patch was not applied. The build applies
`docker/patches/quickfix-1.15.1-portable-atomic-count.patch`, see
[Notes](#notes).

## Notes

**The `quickfix` patch.** `quickfix` 1.15.1 ships as a source distribution
only and `C++/AtomicCount.h` contains x86 inline assembly (`lock xadd`)
without an architecture guard, so it cannot be assembled on aarch64. The
build applies a patch that swaps in a `__atomic_fetch_add` based
implementation, which works on amd64 and arm64 alike.

**Why `ResetOnLogon`.** Client containers are short lived, they start their
FIX sequence numbers at 1 while a long running exchange expects a higher
number. The logon is rejected, the client reconnects and the market data
subscription, which is sent right after the logon, is lost. With
`ResetOnLogon=Y` the client resets its counters and asks the exchange to
reset its own.

**Where state lives.** FIX logs and the message store are written to
`/app/pytradesim/logs` and `/app/pytradesim/store` inside the container.
They live in the container filesystem, so they disappear with the container.
Mount a volume on those paths if you want to keep them.

**Image size.** The image is around 292 MB. The base Python image accounts
for most of it, the compiled `quickfix` extension is stripped of its debug
symbols during the build.
