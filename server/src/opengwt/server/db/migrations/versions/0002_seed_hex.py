"""matches.seed becomes 64 hex characters (ADR 0010)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23

Existing rows keep their 31-bit seed written in decimal: they are matches played before ADR 0009
phase B, kept as history; their records stay ``opengwt.record/1``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("matches") as batch:
        batch.alter_column(
            "seed",
            existing_type=sa.Integer(),
            type_=sa.String(64),
            existing_nullable=False,
            postgresql_using="seed::varchar(64)",
        )


def downgrade() -> None:
    # only rows from before phase B hold a decimal seed; a hex seed has no integer form
    v2 = "SELECT id FROM matches WHERE length(seed) = 64"
    op.execute(f"DELETE FROM match_intents WHERE match_id IN ({v2})")
    op.execute("DELETE FROM matches WHERE length(seed) = 64")
    with op.batch_alter_table("matches") as batch:
        batch.alter_column(
            "seed",
            existing_type=sa.String(64),
            type_=sa.Integer(),
            existing_nullable=False,
            postgresql_using="seed::integer",
        )
