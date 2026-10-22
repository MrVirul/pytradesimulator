#!/bin/sh
#
# Entry point for the pytradesim container.
#
# Modes:
#   server         run the exchange and market data gateways (default)
#   client         run the interactive trading client
#   market-client  run the interactive market data client
#   test           run the test suite
#   shell          start an interactive shell
#   <anything>     executed verbatim
#
set -eu

APP_HOME="${APP_HOME:-/app}"
APP_DIR="${APP_DIR:-/app/pytradesim}"
EXCHANGE_HOST="${EXCHANGE_HOST:-127.0.0.1}"
RESET_ON_LOGON="${RESET_ON_LOGON:-Y}"
RUNTIME_CONFIG_DIR="${RUNTIME_CONFIG_DIR:-/tmp/pytradesim-configs}"

log() {
    printf '[entrypoint] %s\n' "$*"
}

# Render a FIX configuration with the exchange host substituted, so that
# clients can reach the gateways when they live in another container.
# The stock configuration points at 127.0.0.1, which only works when the
# client shares a network namespace with the gateways.
#
# ResetOnLogon is added because client containers are short lived: they
# start their sequence numbers at 1 while a long running exchange expects
# a higher number, which makes the logon bounce. With the reset the client
# asks the exchange to start its sequence numbers over as well.
render_config() {
    src="$1"
    dst="$2"

    mkdir -p "$(dirname "$dst")"
    sed "s|^SocketConnectHost=.*|SocketConnectHost=${EXCHANGE_HOST}|" "$src" > "$dst"

    if [ "$RESET_ON_LOGON" = "Y" ]; then
        printf 'ResetOnLogon=Y\n' >> "$dst"
    fi

    log "rendered ${dst} pointing at exchange host ${EXCHANGE_HOST}"
}

command="${1:-server}"

if [ "$#" -gt 0 ]; then
    shift
fi

case "$command" in
    server)
        cd "$APP_DIR"
        exec python /app/docker/supervisor.py
        ;;

    client)
        cd "$APP_DIR"
        src="${1:-configs/client1.cfg}"
        if [ "$#" -gt 0 ]; then
            shift
        fi
        dst="$RUNTIME_CONFIG_DIR/$(basename "$src")"
        render_config "$src" "$dst"
        exec python client.py "$dst" "$@"
        ;;

    market-client)
        cd "$APP_DIR"
        src="${1:-configs/mdclient1.cfg}"
        if [ "$#" -gt 0 ]; then
            shift
        fi
        dst="$RUNTIME_CONFIG_DIR/$(basename "$src")"
        render_config "$src" "$dst"
        exec python market_client.py "$dst" "$@"
        ;;

    test)
        cd "$APP_HOME"
        exec pytest tests -v "$@"
        ;;

    shell)
        cd "$APP_DIR"
        exec /bin/bash "$@"
        ;;

    *)
        exec "$command" "$@"
        ;;
esac
