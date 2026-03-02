"""
Game routes: new game, submit guess, play again. Render Jinja2; read/write session.
"""

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

import requests
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.models import GameSession, dict_to_game_session, game_session_to_dict

# Max wrong guesses before game over (then show next screenshot; repeat until correct or this many attempts)
MAX_ATTEMPTS = 5

# Cache the game pool from IGDB; refresh when a new calendar day starts in PST (America/Los_Angeles)
PST = ZoneInfo("America/Los_Angeles")
# IGDB allows max 500 items per request (api-docs.igdb.com)
GAME_POOL_LIMIT = 500

# Session keys we clear when starting a new game or when consuming flash data
SESSION_KEYS_TO_CLEAR = [
    "game_session", "message", "answer",
    "last_hint", "last_genre_matches", "last_genre_mismatches",
    "last_generation_text", "last_generation_matched",
]
FLASH_KEYS = [k for k in SESSION_KEYS_TO_CLEAR if k != "game_session"]
# Hint-only keys (cleared on skip-guess so we don't show previous hint)
HINT_FLASH_KEYS = ["last_hint", "last_genre_matches", "last_genre_mismatches", "last_generation_text", "last_generation_matched"]


def _pst_date_string() -> str:
    """Current calendar date in PST (e.g. '2025-02-28'). Used to invalidate cache at start of each PST day."""
    return datetime.now(PST).strftime("%Y-%m-%d")
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
<footer style="margin-top:2.5rem;padding-top:1rem;border-top:1px solid #eee;color:#888;font-size:0.85rem;">
Created by Thamer <a href="https://github.com/Thamer" target="_blank" rel="noopener noreferrer" aria-label="Thamer on GitHub" style="color:#888;display:inline-flex;align-items:center;"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg></a>
</footer>
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
    # Consume flash data (show once)
    flash = {k: _session(request).pop(k, None) for k in FLASH_KEYS}
    return _render_game_page(
        request,
        gs,
        screenshot_url=screenshot_url,
        hint_text=flash.get("last_hint"),
        genre_matches=flash.get("last_genre_matches") or [],
        genre_mismatches=flash.get("last_genre_mismatches") or [],
        generation_text=flash.get("last_generation_text"),
        generation_matched=flash.get("last_generation_matched") or False,
        message=flash.get("message"),
        answer=flash.get("answer"),
        show_guess_form=flash.get("message") is None,
    )


def _get_or_fetch_game_pool(request: Request):
    """
    Return the game pool from app.state cache if still valid for the current PST day, else fetch from IGDB and update cache.
    Requires request.app.state.game_service to be set. Returns list of Game (may be empty).
    """
    service = _get_game_service(request)
    if not service:
        return None
    today_pst = _pst_date_string()
    cache = getattr(request.app.state, "game_pool_cache", None)
    if cache is not None:
        pool, cached_pst_date = cache
        if cached_pst_date == today_pst:
            print(f"[Screenshotle] Game pool: using cache ({len(pool)} games, PST date {today_pst})")
            return pool
    print(f"[Screenshotle] Game pool: fetching from IGDB (new PST day: {today_pst})...")
    pool = service.get_game_pool(limit=GAME_POOL_LIMIT)
    request.app.state.game_pool_cache = (pool, today_pst)
    print(f"[Screenshotle] Game pool: fetched {len(pool)} games from IGDB")
    return pool


@game_router.get("/new-game", response_class=HTMLResponse)
async def new_game(request: Request) -> Any:
    """
    Start a new round: use cached game pool (refresh from IGDB when a new day starts in PST), pick random game, save session, render game page.
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
    gs = service.start_new_game(pool)
    if gs.current_game is None:
        return HTMLResponse(
            "<h1>No games loaded</h1><p>Could not load games from IGDB (pool is empty). "
            "Check your Twitch/IGDB credentials and that the API is reachable.</p>"
            "<p><a href=\"/new-game\">Try again</a></p>",
            status_code=503,
        )
    _save_session(request, gs)
    screenshot_url = service.get_current_screenshot_url(gs)
    if not screenshot_url:
        return RedirectResponse(url="/", status_code=302)
    return _render_game_page(request, gs, screenshot_url=screenshot_url, show_guess_form=True)


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
        return _render_game_page(
            request, gs,
            screenshot_url=screenshot_url,
            message="You win!",
            answer=gs.current_game.name,
            show_guess_form=False,
        )
    _session(request)["last_hint"] = result.hint_text
    _session(request)["last_genre_matches"] = result.genre_matches
    _session(request)["last_genre_mismatches"] = result.genre_mismatches
    _session(request)["last_generation_text"] = result.generation_text
    _session(request)["last_generation_matched"] = result.generation_matched
    gs.attempt_count += 1
    gs.screenshot_index += 1
    _save_session(request, gs)
    screenshot_url = service.get_current_screenshot_url(gs)
    if gs.attempt_count >= MAX_ATTEMPTS:
        _session(request)["message"] = "Game over."
        _session(request)["answer"] = gs.current_game.name
        return _render_game_page(
            request, gs,
            screenshot_url=screenshot_url,
            hint_text=result.hint_text,
            genre_matches=result.genre_matches,
            genre_mismatches=result.genre_mismatches,
            generation_text=result.generation_text,
            generation_matched=result.generation_matched,
            message="Game over.",
            answer=gs.current_game.name,
            show_guess_form=False,
        )
    return _render_game_page(
        request, gs,
        screenshot_url=screenshot_url,
        hint_text=result.hint_text,
        genre_matches=result.genre_matches,
        genre_mismatches=result.genre_mismatches,
        generation_text=result.generation_text,
        generation_matched=result.generation_matched,
        show_guess_form=True,
    )


def _render_game_page(
    request: Request,
    gs: GameSession,
    *,
    screenshot_url: str | None,
    hint_text: str | None = None,
    genre_matches: list[str] | None = None,
    genre_mismatches: list[str] | None = None,
    generation_text: str | None = None,
    generation_matched: bool = False,
    message: str | None = None,
    answer: str | None = None,
    show_guess_form: bool = False,
) -> HTMLResponse:
    """Shared render for game page; pulls game_names from cache."""
    cache = getattr(request.app.state, "game_pool_cache", None)
    pool = cache[0] if cache else []
    game_names = [g.name for g in pool]
    return templates.TemplateResponse(
        request,
        "game.html",
        {
            "screenshot_url": screenshot_url,
            "hint_text": hint_text,
            "genre_matches": genre_matches or [],
            "genre_mismatches": genre_mismatches or [],
            "generation_text": generation_text,
            "generation_matched": generation_matched,
            "message": message,
            "answer": answer,
            "attempt_count": gs.attempt_count,
            "max_attempts": MAX_ATTEMPTS,
            "show_guess_form": show_guess_form,
            "game_names": game_names,
        },
    )


@game_router.post("/skip-guess", response_class=HTMLResponse)
async def skip_guess(request: Request) -> Any:
    """
    Forfeit one guess: advance to next screenshot and attempt count.
    If max attempts reached, show game over; otherwise show next screenshot (no hint).
    """
    service = _get_game_service(request)
    if not service:
        return HTMLResponse("<p>Service unavailable.</p>", status_code=503)
    gs = _get_session(request)
    if gs.current_game is None:
        return RedirectResponse(url="/new-game", status_code=302)
    for key in HINT_FLASH_KEYS:
        _session(request).pop(key, None)
    gs.attempt_count += 1
    gs.screenshot_index += 1
    _save_session(request, gs)
    screenshot_url = service.get_current_screenshot_url(gs)
    if gs.attempt_count >= MAX_ATTEMPTS:
        _session(request)["message"] = "Game over."
        _session(request)["answer"] = gs.current_game.name
        return _render_game_page(
            request, gs,
            screenshot_url=screenshot_url,
            message="Game over.",
            answer=gs.current_game.name,
            show_guess_form=False,
        )
    return _render_game_page(
        request, gs,
        screenshot_url=screenshot_url,
        show_guess_form=True,
    )


@game_router.get("/skip-game")
async def skip_game(request: Request) -> Any:
    """Skip current game and start a new one."""
    for key in SESSION_KEYS_TO_CLEAR:
        _session(request).pop(key, None)
    return RedirectResponse(url="/new-game", status_code=302)


@game_router.get("/play-again")
async def play_again(request: Request) -> Any:
    """Clear game session and start a new game."""
    for key in SESSION_KEYS_TO_CLEAR:
        _session(request).pop(key, None)
    return RedirectResponse(url="/new-game", status_code=302)
