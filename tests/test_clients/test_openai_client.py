"""
Unit tests for app.clients.openai_client (mocked OpenAI API).
"""

import pytest
from unittest.mock import MagicMock, patch

from app.clients.openai_client import OpenAIClient
from app.models import Generation, HintRequest, HintResult


@pytest.fixture
def client():
    return OpenAIClient(api_key="test-key")


@pytest.fixture
def hint_request():
    gen = Generation("Eighth generation", ("PS4", "Xbox One"))
    return HintRequest(
        guess="The Last of Us",
        correct_game_name="The Last of Us",
        generation=gen,
        genres=["Action", "Adventure"],
    )


def test_check_guess_and_get_hint_returns_correct_when_model_says_correct(client, hint_request):
    with patch("openai.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[
                MagicMock(message=MagicMock(content="CORRECT\n"))
            ]
        )
        result = client.check_guess_and_get_hint(hint_request)
        assert result.correct is True
        assert result.hint_text is None


def test_check_guess_and_get_hint_returns_incorrect_with_hint(client, hint_request):
    with patch("openai.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[
                MagicMock(message=MagicMock(content="WRONG\nThink eighth generation, action-adventure."))
            ]
        )
        result = client.check_guess_and_get_hint(hint_request)
        assert result.correct is False
        assert result.hint_text == "Think eighth generation, action-adventure."


def test_check_guess_and_get_hint_handles_empty_content(client, hint_request):
    with patch("openai.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=None))]
        )
        result = client.check_guess_and_get_hint(hint_request)
        assert result.correct is False
        assert result.hint_text is None
