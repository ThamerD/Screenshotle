"""
Application entry point: creates and configures the FastAPI app.

This module is the single place where the web app is assembled. Other modules
(models, clients, services, routes) are registered here as they are added.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import Config


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
    # Store config on app state so routes/services can access it if needed
    app.state.config = config

    # Mount static files from project root/static (when the folder exists)
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Health check for deployment (e.g. Render)
    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # TODO: include router when app.routes exists
    # from app.routes import game_router
    # app.include_router(game_router, ...)

    return app


# Single app instance for ASGI servers (e.g. uvicorn app.main:app)
app = create_app()
