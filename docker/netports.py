"""Helpers to inspect the TCP sockets a process is listening on.

The market data gateway speaks ``multiprocessing.connection`` on the
internal port, and that listener accepts exactly one connection. Probing it
with a plain ``connect()`` would consume the ``accept()`` the gateway is
waiting for and the exchange gateway would never be able to attach. Reading
``/proc/net/tcp`` lets us detect readiness without touching the socket.
"""

import os
import time

TCP_LISTEN = "0A"


def listening_ports():
    """Return the set of TCP ports currently in the LISTEN state."""
    ports = set()

    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path) as handle:
                next(handle, None)  # skip the header row
                for line in handle:
                    fields = line.split()
                    if len(fields) < 4 or fields[3] != TCP_LISTEN:
                        continue
                    ports.add(int(fields[1].rsplit(":", 1)[1], 16))
        except OSError:
            # Not running on Linux, or /proc is not mounted.
            continue

    return ports


def is_listening(port):
    """Return True when *port* is bound and listening."""
    return port in listening_ports()


def wait_for_port(port, timeout=60.0, interval=0.2):
    """Block until *port* is listening, returning False on timeout."""
    deadline = time.time() + timeout

    while time.time() < deadline:
        if is_listening(port):
            return True
        time.sleep(interval)

    return False


def parse_ports(value):
    """Parse a comma separated list of ports into a list of integers."""
    ports = []

    for chunk in value.split(","):
        chunk = chunk.strip()
        if chunk:
            ports.append(int(chunk))

    return ports


def env_ports(name, default):
    """Parse a comma separated port list from the environment."""
    return parse_ports(os.environ.get(name, default))
