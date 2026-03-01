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
# IGDB max items per request (documented at api-docs.igdb.com)
PAGE_SIZE = 500
# Fetch games in batches of this size (smaller = more requests but spreads load)
BATCH_SIZE = 100
# Only include games that have at least this many resolved screenshot URLs (from /screenshots image_id lookup)
MIN_SCREENSHOTS_PER_GAME = 5
# Unix timestamp for 2020-01-01 00:00:00 UTC (for "recent games" filter)
RELEASE_DATE_2020 = 1577836800
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

    def _igdb_headers(self) -> dict[str, str]:
        """Headers for IGDB API: auth plus Accept and Content-Type for Apicalypse body."""
        h = self._headers()
        h["Accept"] = "application/json"
        h["Content-Type"] = "text/plain"
        return h

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
            headers=self._igdb_headers(),
            data="fields id,name; limit 500;",
        )
        r.raise_for_status()
        return {g["id"]: g["name"] for g in r.json()}

    def _fetch_games_stream(
        self,
        genre_map: dict[int, str],
        where_clause: str,
        sort_clause: str,
        target_count: int,
        max_offset: int = 5000,
    ) -> list[dict[str, Any]]:
        """
        Fetch games in batches with the given where/sort; include only games with >= MIN_SCREENSHOTS_PER_GAME resolved URLs.
        Returns list of game dicts (id, name, genres, first_release_date, screenshot_urls).
        """
        result: list[dict[str, Any]] = []
        offset = 0
        while len(result) < target_count and offset < max_offset:
            time.sleep(RATE_LIMIT_DELAY)
            body = (
                "fields id,name,first_release_date,genres,screenshots,total_rating_count; "
                f"sort {sort_clause}; "
                f"limit {BATCH_SIZE}; "
                f"offset {offset}; "
                f"where {where_clause};"
            )
            r = requests.post(IGDB_GAMES, headers=self._igdb_headers(), data=body)
            r.raise_for_status()
            games_raw = r.json()
            if not games_raw:
                break

            screenshot_ids = []
            for g in games_raw:
                screenshot_ids.extend(g.get("screenshots") or [])
            screenshot_ids = list(dict.fromkeys(screenshot_ids))
            id_to_image_id: dict[int, str] = {}
            for i in range(0, len(screenshot_ids), PAGE_SIZE):
                batch = screenshot_ids[i : i + PAGE_SIZE]
                time.sleep(RATE_LIMIT_DELAY)
                ids_str = ",".join(str(x) for x in batch)
                r2 = requests.post(
                    IGDB_SCREENSHOTS,
                    headers=self._igdb_headers(),
                    data=f"fields image_id; where id = ({ids_str}); limit {PAGE_SIZE};",
                )
                r2.raise_for_status()
                for s in r2.json():
                    sid = s.get("id")
                    img = s.get("image_id")
                    if sid is not None and img is not None:
                        id_to_image_id[sid] = str(img)

            for g in games_raw:
                genre_ids = g.get("genres") or []
                genre_names = [genre_map.get(i, str(i)) for i in genre_ids]
                screen_ids = g.get("screenshots") or []
                urls = [
                    IGDB_IMAGE_URL_TEMPLATE.format(image_id=id_to_image_id[sid])
                    for sid in screen_ids
                    if sid in id_to_image_id
                ]
                if len(urls) >= MIN_SCREENSHOTS_PER_GAME:
                    result.append({
                        "id": g["id"],
                        "name": g["name"],
                        "genres": genre_names,
                        "first_release_date": g.get("first_release_date"),
                        "total_rating_count": g.get("total_rating_count"),
                        "screenshot_urls": urls,
                    })
                    if len(result) >= target_count:
                        break
            offset += len(games_raw)
        return result

    def get_popular_games(self, limit: int = 500) -> list[dict[str, Any]]:
        """
        Fetch a mix of (1) all-time popular games and (2) recent games (2020+), each with >= MIN_SCREENSHOTS_PER_GAME screenshots.
        Merges and dedupes by id (popular first, then recent). Returns list of dicts: id, name, genres, first_release_date, screenshot_urls.
        """
        genre_map = self.get_genre_map()
        half = max(1, limit // 2)
        base_where = "screenshots != null & first_release_date != null & total_rating_count != null"

        popular = self._fetch_games_stream(
            genre_map,
            where_clause=base_where,
            sort_clause="total_rating_count desc",
            target_count=half,
            max_offset=5000,
        )
        recent = self._fetch_games_stream(
            genre_map,
            where_clause=f"{base_where} & first_release_date >= {RELEASE_DATE_2020}",
            sort_clause="first_release_date desc",
            target_count=half,
            max_offset=3000,
        )

        seen_ids: set[int] = set()
        result: list[dict[str, Any]] = []
        for g in popular + recent:
            if g["id"] not in seen_ids:
                seen_ids.add(g["id"])
                result.append(g)
                if len(result) >= limit:
                    break
        return result
