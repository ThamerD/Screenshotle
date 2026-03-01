"""
Unit tests for app.services.game_service (mocked IGDB and OpenAI clients).
"""

import pytest
from unittest.mock import MagicMock

from app.models import Game, GameSession, Generation
from app.services.game_service import (
    get_generation_from_release_date,
    raw_dict_to_game,
    GameService,
)


# --- get_generation_from_release_date ---


def test_get_generation_from_release_date_none_for_none():
    assert get_generation_from_release_date(None) is None


def test_get_generation_from_release_date_maps_year_to_generation():
    # 2015 -> Eighth generation
    ts_2015 = 1420070400  # 2015-01-01 UTC
    gen = get_generation_from_release_date(ts_2015)
    assert gen is not None
    assert "Eighth" in gen.label
    assert "PlayStation 4" in gen.primary_consoles


def test_get_generation_from_release_date_seventh_gen():
    # 2008 -> Seventh generation
    ts_2008 = 1199145600  # 2008-01-01 UTC
    gen = get_generation_from_release_date(ts_2008)
    assert gen is not None
    assert "Seventh" in gen.label


def test_get_generation_from_release_date_ninth_gen():
    # 2022 -> Ninth generation
    ts_2022 = 1640995200  # 2022-01-01 UTC
    gen = get_generation_from_release_date(ts_2022)
    assert gen is not None
    assert "Ninth" in gen.label


# --- raw_dict_to_game ---


def test_raw_dict_to_game_builds_game_with_generation():
    raw = {
        "id": 42,
        "name": "Test Game",
        "genres": ["Action", "RPG"],
        "first_release_date": 1420070400,
        "screenshot_urls": ["https://example.com/1.jpg"],
    }
    game = raw_dict_to_game(raw)
    assert game.id == 42
    assert game.name == "Test Game"
    assert game.genres == ["Action", "RPG"]
    assert game.generation is not None
    assert "Eighth" in (game.generation.label or "")
    assert len(game.screenshot_urls) == 1
    assert game.screenshot_urls[0] == "https://example.com/1.jpg"


def test_raw_dict_to_game_none_date_gives_none_generation():
    raw = {
        "id": 1,
        "name": "No Date",
        "genres": [],
        "first_release_date": None,
        "screenshot_urls": [],
    }
    game = raw_dict_to_game(raw)
    assert game.generation is None
    assert game.screenshot_urls == []


# --- GameService ---


@pytest.fixture
def mock_igdb():
    return MagicMock()


@pytest.fixture
def mock_openai():
    return MagicMock()


@pytest.fixture
def game_service(mock_igdb, mock_openai):
    return GameService(igdb_client=mock_igdb, openai_client=mock_openai)


@pytest.fixture
def sample_pool():
    return [
        Game(
            id=1,
            name="Game One",
            genres=["Action"],
            generation=Generation("Eighth generation", ("PS4", "Xbox One")),
            screenshot_urls=["https://img1.jpg", "https://img2.jpg"],
        ),
        Game(
            id=2,
            name="Game Two",
            genres=["RPG"],
            generation=None,
            screenshot_urls=["https://img3.jpg"],
        ),
    ]


def test_get_game_pool_calls_igdb_and_converts_to_games(game_service, mock_igdb):
    mock_igdb.get_popular_games.return_value = [
        {"id": 10, "name": "X", "genres": ["Adventure"], "first_release_date": 1420070400, "screenshot_urls": ["u1"]},
    ]
    pool = game_service.get_game_pool(limit=100)
    mock_igdb.get_popular_games.assert_called_once_with(limit=100)
    assert len(pool) == 1
    assert pool[0].id == 10
    assert pool[0].name == "X"
    assert pool[0].generation is not None


def test_start_new_game_empty_pool_returns_session_with_no_game(game_service):
    session = game_service.start_new_game([])
    assert session.current_game is None
    assert session.screenshot_index == 0
    assert session.attempt_count == 0


def test_start_new_game_picks_from_pool_and_resets_session(game_service, sample_pool):
    session = game_service.start_new_game(sample_pool)
    assert session.current_game is not None
    assert session.current_game.name in ("Game One", "Game Two")
    assert session.screenshot_index == 0
    assert session.attempt_count == 0


def test_start_new_game_exclude_ids_avoids_recent_and_falls_back(game_service, sample_pool):
    """When exclude_ids is set, pick from non-excluded; when all excluded, fall back to full pool."""
    session = game_service.start_new_game(sample_pool, exclude_ids={1})
    assert session.current_game is not None
    assert session.current_game.id == 2  # only Game Two (id 2) is not excluded
    session2 = game_service.start_new_game(sample_pool, exclude_ids={1, 2})
    assert session2.current_game is not None  # fallback to full pool when no candidates
    assert session2.current_game.id in (1, 2)


def test_get_current_screenshot_url_none_when_no_game(game_service):
    session = GameSession(current_game=None, screenshot_index=0, attempt_count=0)
    assert game_service.get_current_screenshot_url(session) is None


def test_get_current_screenshot_url_returns_url_at_index(game_service, sample_pool):
    session = game_service.start_new_game(sample_pool)
    # Force known game for deterministic test
    session.current_game = sample_pool[0]
    session.screenshot_index = 0
    assert game_service.get_current_screenshot_url(session) == "https://img1.jpg"
    session.screenshot_index = 1
    assert game_service.get_current_screenshot_url(session) == "https://img2.jpg"


def test_get_current_screenshot_url_clamps_index_if_out_of_range(game_service, sample_pool):
    session = GameSession(current_game=sample_pool[0], screenshot_index=99, attempt_count=0)
    assert game_service.get_current_screenshot_url(session) == "https://img2.jpg"


def test_submit_guess_no_game_returns_incorrect(game_service):
    session = GameSession(current_game=None, screenshot_index=0, attempt_count=0)
    result = game_service.submit_guess(session, "Anything")
    assert result.correct is False
    assert result.hint_text is None
    game_service._openai.check_guess_and_get_hint.assert_not_called()


def test_submit_guess_calls_openai_and_returns_result(game_service, sample_pool):
    from app.models import HintResult

    game_service._openai.check_guess_and_get_hint.return_value = HintResult(correct=True, hint_text=None)
    session = GameSession(current_game=sample_pool[0], screenshot_index=0, attempt_count=0)
    result = game_service.submit_guess(session, "  Game One  ")
    assert result.correct is True
    game_service._openai.check_guess_and_get_hint.assert_called_once()
    call_arg = game_service._openai.check_guess_and_get_hint.call_args[0][0]
    assert call_arg.guess == "Game One"
    assert call_arg.correct_game_name == "Game One"
    assert call_arg.genres == ["Action"]
