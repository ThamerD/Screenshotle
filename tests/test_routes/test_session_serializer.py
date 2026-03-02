"""
Unit tests for GameSession serialization (app.models roundtrip).
"""

import pytest

from app.models import Game, GameSession, Generation, game_session_to_dict, dict_to_game_session


def test_roundtrip_empty_session():
    gs = GameSession(current_game=None, screenshot_index=0, attempt_count=0)
    data = game_session_to_dict(gs)
    restored = dict_to_game_session(data)
    assert restored.current_game is None
    assert restored.screenshot_index == 0
    assert restored.attempt_count == 0


def test_roundtrip_session_with_game():
    gen = Generation("Eighth generation", ("PS4", "Xbox One"))
    game = Game(id=1, name="Test Game", genres=["Action"], generation=gen, screenshot_urls=["https://a.jpg"])
    gs = GameSession(current_game=game, screenshot_index=1, attempt_count=2)
    data = game_session_to_dict(gs)
    restored = dict_to_game_session(data)
    assert restored.current_game is not None
    assert restored.current_game.id == game.id
    assert restored.current_game.name == game.name
    assert restored.current_game.generation is not None
    assert restored.current_game.generation.label == gen.label
    assert restored.screenshot_index == 1
    assert restored.attempt_count == 2


def test_dict_to_game_session_defaults():
    restored = dict_to_game_session({})
    assert restored.current_game is None
    assert restored.screenshot_index == 0
    assert restored.attempt_count == 0
