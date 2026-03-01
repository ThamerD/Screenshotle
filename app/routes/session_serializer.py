"""
Serialize GameSession to/from session storage (JSON-serializable dict).

Used by game routes to persist session in cookie-backed session middleware.
"""

from typing import Any

from app.models import Game, GameSession, Generation


def _generation_to_dict(gen: Generation | None) -> dict[str, Any] | None:
    if gen is None:
        return None
    return {"label": gen.label, "primary_consoles": list(gen.primary_consoles)}


def _dict_to_generation(d: dict[str, Any] | None) -> Generation | None:
    if d is None:
        return None
    return Generation(label=d["label"], primary_consoles=tuple(d["primary_consoles"]))


def _game_to_dict(g: Game | None) -> dict[str, Any] | None:
    if g is None:
        return None
    return {
        "id": g.id,
        "name": g.name,
        "genres": g.genres,
        "generation": _generation_to_dict(g.generation),
        "screenshot_urls": g.screenshot_urls,
    }


def _dict_to_game(d: dict[str, Any] | None) -> Game | None:
    if d is None:
        return None
    return Game(
        id=d["id"],
        name=d["name"],
        genres=d.get("genres") or [],
        generation=_dict_to_generation(d.get("generation")),
        screenshot_urls=d.get("screenshot_urls") or [],
    )


def game_session_to_dict(gs: GameSession) -> dict[str, Any]:
    """Convert GameSession to a JSON-serializable dict for session storage."""
    return {
        "current_game": _game_to_dict(gs.current_game),
        "screenshot_index": gs.screenshot_index,
        "attempt_count": gs.attempt_count,
    }


def dict_to_game_session(d: dict[str, Any]) -> GameSession:
    """Build GameSession from a dict loaded from session storage."""
    return GameSession(
        current_game=_dict_to_game(d.get("current_game")),
        screenshot_index=int(d.get("screenshot_index", 0)),
        attempt_count=int(d.get("attempt_count", 0)),
    )
