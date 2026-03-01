"""
Server-side session middleware: session data stored in app.state, cookie holds only session ID.

Avoids cookie size limits (~4KB) that cause redirect loops when storing full game data.
"""

import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


SESSION_COOKIE_NAME = "sid"
SESSION_COOKIE_MAX_AGE = 14 * 24 * 3600  # 14 days


class ServerSideSessionMiddleware(BaseHTTPMiddleware):
    """
    Attach request.session as a dict backed by app.state.session_store[session_id].
    Cookie contains only the session ID; full session data lives server-side.
    """

    async def dispatch(self, request: Request, call_next):
        store = getattr(request.app.state, "session_store", None)
        if store is None:
            request.app.state.session_store = {}
            store = request.app.state.session_store

        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_id or session_id not in store:
            session_id = secrets.token_urlsafe(32)
            new_session = True
        else:
            new_session = False

        request.state.session = store.setdefault(session_id, {})

        response = await call_next(request)

        if new_session:
            response.set_cookie(
                SESSION_COOKIE_NAME,
                session_id,
                path="/",
                max_age=SESSION_COOKIE_MAX_AGE,
                httponly=True,
                samesite="lax",
            )

        return response
