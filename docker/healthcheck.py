#!/usr/bin/env python3
"""Health check for the pytradesim container.

Reports the container as healthy once both FIX gateways accept connections.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from netports import env_ports, listening_ports  # noqa: E402


def main():
    expected = env_ports("PYTRADESIM_HEALTH_PORTS", "5001,5002")
    listening = listening_ports()
    missing = [port for port in expected if port not in listening]

    if missing:
        sys.stderr.write(
            "not listening on: {}\n".format(", ".join(str(port) for port in missing))
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
