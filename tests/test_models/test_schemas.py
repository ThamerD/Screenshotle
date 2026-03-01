"""
Unit tests for app.models.schemas: Game, Generation, GameSession, HintRequest, HintResult.
"""

import pytest

from app.models import Game, GameSession, Generation, HintRequest, HintResult


def test_generation_has_label_and_primary_consoles():
    gen = Generation(label="Sixth gen", primary_consoles=("PS2", "Xbox"))
    assert gen.label == "Sixth gen"
    assert gen.primary_consoles == ("PS2", "Xbox")


def test_generation_is_frozen():
    gen = Generation(label="x", primary_consoles=())
    with pytest.raises(AttributeError):
        gen.label = "y"  # type: ignore[misc]


def test_game_holds_required_fields():
    gen = Generation("Eighth", ("PS4", "Switch"))
    game = Game(
        id=123,
        name="Some Game",
        genres=["Action", "RPG"],
        generation=gen,
        screenshot_urls=["https://example.com/1.jpg", "https://example.com/2.jpg"],
    )
    assert game.id == 123
    assert game.name == "Some Game"
    assert game.genres == ["Action", "RPG"]
    assert game.generation is gen
    assert len(game.screenshot_urls) == 2


def test_game_generation_can_be_none():
    game = Game(
        id=1,
        name="Unknown Era",
        genres=[],
        generation=None,
        screenshot_urls=[],
    )
    assert game.generation is None


def test_game_session_defaults():
    session = GameSession()
    assert session.current_game is None
    assert session.screenshot_index == 0
    assert session.attempt_count == 0


def test_game_session_with_game():
    game = Game(1, "Test", [], None, ["url1"])
    session = GameSession(current_game=game, screenshot_index=1, attempt_count=2)
    assert session.current_game is game
    assert session.screenshot_index == 1
    assert session.attempt_count == 2


def test_hint_request_holds_guess_and_metadata():
    gen = Generation("Seventh", ("PS3",))
    req = HintRequest(
        guess="The Last of Us",
        correct_game_name="The Last of Us",
        generation=gen,
        genres=["Action", "Adventure"],
    )
    assert req.guess == "The Last of Us"
    assert req.correct_game_name == "The Last of Us"
    assert req.generation is gen
    assert req.genres == ["Action", "Adventure"]


def test_hint_result_correct():
    result = HintResult(correct=True, hint_text=None)
    assert result.correct is True
    assert result.hint_text is None


def test_hint_result_incorrect_with_hint():
    result = HintResult(correct=False, hint_text="Think eighth generation.")
    assert result.correct is False
    assert result.hint_text == "Think eighth generation."
