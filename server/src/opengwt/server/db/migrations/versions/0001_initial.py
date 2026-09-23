"""players, decks, matches and the intent log

Revision ID: 0001
Revises:
Create Date: 2026-09-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("locale", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "decks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("player_id", sa.String(32), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("faction", sa.String(64), nullable=False),
        sa.Column("leader", sa.String(64), nullable=True),
        sa.Column("cards", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_decks_player_id", "decks", ["player_id"])
    op.create_table(
        "matches",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("room_code", sa.String(16), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("seat0_player_id", sa.String(32), nullable=False),
        sa.Column("seat1_player_id", sa.String(32), nullable=True),
        sa.Column("decks", sa.JSON(), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_matches_status", "matches", ["status"])
    op.create_index("ix_matches_room_code", "matches", ["room_code"])
    op.create_index("ix_matches_seat0_player_id", "matches", ["seat0_player_id"])
    op.create_index("ix_matches_seat1_player_id", "matches", ["seat1_player_id"])
    op.create_table(
        "match_intents",
        sa.Column("match_id", sa.String(32), sa.ForeignKey("matches.id"), primary_key=True),
        sa.Column("index", sa.Integer(), primary_key=True),
        sa.Column("seat", sa.Integer(), nullable=False),
        sa.Column("intent", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("match_intents")
    op.drop_index("ix_matches_seat1_player_id", table_name="matches")
    op.drop_index("ix_matches_seat0_player_id", table_name="matches")
    op.drop_index("ix_matches_room_code", table_name="matches")
    op.drop_index("ix_matches_status", table_name="matches")
    op.drop_table("matches")
    op.drop_index("ix_decks_player_id", table_name="decks")
    op.drop_table("decks")
    op.drop_table("players")
