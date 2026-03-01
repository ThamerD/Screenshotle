"""
Application configuration loaded from environment variables.

All secrets and environment-specific values are read here so the rest of the app
stays testable and deployable without hardcoded keys.
"""

import os


def get_env(key: str, default: str | None = None) -> str | None:
    """Return the value of an environment variable, or default if unset."""
    return os.environ.get(key, default)


class Config:
    """
    Configuration for the Screenshotle app.
    Values are read from the environment at import time (or when create_app runs).
    """

    # OpenAI (hint generation and guess matching)
    OPENAI_API_KEY: str | None = None

    # IGDB via Twitch OAuth2
    TWITCH_CLIENT_ID: str | None = None
    TWITCH_CLIENT_SECRET: str | None = None

    # Optional: app title / debug
    APP_NAME: str = "Screenshotle"
    DEBUG: bool = False

    def __init__(self) -> None:
        self.OPENAI_API_KEY = get_env("OPENAI_API_KEY")
        self.TWITCH_CLIENT_ID = get_env("TWITCH_CLIENT_ID") or get_env("IGDB_CLIENT_ID")
        self.TWITCH_CLIENT_SECRET = get_env("TWITCH_CLIENT_SECRET") or get_env("IGDB_CLIENT_SECRET")
        self.APP_NAME = get_env("APP_NAME", "Screenshotle") or "Screenshotle"
        self.DEBUG = get_env("DEBUG", "").lower() in ("1", "true", "yes")

    def has_igdb_credentials(self) -> bool:
        """True if Twitch (IGDB) client id and secret are set."""
        return bool(self.TWITCH_CLIENT_ID and self.TWITCH_CLIENT_SECRET)

    def has_openai_key(self) -> bool:
        """True if OpenAI API key is set."""
        return bool(self.OPENAI_API_KEY)
