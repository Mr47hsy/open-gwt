"""The client's protocol 2 fixtures are what the core emits today, and together they show the
client every event type of match.md §8 and every kind of choice of §7."""

from __future__ import annotations

from typing import Any

from tests.client_fixtures import DEFAULT_OUT, build

# docs/protocol/match.md §8, in the order of its table.
EVENT_TYPES = (
    "match_started",
    "stratagem_placed",
    "round_started",
    "card_drawn",
    "draw_skipped",
    "mulligan_started",
    "card_redrawn",
    "mulligan_done",
    "turn_started",
    "turn_ended",
    "card_played",
    "order_used",
    "card_summoned",
    "card_moved",
    "card_returned",
    "control_changed",
    "card_discarded",
    "card_destroyed",
    "card_banished",
    "unit_damaged",
    "damage_blocked",
    "unit_boosted",
    "unit_healed",
    "base_power_changed",
    "armor_changed",
    "power_changed",
    "status_added",
    "status_reduced",
    "status_removed",
    "charges_changed",
    "row_effect_set",
    "row_effect_cleared",
    "choice_requested",
    "choice_made",
    "choice_cancelled",
    "player_passed",
    "round_ended",
    "board_cleared",
    "match_ended",
)


def _steps(files: dict[str, str]) -> list[dict[str, Any]]:
    import json

    return [step for text in files.values() for step in json.loads(text)["steps"]]


def test_client_fixtures_are_fresh() -> None:
    """Regenerate with `uv run python -m tests.client_fixtures` from server/."""
    built = build()
    on_disk = {p.name: p.read_text(encoding="utf-8") for p in DEFAULT_OUT.glob("*.json")}
    assert set(on_disk) == set(built), "fixture files added or removed; regenerate"
    for name, text in built.items():
        assert on_disk[name] == text, f"{name} is stale; regenerate"


def test_client_fixtures_cover_the_protocol() -> None:
    steps = _steps(build())
    seen = {e["type"] for step in steps for events in step["events"].values() for e in events}
    assert seen >= set(EVENT_TYPES), sorted(set(EVENT_TYPES) - seen)
    assert seen <= set(EVENT_TYPES), sorted(seen - set(EVENT_TYPES))
    kinds: set[str] = set()
    offers = 0
    for step in steps:
        for seat, view in step.get("views", {}).items():
            assert view["me"]["seat"] == int(seat)
            assert "hand" not in view["opponent"]
            pending = view["pending_choice"]
            if pending is not None:
                kinds.add(pending["kind"])
                if pending["kind"] == "card":
                    offers += sum("instance" not in o for o in pending["options"])
                if pending["kind"] == "place":
                    assert "card" in pending
    assert kinds == {"unit", "row", "place", "card"}, kinds
    assert offers > 0, "a `create` offer (an option without an instance) must appear"
