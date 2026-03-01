"""
Data shapes for Screenshotle. No database, no API calls.

Used by clients, services, and routes to pass structured data.
"""

from app.models.schemas import (
    Game,
    GameSession,
    Generation,
    HintRequest,
    HintResult,
)

__all__ = [
    "Game",
    "GameSession",
    "Generation",
    "HintRequest",
    "HintResult",
]
