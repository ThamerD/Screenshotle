"""
HTTP endpoints: new game, submit guess, play again. Jinja2 templates; session read/write.
"""

from app.routes.game import game_router

__all__ = ["game_router"]
