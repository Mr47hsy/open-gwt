"""decks.stratagem: the stratagem a deck brings for going first (ADR 0011)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("decks") as batch:
        batch.add_column(sa.Column("stratagem", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("decks") as batch:
        batch.drop_column("stratagem")
