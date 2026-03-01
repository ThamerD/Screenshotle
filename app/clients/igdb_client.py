"""
IGDB API client: Twitch OAuth2, fetch genres and popular games with screenshot URLs.

Uses IGDB v4 (api.igdb.com). Rate limit: 4 requests per second.
"""

import time
from typing import Any

import requests

# IGDB base URLs and rate limiting
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_BASE = "https://api.igdb.com/v4"
IGDB_GAMES = f"{IGDB_BASE}/games"
IGDB_GENRES = f"{IGDB_BASE}/genres"
IGDB_SCREENSHOTS = f"{IGDB_BASE}/screenshots"
# Image URL template: image_id from screenshot record (e.g. "sc5abc" or numeric)
IGDB_IMAGE_URL_TEMPLATE = "https://images.igdb.com/igdb/image/upload/t_screenshot_big/{image_id}.jpg"
PAGE_SIZE = 500
RATE_LIMIT_DELAY = 0.3


class IGDBClient:
    """
    Client for IGDB API. Requires Twitch client id and secret (IGDB uses Twitch auth).
    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None

    def _headers(self) -> dict[str, str]:
        """Request headers with auth; refreshes token if needed."""
        if self._token is None:
            self._token = self.get_token()
        return {
            "Client-ID": self._client_id,
            "Authorization": f"Bearer {self._token}",
        }

    def get_token(self) -> str:
        """Get Twitch OAuth2 access token (client credentials)."""
        r = requests.post(
            TWITCH_TOKEN_URL,
            params={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
            },
        )
        r.raise_for_status()
        self._token = r.json()["access_token"]
        return self._token

    def get_genre_map(self) -> dict[int, str]:
        """Fetch all genres from IGDB; return mapping id -> name."""
        r = requests.post(
            IGDB_GENRES,
            headers=self._headers(),
            data="fields id,name; limit 500;",
        )
        r.raise_for_status()
        return {g["id"]: g["name"] for g in r.json()}

    def get_popular_games(self, limit: int = 500) -> list[dict[str, Any]]:
        """
        Fetch popular games (by total_rating_count) with genres and screenshot URLs.
        Returns list of dicts: id, name, genres (list[str]), first_release_date (int|None), screenshot_urls (list[str]).
        """
        genre_map = self.get_genre_map()
        time.sleep(RATE_LIMIT_DELAY)

        # Fetch games with screenshot IDs (screenshots field returns list of screenshot record ids)
        body = (
            "fields id,name,first_release_date,genres,screenshots; "
            "sort total_rating_count desc; "
            f"limit {limit}; "
            "where screenshots != null & first_release_date != null;"
        )
        r = requests.post(IGDB_GAMES, headers=self._headers(), data=body)
        r.raise_for_status()
        games_raw = r.json()
        if not games_raw:
            return []

        # Collect all screenshot IDs and fetch image_id for each
        screenshot_ids: list[int] = []
        for g in games_raw:
            screenshot_ids.extend(g.get("screenshots") or [])
        screenshot_ids = list(dict.fromkeys(screenshot_ids))  # unique, preserve order

        # IGDB allows up to 500 ids in a where clause; batch if needed
        id_to_image_id: dict[int, str] = {}
        for i in range(0, len(screenshot_ids), 500):
            batch = screenshot_ids[i : i + 500]
            time.sleep(RATE_LIMIT_DELAY)
            ids_str = ",".join(str(x) for x in batch)
            r2 = requests.post(
                IGDB_SCREENSHOTS,
                headers=self._headers(),
                data=f"fields image_id; where id = ({ids_str});",
            )
            r2.raise_for_status()
            for s in r2.json():
                sid = s.get("id")
                img = s.get("image_id")
                if sid is not None and img is not None:
                    id_to_image_id[sid] = str(img)

        # Build result: each game gets id, name, genres (names), first_release_date, screenshot_urls
        result: list[dict[str, Any]] = []
        for g in games_raw:
            genre_ids = g.get("genres") or []
            genre_names = [genre_map.get(i, str(i)) for i in genre_ids]
            screen_ids = g.get("screenshots") or []
            urls = [
                IGDB_IMAGE_URL_TEMPLATE.format(image_id=id_to_image_id[sid])
                for sid in screen_ids
                if sid in id_to_image_id
            ]
            result.append({
                "id": g["id"],
                "name": g["name"],
                "genres": genre_names,
                "first_release_date": g.get("first_release_date"),
                "screenshot_urls": urls,
            })
        return result
