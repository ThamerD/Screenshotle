"""
Unit tests for app.config: env loading and helpers.
"""

import os
import pytest


# Import Config after we can patch env, so we reload per test
@pytest.fixture
def config_class():
    """Return the Config class; tests will patch os.environ then instantiate."""
    from app.config import Config
    return Config


def test_config_reads_openai_key_from_env(config_class, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    config = config_class()
    assert config.OPENAI_API_KEY == "sk-test"
    assert config.has_openai_key() is True


def test_config_has_openai_key_false_when_unset(config_class, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = config_class()
    assert config.has_openai_key() is False


def test_config_reads_twitch_credentials_from_env(config_class, monkeypatch):
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id1")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret1")
    config = config_class()
    assert config.TWITCH_CLIENT_ID == "id1"
    assert config.TWITCH_CLIENT_SECRET == "secret1"
    assert config.has_igdb_credentials() is True


def test_config_accepts_igdb_prefixed_env(config_class, monkeypatch):
    monkeypatch.delenv("TWITCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("TWITCH_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("IGDB_CLIENT_ID", "igdb-id")
    monkeypatch.setenv("IGDB_CLIENT_SECRET", "igdb-secret")
    config = config_class()
    assert config.TWITCH_CLIENT_ID == "igdb-id"
    assert config.TWITCH_CLIENT_SECRET == "igdb-secret"
    assert config.has_igdb_credentials() is True


def test_config_has_igdb_credentials_false_when_missing(config_class, monkeypatch):
    monkeypatch.delenv("TWITCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("TWITCH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("IGDB_CLIENT_ID", raising=False)
    monkeypatch.delenv("IGDB_CLIENT_SECRET", raising=False)
    config = config_class()
    assert config.has_igdb_credentials() is False


def test_config_app_name_default(config_class, monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)
    config = config_class()
    assert config.APP_NAME == "Screenshotle"


def test_config_app_name_from_env(config_class, monkeypatch):
    monkeypatch.setenv("APP_NAME", "My Game")
    config = config_class()
    assert config.APP_NAME == "My Game"


def test_config_debug_false_by_default(config_class, monkeypatch):
    monkeypatch.delenv("DEBUG", raising=False)
    config = config_class()
    assert config.DEBUG is False


def test_config_debug_true_when_env_set(config_class, monkeypatch):
    monkeypatch.setenv("DEBUG", "1")
    config = config_class()
    assert config.DEBUG is True
