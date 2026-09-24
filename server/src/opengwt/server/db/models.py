"""Tables. Portable column types only: the same migrations run on SQLite, PostgreSQL and MySQL."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, PrimaryKeyConstraint, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64))
    locale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeckRow(Base):
    """A saved deck. Its id is the owner's own name for it, so two players may each keep a deck
    of the same id: the key is the pair."""

    __tablename__ = "decks"
    __table_args__ = (PrimaryKeyConstraint("player_id", "id"),)

    id: Mapped[str] = mapped_column(String(64))
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("players.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    faction: Mapped[str] = mapped_column(String(64))
    leader: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # ADR 0011; decks saved before it have none and are refused until they name one
    stratagem: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cards: Mapped[list[Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MatchRow(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    room_code: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    # 64 lowercase hex characters (ADR 0010); a match from before ADR 0009 phase B keeps its old
    # 31-bit integer seed, written in decimal
    seed: Mapped[str] = mapped_column(String(64))
    seat0_player_id: Mapped[str] = mapped_column(String(32), index=True)
    seat1_player_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    decks: Mapped[list[Any]] = mapped_column(JSON)
    rules: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MatchIntentRow(Base):
    """The durable intent log of a match: what replay needs and nothing else (ADR 0008)."""

    __tablename__ = "match_intents"

    match_id: Mapped[str] = mapped_column(String(32), ForeignKey("matches.id"), primary_key=True)
    index: Mapped[int] = mapped_column(Integer, primary_key=True)
    seat: Mapped[int] = mapped_column(Integer)
    intent: Mapped[dict[str, Any]] = mapped_column(JSON)
