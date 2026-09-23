"""The content pack: cards, decks and translations as clients receive them (ADR 0003, 0006)."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opengwt.core.model import Deck, Library
from opengwt.core.serialize import canonical_json
from opengwt.data import load_cards_raw, load_data
from opengwt.i18n import Renderer

PACK_SCHEMA = "opengwt.pack/1"


@dataclass
class Content:
    library: Library
    starter_decks: dict[str, Deck]
    i18n: dict[str, dict[str, str]]
    renderer: Renderer
    pack: dict[str, Any]
    pack_hash: str


def deck_entries(deck: Deck) -> list[dict[str, Any]]:
    counts = Counter(deck.cards)
    return [{"id": cid, "count": n} for cid, n in counts.items()]


def load_content(data_dir: Path) -> Content:
    data = load_data(data_dir)
    raw = load_cards_raw(data_dir / "cards")
    body: dict[str, Any] = {
        "schema": PACK_SCHEMA,
        "factions": sorted({d.faction for d in data.library.values()}),
        "cards": [{"id": cid, **mapping} for cid, mapping in raw.items()],
        "decks": [
            {"id": deck_id, "faction": d.faction, "leader": d.leader, "cards": deck_entries(d)}
            for deck_id, d in sorted(data.decks.items())
        ],
        "i18n": data.i18n,
    }
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    pack_hash = "sha256:" + digest
    return Content(
        library=data.library,
        starter_decks=data.decks,
        i18n=data.i18n,
        renderer=Renderer(data.i18n),
        pack={**body, "hash": pack_hash},
        pack_hash=pack_hash,
    )
