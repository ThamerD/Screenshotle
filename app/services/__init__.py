"""
Gameplay logic: pick random game, resolve generation from release date, session state, call clients for hints.
"""

from app.services.game_service import (
    GameService,
    get_generation_from_release_date,
    raw_dict_to_game,
)

__all__ = ["GameService", "get_generation_from_release_date", "raw_dict_to_game"]
