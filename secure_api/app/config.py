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
