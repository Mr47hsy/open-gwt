"""Deck building — docs/protocol/cards.md §12, the rules core's ``check_deck`` (ADR 0009 phase D).

Every rule is checked at its boundary: a deck exactly at a limit is legal, one past it is not,
and a deck breaking several rules reports all of them at once, in the order of §12.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

import pytest

from opengwt.core.engine import (
    DECK_OVER_BUDGET,
    DECK_TOO_FEW_UNITS,
    DECK_TOO_MANY_COPIES,
    check_deck,
    deck_provisions,
    new_match,
)
from opengwt.core.model import Deck, DeckProblem, Library, Rules, card_def_from_mapping
from opengwt.core.replay import MatchRecord, replay
from opengwt.core.rng import seed_from_int

RULES = Rules()
SEED = seed_from_int(7)


def _unit(color: str, provisions: int) -> dict[str, Any]:
    return {"kind": "unit", "color": color, "provisions": provisions, "power": 3}


def _special(provisions: int) -> dict[str, Any]:
    return {
        "kind": "special",
        "color": "bronze",
        "provisions": provisions,
        "abilities": [{"when": "on_play", "do": "draw", "count": 1}],
    }


def _leader(bonus: int) -> dict[str, Any]:
    return {
        "kind": "leader",
        "provision_bonus": bonus,
        "abilities": [{"when": "on_activate", "do": "draw", "count": 1}],
    }


STRATAGEM: dict[str, Any] = {
    "kind": "stratagem",
    "abilities": [{"when": "on_activate", "do": "draw", "count": 1}],
}


def _library() -> Library:
    by_faction: dict[str, dict[str, dict[str, Any]]] = {
        "red": {
            **{f"r-u-{i:02}": _unit("bronze", 6) for i in range(1, 21)},
            "r-u-dear": _unit("bronze", 7),
            **{f"r-g-{i}": _unit("gold", 9) for i in range(1, 6)},
            **{f"r-s-{i:02}": _special(4) for i in range(1, 13)},
            "r-a-1": {"kind": "artifact", "color": "bronze", "provisions": 4},
            "r-tok": {"kind": "unit", "token": True, "power": 1},
            "r-leader": _leader(15),
            "r-leader-16": _leader(16),
            "r-strat": STRATAGEM,
        },
        "blue": {"b-u-1": _unit("bronze", 5), "b-leader": _leader(15), "b-strat": STRATAGEM},
        "neutral": {"n-u-1": _unit("bronze", 5), "n-leader": _leader(15), "n-strat": STRATAGEM},
    }
    return {
        cid: card_def_from_mapping(cid, faction, m)
        for faction, cards in by_faction.items()
        for cid, m in cards.items()
    }


LIB = _library()
# 25 units: ten bronze twice at 6 and five golds at 9 — 165 provisions, the whole budget
AT_THE_LIMIT: tuple[str, ...] = (
    *(f"r-u-{i:02}" for i in range(1, 11)),
    *(f"r-u-{i:02}" for i in range(1, 11)),
    *(f"r-g-{i}" for i in range(1, 6)),
)


def _deck(cards: tuple[str, ...], leader: str = "r-leader", stratagem: str = "r-strat") -> Deck:
    return Deck("red", cards, leader, stratagem)


def _swap(cards: tuple[str, ...], old: str, new: str) -> tuple[str, ...]:
    """``cards`` with the first ``old`` replaced by ``new``."""
    at = cards.index(old)
    return (*cards[:at], new, *cards[at + 1 :])


def _keys(problems: list[DeckProblem]) -> list[str]:
    return [str(p) for p in problems]


def test_a_deck_at_every_limit_is_legal() -> None:
    deck = _deck(AT_THE_LIMIT)
    assert len(deck.cards) == RULES.deck_min_cards
    assert check_deck(LIB, deck, RULES) == []
    assert deck_provisions(LIB, deck, RULES) == (165, 165)


def test_a_deck_needs_the_minimum_of_units() -> None:
    """Thirteen units by default; specials and artifacts are not units."""
    thirteen = (
        *(f"r-u-{i:02}" for i in range(1, 14)),
        *(f"r-s-{i:02}" for i in range(1, 13)),
    )
    assert check_deck(LIB, _deck(thirteen), RULES) == []
    for other in ("r-s-01", "r-a-1"):
        twelve = _swap(thirteen, "r-u-13", other)
        assert check_deck(LIB, _deck(twelve), RULES) == [
            DeckProblem(DECK_TOO_FEW_UNITS, numbers=(("count", 12), ("min", 13)))
        ]


def test_bronze_cards_twice_and_gold_cards_once() -> None:
    bronze = _swap(AT_THE_LIMIT, "r-u-10", "r-u-01")  # three r-u-01, apart from each other
    gold = _swap(AT_THE_LIMIT, "r-g-5", "r-g-1")
    assert check_deck(LIB, _deck(bronze), RULES) == [
        DeckProblem(DECK_TOO_MANY_COPIES, "r-u-01", (("count", 3), ("limit", 2)))
    ]
    assert check_deck(LIB, _deck(gold), RULES) == [
        DeckProblem(DECK_TOO_MANY_COPIES, "r-g-1", (("count", 2), ("limit", 1)))
    ]
    looser = replace(RULES, copies_bronze=3, copies_gold=2)
    assert check_deck(LIB, _deck(bronze), looser) == []
    assert check_deck(LIB, _deck(gold), looser) == []


def test_each_card_over_its_limit_is_reported_once_in_deck_order() -> None:
    cards = _swap(_swap(AT_THE_LIMIT, "r-g-5", "r-g-2"), "r-u-10", "r-u-09")
    assert _keys(check_deck(LIB, _deck(cards), RULES)) == [
        "error.deck.too-many-copies:r-u-09",
        "error.deck.too-many-copies:r-g-2",
    ]


def test_provisions_stay_within_the_leaders_budget() -> None:
    over = _swap(AT_THE_LIMIT, "r-u-10", "r-u-dear")
    assert check_deck(LIB, _deck(over), RULES) == [
        DeckProblem(DECK_OVER_BUDGET, numbers=(("used", 166), ("budget", 165)))
    ]
    assert deck_provisions(LIB, _deck(over, leader="r-leader-16"), RULES) == (166, 166)
    assert check_deck(LIB, _deck(over, leader="r-leader-16"), RULES) == []
    assert check_deck(LIB, _deck(over), replace(RULES, provision_base=151)) == []


def test_the_budget_is_not_judged_without_a_leader() -> None:
    """The leader sets the budget: with none to read it from, only the leader is reported."""
    over = _swap(AT_THE_LIMIT, "r-u-10", "r-u-dear")
    for leader, key in (("nope", "unknown-card"), ("r-u-01", "leader-not-leader")):
        assert _keys(check_deck(LIB, _deck(over, leader=leader), RULES)) == [
            f"error.deck.{key}:{leader}"
        ]
    assert deck_provisions(LIB, _deck(over, leader="nope"), RULES) == (166, 150)


def test_the_leader_belongs_to_the_decks_own_faction_never_neutral() -> None:
    for leader in ("b-leader", "n-leader"):
        assert _keys(check_deck(LIB, _deck(AT_THE_LIMIT, leader=leader), RULES)) == [
            f"error.deck.wrong-faction:{leader}"
        ]
    neutral_deck = Deck("neutral", ("n-u-1",) * 2, "n-leader", "n-strat")
    assert "error.deck.wrong-faction:n-leader" in _keys(check_deck(LIB, neutral_deck, RULES))


def test_the_stratagem_and_cards_belong_to_the_faction_or_neutral() -> None:
    assert check_deck(LIB, _deck(AT_THE_LIMIT, stratagem="n-strat"), RULES) == []
    cards = _swap(_swap(AT_THE_LIMIT, "r-u-10", "n-u-1"), "r-u-09", "b-u-1")
    assert _keys(check_deck(LIB, _deck(cards, stratagem="b-strat"), RULES)) == [
        "error.deck.wrong-faction:b-strat",
        "error.deck.wrong-faction:b-u-1",
    ]


def test_between_the_fewest_and_the_most_cards() -> None:
    assert _keys(check_deck(LIB, _deck(AT_THE_LIMIT[:-1]), RULES)) == ["error.deck.too-few-cards"]
    assert check_deck(LIB, _deck(AT_THE_LIMIT[:-1]), RULES)[0].numbers == (
        ("count", 24),
        ("min", 25),
    )
    forty = tuple(f"r-u-{i:02}" for i in range(1, 21)) * 2
    roomy = replace(RULES, provision_base=1000)
    assert check_deck(LIB, _deck(forty), roomy) == []
    assert check_deck(LIB, _deck((*forty, "r-g-1")), roomy) == [
        DeckProblem("error.deck.too-many-cards", numbers=(("count", 41), ("max", 40)))
    ]


def test_what_a_deck_never_holds_is_reported_and_not_counted() -> None:
    """A leader, a stratagem or a token among the cards, and an unknown card, are reported by
    themselves: they are not units, have no copy limit and cost nothing."""
    cards = (*AT_THE_LIMIT[:12], "r-leader", "r-strat", "r-tok", "nope", "r-tok")
    problems = _keys(check_deck(LIB, _deck(cards, leader="r-u-01", stratagem="r-leader"), RULES))
    assert problems == [
        "error.deck.leader-not-leader:r-u-01",
        "error.deck.stratagem-not-stratagem:r-leader",
        "error.deck.leader-in-deck:r-leader",
        "error.deck.stratagem-in-deck:r-strat",
        "error.deck.token-in-deck:r-tok",
        "error.deck.unknown-card:nope",
        "error.deck.too-few-cards",
        "error.deck.too-few-units",
    ]
    units = next(p for p in check_deck(LIB, _deck(cards), RULES) if p.key == DECK_TOO_FEW_UNITS)
    assert dict(units.numbers) == {"count": 12, "min": 13}
    assert deck_provisions(LIB, _deck(cards), RULES) == (72, 165)


def test_every_problem_at_once_in_the_order_of_the_rules() -> None:
    cards = (
        "b-u-1",
        *(("r-u-01",) * 3),
        *(("r-g-1",) * 2),
        "r-s-01",
        "r-tok",
        *(("r-u-dear",) * 2),
    )
    problems = check_deck(LIB, Deck("red", cards, "n-leader", "b-strat"), RULES)
    assert _keys(problems) == [
        "error.deck.wrong-faction:n-leader",
        "error.deck.wrong-faction:b-strat",
        "error.deck.wrong-faction:b-u-1",
        "error.deck.token-in-deck:r-tok",
        "error.deck.too-few-cards",
        "error.deck.too-few-units",
        "error.deck.too-many-copies:r-u-01",
        "error.deck.too-many-copies:r-g-1",
    ]
    over = check_deck(LIB, _deck((*AT_THE_LIMIT, *(("r-u-dear",) * 3))), RULES)
    assert _keys(over) == ["error.deck.too-many-copies:r-u-dear", "error.deck.over-budget"]
    assert dict(over[1].numbers) == {"used": 186, "budget": 165}


def test_a_match_starts_only_with_legal_decks() -> None:
    legal = _deck(AT_THE_LIMIT)
    three = _deck(_swap(AT_THE_LIMIT, "r-u-10", "r-u-01"))
    with pytest.raises(
        ValueError, match=re.escape("seat 1 is not legal: error.deck.too-many-copies:r-u-01")
    ):
        new_match(LIB, (legal, three), SEED)
    unknown = _deck(_swap(AT_THE_LIMIT, "r-u-10", "nope"))
    with pytest.raises(ValueError, match=re.escape("error.deck.unknown-card:nope")):
        new_match(LIB, (legal, unknown), SEED, check_legality=False)


def test_a_record_replays_whatever_deck_building_says_today() -> None:
    """A record was judged by the deck-building rules it was played under: replay holds its
    decks only to what the engine needs, so tightening deck building breaks no record."""
    three = _deck(_swap(AT_THE_LIMIT, "r-u-10", "r-u-01"))
    state, events = new_match(LIB, (three, three), SEED, check_legality=False)
    again, replayed = replay(LIB, MatchRecord(SEED, (three, three), ()))
    assert replayed == events and again.players[0].deck == state.players[0].deck
