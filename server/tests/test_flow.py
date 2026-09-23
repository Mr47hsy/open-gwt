"""Match flow — docs/protocol/cards.md §11.4 and §11.5: draws, mulligans, turns, rounds."""

import pytest

from opengwt.core.engine import IllegalIntent, acting_seats, apply, legal_intents, new_match
from opengwt.core.events import event_for_seat
from opengwt.core.intents import EndMulligan, Mulligan, Pass, PlayCard
from opengwt.core.model import Deck, Library, MatchState, NextRoundStarter, Phase, Rules, TieRule
from opengwt.core.rng import seed_from_int
from opengwt.core.view import player_view
from tests.helpers import MELEE, Builder, event_types, events_of, make_library, play

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
    for seat, deck in enumerate(starter_decks):
        p = state.players[seat]
        assert len(p.hand) == 10 and len(p.deck) == len(deck.cards) - 10
        assert p.mulligan is not None and p.mulligan.remaining == 3
        legal = legal_intents(library, state, seat)
        assert legal == [Mulligan(c.instance) for c in p.hand] + [EndMulligan()]
    assert event_types(events)[:2] == ["match_started", "round_started"]
    assert events_of(events, "mulligan_started") == [{"round": 1, "redraws": [3, 3]}]
    assert set(acting_seats(state)) == {0, 1}


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
