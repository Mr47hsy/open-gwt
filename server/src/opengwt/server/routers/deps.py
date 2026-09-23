"""FastAPI dependencies: database sessions, the authenticated player, the negotiated locale."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Header, Request, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from opengwt.i18n import negotiate_locale
from opengwt.server.db.models import Player
from opengwt.server.errors import AppError
from opengwt.server.services.auth import bearer_token, player_id_from_token
from opengwt.server.services.matches import MatchService


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _load_player(app_state: object, session: AsyncSession, token: str | None) -> Player:
    settings = getattr(app_state, "settings")  # noqa: B009 - app.state is dynamic
    if token is None:
        raise AppError("unauthorised", 401)
    player_id = player_id_from_token(token, settings.auth_secret)
    player = await session.get(Player, player_id)
    if player is None:
        raise AppError("unauthorised", 401)
    return player


async def current_player(
    request: Request,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
    accept_language: str | None = Header(default=None),
) -> Player:
    player = await _load_player(request.app.state, session, bearer_token(authorization))
    renderer = request.app.state.renderer
    request.state.locale = negotiate_locale(renderer.locales, player.locale, accept_language)
    return player


async def websocket_player(websocket: WebSocket, token: str | None) -> tuple[Player, str]:
    """The player behind a socket, from ``?token=`` or the Authorization header, plus locale."""
    header_token = bearer_token(websocket.headers.get("authorization"))
    async with websocket.app.state.sessions() as session:
        player = await _load_player(websocket.app.state, session, token or header_token)
    renderer = websocket.app.state.renderer
    locale = negotiate_locale(
        renderer.locales, player.locale, websocket.headers.get("accept-language")
    )
    return player, locale


def match_service(request: Request) -> MatchService:
    service: MatchService = request.app.state.matches
    return service
