"""
Unit tests for app.routes.game (mocked GameService and session).
"""

import pytest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Game, GameSession, Generation, HintResult
from app.routes.game import _pst_date_string


@pytest.fixture
def mock_game_service():
    service = MagicMock()
    return service


@pytest.fixture
def app_with_mock_service(mock_game_service):
    app = create_app()
    app.state.game_service = mock_game_service
    return app


@pytest.fixture
def client(app_with_mock_service):
    return TestClient(app_with_mock_service)


@pytest.fixture
def sample_game():
    gen = Generation("Eighth", ("PS4",))
    return Game(id=1, name="The Game", genres=["Action"], generation=gen, screenshot_urls=["https://img.jpg"])


def test_get_root_without_session_shows_start_page(client, mock_game_service):
    """When no game in session, GET / shows start page with link to /new-game (no redirect loop)."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert "new game" in response.text.lower() or "start" in response.text.lower()
    assert "/new-game" in response.text


def test_get_new_game_calls_service_and_renders_game_page(client, mock_game_service, sample_game):
    mock_game_service.get_game_pool.return_value = [sample_game]
    mock_game_service.start_new_game.return_value = GameSession(
        current_game=sample_game, screenshot_index=0, attempt_count=0
    )
    mock_game_service.get_current_screenshot_url.return_value = "https://img.jpg"
    response = client.get("/new-game", follow_redirects=False)
    assert response.status_code == 200
    mock_game_service.get_game_pool.assert_called_once()
    mock_game_service.start_new_game.assert_called_once()
    assert "img.jpg" in response.text or "screenshot" in response.text.lower()

    # Next request with session cookie should show game page
    response2 = client.get("/")
    assert response2.status_code == 200
    assert "img.jpg" in response2.text or "screenshot" in response2.text.lower()


def test_post_guess_correct_returns_win(client, mock_game_service, sample_game):
    mock_game_service.get_game_pool.return_value = [sample_game]
    mock_game_service.start_new_game.return_value = GameSession(
        current_game=sample_game, screenshot_index=0, attempt_count=0
    )
    mock_game_service.get_current_screenshot_url.return_value = "https://img.jpg"
    mock_game_service.submit_guess.return_value = HintResult(correct=True, hint_text=None)
    client.get("/new-game")
    response = client.post("/guess", data={"guess": "The Game"})
    assert response.status_code == 200
    assert "You win" in response.text or "win" in response.text.lower()


def test_post_guess_wrong_returns_hint(client, mock_game_service, sample_game):
    mock_game_service.get_game_pool.return_value = [sample_game]
    mock_game_service.start_new_game.return_value = GameSession(
        current_game=sample_game, screenshot_index=0, attempt_count=0
    )
    mock_game_service.get_current_screenshot_url.return_value = "https://img.jpg"
    mock_game_service.submit_guess.return_value = HintResult(correct=False, hint_text="Think eighth gen.")
    client.get("/new-game")
    response = client.post("/guess", data={"guess": "Wrong Title"})
    assert response.status_code == 200
    assert "Think eighth gen" in response.text or "Hint" in response.text


def test_play_again_redirects_to_new_game(client, mock_game_service, sample_game):
    mock_game_service.get_game_pool.return_value = [sample_game]
    mock_game_service.start_new_game.return_value = GameSession(
        current_game=sample_game, screenshot_index=0, attempt_count=0
    )
    client.get("/new-game", follow_redirects=False)
    response = client.get("/play-again", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/new-game"


def test_new_game_uses_cache_when_fresh(app_with_mock_service, client, mock_game_service, sample_game):
    """When game_pool_cache is set for the current PST day, /new-game does not call get_game_pool."""
    mock_game_service.start_new_game.return_value = GameSession(
        current_game=sample_game, screenshot_index=0, attempt_count=0
    )
    mock_game_service.get_current_screenshot_url.return_value = "https://img.jpg"
    today_pst = _pst_date_string()
    app_with_mock_service.state.game_pool_cache = ([sample_game], today_pst)
    response = client.get("/new-game", follow_redirects=False)
    assert response.status_code == 200
    mock_game_service.get_game_pool.assert_not_called()
    mock_game_service.start_new_game.assert_called_once_with([sample_game])


def test_new_game_refetches_when_cache_stale(app_with_mock_service, client, mock_game_service, sample_game):
    """When game_pool_cache is for a different PST day, /new-game calls get_game_pool and updates cache."""
    mock_game_service.get_game_pool.return_value = [sample_game]
    mock_game_service.start_new_game.return_value = GameSession(
        current_game=sample_game, screenshot_index=0, attempt_count=0
    )
    mock_game_service.get_current_screenshot_url.return_value = "https://img.jpg"
    app_with_mock_service.state.game_pool_cache = ([sample_game], "2000-01-01")
    response = client.get("/new-game", follow_redirects=False)
    assert response.status_code == 200
    mock_game_service.get_game_pool.assert_called_once()
    pool, cached_date = app_with_mock_service.state.game_pool_cache
    assert pool == [sample_game]
    assert cached_date == _pst_date_string()
