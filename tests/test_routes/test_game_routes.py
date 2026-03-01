"""
Unit tests for app.routes.game (mocked GameService and session).
"""

import pytest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Game, GameSession, Generation, HintResult


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


def test_get_root_without_session_redirects_to_new_game(client, mock_game_service):
    mock_game_service.get_game_pool.return_value = []
    mock_game_service.start_new_game.return_value = GameSession(current_game=None, screenshot_index=0, attempt_count=0)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/new-game"


def test_get_new_game_calls_service_and_redirects(client, mock_game_service, sample_game):
    mock_game_service.get_game_pool.return_value = [sample_game]
    mock_game_service.start_new_game.return_value = GameSession(
        current_game=sample_game, screenshot_index=0, attempt_count=0
    )
    mock_game_service.get_current_screenshot_url.return_value = "https://img.jpg"
    response = client.get("/new-game", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"
    mock_game_service.get_game_pool.assert_called_once()
    mock_game_service.start_new_game.assert_called_once()

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
