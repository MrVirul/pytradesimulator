"""Process settings. Read on each call so tests can change the environment."""

import os


def jwt_public_key():
    key = os.environ.get("JWT_PUBLIC_KEY", "")
    if not key:
        raise RuntimeError("JWT_PUBLIC_KEY is required")
    return key.replace("\\n", "\n")


def jwt_issuer():
    return os.environ.get("JWT_ISSUER", "https://issuer.test/realms/pytradesim")


def jwt_audience():
    return os.environ.get("JWT_AUDIENCE", "pytradesim-api")


def database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    return url


def public_api_url():
    return os.environ.get("PUBLIC_API_URL", "http://localhost:8080").rstrip("/")


def public_keycloak_url():
    configured = os.environ.get("PUBLIC_KEYCLOAK_URL") or os.environ.get(
        "KEYCLOAK_PUBLIC_URL", "http://localhost:8081"
    )
    return configured.rstrip("/")


def keycloak_internal_url():
    return os.environ.get("KEYCLOAK_INTERNAL_URL", "").rstrip("/")


def keycloak_realm():
    return os.environ.get("KEYCLOAK_REALM", "pytradesim")


def keycloak_client_id():
    return os.environ.get("KEYCLOAK_CLIENT_ID", "pytradesim-ui")


def keycloak_redirect_uri():
    configured = os.environ.get("KEYCLOAK_REDIRECT_URI", "")
    if configured:
        return configured
    return public_api_url() + "/ui/callback"


def scenario_client_id():
    return os.environ.get("KEYCLOAK_SCENARIO_CLIENT_ID", "pytradesim-scenario")


def scenario_client_secret():
    return os.environ.get("KEYCLOAK_SCENARIO_CLIENT_SECRET", "pytradesim-scenario")


def show_demo_credentials():
    return os.environ.get("SHOW_DEMO_CREDENTIALS", "1") != "0"


def session_minutes():
    try:
        minutes = int(os.environ.get("SESSION_MINUTES", "15"))
    except ValueError:
        minutes = 15
    if minutes < 1:
        return 1
    return minutes


def cookie_secure():
    return os.environ.get("COOKIE_SECURE", "1") != "0"


def demo_users():
    """Demo accounts. Passwords come from the environment, not from the image."""
    return [
        {
            "username": "market",
            "password": os.environ.get("DEMO_MARKET_PASSWORD", "market"),
            "role": "market_data_client",
            "opens": "Market",
        },
        {
            "username": "analyst",
            "password": os.environ.get("DEMO_ANALYST_PASSWORD", "analyst"),
            "role": "surveillance_analyst",
            "opens": "Market and Surveillance",
        },
        {
            "username": "admin",
            "password": os.environ.get("DEMO_ADMIN_PASSWORD", "admin"),
            "role": "security_admin",
            "opens": "Market, Surveillance, Security, and Scenarios",
        },
    ]
