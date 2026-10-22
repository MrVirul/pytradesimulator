#!/usr/bin/env python3
"""Supervisor for the pytradesim gateways.

The exchange gateway (``server.py``) and the market data gateway
(``market_data.py``) hand order books to each other over a
``multiprocessing`` connection bound to ``localhost``, so both processes have
to live in the same network namespace. They are therefore started together
here, in the right order, and the container lives as long as both of them do.

Order matters: ``server.py`` connects to the market data listener as soon as
it starts and does not retry, so the market data gateway has to be listening
on the internal port before the exchange gateway is launched.
"""

import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from netports import wait_for_port  # noqa: E402

APP_DIR = os.environ.get("APP_DIR", "/app/pytradesim")
INTERNAL_PORT = int(os.environ.get("PYTRADESIM_INTERNAL_PORT", "9000"))
FIX_PORT = int(os.environ.get("PYTRADESIM_FIX_PORT", "5001"))
MD_FIX_PORT = int(os.environ.get("PYTRADESIM_MD_FIX_PORT", "5002"))
START_TIMEOUT = float(os.environ.get("PYTRADESIM_START_TIMEOUT", "60"))

children = []
shutting_down = False


def log(message):
    sys.stdout.write("[supervisor] {}\n".format(message))
    sys.stdout.flush()


def spawn(name, script):
    log("starting {}".format(name))
    process = subprocess.Popen([sys.executable, script], cwd=APP_DIR)
    children.append((name, process))
    log("started {} with pid {}".format(name, process.pid))
    return process


def stop_children():
    for name, process in children:
        if process.poll() is None:
            log("stopping {}".format(name))
            process.terminate()


def on_signal(signum, _frame):
    global shutting_down

    if shutting_down:
        return

    shutting_down = True
    log("received signal {}, shutting down".format(signum))
    stop_children()


def wait_for_children(timeout=10):
    for name, process in children:
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log("{} did not exit in time, killing it".format(name))
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


def wait_for_port_or_exit(port, process, timeout):
    """Wait until *port* is listening, or until *process* gives up.

    Returns True when the port came up, False when the process died first
    and None on timeout.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        if process.poll() is not None:
            return False

        if wait_for_port(port, timeout=0.2, interval=0.05):
            return True

    return None


def main():
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    market_data = spawn("market data gateway", "market_data.py")

    ready = wait_for_port_or_exit(INTERNAL_PORT, market_data, START_TIMEOUT)

    if ready is False:
        log("market data gateway exited during startup")
        stop_children()
        wait_for_children()
        return 1

    if ready is None:
        log(
            "market data gateway never listened on the internal port {}".format(
                INTERNAL_PORT
            )
        )
        stop_children()
        wait_for_children()
        return 1

    ready = wait_for_port_or_exit(MD_FIX_PORT, market_data, START_TIMEOUT)

    if ready is not True:
        log("market data gateway never listened on port {}".format(MD_FIX_PORT))
        stop_children()
        wait_for_children()
        return 1

    exchange = spawn("exchange gateway", "server.py")

    ready = wait_for_port_or_exit(FIX_PORT, exchange, START_TIMEOUT)

    if ready is not True:
        log("exchange gateway never listened on port {}".format(FIX_PORT))
        stop_children()
        wait_for_children()
        return 1

    log(
        "exchange gateway accepting FIX orders on {}, market data gateway on {}".format(
            FIX_PORT, MD_FIX_PORT
        )
    )
    log("ready")

    while True:
        for name, process in children:
            code = process.poll()

            if code is None:
                continue

            if shutting_down:
                log("{} stopped".format(name))
                wait_for_children()
                return 0

            log("{} exited unexpectedly with code {}".format(name, code))
            stop_children()
            wait_for_children()
            return code if code else 1

        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
