"""
External API clients: IGDB (games, screenshots) and OpenAI (guess check, hints).
"""

from app.clients.igdb_client import IGDBClient
from app.clients.openai_client import OpenAIClient

__all__ = ["IGDBClient", "OpenAIClient"]
