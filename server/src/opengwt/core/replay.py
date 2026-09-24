"""A match is a seed plus decks plus the accepted intents. Replaying reproduces it exactly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .engine import apply, new_match
from .events import Event
from .intents import Intent, intent_from_dict, intent_to_dict
from .model import Deck, Library, MatchState, Rules
from .rng import parse_seed
from .serialize import deck_from_dict, deck_to_dict, rules_from_dict, rules_to_dict

RECORD_SCHEMA = "opengwt.record/2"


@dataclass(frozen=True)
class MatchRecord:
    """``seed`` is 256 bits as 64 lowercase hex characters (ADR 0010)."""

    seed: str
    decks: tuple[Deck, Deck]
    intents: tuple[tuple[int, Intent], ...]
    rules: Rules = field(default_factory=Rules)


def record_to_dict(record: MatchRecord) -> dict[str, Any]:
    return {
        "schema": RECORD_SCHEMA,
        "seed": record.seed,
        "rules": rules_to_dict(record.rules),
        "decks": [deck_to_dict(d) for d in record.decks],
        "intents": [{"seat": seat, "intent": intent_to_dict(i)} for seat, i in record.intents],
    }


def record_from_dict(d: dict[str, Any]) -> MatchRecord:
    if d.get("schema") != RECORD_SCHEMA:
        raise ValueError(f"unsupported record schema {d.get('schema')!r}")
    seed = str(d["seed"])
    parse_seed(seed)
    decks = tuple(deck_from_dict(x) for x in d["decks"])
    if len(decks) != 2:
        raise ValueError("a record has exactly two decks")
    return MatchRecord(
        seed=seed,
        decks=(decks[0], decks[1]),
        intents=tuple((int(x["seat"]), intent_from_dict(x["intent"])) for x in d["intents"]),
        rules=rules_from_dict(d["rules"]),
    )


def replay(lib: Library, record: MatchRecord) -> tuple[MatchState, list[Event]]:
    """Play a record's intents again. Its decks are not judged by today's deck-building rules,
    only by what the engine needs (``new_match``): a record stays replayable when deck building
    tightens (cards.md §12)."""
    state, events = new_match(lib, record.decks, record.seed, record.rules, check_legality=False)
    for seat, intent in record.intents:
        state, more = apply(lib, state, seat, intent)
        events.extend(more)
    return state, events
