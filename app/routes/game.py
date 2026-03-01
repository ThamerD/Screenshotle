"""
Game routes: new game, submit guess, play again. Render Jinja2; read/write session.
"""

import time
from typing import Any

import requests
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.models import GameSession
from app.routes.session_serializer import dict_to_game_session, game_session_to_dict

# Max wrong guesses before game over (then show next screenshot; repeat until correct or this many attempts)
MAX_ATTEMPTS = 5

# Cache the game pool from IGDB; refresh only when older than this (seconds)
GAME_POOL_CACHE_MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 days
# IGDB allows max 500 items per request (api-docs.igdb.com)
GAME_POOL_LIMIT = 500
# When starting a new game, exclude this many recently played game IDs to reduce repetition
RECENT_GAME_IDS_MAX = 30

# Templates at project root / templates
TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

game_router = APIRouter(tags=["game"])


def _get_game_service(request: Request):
    """GameService is attached to app.state in main."""
    return getattr(request.app.state, "game_service", None)


def _session(request: Request) -> dict:
    """Session dict (server-side); set by ServerSideSessionMiddleware."""
    return getattr(request.state, "session", {})


def _get_session(request: Request) -> GameSession:
    """Load GameSession from session; default empty session."""
    data = _session(request).get("game_session")
    if not data:
        return GameSession(current_game=None, screenshot_index=0, attempt_count=0)
    return dict_to_game_session(data)


def _save_session(request: Request, gs: GameSession) -> None:
    """Persist GameSession into session."""
    _session(request)["game_session"] = game_session_to_dict(gs)


# Inline "no game" page to avoid redirect loop: / → /new-game → / (session cookie can be missing on first redirect)
_NO_GAME_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Screenshotle</title></head>
<body style="font-family:system-ui;max-width:640px;margin:2rem auto;padding:0 1rem;">
<h1>Screenshotle</h1>
<p>Guess the video game from a screenshot.</p>
<p><a href="/new-game" style="display:inline-block;padding:0.5rem 1rem;background:#333;color:#fff;text-decoration:none;border-radius:6px;">Start a new game</a></p>
</body></html>"""


@game_router.get("/", response_class=HTMLResponse)
async def game_page(request: Request) -> Any:
    """
    Show current game: screenshot and guess form.
    If no game in session, show "Start game" page (link to /new-game) to avoid redirect loop.
    """
    service = _get_game_service(request)
    if not service:
        return HTMLResponse(
            "<h1>Configuration error</h1><p>Game service not available. Check IGDB and OpenAI credentials.</p>",
            status_code=503,
        )
    gs = _get_session(request)
    if gs.current_game is None:
        return HTMLResponse(_NO_GAME_HTML)
    screenshot_url = service.get_current_screenshot_url(gs)
    if not screenshot_url:
        return HTMLResponse(_NO_GAME_HTML)
    # Show last hint if present (from previous wrong guess)
    last_hint = _session(request).pop("last_hint", None)
    last_genre_matches = _session(request).pop("last_genre_matches", [])
    last_genre_mismatches = _session(request).pop("last_genre_mismatches", [])
    last_generation_text = _session(request).pop("last_generation_text", None)
    last_generation_matched = _session(request).pop("last_generation_matched", False)
    message = _session(request).pop("message", None)
    answer = _session(request).pop("answer", None)
    # Game names from pool for autofill (same pool the current game came from)
    cache = getattr(request.app.state, "game_pool_cache", None)
    pool = cache[0] if cache else []
    game_names = [g.name for g in pool]
    return templates.TemplateResponse(
        request,
        "game.html",
        {
            "screenshot_url": screenshot_url,
            "hint_text": last_hint,
            "genre_matches": last_genre_matches,
            "genre_mismatches": last_genre_mismatches,
            "generation_text": last_generation_text,
            "generation_matched": last_generation_matched,
            "message": message,
            "answer": answer,
            "attempt_count": gs.attempt_count,
            "max_attempts": MAX_ATTEMPTS,
            "show_guess_form": message is None,
            "game_names": game_names,
        },
    )


def _get_or_fetch_game_pool(request: Request):
    """
    Return the game pool from app.state cache if fresh (< 7 days), else fetch from IGDB and update cache.
    Requires request.app.state.game_service to be set. Returns list of Game (may be empty).
    """
    service = _get_game_service(request)
    if not service:
        return None
    now = time.time()
    cache = getattr(request.app.state, "game_pool_cache", None)
    if cache is not None:
        pool, fetched_at = cache
        if (now - fetched_at) < GAME_POOL_CACHE_MAX_AGE_SECONDS:
            print(f"[Screenshotle] Game pool: using cache ({len(pool)} games)")
            return pool
    print("[Screenshotle] Game pool: fetching from IGDB...")
    pool = service.get_game_pool(limit=GAME_POOL_LIMIT)
    request.app.state.game_pool_cache = (pool, now)
    print(f"[Screenshotle] Game pool: fetched {len(pool)} games from IGDB")
    return pool


@game_router.get("/new-game", response_class=HTMLResponse)
async def new_game(request: Request) -> Any:
    """
    Start a new round: use cached game pool (refresh from IGDB if older than 7 days), pick random game, save session, redirect to game page.
    If service is missing or pool is empty, show an error page instead of redirecting (avoids redirect loop).
    """
    service = _get_game_service(request)
    if not service:
        return HTMLResponse(
            "<h1>Configuration error</h1><p>Game service not available. Set TWITCH_CLIENT_ID, "
            "TWITCH_CLIENT_SECRET, and OPENAI_API_KEY in your environment, then restart.</p>"
            "<p><a href=\"/new-game\">Try again</a></p>",
            status_code=503,
        )
    try:
        pool = _get_or_fetch_game_pool(request)
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status == 403:
            msg = "IGDB returned 403 Forbidden. Check your Twitch Client ID and Secret (and that the app is approved for IGDB)."
        elif status:
            msg = f"Could not load games from IGDB (error {status})."
        else:
            msg = "Could not reach IGDB."
        return HTMLResponse(
            f"<h1>Could not load games</h1><p>{msg}</p><p><a href=\"/new-game\">Try again</a></p>",
            status_code=503,
        )
    if pool is None:
        return HTMLResponse(
            "<h1>Configuration error</h1><p>Game service not available.</p>"
            "<p><a href=\"/new-game\">Try again</a></p>",
            status_code=503,
        )
    recent_ids = list(_session(request).get("recent_game_ids") or [])[:RECENT_GAME_IDS_MAX]
    gs = service.start_new_game(pool, exclude_ids=set(recent_ids))
    if gs.current_game is None:
        return HTMLResponse(
            "<h1>No games loaded</h1><p>Could not load games from IGDB (pool is empty). "
            "Check your Twitch/IGDB credentials and that the API is reachable.</p>"
            "<p><a href=\"/new-game\">Try again</a></p>",
            status_code=503,
        )
    _save_session(request, gs)
    # Remember this game so we don't pick it again for a while
    if gs.current_game is not None:
        recent_ids = list(_session(request).get("recent_game_ids") or [])
        recent_ids.append(gs.current_game.id)
        _session(request)["recent_game_ids"] = recent_ids[-RECENT_GAME_IDS_MAX:]
    # Render game page directly (no redirect) so one click always shows the game; avoids cookie/redirect issues
    screenshot_url = service.get_current_screenshot_url(gs)
    if not screenshot_url:
        # Should not happen if pool only has games with screenshots; fallback to GET / to show game
        return RedirectResponse(url="/", status_code=302)
    game_names = [g.name for g in pool]
    return templates.TemplateResponse(
        request,
        "game.html",
        {
            "screenshot_url": screenshot_url,
            "hint_text": None,
            "genre_matches": [],
            "genre_mismatches": [],
            "generation_text": None,
            "generation_matched": False,
            "message": None,
            "answer": None,
            "attempt_count": gs.attempt_count,
            "max_attempts": MAX_ATTEMPTS,
            "show_guess_form": True,
            "game_names": game_names,
        },
    )


@game_router.post("/guess", response_class=HTMLResponse)
async def submit_guess(request: Request) -> Any:
    """
    Check guess. If correct: show win. If wrong: store hint, advance screenshot/attempts; if max attempts show game over.
    Renders game page (no redirect) so user sees hint and next screenshot.
    """
    service = _get_game_service(request)
    if not service:
        return HTMLResponse("<p>Service unavailable.</p>", status_code=503)
    form = await request.form()
    guess = (form.get("guess") or "").strip()
    gs = _get_session(request)
    if gs.current_game is None or not guess:
        return RedirectResponse(url="/new-game", status_code=302)
    cache = getattr(request.app.state, "game_pool_cache", None)
    pool = cache[0] if cache else None
    result = service.submit_guess(gs, guess, pool=pool)
    if result.correct:
        _session(request)["message"] = "You win!"
        _session(request)["answer"] = gs.current_game.name
        _save_session(request, gs)
        screenshot_url = service.get_current_screenshot_url(gs)
        cache = getattr(request.app.state, "game_pool_cache", None)
        pool = cache[0] if cache else []
        game_names = [g.name for g in pool]
        return templates.TemplateResponse(
            request,
            "game.html",
            {
                "screenshot_url": screenshot_url,
                "hint_text": None,
                "genre_matches": [],
                "genre_mismatches": [],
                "generation_text": None,
                "generation_matched": False,
                "message": "You win!",
                "answer": gs.current_game.name,
                "attempt_count": gs.attempt_count,
                "max_attempts": MAX_ATTEMPTS,
                "show_guess_form": False,
                "game_names": game_names,
            },
        )
    # Wrong: store hint and match hints, increment attempt and screenshot index
    _session(request)["last_hint"] = result.hint_text
    _session(request)["last_genre_matches"] = result.genre_matches
    _session(request)["last_genre_mismatches"] = result.genre_mismatches
    _session(request)["last_generation_text"] = result.generation_text
    _session(request)["last_generation_matched"] = result.generation_matched
    gs.attempt_count += 1
    gs.screenshot_index += 1
    _save_session(request, gs)
    if gs.attempt_count >= MAX_ATTEMPTS:
        _session(request)["message"] = "Game over."
        _session(request)["answer"] = gs.current_game.name
        screenshot_url = service.get_current_screenshot_url(gs)
        cache = getattr(request.app.state, "game_pool_cache", None)
        pool = cache[0] if cache else []
        game_names = [g.name for g in pool]
        return templates.TemplateResponse(
            request,
            "game.html",
            {
                "screenshot_url": screenshot_url,
                "hint_text": result.hint_text,
                "genre_matches": result.genre_matches,
                "genre_mismatches": result.genre_mismatches,
                "generation_text": result.generation_text,
                "generation_matched": result.generation_matched,
                "message": "Game over.",
                "answer": gs.current_game.name,
                "attempt_count": gs.attempt_count,
                "max_attempts": MAX_ATTEMPTS,
                "show_guess_form": False,
                "game_names": game_names,
            },
        )
    screenshot_url = service.get_current_screenshot_url(gs)
    cache = getattr(request.app.state, "game_pool_cache", None)
    pool = cache[0] if cache else []
    game_names = [g.name for g in pool]
    return templates.TemplateResponse(
        request,
        "game.html",
        {
            "screenshot_url": screenshot_url,
            "hint_text": result.hint_text,
            "genre_matches": result.genre_matches,
            "genre_mismatches": result.genre_mismatches,
            "generation_text": result.generation_text,
            "generation_matched": result.generation_matched,
            "message": None,
            "answer": None,
            "attempt_count": gs.attempt_count,
            "max_attempts": MAX_ATTEMPTS,
            "show_guess_form": True,
            "game_names": game_names,
        },
    )


@game_router.get("/play-again")
async def play_again(request: Request) -> Any:
    """Clear game session and start a new game."""
    for key in ("game_session", "message", "answer", "last_hint", "last_genre_matches", "last_genre_mismatches", "last_generation_text", "last_generation_matched"):
        _session(request).pop(key, None)
    return RedirectResponse(url="/new-game", status_code=302)
