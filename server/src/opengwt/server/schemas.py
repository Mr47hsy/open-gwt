"""Request and response bodies of the HTTP API (docs/protocol/match.md §2)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

# A deck id has the shape of the content's ids (decks.schema.json), so every starter deck's id is
# one; it fits `decks.id` (String(64)) and compares alike on every database (match.md §2).
DECK_ID_PATTERN = r"^[a-z][a-z0-9-]{1,63}$"
DeckId = Annotated[str, Field(pattern=DECK_ID_PATTERN)]


class GuestRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)


class TokenResponse(BaseModel):
    token: str
    player_id: str


class Profile(BaseModel):
    player_id: str
    display_name: str
    locale: str | None


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    locale: str | None = Field(default=None, max_length=16)


class DeckCardEntry(BaseModel):
    id: str
    count: int = Field(ge=1, le=99)


class DeckUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    faction: str
    leader: str
    stratagem: str
    cards: list[DeckCardEntry]


class DeckProvisions(BaseModel):
    used: int
    budget: int


class DeckOut(BaseModel):
    deck_id: str
    name: str
    faction: str
    leader: str | None
    stratagem: str | None
    cards: list[DeckCardEntry]
    provisions: DeckProvisions
    # the deck-building rules the deck breaks, as in an error's details (match.md §10)
    problems: list[dict[str, Any]]


class CreateMatch(BaseModel):
    mode: Literal["bot", "room"]
    deck_id: DeckId


class JoinMatch(BaseModel):
    room_code: str = Field(min_length=1, max_length=16)
    deck_id: DeckId


class MatchCreated(BaseModel):
    match_id: str
    room_code: str | None
    ws_url: str


class MatchStatus(BaseModel):
    match_id: str
    mode: str
    status: str
    seat: int | None
    room_code: str | None
    result: dict[str, Any] | None
