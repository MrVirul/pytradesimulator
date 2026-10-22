"""Role to permission map shared by REST and, later, HTMX routes."""

ROLE_PERMISSIONS = {
    "market_data_client": frozenset(["market-data:read"]),
    "surveillance_analyst": frozenset(["market-data:read", "alerts:read"]),
    "security_admin": frozenset(
        ["market-data:read", "alerts:read", "audit:read", "scenarios:run"]
    ),
}

RATE_CATEGORY = {
    "market-data:read": "market_data",
    "alerts:read": "alerts",
    "audit:read": "audit",
    "scenarios:run": "scenario",
}


def allows(roles, permission):
    for role in roles or []:
        granted = ROLE_PERMISSIONS.get(role)
        if granted is not None and permission in granted:
            return True
    return False
