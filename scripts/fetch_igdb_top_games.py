#!/usr/bin/env python3
"""
Quick prototype: fetch the 1000 most popular games from IGDB API.

Includes: name, slug, rating, genres, first_release_date, and a "generation" bucket
based on release date (Wikipedia: History of video game consoles § Console generations),
with primary consoles for hints.

Requires Twitch app credentials (used for IGDB auth):
  - TWITCH_CLIENT_ID
  - TWITCH_CLIENT_SECRET

Run: python scripts/fetch_igdb_top_games.py
"""

import json
import os
import time
from datetime import datetime

import requests

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_GAMES_URL = "https://api.igdb.com/v4/games"
IGDB_GENRES_URL = "https://api.igdb.com/v4/genres"
PAGE_SIZE = 500  # IGDB allows up to 500 per request
TOTAL_GAMES = 1000
RATE_LIMIT_DELAY = 0.3  # seconds between requests (IGDB: 4 req/s max)

# Console generations from Wikipedia: History of video game consoles § Home console history timeline by generation
# https://en.wikipedia.org/wiki/History_of_video_game_consoles#Console_generations
# Each entry: (year_start_inclusive, year_end_inclusive, label, primary_consoles)
CONSOLE_GENERATIONS = [
    (1972, 1975, "First generation (1972–1983)", ["Magnavox Odyssey", "Atari Pong", "Coleco Telstar series"]),
    (1976, 1982, "Second generation (1976–1992)", ["Fairchild Channel F", "Atari 2600", "Odyssey 2", "Intellivision", "ColecoVision"]),
    (1983, 1986, "Third generation / 8-bit (1983–2003)", ["Nintendo Entertainment System (NES)", "Sega Master System", "Atari 7800"]),
    (1987, 1992, "Fourth generation / 16-bit (1987–2004)", ["TurboGrafx-16", "Sega Genesis", "Neo Geo", "Super NES"]),
    (1993, 1997, "Fifth generation / 32-bit (1993–2006)", ["3DO", "Atari Jaguar", "Sega Saturn", "PlayStation", "Nintendo 64"]),
    (1998, 2004, "Sixth generation (1998–2013)", ["Dreamcast", "PlayStation 2", "GameCube", "Xbox"]),
    (2005, 2011, "Seventh generation (2005–2017)", ["Xbox 360", "PlayStation 3", "Wii"]),
    (2012, 2019, "Eighth generation (2012–present)", ["Wii U", "PlayStation 4", "Xbox One", "Nintendo Switch"]),
    (2020, 9999, "Ninth generation (2020–present)", ["Xbox Series X/S", "PlayStation 5"]),
]


def get_twitch_token(client_id: str, client_secret: str) -> str:
    """Get OAuth2 access token from Twitch (client credentials)."""
    r = requests.post(
        TWITCH_TOKEN_URL,
        params={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
    )
    r.raise_for_status()
    return r.json()["access_token"]


def get_generation_from_release_date(first_release_date: int | None) -> dict | None:
    """Map Unix timestamp to console generation (label + primary_consoles). Returns None if no date."""
    if first_release_date is None:
        return None
    year = datetime.utcfromtimestamp(first_release_date).year
    for start, end, label, consoles in CONSOLE_GENERATIONS:
        if start <= year <= end:
            return {"label": label, "primary_consoles": consoles}
    return None


def fetch_genres(client_id: str, access_token: str) -> dict[int, str]:
    """Fetch all genres from IGDB; return mapping id -> name."""
    r = requests.post(
        IGDB_GENRES_URL,
        headers={
            "Client-ID": client_id,
            "Authorization": f"Bearer {access_token}",
        },
        data="fields id,name; limit 500;",
    )
    r.raise_for_status()
    return {g["id"]: g["name"] for g in r.json()}


def fetch_games_page(
    client_id: str,
    access_token: str,
    limit: int = PAGE_SIZE,
    offset: int = 0,
) -> list[dict]:
    """Fetch one page of games sorted by popularity (desc)."""
    # Game has no "popularity" field; sort by total_rating_count for most-known games
    body = (
        "fields name,slug,rating,total_rating_count,first_release_date,genres; "
        f"sort total_rating_count desc; "
        f"limit {limit}; "
        f"offset {offset};"
    )
    r = requests.post(
        IGDB_GAMES_URL,
        headers={
            "Client-ID": client_id,
            "Authorization": f"Bearer {access_token}",
        },
        data=body,
    )
    r.raise_for_status()
    return r.json()


def main() -> None:
    client_id = os.environ.get("TWITCH_CLIENT_ID") or os.environ.get("IGDB_CLIENT_ID")
    client_secret = (
        os.environ.get("TWITCH_CLIENT_SECRET") or os.environ.get("IGDB_CLIENT_SECRET")
    )
    if not client_id or not client_secret:
        print(
            "Set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET (or IGDB_*). "
            "Get them from https://dev.twitch.tv/console/apps"
        )
        raise SystemExit(1)

    print("Getting Twitch access token...")
    token = get_twitch_token(client_id, client_secret)
    print("Token obtained.")

    print("Fetching genres...")
    genre_by_id = fetch_genres(client_id, token)
    time.sleep(RATE_LIMIT_DELAY)

    all_games_raw: list[dict] = []
    offset = 0
    while offset < TOTAL_GAMES:
        print(f"Fetching games {offset + 1}–{offset + PAGE_SIZE}...")
        page = fetch_games_page(client_id, token, limit=PAGE_SIZE, offset=offset)
        if not page:
            break
        all_games_raw.extend(page)
        offset += len(page)
        if len(page) < PAGE_SIZE:
            break
        time.sleep(RATE_LIMIT_DELAY)

    # Enrich: genre names, generation (label + primary_consoles)
    all_games: list[dict] = []
    for g in all_games_raw:
        genre_ids = g.get("genres") or []
        genre_names = [genre_by_id.get(i, str(i)) for i in genre_ids]
        release_ts = g.get("first_release_date")
        generation = get_generation_from_release_date(release_ts)
        enriched = {
            "id": g.get("id"),
            "name": g.get("name"),
            "slug": g.get("slug"),
            "rating": g.get("rating"),
            "total_rating_count": g.get("total_rating_count"),
            "first_release_date": release_ts,
            "genres": genre_names,
            "generation": generation,
        }
        all_games.append(enriched)

    print(f"\nTotal games retrieved: {len(all_games)}")
    print("\nFirst 20 (by rating count):")
    print("-" * 60)
    for i, g in enumerate(all_games[:20], 1):
        name = g.get("name", "?")
        genres = g.get("genres") or []
        gen = g.get("generation") or {}
        gen_label = gen.get("label", "?")
        consoles = gen.get("primary_consoles", [])
        print(f"  {i:2}. {name!r}")
        print(f"      genres={genres!r}  generation={gen_label!r}")
        print(f"      primary_consoles={consoles}")

    out_path = os.path.join(os.path.dirname(__file__), "..", "igdb_top_games.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_games, f, indent=2, ensure_ascii=False)
    print(f"\nFull list (with genres and generation) written to {out_path}")


if __name__ == "__main__":
    main()
