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
    dict_to_game_session,
    game_session_to_dict,
)

__all__ = [
    "Game",
    "GameSession",
    "Generation",
    "HintRequest",
    "HintResult",
    "dict_to_game_session",
    "game_session_to_dict",
]
