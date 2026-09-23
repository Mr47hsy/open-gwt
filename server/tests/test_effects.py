"""Power, statuses, row effects and the phase-B actions — docs/protocol/cards.md §7 to §11."""

from typing import Any

import pytest

from opengwt.core.engine import QUEUE_STEPS_MAX, IllegalIntent, apply, legal_intents
from opengwt.core.intents import Pass, PlayCard, UseOrder
from opengwt.core.model import Phase, Rules, Status, StatusEntry
from opengwt.core.power import score
from tests.helpers import (
    CARDS,
    MELEE,
    RANGED,
    Builder,
    cards_on,
    choose,
    event_types,
    events_of,
    hand_instance,
    make_library,
    play,
    powers_on,
    statuses,
    unit,
)

LIB = make_library()


def build() -> Builder:
    return Builder(LIB)


def lib_with(**extra: dict[str, Any]) -> Any:
    return make_library({**CARDS, **extra})


THIS = {"units": "this"}
ALL_ENEMIES = {"units": "all", "side": "opponent"}


def _unit_card(power: int, abilities: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "unit",
        "color": "bronze",
        "provisions": 4,
        "power": power,
        "abilities": abilities,
    }


def _special_card(*abilities: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "special", "color": "bronze", "provisions": 4, "abilities": list(abilities)}


def hit(amount: int) -> dict[str, Any]:
    return {
        "kind": "special",
        "color": "bronze",
        "provisions": 4,
        "abilities": [
            {
                "when": "on_play",
                "do": "damage",
                "amount": amount,
                "target": {"units": "chosen", "side": "opponent"},
            }
        ],
    }


def options(state: Any) -> list[str]:
    """The card ids a pending choice offers, in option order."""
    assert state.pending is not None
    by_id = {c.instance: c.card for p in state.players for s in p.rows.values() for c in s.cards}
    return [by_id[i] for i in state.pending.options]


# --- damage, armour, shields ------------------------------------------------------------------


def test_damage_meets_shield_then_armour_then_power() -> None:
    lib = lib_with(hit5=hit(5))
    s = Builder(lib).state(
        hand0=["hit5", "hit5", "plain5"],
        board1={"melee": ["shield4", "armored4"]},
        hand1=["plain3", "plain3", "plain3"],
    )
    s, _ = play(lib, s, 0, "hit5")
    s, events = choose(lib, s, 0, 0)  # the shield blocks all five
    assert event_types(events)[:3] == ["choice_made", "damage_blocked", "status_removed"]
    assert unit(s, "shield4").power == 4 and statuses(unit(s, "shield4")) == []
    s, _ = play(lib, s, 1, "plain3", RANGED)
    s, _ = play(lib, s, 0, "hit5")
    s, events = choose(lib, s, 0, 1)  # armour 3 absorbs, 2 reach power
    armored = unit(s, "armored4")
    assert (armored.armor, armored.power) == (0, 2)
    change = events_of(events, "armor_changed")[0]
    assert (change["instance"], change["from"], change["to"]) == (armored.instance, 3, 0)
    assert events_of(events, "unit_damaged")[0]["amount"] == 2


def test_a_unit_at_zero_power_is_destroyed_and_doomed_ones_are_banished() -> None:
    lib = lib_with(hit5=hit(5))
    s = Builder(lib).state(
        hand0=["hit5", "hit5", "plain5"], board1={"melee": ["plain5", "doomed5"]}
    )
    s, _ = play(lib, s, 0, "hit5")
    s, events = choose(lib, s, 0, 0)
    assert cards_on(s, 1, MELEE) == ["doomed5"]
    assert [c.card for c in s.players[1].graveyard] == ["plain5"]
    assert events_of(events, "card_destroyed")[0]["banished"] is False
    s, _ = apply(lib, s, 1, Pass())
    s, _ = play(lib, s, 0, "hit5")
    s, events = choose(lib, s, 0, 0)
    assert [c.card for c in s.players[1].banished] == ["doomed5"]
    assert events_of(events, "card_destroyed")[0]["banished"] is True


def test_heal_restores_damage_only_and_reset_returns_to_base() -> None:
    s = build().state(
        hand0=["heal-all", "reset", "plain5"],
        board0={"melee": ["plain5", "plain3"]},
    )
    hurt, boosted = s.players[0].rows[MELEE].cards
    hurt.power = 2
    boosted.power = 7
    s, events = play(LIB, s, 0, "heal-all")
    assert powers_on(LIB, s, 0, MELEE) == [5, 7]
    assert events_of(events, "unit_healed")[0]["amount"] == 3
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = play(LIB, s, 0, "reset")
    s, events = choose(LIB, s, 0, 1)
    assert powers_on(LIB, s, 0, MELEE) == [5, 3]
    assert events_of(events, "power_changed")[0]["reason"] == "reset_power"


def test_raising_base_power_raises_power_with_it() -> None:
    s = build().state(hand0=["raise2", "plain5"], board0={"melee": ["plain3"]})
    s.players[0].rows[MELEE].cards[0].power = 1
    s, events = play(LIB, s, 0, "raise2")
    s, events = choose(LIB, s, 0, 0)
    card = unit(s, "plain3")
    assert (card.base, card.power) == (5, 3)
    assert events_of(events, "base_power_changed")[0]["to"] == 5


# --- statuses ---------------------------------------------------------------------------------


def test_bleeding_ticks_at_its_controllers_turn_end_and_ignores_armour() -> None:
    s = build().state(
        hand0=["bleed2", "plain5", "plain5"],
        hand1=["plain3", "plain3", "plain3"],
        board1={"melee": ["armored4"]},
    )
    s, _ = play(LIB, s, 0, "bleed2")
    s, _ = choose(LIB, s, 0, 0)
    target = unit(s, "armored4")
    assert statuses(target) == [("bleeding", 2)] and target.power == 4  # not seat 0's turn end
    s, events = play(LIB, s, 1, "plain3", RANGED)
    target = unit(s, "armored4")
    assert (target.power, target.armor) == (3, 3)
    assert statuses(target) == [("bleeding", 1)]
    assert events_of(events, "unit_damaged")[0]["reason"] == "bleeding"
    s, _ = play(LIB, s, 0, "plain5")
    s, events = play(LIB, s, 1, "plain3", RANGED)
    assert unit(s, "armored4").power == 2 and statuses(unit(s, "armored4")) == []
    assert events_of(events, "status_removed")[0]["reason"] == "expired"


def test_growing_boosts_at_turn_end_and_cancels_bleeding_turn_for_turn() -> None:
    s = build().state(hand0=["grow3", "bleed2", "plain5"], board1={"melee": ["plain5"]})
    s, _ = play(LIB, s, 0, "grow3")
    assert unit(s, "grow3").power == 4 and statuses(unit(s, "grow3")) == [("growing", 2)]
    target = s.players[1].rows[MELEE].cards[0]
    target.statuses.append(StatusEntry(Status.GROWING, 3))
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = play(LIB, s, 0, "bleed2")
    s, events = choose(LIB, s, 0, 0)
    assert statuses(unit(s, "plain5", 1)) == [("growing", 1)]
    reduced = events_of(events, "status_reduced")[0]
    assert (reduced["status"], reduced["turns"]) == ("growing", 1)


def test_bleeding_longer_than_growing_leaves_the_rest() -> None:
    s = build().state(hand0=["bleed2", "plain5"], board1={"melee": ["plain5"]})
    s.players[1].rows[MELEE].cards[0].statuses.append(StatusEntry(Status.GROWING, 1))
    s, _ = play(LIB, s, 0, "bleed2")
    s, events = choose(LIB, s, 0, 0)
    assert statuses(unit(s, "plain5", 1)) == [("bleeding", 1)]
    assert events_of(events, "status_removed")[0]["reason"] == "cancelled"


def test_a_timer_on_a_status_that_has_none_changes_nothing() -> None:
    lock3 = {
        **CARDS["lock"],
        "abilities": [{**CARDS["lock"]["abilities"][0], "turns": 3}],
    }
    lib = lib_with(lock3=lock3)
    s = Builder(lib).state(hand0=["lock3", "plain5"], board1={"melee": ["plain5"]})
    s.players[1].rows[MELEE].cards[0].statuses.append(StatusEntry(Status.LOCKED))
    s, _ = play(lib, s, 0, "lock3")
    s, events = choose(lib, s, 0, 0)
    assert statuses(unit(s, "plain5", 1)) == [("locked", None)]
    assert "status_added" not in event_types(events)


def test_a_second_poison_destroys() -> None:
    s = build().state(hand0=["poison", "poison", "plain5"], board1={"melee": ["plain8"]})
    s, _ = play(LIB, s, 0, "poison")
    s, _ = choose(LIB, s, 0, 0)
    assert statuses(unit(s, "plain8")) == [("poisoned", None)]
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = play(LIB, s, 0, "poison")
    s, events = choose(LIB, s, 0, 0)
    assert cards_on(s, 1, MELEE) == [] and "card_destroyed" in event_types(events)


def test_status_proof_takes_no_status() -> None:
    s = build().state(hand0=["poison", "plain5"], board1={"melee": ["proof4"]})
    s, _ = play(LIB, s, 0, "poison")
    s, events = choose(LIB, s, 0, 0)
    assert statuses(unit(s, "proof4")) == [("status_proof", None)]
    assert "status_added" not in event_types(events)


def test_immune_units_cannot_be_chosen_but_area_damage_reaches_them() -> None:
    s = build().state(hand0=["zap2", "zap-all", "plain5"], board1={"melee": ["immune6", "plain5"]})
    s, _ = play(LIB, s, 0, "zap2")
    assert options(s) == ["plain5"]
    s, _ = choose(LIB, s, 0, 0)
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = play(LIB, s, 0, "zap-all")
    assert powers_on(LIB, s, 1, MELEE) == [5, 2]


def test_a_guard_keeps_the_other_units_of_its_row_from_being_chosen() -> None:
    s = build().state(
        hand0=["zap2", "plain5"], board1={"melee": ["plain5", "guard6"], "ranged": ["plain3"]}
    )
    s, _ = play(LIB, s, 0, "zap2")
    assert options(s) == ["guard6", "plain3"]


def test_locked_cards_lose_their_aura_and_status_removal_brings_it_back() -> None:
    s = build().state(
        hand0=["lock", "plain5"],
        hand1=["purify", "plain3"],
        board0={"melee": ["plain5"]},
        board1={"melee": ["aura-row", "plain3"]},
    )
    assert powers_on(LIB, s, 1, MELEE) == [2, 4]
    s, _ = play(LIB, s, 0, "lock")
    assert options(s) == ["plain5", "aura-row", "plain3"]
    s, events = choose(LIB, s, 0, 1)
    assert powers_on(LIB, s, 1, MELEE) == [2, 3]
    aura = [e for e in events_of(events, "power_changed") if e["reason"] == "aura"]
    assert [(e["from"], e["to"]) for e in aura] == [(4, 3)]
    s, _ = play(LIB, s, 1, "purify")
    assert powers_on(LIB, s, 1, MELEE) == [2, 4]


# --- power, aura and the board ----------------------------------------------------------------


def test_auras_cover_the_row_or_the_neighbours_and_their_loss_can_destroy() -> None:
    s = build().state(
        hand0=["lock", "plain5"], board1={"melee": ["aura-adj", "plain3", "aura-row"]}
    )
    assert powers_on(LIB, s, 1, MELEE) == [3, 6, 2]
    s.players[1].rows[MELEE].cards[1].power = -1  # damaged deep, kept up by the auras
    assert powers_on(LIB, s, 1, MELEE) == [3, 2, 2]
    s, _ = play(LIB, s, 0, "lock")
    s, events = choose(LIB, s, 0, 0)  # lock aura-adj: plain3 falls to 0 and is destroyed
    assert cards_on(s, 1, MELEE) == ["aura-adj", "aura-row"]
    types = event_types(events)
    assert types.index("card_destroyed") < types.index("turn_ended")  # at once, not next turn


def test_aura_events_carry_the_power_before_and_after_the_aura_alone() -> None:
    flicker = {
        **CARDS["aura-row"],
        "power": 1,
    }
    lib = lib_with(flicker=flicker)
    s = Builder(lib).state(hand0=["zap-all", "plain5"], board1={"melee": ["flicker", "plain5"]})
    s, events = play(lib, s, 0, "zap-all")
    relevant = [
        (e.type, e.data.get("card"), e.data.get("from"), e.data.get("to"), e.data.get("power"))
        for e in events
        if e.type in ("card_destroyed", "power_changed", "unit_damaged")
    ]
    assert relevant == [
        ("unit_damaged", "flicker", None, None, 0),
        ("card_destroyed", "flicker", None, None, None),
        ("power_changed", "plain5", 6, 5, None),
        ("unit_damaged", "plain5", None, None, 4),
    ]


def test_on_row_looks_at_the_row_the_card_was_played_on() -> None:
    wanderer = {
        "kind": "unit",
        "color": "bronze",
        "provisions": 4,
        "power": 3,
        "abilities": [
            {"when": "on_play", "do": "move_to_other_row", "target": {"units": "this"}},
            {
                "when": "on_play",
                "if": {"on_row": "melee"},
                "do": "boost",
                "amount": 5,
                "target": {"units": "this"},
            },
        ],
    }
    lib = lib_with(wanderer=wanderer)
    s = Builder(lib).state(hand0=["wanderer", "plain5"])
    s, _ = play(lib, s, 0, "wanderer", MELEE)
    assert cards_on(s, 0, RANGED) == ["wanderer"] and powers_on(lib, s, 0, RANGED) == [8]


def test_positions_and_row_capacity() -> None:
    rules = Rules(row_capacity=2)
    s = build().state(
        hand0=["plain3", "plain8", "plain5"], board0={"melee": ["plain5"]}, rules=rules
    )
    s, _ = play(LIB, s, 0, "plain3", MELEE, position=0)
    assert cards_on(s, 0, MELEE) == ["plain3", "plain5"]
    s, _ = apply(LIB, s, 1, Pass())
    plays = [i for i in legal_intents(LIB, s, 0) if isinstance(i, PlayCard)]
    assert {i.row for i in plays} == {RANGED} and all(i.position is None for i in plays)
    iid = hand_instance(s, 0, "plain8")
    for intent, reason in (
        (PlayCard(iid, MELEE, 0), "error.play.row-full"),
        (PlayCard(iid, RANGED, 1), "error.play.position-out-of-range"),
        (PlayCard(iid, RANGED), "error.play.position-required"),
        (PlayCard(iid), "error.play.row-required"),
    ):
        with pytest.raises(IllegalIntent) as info:
            apply(LIB, s, 0, intent)
        assert info.value.reason == reason
    with pytest.raises(IllegalIntent) as info:
        apply(LIB, s, 0, PlayCard(hand_instance(s, 0, "plain5"), MELEE, 0))
    assert info.value.reason == "error.play.row-full"


def test_row_restrictions_only_govern_playing() -> None:
    s = build().state(hand0=["melee4", "plain5"])
    with pytest.raises(IllegalIntent) as info:
        play(LIB, s, 0, "melee4", RANGED)
    assert info.value.reason == "error.play.row-not-allowed"


def test_a_unit_for_the_other_side_lands_there_marked_and_draws() -> None:
    s = build().state(hand0=["spy7", "plain5"], deck0=["plain3"])
    s, events = play(LIB, s, 0, "spy7")
    spy = unit(s, "spy7")
    assert cards_on(s, 1, MELEE) == ["spy7"] and spy.owner == 0
    assert statuses(spy) == [("on_enemy_side", None)]
    assert events_of(events, "card_played")[0]["side"] == "opponent"
    assert [c.card for c in s.players[0].hand] == ["plain5", "plain3"]
    assert score(LIB, s, 1) == 7


def test_taking_control_moves_a_unit_and_marks_whose_it_is() -> None:
    s = build().state(
        hand0=["seize", "seize", "plain5"],
        board0={"melee": ["plain3"]},
        board1={"melee": ["plain5", ("spy7", 0)]},
    )
    s, _ = play(LIB, s, 0, "seize")
    s, events = choose(LIB, s, 0, 0)
    assert cards_on(s, 0, MELEE) == ["plain3", "plain5"]
    assert statuses(unit(s, "plain5", 0)) == [("on_enemy_side", None)]
    assert events_of(events, "control_changed")[0]["from_seat"] == 1
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = play(LIB, s, 0, "seize")
    s, _ = choose(LIB, s, 0, 0)  # the spy comes home
    assert statuses(unit(s, "spy7", 0)) == []


def test_drain_duel_and_consume() -> None:
    s = build().state(
        hand0=["drain3", "duel", "consume", "plain5"],
        board0={"melee": ["plain3"]},
        board1={"melee": ["armored4", "plain8"]},
    )
    s, _ = play(LIB, s, 0, "drain3")
    s, _ = choose(LIB, s, 0, 0)  # armour takes all three: nothing drained
    assert unit(s, "drain3").power == 2 and unit(s, "armored4").armor == 0
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = play(LIB, s, 0, "duel")
    s, _ = choose(LIB, s, 0, 1)  # 8 -> 3, 5 -> 2, 3 -> 1, 2 -> 1, 1 -> 0
    assert cards_on(s, 1, MELEE) == ["armored4"] and unit(s, "duel").power == 1
    s, _ = play(LIB, s, 0, "consume")
    s, _ = choose(LIB, s, 0, 0)  # eats plain3
    assert unit(s, "consume").power == 1 + 3
    assert "plain3" not in cards_on(s, 0, MELEE)


def test_return_to_hand_resets_the_card_and_respects_the_hand_limit() -> None:
    s = build().state(hand0=["recall", "plain5"], board0={"melee": ["plain3", "doomed5"]})
    s.players[0].rows[MELEE].cards[0].power = 9
    s, _ = play(LIB, s, 0, "recall")
    s, events = choose(LIB, s, 0, 0)
    back = s.players[0].hand[-1]
    assert back.card == "plain3" and back.power == 3
    assert "card_returned" in event_types(events)
    full = build().state(hand0=["recall"] + ["plain5"] * 10, board0={"melee": ["plain3"]})
    full, _ = play(LIB, full, 0, "recall")
    full, _ = choose(LIB, full, 0, 0)
    assert cards_on(full, 0, MELEE) == ["plain3"]


def test_moving_to_the_other_row_meets_its_row_effect() -> None:
    s = build().state(hand0=["trap", "shove", "plain5"], board1={"ranged": ["plain5"]})
    s, _ = play(LIB, s, 0, "trap")
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = play(LIB, s, 0, "shove")
    s, events = choose(LIB, s, 0, 0)
    assert cards_on(s, 1, MELEE) == ["plain5"] and powers_on(LIB, s, 1, MELEE) == [3]
    assert events_of(events, "unit_damaged")[0]["reason"] == "damage_on_arrival"


def test_summoned_copies_stand_right_of_the_card_and_a_full_row_leaves_them() -> None:
    s = build().state(
        hand0=["muster", "plain5"],
        deck0=["muster", "plain3", "muster"],
        board0={"melee": ["plain5"]},
        rules=Rules(row_capacity=3),
    )
    s, events = play(LIB, s, 0, "muster", MELEE, position=0)
    assert cards_on(s, 0, MELEE) == ["muster", "muster", "plain5"]
    assert [c.card for c in s.players[0].deck] == ["plain3", "muster"]
    summoned = events_of(events, "card_summoned")[0]
    assert (summoned["from"], summoned["position"]) == ("deck", 1)


def test_tokens_are_banished_when_they_leave() -> None:
    s = build().state(hand0=["token-maker", "scorch", "plain5"], hand1=["plain3", "plain3"])
    s, _ = play(LIB, s, 0, "token-maker")
    assert cards_on(s, 0, MELEE) == ["token-maker", "tok", "tok"]
    assert statuses(s.players[0].rows[MELEE].cards[1]) == [("banish_on_leave", None)]
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = apply(LIB, s, 0, Pass())  # round ends: the tokens are banished, not buried
    assert [c.card for c in s.players[0].banished] == ["tok", "tok"]
    assert [c.card for c in s.players[0].graveyard] == ["token-maker"]


def test_a_token_never_reaches_a_hand() -> None:
    s = build().state(hand0=["token-maker", "purify", "recall", "plain5"])
    s, _ = play(LIB, s, 0, "token-maker")
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = play(LIB, s, 0, "purify")  # strips the banish_on_leave the tokens came with
    assert statuses(s.players[0].rows[MELEE].cards[1]) == []
    s, _ = play(LIB, s, 0, "recall")
    s, events = choose(LIB, s, 0, 1)
    assert "tok" not in [c.card for c in s.players[0].hand]
    assert [c.card for c in s.players[0].banished] == ["tok"]
    assert "card_banished" in event_types(events)


def test_several_summoned_cards_keep_their_order() -> None:
    caller = {
        "kind": "unit",
        "color": "bronze",
        "provisions": 4,
        "power": 2,
        "abilities": [
            {
                "when": "on_play",
                "do": "summon_from_deck",
                "cards": {"pick": "all", "where": {"tags_any": ["tx"]}},
            }
        ],
    }
    xa = {"kind": "unit", "color": "bronze", "provisions": 4, "power": 1, "tags": ["tx"]}
    lib = lib_with(caller=caller, xa=xa, xb={**xa, "power": 2})
    s = Builder(lib).state(
        hand0=["caller", "plain5"], deck0=["xa", "plain3", "xb"], board0={"melee": ["plain5"]}
    )
    s, _ = play(lib, s, 0, "caller", MELEE, position=0)
    assert cards_on(s, 0, MELEE) == ["caller", "xa", "xb", "plain5"]


def test_artifacts_take_a_place_add_no_power_and_ignore_power_actions() -> None:
    s = build().state(hand0=["relic", "zap-all", "plain5"], board0={"melee": ["plain3"]})
    s, _ = play(LIB, s, 0, "relic")
    assert powers_on(LIB, s, 0, MELEE) == [4, 0] and score(LIB, s, 0) == 4
    s.players[0].rows[MELEE].cards, s.players[1].rows[MELEE].cards = (
        s.players[1].rows[MELEE].cards,
        s.players[0].rows[MELEE].cards,
    )
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = play(LIB, s, 0, "zap-all")
    assert cards_on(s, 1, MELEE) == ["plain3", "relic"] and powers_on(LIB, s, 1, MELEE) == [3, 0]


# --- row effects ------------------------------------------------------------------------------


def test_row_effects_act_at_their_players_turn_start() -> None:
    s = build().state(
        hand0=["frost", "plain5", "plain5"],
        hand1=["plain3", "plain3"],
        board1={"melee": ["plain8", "plain3"]},
    )
    s, events = play(LIB, s, 0, "frost")
    assert powers_on(LIB, s, 1, MELEE) == [8, 1]  # seat 1's turn started: weakest took 2
    assert events_of(events, "row_effect_set")[0]["effect"] == "damage_weakest"
    s, _ = apply(LIB, s, 1, Pass())
    s, _ = play(LIB, s, 0, "plain5")
    assert powers_on(LIB, s, 1, MELEE) == [8, 1]  # passed: no more turn starts, no more damage


def test_boosting_row_effect_and_clearing_only_hazards() -> None:
    s = build().state(
        hand0=["froth", "plain5", "plain5"],
        hand1=["plain3", "clear-hazards", "frost", "plain3"],
        board0={"melee": ["plain3", "plain3"]},
    )
    s, _ = play(LIB, s, 0, "froth")
    s, _ = play(LIB, s, 1, "plain3", RANGED)  # seat 0's turn starts: both boosted by 1
    assert powers_on(LIB, s, 0, MELEE) == [4, 4]
    s, _ = play(LIB, s, 0, "plain5", RANGED)
    s, events = play(LIB, s, 1, "clear-hazards")
    effect = s.players[0].rows[MELEE].effect
    assert effect is not None and effect.effect.value == "boost_random"
    assert events_of(events, "row_effect_cleared") == []
    s, _ = play(LIB, s, 0, "plain5", RANGED)
    s, _ = play(LIB, s, 1, "frost")  # a row-side holds one effect: frost replaces the boost
    effect = s.players[0].rows[MELEE].effect
    assert effect is not None and effect.effect.value == "damage_weakest"


def test_row_effects_and_boards_clear_at_round_end_except_kept_cards() -> None:
    s = build().state(
        hand0=["frost", "plain5"],
        board0={"melee": ["kept3", "round-end-boost"]},
        board1={"melee": ["plain5"]},
    )
    s, _ = play(LIB, s, 0, "frost")
    s, _ = apply(LIB, s, 1, Pass())
    s, events = apply(LIB, s, 0, Pass())
    ended = events_of(events, "round_ended")[0]
    assert ended["scores"] == [3 + 5, 3]  # the round-end boost counts; frost hit plain5 once
    assert cards_on(s, 0, MELEE) == ["kept3"] and statuses(unit(s, "kept3")) == []
    assert events_of(events, "board_cleared")[0]["kept"] == [unit(s, "kept3").instance]
    assert all(side.effect is None for p in s.players for side in p.rows.values())


# --- conditions and zones ---------------------------------------------------------------------


def test_conditions_on_hand_size_starting_deck_and_damaged_enemies() -> None:
    s = build().state(hand0=["adrenaline", "plain5"])
    s, _ = play(LIB, s, 0, "adrenaline")
    assert unit(s, "adrenaline").power == 7
    s = build().state(hand0=["adrenaline", "plain5", "plain5"])
    s, _ = play(LIB, s, 0, "adrenaline")
    assert unit(s, "adrenaline").power == 2
    s = build().state(hand0=["devotion", "plain5"])
    s.players[0].deck_had_neutral = True
    s, _ = play(LIB, s, 0, "devotion")
    assert unit(s, "devotion").power == 2
    s = build().state(hand0=["bloodthirst", "plain5"], board1={"melee": ["plain5"]})
    s.players[1].rows[MELEE].cards[0].power = 4
    s, _ = play(LIB, s, 0, "bloodthirst")
    assert unit(s, "bloodthirst").power == 6


def test_discard_and_draw_respect_the_hand() -> None:
    s = build().state(hand0=["discard2", "plain3", "plain5", "plain8"])
    s, events = play(LIB, s, 0, "discard2")
    assert len(s.players[0].hand) == 1
    assert sorted(c.card for c in s.players[0].graveyard) == sorted(
        [e["card"] for e in events_of(events, "card_discarded")] + ["discard2"]
    )
    s = build().state(hand0=["draw2"] + ["plain5"] * 9, deck0=["plain3", "plain3"])
    s, events = play(LIB, s, 0, "draw2")
    assert len(s.players[0].hand) == 10 and len(s.players[0].deck) == 1
    assert events_of(events, "draw_skipped") == [{"seat": 0, "reason": "hand_full", "count": 1}]


def test_strongest_breaks_ties_with_the_seeded_prng() -> None:
    s = build().state(
        hand0=["scorch", "plain5"], board0={"melee": ["plain8"]}, board1={"melee": ["plain8"]}
    )
    s, _ = play(LIB, s, 0, "scorch")
    assert len(cards_on(s, 0, MELEE) + cards_on(s, 1, MELEE)) == 1


# --- the resolution queue ----------------------------------------------------------------------


def test_a_trigger_loop_stops_after_the_most_abilities_one_resolution_resolves() -> None:
    """§11.3: content that keeps triggering itself stops, deterministically, and the match goes
    on."""
    lib = lib_with(
        vain=_unit_card(1, [{"when": "on_boosted", "do": "boost", "amount": 1, "target": THIS}])
    )
    s = Builder(lib).state(hand0=["boost3", "plain5"], board0={"melee": ["vain"]})
    s, events = play(lib, s, 0, "boost3")
    s, events = choose(lib, s, 0, 0)  # the boost, then its triggers up to the limit
    assert len(events_of(events, "unit_boosted")) == 1 + QUEUE_STEPS_MAX
    assert powers_on(lib, s, 0, MELEE) == [1 + 3 + QUEUE_STEPS_MAX]
    assert s.turn == 1 and s.phase is Phase.PLAYING


def test_the_queued_abilities_of_a_locked_card_are_skipped() -> None:
    """§11.3 and §9: the damage reaches the unit, its on_damaged is queued, and the lock added
    before it resolves stops it."""
    lib = lib_with(
        hardy=_unit_card(5, [{"when": "on_damaged", "do": "boost", "amount": 3, "target": THIS}]),
        sting_then_lock=_special_card(
            {"when": "on_play", "do": "damage", "amount": 1, "target": ALL_ENEMIES},
            {"when": "on_play", "do": "add_status", "status": "locked", "target": ALL_ENEMIES},
        ),
    )
    s = Builder(lib).state(hand0=["sting_then_lock", "plain5"], board1={"melee": ["hardy"]})
    s, events = play(lib, s, 0, "sting_then_lock")
    assert "unit_boosted" not in event_types(events)
    assert powers_on(lib, s, 1, MELEE) == [4]


def test_the_leader_order_waits_for_the_rest_of_phase_c() -> None:
    s = build().state(hand0=["plain5", "plain5"], leaders=("leader", None))
    assert all(not isinstance(i, UseOrder) for i in legal_intents(LIB, s, 0))
    with pytest.raises(IllegalIntent) as info:
        apply(LIB, s, 0, UseOrder(s.players[0].leader.instance))  # type: ignore[union-attr]
    assert info.value.reason == "error.order.not-ready"
