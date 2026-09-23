import pytest

from opengwt.core.engine import IllegalIntent, apply, legal_intents
from opengwt.core.intents import Choose, Pass, PlayCard, UseLeader
from opengwt.core.model import Phase, Row, RowEffect
from opengwt.core.power import row_total, score
from tests.helpers import CARDS, Builder, cards_on, event_types, hand_instance, make_library, play

LIB = make_library()
CARDS_SUBSET = {k: CARDS[k] for k in ("plain5", "frost", "horn-melee")}


def build() -> Builder:
    return Builder(LIB)


def test_weather_sets_non_immune_units_to_one_and_clear_restores() -> None:
    s = build().state(
        hand0=["frost", "clear", "plain5"],
        board0={"melee": ["plain5", "immune10"]},
        board1={"melee": ["plain5"]},
    )
    s, events = play(LIB, s, 0, "frost")
    assert s.players[0].rows[Row.MELEE].effects == [RowEffect.POWER_TO_ONE]
    assert s.players[1].rows[Row.MELEE].effects == [RowEffect.POWER_TO_ONE]
    assert row_total(LIB, s, 0, Row.MELEE) == 11
    assert row_total(LIB, s, 1, Row.MELEE) == 1
    assert "power_changed" in event_types(events)
    assert s.turn == 1
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = play(LIB, s, 0, "clear")
    assert row_total(LIB, s, 0, Row.MELEE) == 15
    assert all(p.rows[Row.MELEE].effects == [] for p in s.players)


def test_bond_multiplies_by_copies_on_the_row() -> None:
    s = build().state(hand0=["bond4"], board0={"melee": ["bond4", "bond4"]}, turn=0)
    assert row_total(LIB, s, 0, Row.MELEE) == 16
    s, _ = play(LIB, s, 0, "bond4")
    assert row_total(LIB, s, 0, Row.MELEE) == 36


def test_morale_boosts_the_others_only() -> None:
    s = build().state(board0={"melee": ["morale1", "plain5", "plain5"]})
    assert row_total(LIB, s, 0, Row.MELEE) == 13


def test_effective_power_resolution_order() -> None:
    # weather -> bond -> morale -> doubling; immune units stop after their base power
    s = build().state(
        hand0=["frost", "horn-melee", "plain5"],
        hand1=["plain8r"],
        board0={"melee": ["bond4", "bond4", "morale1", "immune10"]},
    )
    s, _ = play(LIB, s, 0, "frost")
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = play(LIB, s, 0, "horn-melee")
    powers = [u["power"] for u in _view_units(s, 0, Row.MELEE)]
    assert powers == [6, 6, 2, 10]
    assert s.players[0].rows[Row.MELEE].effects == [RowEffect.POWER_TO_ONE, RowEffect.DOUBLE_POWER]


def _view_units(state, seat, row):  # type: ignore[no-untyped-def]
    from opengwt.core.view import player_view

    return player_view(LIB, state, seat)["me"]["rows"][row.value]["units"]


def test_scorch_destroys_strongest_non_immune_on_both_sides_with_ties() -> None:
    s = build().state(
        hand0=["scorch"],
        board0={"melee": ["immune10", "plain5"], "ranged": ["plain8r"]},
        board1={"ranged": ["plain8r"]},
    )
    s, events = play(LIB, s, 0, "scorch")
    assert cards_on(s, 0, Row.RANGED) == [] and cards_on(s, 1, Row.RANGED) == []
    assert cards_on(s, 0, Row.MELEE) == ["immune10", "plain5"]
    assert event_types(events).count("unit_destroyed") == 2
    assert [u.card for u in s.players[1].discard] == ["plain8r"]
    assert [u.card for u in s.players[0].discard] == ["plain8r", "scorch"]


def test_row_scorch_needs_the_row_total() -> None:
    s = build().state(
        hand0=["row-scorch", "row-scorch", "plain5"], board1={"melee": ["plain5", "bond4"]}
    )
    s, _ = play(LIB, s, 0, "row-scorch")  # 9 < 10: nothing happens
    assert cards_on(s, 1, Row.MELEE) == ["plain5", "bond4"]
    s, _ = apply(LIB, s, 1, Pass())
    s.players[1].rows[Row.MELEE].units[0].power = 6  # now 10
    s, _ = play(LIB, s, 0, "row-scorch")
    assert cards_on(s, 1, Row.MELEE) == ["bond4"]


def test_spy_deploys_on_the_other_side_draws_and_ends_in_their_discard() -> None:
    s = build().state(hand0=["spy4"], deck0=["plain5", "plain5", "plain5"])
    s, events = play(LIB, s, 0, "spy4")
    assert cards_on(s, 1, Row.MELEE) == ["spy4"]
    assert len(s.players[0].hand) == 2 and len(s.players[0].deck) == 1
    assert score(LIB, s, 1) == 4
    assert event_types(events).count("card_drawn") == 2
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = apply(LIB, s, 0, Pass())
    assert [u.card for u in s.players[1].discard] == ["spy4"]
    assert s.players[0].discard == []


def test_medic_asks_for_a_choice_then_returns_the_unit() -> None:
    s = build().state(hand0=["medic"], discard0=["immune10", "plain5", "frost"])
    s, events = play(LIB, s, 0, "medic")
    assert s.phase is Phase.CHOOSING and s.pending is not None
    assert s.pending.options == [s.players[0].discard[1].instance]
    assert legal_intents(LIB, s, 0) == [Choose(0)] and legal_intents(LIB, s, 1) == []
    assert "choice_requested" in event_types(events)
    with pytest.raises(IllegalIntent) as info:
        apply(LIB, s, 1, Pass())
    assert info.value.code == "choice_pending"
    s, events = apply(LIB, s, 0, Choose(0))
    assert s.phase is Phase.PLAYING and s.turn == 1
    assert cards_on(s, 0, Row.MELEE) == ["plain5"] and cards_on(s, 0, Row.RANGED) == ["medic"]
    assert [u.card for u in s.players[0].discard] == ["immune10", "frost"]
    assert "unit_summoned" in event_types(events)


def test_medic_with_nothing_to_return_does_not_ask() -> None:
    s = build().state(hand0=["medic"], discard0=["immune10"])
    s, _ = play(LIB, s, 0, "medic")
    assert s.phase is Phase.PLAYING and s.turn == 1


def test_decoy_swaps_with_a_chosen_unit() -> None:
    s = build().state(hand0=["decoy"], board0={"melee": ["plain5", "immune10"]})
    s.players[0].rows[Row.MELEE].units[0].power = 9  # boosted; must reset on return
    s, _ = play(LIB, s, 0, "decoy")
    assert s.phase is Phase.CHOOSING and len(s.pending.options) == 1  # type: ignore[union-attr]
    s, events = apply(LIB, s, 0, Choose(0))
    assert cards_on(s, 0, Row.MELEE) == ["decoy", "immune10"]
    assert [u.card for u in s.players[0].hand] == ["plain5"]
    assert s.players[0].hand[0].power == 5
    assert row_total(LIB, s, 0, Row.MELEE) == 10
    assert {"unit_returned", "card_placed"} <= set(event_types(events))


def test_muster_pulls_copies_from_the_deck_in_order() -> None:
    s = build().state(hand0=["muster"], deck0=["plain5", "muster", "plain8r", "muster"])
    s, events = play(LIB, s, 0, "muster")
    assert cards_on(s, 0, Row.SIEGE) == ["muster", "muster", "muster"]
    assert [u.card for u in s.players[0].deck] == ["plain5", "plain8r"]
    assert event_types(events).count("unit_summoned") == 2


def test_boost_changes_current_power_and_emits_changes() -> None:
    s = build().state(hand0=["boost-siege"], board0={"siege": ["muster"]})
    s, events = play(LIB, s, 0, "boost-siege")
    assert [u.power for u in s.players[0].rows[Row.SIEGE].units] == [5, 4]
    changed = [e for e in events if e.type == "power_changed"]
    assert changed and changed[0].data["reason"] == "boost"


def test_leader_can_be_used_once() -> None:
    s = build().state(hand0=["frost", "plain5"], leaders=("leader-clear", None))
    s, _ = play(LIB, s, 0, "frost")
    s, _ = apply(LIB, s, 1, Pass())
    assert UseLeader() in legal_intents(LIB, s, 0)
    s, events = apply(LIB, s, 0, UseLeader())
    assert s.players[0].rows[Row.MELEE].effects == []
    assert "leader_used" in event_types(events)
    assert s.turn == 0  # opponent passed, so the turn stays
    with pytest.raises(IllegalIntent):
        apply(LIB, s, 0, UseLeader())


def test_draw_from_empty_deck_is_harmless() -> None:
    s = build().state(hand0=["draw2"])
    s, _ = play(LIB, s, 0, "draw2")
    assert s.players[0].hand == []


def test_row_choice_is_validated() -> None:
    s = build().state(hand0=["flex6", "plain5"])
    flex = hand_instance(s, 0, "flex6")
    with pytest.raises(IllegalIntent):
        apply(LIB, s, 0, PlayCard(flex))  # two rows, none chosen
    with pytest.raises(IllegalIntent):
        apply(LIB, s, 0, PlayCard(flex, Row.MELEE))
    s2, _ = apply(LIB, s, 0, PlayCard(flex, Row.SIEGE))
    assert cards_on(s2, 0, Row.SIEGE) == ["flex6"]
    with pytest.raises(IllegalIntent):
        apply(LIB, s, 0, PlayCard(hand_instance(s, 0, "plain5"), Row.RANGED))


def test_clearing_can_target_one_effect_kind() -> None:
    weather_only = {
        **CARDS_SUBSET,
        "clear-weather": {
            "kind": "special",
            "abilities": [
                {"when": "played", "do": "clear_row_effects", "effects": ["power_to_one"]}
            ],
        },
    }
    lib = make_library(weather_only)
    s = Builder(lib).state(
        hand0=["frost", "horn-melee", "clear-weather", "plain5"], board0={"melee": ["plain5"]}
    )
    s, _ = play(lib, s, 0, "frost")
    s, _ = apply(lib, s, 1, Pass())
    s, _ = play(lib, s, 0, "horn-melee")
    assert row_total(lib, s, 0, Row.MELEE) == 2
    s, events = play(lib, s, 0, "clear-weather")
    assert s.players[0].rows[Row.MELEE].effects == [RowEffect.DOUBLE_POWER]
    assert row_total(lib, s, 0, Row.MELEE) == 10
    cleared = [e.data for e in events if e.type == "row_effect_cleared"]
    assert cleared == [
        {"seat": 0, "row": "melee", "effect": "power_to_one"},
        {"seat": 1, "row": "melee", "effect": "power_to_one"},
    ]
