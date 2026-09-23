"""Match flow — docs/protocol/cards.md §11.4 and §11.5: draws, mulligans, turns, rounds."""

from typing import Any

import pytest

from opengwt.core.engine import IllegalIntent, acting_seats, apply, legal_intents, new_match
from opengwt.core.events import event_for_seat
from opengwt.core.intents import (
    CancelChoice,
    Choose,
    EndMulligan,
    Mulligan,
    Pass,
    PlayCard,
    UseOrder,
)
from opengwt.core.model import (
    Deck,
    Library,
    MatchState,
    NextRoundStarter,
    Phase,
    Rules,
    Status,
    StatusEntry,
    TieRule,
)
from opengwt.core.rng import seed_from_int
from opengwt.core.view import player_view
from tests.helpers import (
    CARDS,
    MELEE,
    RANGED,
    Builder,
    choose,
    event_types,
    events_of,
    make_library,
    play,
)

LIB = make_library()
SEED = seed_from_int(5)


def _both_keep(lib: Library, state: MatchState) -> MatchState:
    """End both mulligans, if there is one: with an empty deck there is nothing to redraw."""
    if state.phase is Phase.MULLIGAN:
        for seat in acting_seats(state):
            state, _ = apply(lib, state, seat, EndMulligan())
    return state


def test_new_match_deals_ten_and_opens_the_mulligan_for_both(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state, events = new_match(library, starter_decks, SEED)
    assert state.phase is Phase.MULLIGAN and state.turn is None
    starter = state.starter
    redraws = [3 if seat == starter else 2 for seat in (0, 1)]  # ADR 0011: one more for the starter
    for seat, deck in enumerate(starter_decks):
        p = state.players[seat]
        assert len(p.hand) == 10 and len(p.deck) == len(deck.cards) - 10
        assert p.mulligan is not None and p.mulligan.remaining == redraws[seat]
        legal = legal_intents(library, state, seat)
        assert legal == [Mulligan(c.instance) for c in p.hand] + [EndMulligan()]
    assert event_types(events)[:3] == ["match_started", "stratagem_placed", "round_started"]
    assert events_of(events, "mulligan_started") == [{"round": 1, "redraws": redraws}]
    assert set(acting_seats(state)) == {0, 1}
    placed = events_of(events, "stratagem_placed")[0]
    assert placed["seat"] == starter and placed["card"] == starter_decks[starter].stratagem
    on_board = [c.card for p in state.players for side in p.rows.values() for c in side.cards]
    assert on_board == [starter_decks[starter].stratagem]


def test_a_redraw_skips_returned_ids_and_puts_the_card_back(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state, _ = new_match(library, starter_decks, SEED)
    p = state.players[0]
    returned = p.hand[3]
    after, events = apply(library, state, 0, Mulligan(returned.instance))
    q = after.players[0]
    assert q.hand[3].card != returned.card  # the replacement differs from what went back
    assert returned.instance in {c.instance for c in q.deck}
    assert len(q.hand) == 10 and len(q.deck) == len(p.deck)
    assert event_types(events) == ["card_redrawn", "card_drawn"]
    assert q.mulligan is not None and q.mulligan.remaining == 2
    hidden = event_for_seat(events[0], 1)
    assert "card" not in hidden.data and "instance" not in hidden.data


def test_both_players_mulligan_at_once_and_the_starter_then_plays(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state, _ = new_match(library, starter_decks, SEED)
    second = state.other(state.starter)
    state, _ = apply(library, state, second, EndMulligan())
    assert acting_seats(state) == (state.starter,)
    with pytest.raises(IllegalIntent) as info:
        apply(library, state, second, EndMulligan())
    assert info.value.reason == "error.mulligan.over"
    for _ in range(3):
        state, events = apply(
            library, state, state.starter, Mulligan(state.players[state.starter].hand[0].instance)
        )
    assert state.phase is Phase.PLAYING and state.turn == state.starter
    assert event_types(events)[-2:] == ["mulligan_done", "turn_started"]
    with pytest.raises(IllegalIntent) as info:
        apply(library, state, state.starter, EndMulligan())
    assert info.value.reason == "error.intent.not-mulligan-phase"


def test_draws_into_a_full_hand_become_extra_redraws() -> None:
    s = Builder(LIB).state(
        hand0=["plain5"] * 10,
        hand1=["plain5"] * 8,
        deck0=["plain3"] * 5,
        deck1=["plain3"] * 5,
    )
    s, _ = apply(LIB, s, 0, Pass())
    s, events = apply(LIB, s, 1, Pass())
    assert s.starter == 1  # the tied round goes to both; the other player starts
    assert events_of(events, "draw_skipped") == [
        {"seat": 1, "reason": "hand_full", "count": 1},
        {"seat": 0, "reason": "hand_full", "count": 3},
    ]
    assert [len(p.hand) for p in s.players] == [10, 10]
    assert events_of(events, "mulligan_started") == [{"round": 2, "redraws": [2 + 3, 2 + 1]}]


def test_a_tied_round_counts_for_both_and_two_ties_are_a_draw() -> None:
    s = Builder(LIB).state()
    s, _ = apply(LIB, s, 0, Pass())
    s, events = apply(LIB, s, 1, Pass())
    assert events_of(events, "round_ended")[0]["winners"] == [0, 1]
    assert [p.rounds_won for p in s.players] == [1, 1]
    assert s.starter == 1  # a tie: the player who did not start the last round starts
    s = _both_keep(LIB, s)
    s, _ = apply(LIB, s, 1, Pass())
    s, events = apply(LIB, s, 0, Pass())
    assert s.phase is Phase.MATCH_OVER and s.winner is None
    assert events[-1].type == "match_ended" and events[-1].data["winner"] is None
    with pytest.raises(IllegalIntent) as info:
        apply(LIB, s, 0, Pass())
    assert info.value.code == "match_over"


def test_with_neither_wins_ties_play_on_to_the_last_round() -> None:
    s = Builder(LIB).state(rules=Rules(tie_rule=TieRule.NEITHER_WINS))
    for _ in range(3):
        s = _both_keep(LIB, s)
        first = s.turn
        assert first is not None
        s, _ = apply(LIB, s, first, Pass())
        s, _ = apply(LIB, s, 1 - first, Pass())
    assert s.phase is Phase.MATCH_OVER and s.winner is None and s.round == 3
    assert [r.winners for r in s.rounds] == [(), (), ()]


@pytest.mark.parametrize(
    ("rule", "starter"),
    [
        (NextRoundStarter.ROUND_WINNER, 0),
        (NextRoundStarter.ROUND_LOSER, 1),
        (NextRoundStarter.ALTERNATE, 1),
    ],
)
def test_who_starts_the_next_round(rule: NextRoundStarter, starter: int) -> None:
    s = Builder(LIB).state(
        hand0=["plain5", "plain5", "plain5"], rules=Rules(next_round_starter=rule)
    )
    s, _ = play(LIB, s, 0, "plain5")
    s, _ = apply(LIB, s, 1, Pass())
    assert s.turn == 0  # the opponent passed: the same player goes on
    s, _ = apply(LIB, s, 0, Pass())
    assert s.round == 2 and s.rounds[0].winners == (0,) and s.starter == starter
    assert [p.rounds_won for p in s.players] == [1, 0]


def test_a_player_with_an_empty_hand_passes_automatically() -> None:
    s = Builder(LIB).state(hand0=["plain5"], hand1=[])
    s, events = play(LIB, s, 0, "plain5")
    # seat 1 has nothing and passes; seat 0 then runs out too, so round 1 ends 5-0; with empty
    # decks round 2 is passed by both, tied, and seat 0 has its two round wins
    auto = [e for e in events if e.type == "player_passed" and e.data["auto"]]
    assert [e.data["seat"] for e in auto] == [1, 0, 0, 1]
    assert [(r.winners, r.scores) for r in s.rounds] == [((0,), (5, 0)), ((0, 1), (0, 0))]
    assert s.phase is Phase.MATCH_OVER and s.winner == 0


def test_illegal_intents_are_rejected_with_codes(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state, _ = new_match(library, starter_decks, SEED)
    with pytest.raises(IllegalIntent) as info:
        apply(library, state, 0, Pass())
    assert info.value.reason == "error.intent.mulligan-phase"
    with pytest.raises(IllegalIntent) as info:
        apply(library, state, 0, Mulligan("nope"))
    assert info.value.code == "unknown_instance"
    state = _both_keep(library, state)
    a = state.starter
    with pytest.raises(IllegalIntent) as info:
        apply(library, state, 1 - a, Pass())
    assert info.value.code == "not_your_turn"
    with pytest.raises(IllegalIntent) as info:
        apply(library, state, a, PlayCard("nope", MELEE, 0))
    assert info.value.code == "unknown_instance"


def test_the_view_shows_only_what_the_player_may_see(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state, _ = new_match(library, starter_decks, SEED)
    state = _both_keep(library, state)
    view = player_view(library, state, 0, match_id="m1")
    assert view["protocol"] == 2 and view["match_id"] == "m1" and view["phase"] == "playing"
    assert len(view["me"]["hand"]) == 10
    assert "hand" not in view["opponent"] and view["opponent"]["hand_count"] == 10
    assert view["opponent"]["deck_count"] == len(state.players[1].deck)
    assert view["turn"] == ("me" if state.turn == 0 else "opponent")
    assert set(view["me"]["rows"]) == {"melee", "ranged"}
    assert view["me"]["leader"]["order"] == {"ready": False, "charges": 2, "cooldown": 0}
    assert "seed" not in str(view) and state.seed not in str(view)


# --- the starter's stratagem (ADR 0011) ---------------------------------------------------------


def _strategist(**kwargs: Any) -> MatchState:
    return Builder(LIB).state(
        hand0=["plain5", "plain5"], board0={"melee": ["strat-boost", "plain5"]}, **kwargs
    )


def test_a_stratagem_is_used_once_after_a_choice_that_can_be_cancelled() -> None:
    s = _strategist()
    strat = s.players[0].rows[MELEE].cards[0]
    assert UseOrder(strat.instance) in legal_intents(LIB, s, 0)
    s, events = apply(LIB, s, 0, UseOrder(strat.instance))
    assert s.pending is not None and s.pending.cancellable and len(s.pending.options) == 1
    assert events_of(events, "choice_requested")[0]["cancellable"] is True
    assert CancelChoice() in legal_intents(LIB, s, 0)
    s, events = apply(LIB, s, 0, CancelChoice())
    assert event_types(events) == ["choice_cancelled"]
    assert s.phase is Phase.PLAYING and s.turn == 0 and s.pending is None
    assert s.players[0].rows[MELEE].cards[0].charges == 1
    s, _ = apply(LIB, s, 0, UseOrder(strat.instance))
    s, events = choose(LIB, s, 0, 0)
    assert event_types(events)[:3] == ["choice_made", "order_used", "unit_boosted"]
    assert events_of(events, "order_used")[0]["charges"] == 0
    assert [c.card for c in s.players[0].rows[MELEE].cards] == ["plain5"]
    assert [c.card for c in s.players[0].banished] == ["strat-boost"]
    assert s.turn == 0 and s.phase is Phase.PLAYING  # an order does not end the turn
    assert not any(isinstance(i, UseOrder) for i in legal_intents(LIB, s, 0))


def test_a_stratagem_takes_a_place_and_nothing_acts_on_it() -> None:
    s = _strategist(rules=Rules(row_capacity=2), hand1=["zap2", "plain5"], turn=1)
    plays = [i for i in legal_intents(LIB, s, 0) if isinstance(i, PlayCard)]
    assert plays == []  # not seat 0's turn
    s, _ = play(LIB, s, 1, "zap2")
    assert s.pending is not None and len(s.pending.options) == 1  # only the unit
    s, _ = choose(LIB, s, 1, 0)
    melee_plays = [
        i for i in legal_intents(LIB, s, 0) if isinstance(i, PlayCard) and i.row is MELEE
    ]
    assert melee_plays == []  # the stratagem fills a place of the full melee row
    view = player_view(LIB, s, 0)
    strat_view = view["me"]["rows"]["melee"]["cards"][0]
    assert strat_view["order"] == {"ready": True, "charges": 1, "cooldown": 0}
    assert (
        player_view(LIB, s, 1)["opponent"]["rows"]["melee"]["cards"][0]["order"]["ready"] is False
    )


def test_an_unused_stratagem_is_gone_when_round_one_ends() -> None:
    s = _strategist(hand1=["plain3"])
    strat = s.players[0].rows[MELEE].cards[0].instance
    s, _ = apply(LIB, s, 0, Pass())
    s, events = play(LIB, s, 1, "plain3")  # seat 1's hand is then empty: it passes, round over
    assert s.round == 2
    assert s.players[0].rows[MELEE].cards == []
    assert [c.card for c in s.players[0].banished] == ["strat-boost"]
    assert [c.card for c in s.players[0].graveyard] == ["plain5"]
    banished = events_of(events, "card_banished")
    assert [e["instance"] for e in banished] == [strat]
    assert events_of(events, "board_cleared")[0]["kept"] == []


def test_a_stratagem_whose_first_ability_asks_nothing_starts_at_once() -> None:
    s = Builder(LIB).state(
        hand0=["plain5", "plain5"],
        deck0=["plain3"],
        board0={"ranged": ["strat-draw", "plain5"]},
    )
    strat = s.players[0].rows[RANGED].cards[0]
    s, events = apply(LIB, s, 0, UseOrder(strat.instance))
    assert event_types(events)[:2] == ["order_used", "card_drawn"]
    assert s.pending is not None and not s.pending.cancellable
    with pytest.raises(IllegalIntent) as info:
        apply(LIB, s, 0, CancelChoice())
    assert info.value.reason == "error.choice.not-cancellable"
    s, events = choose(LIB, s, 0, 0)
    assert "card_banished" in event_types(events) and s.turn == 0


def test_only_the_round_one_starter_gets_the_extra_redraw_and_the_stratagem(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    rules = Rules(starter_extra_mulligans=0, starter_stratagem=False)
    _, events = new_match(library, starter_decks, SEED, rules)
    assert events_of(events, "mulligan_started")[0]["redraws"] == [2, 2]
    assert "stratagem_placed" not in event_types(events)


# --- activated abilities of units, artifacts and leaders (cards.md §6.3, §11.4) ----------------

ORDERS = make_library(
    {
        **CARDS,
        "gunner": {
            "kind": "unit",
            "color": "bronze",
            "provisions": 5,
            "power": 3,
            "activation": {"charges": 2},
            "abilities": [
                {
                    "when": "on_activate",
                    "do": "damage",
                    "amount": 1,
                    "target": {"units": "chosen", "side": "opponent"},
                }
            ],
        },
        "tinker": {
            "kind": "unit",
            "color": "bronze",
            "provisions": 5,
            "power": 3,
            "activation": {"cooldown": 1},
            "abilities": [
                {"when": "on_activate", "do": "boost", "amount": 1, "target": {"units": "this"}},
                {"when": "on_activate", "do": "add_charges", "to": "this", "amount": 3},
            ],
        },
    }
)


def test_a_locked_card_or_one_without_a_target_is_not_ready() -> None:
    s = Builder(ORDERS).state(board0={"melee": ["gunner"]})
    gunner = s.players[0].rows[MELEE].cards[0]
    assert UseOrder(gunner.instance) not in legal_intents(ORDERS, s, 0)  # no enemy to choose
    s = Builder(ORDERS).state(board0={"melee": ["gunner"]}, board1={"melee": ["plain5"]})
    gunner = s.players[0].rows[MELEE].cards[0]
    assert UseOrder(gunner.instance) in legal_intents(ORDERS, s, 0)
    gunner.statuses.append(StatusEntry(Status.LOCKED))
    assert UseOrder(gunner.instance) not in legal_intents(ORDERS, s, 0)


def test_a_card_taken_over_serves_its_new_controller() -> None:
    s = Builder(ORDERS).state(
        board0={"melee": [("gunner", 1), "plain5"]}, board1={"melee": ["plain5"]}
    )
    gunner = s.players[0].rows[MELEE].cards[0]
    assert UseOrder(gunner.instance) in legal_intents(ORDERS, s, 0)
    s, _ = apply(ORDERS, s, 0, UseOrder(gunner.instance))
    s, events = apply(ORDERS, s, 0, Choose(0))
    assert events_of(events, "order_used")[0]["seat"] == 0


def test_after_an_order_a_pass_is_legal_only_when_no_card_can_be_played() -> None:
    s = Builder(ORDERS).state(hand0=[], board0={"melee": ["tinker"]})
    tinker = s.players[0].rows[MELEE].cards[0]
    s, _ = apply(ORDERS, s, 0, UseOrder(tinker.instance))
    assert s.ordered and legal_intents(ORDERS, s, 0) == [Pass()]
    s, events = apply(ORDERS, s, 0, Pass())
    assert "player_passed" in event_types(events)


def test_unlimited_charges_gain_nothing() -> None:
    s = Builder(ORDERS).state(board0={"melee": ["tinker"]})
    tinker = s.players[0].rows[MELEE].cards[0]
    s, events = apply(ORDERS, s, 0, UseOrder(tinker.instance))
    assert "charges_changed" not in event_types(events)
    assert events_of(events, "order_used") == [
        {"seat": 0, "instance": tinker.instance, "card": "tinker", "charges": None, "cooldown": 1}
    ]


def test_the_view_shows_the_leaders_order() -> None:
    s = Builder(LIB).state(board0={"melee": ["plain5"]}, leaders=("leader", "leader"))
    mine = player_view(LIB, s, 0)["me"]["leader"]["order"]
    theirs = player_view(LIB, s, 1)["opponent"]["leader"]["order"]
    assert mine == {"ready": True, "charges": 1, "cooldown": 0}
    assert theirs == {"ready": False, "charges": 1, "cooldown": 0}  # only for its own player
    assert player_view(LIB, s, 1)["me"]["leader"]["order"]["ready"] is False  # not their turn
    leader = s.players[0].leader
    assert leader is not None and UseOrder(leader.instance) in legal_intents(LIB, s, 0)
