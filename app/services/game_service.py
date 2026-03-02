"""
Gameplay logic: pick random game, map release date to Generation, session state, call clients for hints.

Depends on app.models and app.clients. No HTTP or session storage; callers (routes) own session.
"""

import json
import os
import re
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.clients import IGDBClient, OpenAIClient
from app.models import Game, GameSession, Generation, HintRequest, HintResult


# Console generations from Wikipedia: History of video game consoles § Home console history
# https://en.wikipedia.org/wiki/History_of_video_game_consoles#Console_generations
# Each entry: (year_start_inclusive, year_end_inclusive, label, primary_consoles)
CONSOLE_GENERATIONS: list[tuple[int, int, str, tuple[str, ...]]] = [
    (1972, 1975, "First generation (1972–1983)", ("Magnavox Odyssey", "Atari Pong", "Coleco Telstar series")),
    (1976, 1982, "Second generation (1976–1992)", ("Fairchild Channel F", "Atari 2600", "Odyssey 2", "Intellivision", "ColecoVision")),
    (1983, 1986, "Third generation / 8-bit (1983–2003)", ("Nintendo Entertainment System (NES)", "Sega Master System", "Atari 7800")),
    (1987, 1992, "Fourth generation / 16-bit (1987–2004)", ("TurboGrafx-16", "Sega Genesis", "Neo Geo", "Super NES")),
    (1993, 1997, "Fifth generation / 32-bit (1993–2006)", ("3DO", "Atari Jaguar", "Sega Saturn", "PlayStation", "Nintendo 64")),
    (1998, 2004, "Sixth generation (1998–2013)", ("Dreamcast", "PlayStation 2", "GameCube", "Xbox")),
    (2005, 2011, "Seventh generation (2005–2017)", ("Xbox 360", "PlayStation 3", "Wii")),
    (2012, 2019, "Eighth generation (2012–present)", ("Wii U", "PlayStation 4", "Xbox One", "Nintendo Switch")),
    (2020, 9999, "Ninth generation (2020–present)", ("Xbox Series X/S", "PlayStation 5")),
]


def get_generation_from_release_date(first_release_date: int | None) -> Generation | None:
    """Map Unix timestamp to console generation (label + primary_consoles). Returns None if no date."""
    if first_release_date is None:
        return None
    year = datetime.fromtimestamp(first_release_date, tz=timezone.utc).year
    for start, end, label, consoles in CONSOLE_GENERATIONS:
        if start <= year <= end:
            return Generation(label=label, primary_consoles=consoles)
    return None


def _write_pool_debug(raw_list: list[dict[str, Any]]) -> None:
    """When DEBUG=1, write the raw popular games list to popular_games.json for verification."""
    if os.environ.get("DEBUG", "").lower() not in ("1", "true", "yes"):
        return
    try:
        path = Path(__file__).resolve().parent.parent.parent / "popular_games.json"
        # Sort by first_release_date ascending (oldest first); treat None as 0 so null dates sort first
        sorted_list = sorted(
            raw_list,
            key=lambda g: g.get("first_release_date") or 0,
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sorted_list, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def raw_dict_to_game(raw: dict[str, Any]) -> Game:
    """
    Convert a game dict from IGDBClient.get_popular_games into app.models.Game.
    Expects keys: id, name, genres (list[str]), first_release_date (int|None), screenshot_urls (list[str]).
    """
    first_release_date = raw.get("first_release_date")
    generation = get_generation_from_release_date(first_release_date)
    return Game(
        id=raw["id"],
        name=raw["name"],
        genres=raw.get("genres") or [],
        generation=generation,
        screenshot_urls=raw.get("screenshot_urls") or [],
    )


class GameService:
    """
    Gameplay service: fetch game pool, start a round, resolve current screenshot, submit guess for hints.
    Uses IGDBClient for games and OpenAIClient for guess check + hint text.
    """

    def __init__(self, igdb_client: IGDBClient, openai_client: OpenAIClient) -> None:
        self._igdb = igdb_client
        self._openai = openai_client

    def get_game_pool(self, limit: int = 500) -> list[Game]:
        """Fetch popular games from IGDB and return as list of Game (with generation from release date)."""
        raw_list = self._igdb.get_popular_games(limit=limit)
        # Write full list to JSON for verification (id, name, genres, first_release_date, screenshot_urls)
        _write_pool_debug(raw_list)
        return [raw_dict_to_game(r) for r in raw_list]

    def start_new_game(self, pool: list[Game]) -> GameSession:
        """Pick a random game from the pool (pool is expected to have only games with enough screenshots)."""
        if not pool:
            return GameSession(current_game=None, screenshot_index=0, attempt_count=0)
        game = random.choice(pool)
        return GameSession(current_game=game, screenshot_index=0, attempt_count=0)

    def get_current_screenshot_url(self, session: GameSession) -> str | None:
        """Return the URL of the current screenshot for the session's game, or None if no game or no URLs."""
        if session.current_game is None or not session.current_game.screenshot_urls:
            return None
        idx = min(session.screenshot_index, len(session.current_game.screenshot_urls) - 1)
        return session.current_game.screenshot_urls[idx]

    def submit_guess(self, session: GameSession, guess: str, pool: list[Game] | None = None) -> HintResult:
        """
        Check the guess against the correct game and return HintResult (correct flag + hints).
        If pool is provided and guess is wrong, compute genre_match and generation_match_text.
        Does not mutate session; caller should update attempt_count and screenshot_index.
        """
        if session.current_game is None:
            return HintResult(correct=False, hint_text=None)
        request = HintRequest(
            guess=guess.strip(),
            correct_game_name=session.current_game.name,
            generation=session.current_game.generation,
            genres=session.current_game.genres,
        )
        result = self._openai.check_guess_and_get_hint(request)
        if result.correct or not pool:
            return result
        guessed_game = _find_game_by_name(pool, request.guess)
        if guessed_game is None:
            return result
        correct_genres = set(session.current_game.genres)
        guess_genres_list = list(dict.fromkeys(guessed_game.genres))  # preserve order, no dupes
        genre_matches = [g for g in guess_genres_list if g in correct_genres]
        genre_mismatches = [g for g in guess_genres_list if g not in correct_genres]
        cgen = session.current_game.generation
        ggen = guessed_game.generation
        generation_text = None
        generation_matched = False
        if ggen:
            generation_text = f"{ggen.label} ({', '.join(ggen.primary_consoles)})"
            generation_matched = cgen is not None and cgen.label == ggen.label
        return HintResult(
            correct=result.correct,
            hint_text=result.hint_text,
            genre_matches=genre_matches,
            genre_mismatches=genre_mismatches,
            generation_text=generation_text,
            generation_matched=generation_matched,
        )


def _normalize_for_match(s: str) -> str:
    """Lowercase, strip, remove leading 'the ', collapse spaces."""
    s = s.strip().lower()
    if s.startswith("the "):
        s = s[4:].strip()
    return " ".join(s.split())


def _words(s: str) -> set[str]:
    """Alphanumeric words (digits allowed) for overlap matching."""
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def _find_game_by_name(pool: list[Game], guess: str) -> Game | None:
    """Return a game from the pool whose name matches guess (exact, substring, or word overlap)."""
    g = _normalize_for_match(guess)
    if not g:
        return None
    g_name = g.replace(":", "").replace("-", " ")
    for game in pool:
        n = _normalize_for_match(game.name)
        if n == g_name:
            return game
    for game in pool:
        n = _normalize_for_match(game.name)
        if g_name in n or n in g_name:
            return game
    # Word overlap: guess words all appear in game name (or vice versa for short names)
    guess_words = _words(guess)
    if not guess_words:
        return None
    for game in pool:
        name_words = _words(game.name)
        if guess_words <= name_words or (len(guess_words) >= 2 and name_words <= guess_words):
            return game
    return None
