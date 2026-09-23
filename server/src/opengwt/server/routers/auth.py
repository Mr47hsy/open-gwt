from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from opengwt.server.db.models import Player
from opengwt.server.errors import AppError
from opengwt.server.routers.deps import current_player, get_session
from opengwt.server.schemas import GuestRequest, Profile, ProfileUpdate, TokenResponse
from opengwt.server.services.auth import create_token, new_id

router = APIRouter()


@router.post("/auth/guest", response_model=TokenResponse)
async def guest(
    body: GuestRequest, request: Request, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    settings = request.app.state.settings
    player = Player(
        id=new_id(),
        display_name=body.display_name or "Guest",
        locale=None,
        created_at=datetime.now(timezone.utc),
    )
    session.add(player)
    await session.flush()
    token = create_token(player.id, settings.auth_secret, settings.token_ttl_seconds)
    return TokenResponse(token=token, player_id=player.id)


def _profile(player: Player) -> Profile:
    return Profile(player_id=player.id, display_name=player.display_name, locale=player.locale)


@router.get("/me", response_model=Profile)
async def me(player: Player = Depends(current_player)) -> Profile:
    return _profile(player)


@router.patch("/me", response_model=Profile)
async def update_me(
    body: ProfileUpdate,
    request: Request,
    player: Player = Depends(current_player),
    session: AsyncSession = Depends(get_session),
) -> Profile:
    if body.locale is not None and not request.app.state.renderer.has(body.locale):
        raise AppError("locale_unsupported", 422, {"locale": body.locale})
    if body.display_name is not None:
        player.display_name = body.display_name
    if body.locale is not None:
        player.locale = body.locale
    session.add(player)
    await session.flush()
    return _profile(player)
