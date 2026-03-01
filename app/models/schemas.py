"""
Data schemas: dataclasses for game, session, and hint flow.

All fields are plain data; no ORM or external calls.
"""

from dataclasses import dataclass


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
    """Result of checking a guess: whether it was correct and optional hint text."""

    correct: bool
    hint_text: str | None = None
