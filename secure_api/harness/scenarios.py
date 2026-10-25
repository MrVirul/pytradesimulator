"""Named CLIENT3 scenarios. The only input is the scenario name.

Symbol, side, price, and quantity live in this module. A request that
carries any other field is rejected. This module does not import
QuickFIX and does not open a socket.
"""


SCENARIOS = {
    "price_movement": {
        "symbol": "PRICE",
        "orders": [
            {"side": "buy", "quantity": 10, "price": 150, "expect": "0"},
            {"side": "sell", "quantity": 10, "price": 150, "expect": "2"},
        ],
    },
    "spread_widening": {
        "symbol": "SPREAD",
        "orders": [
            {"side": "buy", "quantity": 10, "price": 50, "expect": "0"},
            {"side": "sell", "quantity": 10, "price": 60, "expect": "0"},
        ],
    },
    "volume": {
        "symbol": "VOLUME",
        "orders": [
            {"side": "sell", "quantity": 400, "price": 101, "expect": "0"},
            {"side": "buy", "quantity": 400, "price": 101, "expect": "2", "pause_after": 2},
            {"side": "sell", "quantity": 350, "price": 102, "expect": "0"},
            {"side": "buy", "quantity": 350, "price": 102, "expect": "2", "pause_after": 2},
            {"side": "sell", "quantity": 300, "price": 103, "expect": "0"},
            {"side": "buy", "quantity": 300, "price": 103, "expect": "2"},
        ],
    },
}


ACCESS_SCENARIOS = ("unauthorized_access", "rate_limit_abuse")


class ScenarioError(Exception):
    def __init__(self, reason):
        super(ScenarioError, self).__init__(reason)
        self.reason = reason


def resolve_scenario(argv, environ):
    """One positional name, or SCENARIO. Extra arguments are an order payload."""
    if len(argv) > 1:
        raise ScenarioError("free_form_order")
    if argv:
        name = argv[0]
    else:
        name = environ.get("SCENARIO", "")
    if name not in SCENARIOS:
        raise ScenarioError("unknown_scenario")
    return name


def parse_request(payload):
    """Accept ``{"scenario": "<name>"}`` and nothing else."""
    if not isinstance(payload, dict):
        raise ScenarioError("invalid_request")
    if any(key != "scenario" for key in payload):
        raise ScenarioError("free_form_order")
    name = payload.get("scenario")
    if not isinstance(name, str):
        raise ScenarioError("unknown_scenario")
    if name in SCENARIOS or name in ACCESS_SCENARIOS:
        return name
    raise ScenarioError("unknown_scenario")


def orders_for(name):
    """Return the fixed symbol and orders. The caller cannot change them."""
    if name not in SCENARIOS:
        raise ScenarioError("unknown_scenario")
    spec = SCENARIOS[name]
    orders = []
    for order in spec["orders"]:
        copied = {
            "side": order["side"],
            "quantity": order["quantity"],
            "price": order["price"],
            "expect": order["expect"],
        }
        if "pause_after" in order:
            copied["pause_after"] = order["pause_after"]
        orders.append(copied)
    return spec["symbol"], orders
