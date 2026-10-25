"""Demo settings come from the environment and keep today's defaults."""

from secure_api.app.config import demo_users, show_demo_credentials


def test_demo_defaults_match_the_realm(monkeypatch):
    monkeypatch.delenv("DEMO_MARKET_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_ANALYST_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("SHOW_DEMO_CREDENTIALS", raising=False)
    names = {user["username"]: user["password"] for user in demo_users()}
    assert names == {"market": "market", "analyst": "analyst", "admin": "admin"}
    assert show_demo_credentials() is True


def test_demo_password_override(monkeypatch):
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "changeme")
    monkeypatch.setenv("SHOW_DEMO_CREDENTIALS", "0")
    admin = [user for user in demo_users() if user["username"] == "admin"][0]
    assert admin["password"] == "changeme"
    assert show_demo_credentials() is False
