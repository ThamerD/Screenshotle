"""
Game routes: new game, submit guess, play again. Render Jinja2; read/write session.
"""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.models import GameSession
from app.routes.session_serializer import dict_to_game_session, game_session_to_dict

# Max wrong guesses before game over (then show next screenshot; repeat until correct or this many attempts)
MAX_ATTEMPTS = 5

# Templates at project root / templates
TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

game_router = APIRouter(tags=["game"])


def _get_game_service(request: Request):
    """GameService is attached to app.state in main."""
    return getattr(request.app.state, "game_service", None)


def _get_session(request: Request) -> GameSession:
    """Load GameSession from request.session; default empty session."""
    data = request.session.get("game_session")
    if not data:
        return GameSession(current_game=None, screenshot_index=0, attempt_count=0)
    return dict_to_game_session(data)


def _save_session(request: Request, gs: GameSession) -> None:
    """Persist GameSession into request.session."""
    request.session["game_session"] = game_session_to_dict(gs)


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
    last_hint = request.session.pop("last_hint", None)
    message = request.session.pop("message", None)
    answer = request.session.pop("answer", None)
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


@game_router.get("/new-game")
async def new_game(request: Request) -> Any:
    """
    Start a new round: fetch pool, pick random game, save session, redirect to game page.
    """
    service = _get_game_service(request)
    if not service:
        return RedirectResponse(url="/", status_code=302)
    pool = service.get_game_pool(limit=200)
    gs = service.start_new_game(pool)
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
        request.session["message"] = "You win!"
        request.session["answer"] = gs.current_game.name
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
    request.session["last_hint"] = result.hint_text
    gs.attempt_count += 1
    gs.screenshot_index += 1
    _save_session(request, gs)
    if gs.attempt_count >= MAX_ATTEMPTS:
        request.session["message"] = "Game over."
        request.session["answer"] = gs.current_game.name
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
        request.session.pop(key, None)
    return RedirectResponse(url="/new-game", status_code=302)
