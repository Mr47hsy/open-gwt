"""Generalised choices — docs/protocol/match.md §7 view shapes, cards.md §6.3 cancelling, and
canonical round trips of a match paused on each kind of choice."""

import json
from pathlib import Path
from typing import Any

import pytest

from opengwt.core.engine import IllegalIntent, apply
from opengwt.core.intents import CancelChoice, Choose
from opengwt.core.model import ChoiceKind, MatchState, Placement, Rules
from opengwt.core.serialize import canonical_json, state_from_dict, state_to_dict
from opengwt.core.view import player_view
from tests.helpers import CARDS, Builder, make_library, play
from tests.scenario import SCENARIOS, Played, load_scenario, play_scenario


def _paused(name: str, steps: int) -> Played:
    """A scenario played up to its first ``steps`` steps."""
    spec = load_scenario(SCENARIOS / f"{name}.yaml")
    spec["steps"] = spec["steps"][:steps]
    played = play_scenario(spec)
    assert played.state.pending is not None
    return played


def _round_trips(state: MatchState) -> None:
    once = canonical_json(state_to_dict(state))
    assert canonical_json(state_to_dict(state_from_dict(json.loads(once)))) == once


def _pending_view(played: Played) -> dict[str, Any]:
    pending = player_view(played.lib, played.state, 0)["pending_choice"]
    assert pending is not None
    assert player_view(played.lib, played.state, 1)["pending_choice"] is None
    return pending


def test_a_row_choice() -> None:
    played = _paused("choose-a-row-side", 5)
    pending = _pending_view(played)
    assert pending["kind"] == "row" and pending["prompt_key"] == "choice.set-row-effect"
    assert pending["options"] == [
        {"side": "opponent", "row": "melee"},
        {"side": "opponent", "row": "ranged"},
    ]
    _round_trips(played.state)


def test_a_card_choice_and_then_a_place() -> None:
    played = _paused("play-from-deck", 1)
    pending = _pending_view(played)
    assert pending["kind"] == "card" and not pending["cancellable"]
    assert [o["card"] for o in pending["options"]] == ["recruit", "recruit", "scout"]
    assert all(set(o) == {"instance", "card"} for o in pending["options"])
    _round_trips(played.state)

    played = _paused("play-from-deck", 2)
    pending = _pending_view(played)
    assert pending["kind"] == "place" and pending["prompt_key"] == "choice.place"
    assert pending["source"]["card"] == "recruiter" and pending["card"]["card"] == "scout"
    assert pending["options"] == [
        {"side": "me", "row": "melee", "position": 0},
        {"side": "me", "row": "ranged", "position": 0},
    ]
    assert isinstance(played.state.pending.step, Placement)  # type: ignore[union-attr]
    _round_trips(played.state)


def test_a_created_card_is_offered_without_an_instance() -> None:
    played = _paused("create", 1)
    pending = _pending_view(played)
    assert pending["kind"] == "card" and pending["prompt_key"] == "choice.create"
    assert pending["options"] == [{"card": "anvil"}, {"card": "bellows"}]
    _round_trips(played.state)


def test_what_a_choice_shows_decides_whether_it_can_be_cancelled() -> None:
    """cards.md §6.3: a deck's cards or a random offer are not shown twice for free."""
    played = _paused("play-from-deck", 1)
    with pytest.raises(IllegalIntent) as info:
        apply(played.lib, played.state, 0, CancelChoice())
    assert info.value.reason == "error.choice.not-cancellable"
    played = _paused("play-from-graveyard", 6)
    assert played.state.pending is not None and played.state.pending.cancellable
    assert played.state.pending.kind is ChoiceKind.CARD


def test_a_created_card_with_nowhere_to_go_never_enters_the_match() -> None:
    lib = make_library(
        {
            **CARDS,
            "craft": {
                "kind": "special",
                "color": "bronze",
                "provisions": 4,
                "abilities": [
                    {"when": "on_play", "do": "create", "pool": {"tags_any": ["crafted"]}}
                ],
            },
            "anvil": {
                "kind": "unit",
                "color": "bronze",
                "provisions": 4,
                "power": 4,
                "tags": ["crafted"],
                "rows": ["melee"],
            },
        }
    )
    s = Builder(lib).state(
        hand0=["craft", "plain5"], board0={"melee": ["plain5"]}, rules=Rules(row_capacity=1)
    )
    s, _ = play(lib, s, 0, "craft", end=False)
    assert s.pending is not None and [o.card for o in s.pending.options] == ["anvil"]
    s, events = apply(lib, s, 0, Choose(0))
    assert "card_played" not in [e.type for e in events]
    assert s.resolving == [] and [c.card for c in s.players[0].graveyard] == ["craft"]
    assert all(c.card != "anvil" for p in s.players for c in p.banished + p.graveyard)


def test_scenarios_exist_for_every_kind_of_choice() -> None:
    kinds = set()
    for path in sorted(Path(SCENARIOS).glob("*.yaml")):
        for event in load_scenario(path).get("events", []):
            if event.get("type") == "choice_requested" and "kind" in event:
                kinds.add(event["kind"])
    assert kinds >= {"row", "place", "card"}
