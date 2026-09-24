"""The content pack: cards, decks and translations as clients receive them (ADR 0003, 0006)."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opengwt.core.model import DEFAULT_RULES, Deck, Library, Rules
from opengwt.core.serialize import canonical_json, rules_to_dict
from opengwt.data import load_cards_raw, load_data
from opengwt.i18n import Renderer
from opengwt.server.services.decks import provisions_to_dict

PACK_SCHEMA = "opengwt.pack/2"


@dataclass
class Content:
    """What the server serves and plays with. ``rules`` is the one ``Rules`` value of the
    server (cards.md §4): the pack publishes it, decks are judged by it and matches start with
    it."""

    rules: Rules
    library: Library
    starter_decks: dict[str, Deck]
    i18n: dict[str, dict[str, str]]
    renderer: Renderer
    pack: dict[str, Any]
    pack_hash: str


def deck_entries(deck: Deck) -> list[dict[str, Any]]:
    counts = Counter(deck.cards)
    return [{"id": cid, "count": n} for cid, n in counts.items()]


def load_content(data_dir: Path, rules: Rules = DEFAULT_RULES) -> Content:
    data = load_data(data_dir, rules)
    raw = load_cards_raw(data_dir / "cards")
    body: dict[str, Any] = {
        "schema": PACK_SCHEMA,
        # the Rules the server plays with; clients read row capacity and hand limit from here
        "rules": rules_to_dict(rules),
        "factions": sorted({d.faction for d in data.library.values()}),
        "cards": [{"id": cid, **mapping} for cid, mapping in raw.items()],
        "decks": [
            {
                "id": deck_id,
                "faction": d.faction,
                "leader": d.leader,
                "stratagem": d.stratagem,
                "cards": deck_entries(d),
                "provisions": provisions_to_dict(data.library, d, rules),
            }
            for deck_id, d in sorted(data.decks.items())
        ],
        "i18n": data.i18n,
    }
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    pack_hash = "sha256:" + digest
    return Content(
        rules=rules,
        library=data.library,
        starter_decks=data.decks,
        i18n=data.i18n,
        renderer=Renderer(data.i18n),
        pack={**body, "hash": pack_hash},
        pack_hash=pack_hash,
    )
