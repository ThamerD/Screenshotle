"""
Application entry point: creates and configures the FastAPI app.

This module is the single place where the web app is assembled. Other modules
(models, clients, services, routes) are registered here as they are added.

Loads .env from the project root (and cwd) when the app starts so uvicorn gets
the same env vars as when you run scripts with exported variables.
"""

from pathlib import Path

from dotenv import load_dotenv

# Load .env: first from project root (path relative to this file), then from cwd
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
load_dotenv(_env_path)
load_dotenv()  # fallback: .env in current working directory

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import Config
from app.middleware import ServerSideSessionMiddleware
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

    # Session: server-side store (session_store); cookie holds only session ID so it stays under 4KB
    app.state.session_store = {}
    app.add_middleware(ServerSideSessionMiddleware)

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
