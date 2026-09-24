"""Decks on the wire: a deck's provisions and the deck-building rules it breaks, in the shapes of
docs/protocol/match.md §2 and §10 (cards.md §12)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from opengwt.core.engine import DECK_UNKNOWN_CARD, deck_provisions
from opengwt.core.model import Deck, DeckProblem, Library, Rules
from opengwt.i18n import Param


def _literal(text: str) -> str:
    """A string parameter rendered as it is, even one that starts with ``@`` (i18n.md §4)."""
    return "@" + text if text.startswith("@") else text


def problem_to_dict(problem: DeckProblem) -> dict[str, Any]:
    """``{key, card?, params}``: the rule's key, the id of the card it is about, and parameters a
    client renders the key with — ``card`` as a reference to the card's name, or, for a card the
    pack does not have, the id itself, with an ``@`` in front when it starts with one."""
    params: dict[str, Param] = dict(problem.numbers)
    out: dict[str, Any] = {"key": problem.key}
    if problem.card is not None:
        out["card"] = problem.card
        params["card"] = (
            _literal(problem.card)
            if problem.key == DECK_UNKNOWN_CARD
            else f"@card.{problem.card}.name"
        )
    out["params"] = params
    return out


def problems_to_list(problems: Iterable[DeckProblem]) -> list[dict[str, Any]]:
    return [problem_to_dict(p) for p in problems]


def provisions_to_dict(lib: Library, deck: Deck, rules: Rules) -> dict[str, int]:
    used, budget = deck_provisions(lib, deck, rules)
    return {"used": used, "budget": budget}
