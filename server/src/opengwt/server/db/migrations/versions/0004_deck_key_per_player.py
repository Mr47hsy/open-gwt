"""decks are keyed by (player_id, id): a deck id is its owner's own name for it

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-24

The id alone was the key, so once one player had saved a deck ``mine`` no other player could.
Existing rows keep their ids; they were unique, so they are unique per player too.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _rekey_decks(old: list[str], new: list[str]) -> None:
    # PostgreSQL named the key of 0001 decks_pkey and MySQL drops a key whatever its name.
    # SQLite cannot alter a key, so batch mode rebuilds the table there from a reflection that
    # sees that key without a name; naming it lets the rebuild leave it out.
    key = sa.PrimaryKeyConstraint(*old, name="decks_pkey")
    with op.batch_alter_table("decks", reflect_args=(key,)) as batch:
        batch.drop_constraint("decks_pkey", type_="primary")
        batch.create_primary_key("decks_pkey", new)


def upgrade() -> None:
    _rekey_decks(["id"], ["player_id", "id"])


def downgrade() -> None:
    # a global key holds one deck per id: of the players who share one, the smallest player id
    # keeps it and the others lose theirs
    decks = sa.table("decks", sa.column("player_id", sa.String), sa.column("id", sa.String))
    bind = op.get_bind()
    rows = bind.execute(sa.select(decks.c.id, decks.c.player_id)).all()
    keeper: dict[str, str] = {}
    for deck_id, player_id in rows:
        keeper[deck_id] = min(keeper.get(deck_id, player_id), player_id)
    for deck_id, player_id in rows:
        if player_id != keeper[deck_id]:
            bind.execute(
                decks.delete().where(decks.c.id == deck_id, decks.c.player_id == player_id)
            )
    _rekey_decks(["player_id", "id"], ["id"])
