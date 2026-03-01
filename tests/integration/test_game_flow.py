"""
Integration test: full flow start game → get screenshot → submit wrong guess → get hints.

Uses real app and router with mocked GameService (no live IGDB/OpenAI).
"""

import pytest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Game, GameSession, Generation, HintResult


@pytest.fixture
def mock_service():
    service = MagicMock()
    game = Game(
        id=100,
        name="The Last of Us",
        genres=["Action", "Adventure"],
        generation=Generation("Eighth generation", ("PS4", "Xbox One")),
        screenshot_urls=["https://img1.jpg", "https://img2.jpg"],
    )
    service.get_game_pool.return_value = [game]
    service.start_new_game.return_value = GameSession(current_game=game, screenshot_index=0, attempt_count=0)
    def _screenshot_url(session):
        if session.current_game and session.current_game.screenshot_urls:
            idx = min(session.screenshot_index, len(session.current_game.screenshot_urls) - 1)
            return session.current_game.screenshot_urls[idx]
        return "https://img1.jpg"
    service.get_current_screenshot_url.side_effect = _screenshot_url
    service.submit_guess.return_value = HintResult(correct=False, hint_text="Think eighth generation, action-adventure.")
    return service


@pytest.fixture
def client(mock_service):
    app = create_app()
    app.state.game_service = mock_service
    return TestClient(app)


def test_full_flow_start_wrong_guess_then_hint(client, mock_service):
    # Start new game
    r1 = client.get("/new-game", follow_redirects=False)
    assert r1.status_code == 302
    mock_service.get_game_pool.assert_called_once()
    mock_service.start_new_game.assert_called_once()

    # Game page shows first screenshot
    r2 = client.get("/")
    assert r2.status_code == 200
    assert "img1.jpg" in r2.text

    # Submit wrong guess → see hint and next screenshot
    r3 = client.post("/guess", data={"guess": "Uncharted"})
    assert r3.status_code == 200
    assert "Think eighth generation" in r3.text or "hint" in r3.text.lower()
    assert "img2.jpg" in r3.text
