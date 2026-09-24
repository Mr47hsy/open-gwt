from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from opengwt.server.db.models import Player
from opengwt.server.routers.decks import resolve_deck
from opengwt.server.routers.deps import current_player, get_session, match_service
from opengwt.server.schemas import CreateMatch, JoinMatch, MatchCreated, MatchStatus
from opengwt.server.services.matches import MatchInfo, MatchService

router = APIRouter()


def ws_url(request: Request, match_id: str) -> str:
    scheme = "wss" if request.url.scheme == "https" else "ws"
    host = request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}/ws/matches/{match_id}"


def _created(request: Request, info: MatchInfo) -> MatchCreated:
    return MatchCreated(
        match_id=info.match_id, room_code=info.room_code, ws_url=ws_url(request, info.match_id)
    )


@router.post("/matches", response_model=MatchCreated, status_code=201)
async def create_match(
    body: CreateMatch,
    request: Request,
    player: Player = Depends(current_player),
    session: AsyncSession = Depends(get_session),
    service: MatchService = Depends(match_service),
) -> MatchCreated:
    deck = await resolve_deck(request, session, player.id, body.deck_id)
    await session.commit()
    if body.mode == "bot":
        info = await service.create_bot_match(player.id, deck)
    else:
        info = await service.create_room(player.id, deck)
    return _created(request, info)


@router.post("/matches/join", response_model=MatchCreated)
async def join_match(
    body: JoinMatch,
    request: Request,
    player: Player = Depends(current_player),
    session: AsyncSession = Depends(get_session),
    service: MatchService = Depends(match_service),
) -> MatchCreated:
    # judged by the rules the room was made with, in join_room
    deck = await resolve_deck(request, session, player.id, body.deck_id, judge=False)
    await session.commit()
    info = await service.join_room(player.id, deck, body.room_code)
    return _created(request, info)


@router.get("/matches/{match_id}", response_model=MatchStatus)
async def match_status(
    match_id: str,
    player: Player = Depends(current_player),
    service: MatchService = Depends(match_service),
) -> MatchStatus:
    info = await service.get_info(match_id)
    return MatchStatus(
        match_id=info.match_id,
        mode=info.mode,
        status=info.status,
        seat=info.seat_of(player.id),
        room_code=info.room_code,
        result=info.result,
    )


@router.get("/matches/{match_id}/replay")
async def match_replay(
    match_id: str,
    player: Player = Depends(current_player),
    service: MatchService = Depends(match_service),
) -> dict[str, Any]:
    return await service.replay_record(match_id, player.id)
