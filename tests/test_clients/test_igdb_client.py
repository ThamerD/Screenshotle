"""
Unit tests for app.clients.igdb_client (mocked HTTP).
"""

import pytest
from unittest.mock import patch, MagicMock

from app.clients.igdb_client import IGDBClient, IGDB_IMAGE_URL_TEMPLATE


@pytest.fixture
def client():
    return IGDBClient(client_id="test-id", client_secret="test-secret")


def test_get_token_returns_access_token(client):
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "fake-token", "expires_in": 3600},
        )
        mock_post.return_value.raise_for_status = MagicMock()
        token = client.get_token()
        assert token == "fake-token"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["params"]["client_id"] == "test-id"
        assert call_args[1]["params"]["grant_type"] == "client_credentials"


def test_get_genre_map_returns_id_to_name(client):
    with patch.object(client, "_headers", return_value={"Client-ID": "x", "Authorization": "Bearer y"}):
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: [{"id": 1, "name": "Action"}, {"id": 2, "name": "RPG"}],
            )
            mock_post.return_value.raise_for_status = MagicMock()
            result = client.get_genre_map()
            assert result == {1: "Action", 2: "RPG"}


def test_get_popular_games_returns_list_with_screenshot_urls(client):
    # _headers triggers get_token; then get_genre_map; then games; then screenshots
    client._token = "fake"
    with patch("requests.post") as mock_post:
        genre_resp = MagicMock(status_code=200, json=lambda: [{"id": 12, "name": "Adventure"}])
        genre_resp.raise_for_status = MagicMock()
        games_resp = MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "id": 100,
                    "name": "Test Game",
                    "first_release_date": 1609459200,
                    "genres": [12],
                    "screenshots": [500, 501],
                }
            ],
        )
        games_resp.raise_for_status = MagicMock()
        screens_resp = MagicMock(
            status_code=200,
            json=lambda: [
                {"id": 500, "image_id": "sc5abc"},
                {"id": 501, "image_id": "sc6def"},
            ],
        )
        screens_resp.raise_for_status = MagicMock()
        mock_post.side_effect = [genre_resp, games_resp, screens_resp]

        with patch("time.sleep"):
            result = client.get_popular_games(limit=10)

        assert len(result) == 1
        g = result[0]
        assert g["id"] == 100
        assert g["name"] == "Test Game"
        assert g["genres"] == ["Adventure"]
        assert g["first_release_date"] == 1609459200
        assert g["screenshot_urls"] == [
            IGDB_IMAGE_URL_TEMPLATE.format(image_id="sc5abc"),
            IGDB_IMAGE_URL_TEMPLATE.format(image_id="sc6def"),
        ]


def test_get_popular_games_empty_when_no_games(client):
    client._token = "fake"
    with patch("requests.post") as mock_post:
        genre_resp = MagicMock(status_code=200, json=lambda: [])
        genre_resp.raise_for_status = MagicMock()
        games_resp = MagicMock(status_code=200, json=lambda: [])
        games_resp.raise_for_status = MagicMock()
        mock_post.side_effect = [genre_resp, games_resp]
        with patch("time.sleep"):
            result = client.get_popular_games(limit=10)
        assert result == []
