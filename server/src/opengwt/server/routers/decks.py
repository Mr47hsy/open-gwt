from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opengwt.core.engine import check_deck
from opengwt.core.model import Deck, Rules
from opengwt.server.db.models import DeckRow, Player
from opengwt.server.errors import AppError
from opengwt.server.routers.deps import current_player, get_session
from opengwt.server.schemas import DeckCardEntry, DeckOut, DeckUpsert
from opengwt.server.services.content import Content

router = APIRouter()


def _out(row: DeckRow) -> DeckOut:
    return DeckOut(
        deck_id=row.id,
        name=row.name,
        faction=row.faction,
        leader=row.leader,
        cards=[DeckCardEntry(**c) for c in row.cards],
    )


async def resolve_deck(
    request: Request, session: AsyncSession, player_id: str, deck_id: str
) -> Deck:
    """A player's own deck by id, or one of the starter decks shipped with the content. A saved
    deck the current content makes illegal — one saved before ADR 0009 phase B, say — is refused
    with its problems."""
    content: Content = request.app.state.content
    row = await session.get(DeckRow, deck_id)
    if row is not None and row.player_id == player_id:
        deck = Deck(
            faction=row.faction,
            cards=tuple(c["id"] for c in row.cards for _ in range(int(c["count"]))),
            leader=row.leader or "",
        )
        problems = check_deck(content.library, deck, Rules())
        if problems:
            raise AppError("deck_illegal", 422, details={"problems": problems})
        return deck
    starter = content.starter_decks.get(deck_id)
    if starter is not None:
        return starter
    raise AppError("deck_not_found", 404, {"deck": deck_id})


@router.get("/decks", response_model=list[DeckOut])
async def list_decks(
    player: Player = Depends(current_player), session: AsyncSession = Depends(get_session)
) -> list[DeckOut]:
    rows = (await session.execute(select(DeckRow).where(DeckRow.player_id == player.id))).scalars()
    return [_out(r) for r in rows]


@router.put("/decks/{deck_id}", response_model=DeckOut)
async def put_deck(
    deck_id: str,
    body: DeckUpsert,
    request: Request,
    player: Player = Depends(current_player),
    session: AsyncSession = Depends(get_session),
) -> DeckOut:
    library = request.app.state.content.library
    deck = Deck(
        faction=body.faction,
        cards=tuple(c.id for c in body.cards for _ in range(c.count)),
        leader=body.leader,
    )
    problems = check_deck(library, deck, Rules())
    if problems:
        raise AppError("deck_illegal", 422, details={"problems": problems})
    row = await session.get(DeckRow, deck_id)
    if row is not None and row.player_id != player.id:
        raise AppError("deck_not_found", 404, {"deck": deck_id})
    if row is None:
        row = DeckRow(id=deck_id, player_id=player.id, name=body.name, faction=body.faction)
        session.add(row)
    row.name = body.name
    row.faction = body.faction
    row.leader = body.leader
    row.cards = [c.model_dump() for c in body.cards]
    row.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return _out(row)


@router.delete("/decks/{deck_id}", status_code=204)
async def delete_deck(
    deck_id: str,
    player: Player = Depends(current_player),
    session: AsyncSession = Depends(get_session),
) -> Response:
    row = await session.get(DeckRow, deck_id)
    if row is None or row.player_id != player.id:
        raise AppError("deck_not_found", 404, {"deck": deck_id})
    await session.delete(row)
    return Response(status_code=204)
