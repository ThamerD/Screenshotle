"""
Data schemas: dataclasses for game, session, and hint flow.
Serialization to/from JSON-serializable dicts for session storage.

All fields are plain data; no ORM or external calls.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Generation:
    """Console era for hinting: label and primary consoles (e.g. 'PlayStation 2', 'Xbox')."""

    label: str
    primary_consoles: tuple[str, ...]


@dataclass
class Game:
    """
    A video game used in a round: name, genres, generation, and screenshot URLs.
    Built from IGDB (or cache); stored in session for the current round.
    """

    id: int
    name: str
    genres: list[str]
    generation: Generation | None
    screenshot_urls: list[str]


@dataclass
class GameSession:
    """
    Per-player session state: the current game (if any), which screenshot we're on,
    and how many guesses have been made.
    """

    current_game: Game | None = None
    screenshot_index: int = 0
    attempt_count: int = 0


@dataclass
class HintRequest:
    """Input for hint generation: user's guess and the correct game's metadata."""

    guess: str
    correct_game_name: str
    generation: Generation | None
    genres: list[str]


@dataclass
class HintResult:
    """Result of checking a guess: correct flag, general hint, and genre/era hints (green=match, red=mismatch)."""

    correct: bool
    hint_text: str | None = None
    genre_matches: list[str] = field(default_factory=list)  # guessed game's genres that match correct → show green
    genre_mismatches: list[str] = field(default_factory=list)  # guessed game's genres that don't match → show red
    generation_text: str | None = None  # guessed game's era text (e.g. "Eighth generation (PS4, ...)")
    generation_matched: bool = False  # True → show generation_text in green, False → red


# --- Session serialization (for server-side session store) ---


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
