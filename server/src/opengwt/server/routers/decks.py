from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opengwt.core.engine import check_deck
from opengwt.core.model import Deck
from opengwt.server.db.models import DeckRow, Player
from opengwt.server.errors import AppError
from opengwt.server.routers.deps import current_player, get_session
from opengwt.server.schemas import DeckCardEntry, DeckOut, DeckProvisions, DeckUpsert
from opengwt.server.services.content import Content
from opengwt.server.services.decks import problems_to_list, provisions_to_dict

router = APIRouter()


def _deck(row: DeckRow) -> Deck:
    """A saved deck as the rules core reads it; one saved before ADR 0011 names no stratagem."""
    return Deck(
        faction=row.faction,
        cards=tuple(c["id"] for c in row.cards for _ in range(int(c["count"]))),
        leader=row.leader or "",
        stratagem=row.stratagem or "",
    )


def _out(row: DeckRow, content: Content) -> DeckOut:
    """A saved deck with its provisions and the rules it breaks under the server's ``Rules`` —
    a deck saved under older rules may break some (match.md §2)."""
    deck = _deck(row)
    return DeckOut(
        deck_id=row.id,
        name=row.name,
        faction=row.faction,
        leader=row.leader,
        stratagem=row.stratagem,
        cards=[DeckCardEntry(**c) for c in row.cards],
        provisions=DeckProvisions(**provisions_to_dict(content.library, deck, content.rules)),
        problems=problems_to_list(check_deck(content.library, deck, content.rules)),
    )


async def _own_deck(session: AsyncSession, player_id: str, deck_id: str) -> DeckRow | None:
    """The player's deck of that id. Deck ids are per player: another player's deck of the same
    id is a different deck, and never this one."""
    return await session.get(DeckRow, {"player_id": player_id, "id": deck_id})


async def resolve_deck(
    request: Request, session: AsyncSession, player_id: str, deck_id: str, judge: bool = True
) -> Deck:
    """A player's own deck by id, or one of the starter decks shipped with the content. A saved
    deck the server's rules make illegal — one saved under older rules, say — is refused with
    its problems, unless ``judge`` is off: joining a room judges it by the room's rules."""
    content: Content = request.app.state.content
    row = await _own_deck(session, player_id, deck_id)
    if row is not None:
        deck = _deck(row)
        problems = check_deck(content.library, deck, content.rules) if judge else []
        if problems:
            raise AppError("deck_illegal", 422, details={"problems": problems_to_list(problems)})
        return deck
    starter = content.starter_decks.get(deck_id)
    if starter is not None:
        return starter
    raise AppError("deck_not_found", 404, {"deck": deck_id})


@router.get("/decks", response_model=list[DeckOut])
async def list_decks(
    request: Request,
    player: Player = Depends(current_player),
    session: AsyncSession = Depends(get_session),
) -> list[DeckOut]:
    content: Content = request.app.state.content
    rows = (await session.execute(select(DeckRow).where(DeckRow.player_id == player.id))).scalars()
    return [_out(r, content) for r in rows]


@router.put("/decks/{deck_id}", response_model=DeckOut)
async def put_deck(
    deck_id: str,
    body: DeckUpsert,
    request: Request,
    player: Player = Depends(current_player),
    session: AsyncSession = Depends(get_session),
) -> DeckOut:
    content: Content = request.app.state.content
    deck = Deck(
        faction=body.faction,
        cards=tuple(c.id for c in body.cards for _ in range(c.count)),
        leader=body.leader,
        stratagem=body.stratagem,
    )
    problems = check_deck(content.library, deck, content.rules)
    if problems:
        raise AppError("deck_illegal", 422, details={"problems": problems_to_list(problems)})
    row = await _own_deck(session, player.id, deck_id)
    if row is None:
        row = DeckRow(id=deck_id, player_id=player.id, name=body.name, faction=body.faction)
        session.add(row)
    row.name = body.name
    row.faction = body.faction
    row.leader = body.leader
    row.stratagem = body.stratagem
    row.cards = [c.model_dump() for c in body.cards]
    row.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return _out(row, content)


@router.delete("/decks/{deck_id}", status_code=204)
async def delete_deck(
    deck_id: str,
    player: Player = Depends(current_player),
    session: AsyncSession = Depends(get_session),
) -> Response:
    row = await _own_deck(session, player.id, deck_id)
    if row is None:
        raise AppError("deck_not_found", 404, {"deck": deck_id})
    await session.delete(row)
    return Response(status_code=204)
