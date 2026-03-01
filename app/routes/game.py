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


@game_router.get("/", response_class=HTMLResponse)
async def game_page(request: Request) -> Any:
    """
    Show current game: screenshot and guess form.
    If no game in session, redirect to /new-game.
    """
    service = _get_game_service(request)
    if not service:
        return HTMLResponse(
            "<h1>Configuration error</h1><p>Game service not available. Check IGDB and OpenAI credentials.</p>",
            status_code=503,
        )
    gs = _get_session(request)
    if gs.current_game is None:
        return RedirectResponse(url="/new-game", status_code=302)
    screenshot_url = service.get_current_screenshot_url(gs)
    if not screenshot_url:
        return RedirectResponse(url="/new-game", status_code=302)
    # Show last hint if present (from previous wrong guess)
    last_hint = _session(request).pop("last_hint", None)
    message = _session(request).pop("message", None)
    answer = _session(request).pop("answer", None)
    return templates.TemplateResponse(
        request,
        "game.html",
        {
            "screenshot_url": screenshot_url,
            "hint_text": last_hint,
            "message": message,
            "answer": answer,
            "attempt_count": gs.attempt_count,
            "max_attempts": MAX_ATTEMPTS,
            "show_guess_form": message is None,
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
        if (now - fetched_at) < GAME_POOL_CACHE_MAX_AGE_SECONDS and pool:
            return pool
    pool = service.get_game_pool(limit=GAME_POOL_LIMIT)
    request.app.state.game_pool_cache = (pool, now)
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
        print(f"[Screenshotle] /new-game: IGDB request failed — {type(e).__name__} status={status}")
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
        print("[Screenshotle] /new-game: pool is None")
        return HTMLResponse(
            "<h1>Configuration error</h1><p>Game service not available.</p>"
            "<p><a href=\"/new-game\">Try again</a></p>",
            status_code=503,
        )
    gs = service.start_new_game(pool)
    if gs.current_game is None:
        print(f"[Screenshotle] /new-game: pool empty (len={len(pool)}), cannot start game")
        return HTMLResponse(
            "<h1>No games loaded</h1><p>Could not load games from IGDB (pool is empty). "
            "Check your Twitch/IGDB credentials and that the API is reachable.</p>"
            "<p><a href=\"/new-game\">Try again</a></p>",
            status_code=503,
        )
    _save_session(request, gs)
    return RedirectResponse(url="/", status_code=302)


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
    result = service.submit_guess(gs, guess)
    if result.correct:
        _session(request)["message"] = "You win!"
        _session(request)["answer"] = gs.current_game.name
        _save_session(request, gs)
        screenshot_url = service.get_current_screenshot_url(gs)
        return templates.TemplateResponse(
            request,
            "game.html",
            {
                "screenshot_url": screenshot_url,
                "hint_text": None,
                "message": "You win!",
                "answer": gs.current_game.name,
                "attempt_count": gs.attempt_count,
                "max_attempts": MAX_ATTEMPTS,
                "show_guess_form": False,
            },
        )
    # Wrong: store hint, increment attempt and screenshot index
    _session(request)["last_hint"] = result.hint_text
    gs.attempt_count += 1
    gs.screenshot_index += 1
    _save_session(request, gs)
    if gs.attempt_count >= MAX_ATTEMPTS:
        _session(request)["message"] = "Game over."
        _session(request)["answer"] = gs.current_game.name
        screenshot_url = service.get_current_screenshot_url(gs)
        return templates.TemplateResponse(
            request,
            "game.html",
            {
                "screenshot_url": screenshot_url,
                "hint_text": result.hint_text,
                "message": "Game over.",
                "answer": gs.current_game.name,
                "attempt_count": gs.attempt_count,
                "max_attempts": MAX_ATTEMPTS,
                "show_guess_form": False,
            },
        )
    screenshot_url = service.get_current_screenshot_url(gs)
    return templates.TemplateResponse(
        request,
        "game.html",
        {
            "screenshot_url": screenshot_url,
            "hint_text": result.hint_text,
            "message": None,
            "answer": None,
            "attempt_count": gs.attempt_count,
            "max_attempts": MAX_ATTEMPTS,
            "show_guess_form": True,
        },
    )


@game_router.get("/play-again")
async def play_again(request: Request) -> Any:
    """Clear game session and start a new game."""
    for key in ("game_session", "message", "answer", "last_hint"):
        _session(request).pop(key, None)
    return RedirectResponse(url="/new-game", status_code=302)
