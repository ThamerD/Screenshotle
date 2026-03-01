"""
Application entry point: creates and configures the FastAPI app.

This module is the single place where the web app is assembled. Other modules
(models, clients, services, routes) are registered here as they are added.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import Config
from app.clients import IGDBClient, OpenAIClient
from app.services import GameService
from app.routes import game_router


def create_app() -> FastAPI:
    """
    Create and return the FastAPI application instance.
    Config is loaded from the environment; routes and middleware are attached here.
    """
    config = Config()
    app = FastAPI(
        title=config.APP_NAME,
        description="Guess the video game from a screenshot.",
        debug=config.DEBUG,
    )
    app.state.config = config

    # Session: signed cookie; required for game state (current game, screenshot index, attempts)
    app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET_KEY)

    # Game service: only available when IGDB and OpenAI credentials are set
    if config.has_igdb_credentials() and config.has_openai_key():
        igdb = IGDBClient(client_id=config.TWITCH_CLIENT_ID, client_secret=config.TWITCH_CLIENT_SECRET)
        openai = OpenAIClient(api_key=config.OPENAI_API_KEY)
        app.state.game_service = GameService(igdb_client=igdb, openai_client=openai)
    else:
        app.state.game_service = None

    # Mount static files from project root/static (when the folder exists)
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(game_router)

    return app


# Single app instance for ASGI servers (e.g. uvicorn app.main:app)
app = create_app()
