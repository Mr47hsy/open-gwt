import pytest

from opengwt.core.engine import IllegalIntent, apply, legal_intents, new_match
from opengwt.core.intents import Mulligan, Pass, PlayCard
from opengwt.core.model import Deck, Kind, Library, Phase
from opengwt.core.view import player_view


def _to_playing(lib: Library, decks: tuple[Deck, Deck], seed: int):  # type: ignore[no-untyped-def]
    state, _ = new_match(lib, decks, seed)
    state, _ = apply(lib, state, state.starter, Mulligan())
    state, _ = apply(lib, state, state.other(state.starter), Mulligan())
    return state


def test_new_match_deals_hands_and_starts_the_mulligan(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state, events = new_match(library, starter_decks, seed=5)
    assert state.phase is Phase.MULLIGAN and state.mulligan_seat == state.starter
    for seat, deck in enumerate(starter_decks):
        p = state.players[seat]
        assert len(p.hand) == 10 and len(p.deck) == len(deck.cards) - 10
        assert p.leader is not None and library[p.leader.card].kind is Kind.LEADER
    assert events[0].type == "match_started"
    assert legal_intents(library, state, state.other(state.starter)) == []
    assert legal_intents(library, state, state.starter) == [Mulligan()]


def test_mulligan_replaces_cards_and_enforces_the_limit(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state, _ = new_match(library, starter_decks, seed=5)
    seat = state.starter
    hand = state.players[seat].hand
    swapped = (hand[0].instance, hand[1].instance)
    with pytest.raises(IllegalIntent) as info:
        apply(library, state, state.other(seat), Mulligan())
    assert info.value.code == "not_your_turn"
    with pytest.raises(IllegalIntent):
        apply(
            library, state, seat, Mulligan((hand[0].instance, hand[1].instance, hand[2].instance))
        )
    after, events = apply(library, state, seat, Mulligan(swapped))
    ids = {u.instance for u in after.players[seat].hand}
    assert len(ids) == 10 and not ids & set(swapped)
    assert {u.instance for u in after.players[seat].deck} >= set(swapped)
    assert after.mulligan_seat == state.other(seat)
    assert [e.type for e in events].count("card_drawn") == 2


def test_after_both_mulligans_the_starter_plays(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state = _to_playing(library, starter_decks, seed=9)
    assert state.phase is Phase.PLAYING and state.turn == state.starter
    legal = legal_intents(library, state, state.starter)
    assert Pass() in legal and any(isinstance(i, PlayCard) for i in legal)
    assert legal_intents(library, state, state.other(state.starter)) == []


def test_two_tied_rounds_end_the_match_in_a_draw(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state = _to_playing(library, starter_decks, seed=9)
    a, b = state.starter, state.other(state.starter)
    state, _ = apply(library, state, a, Pass())
    state, events = apply(library, state, b, Pass())
    assert state.round == 2 and [p.lives for p in state.players] == [1, 1]
    assert state.starter == b  # a tie hands the start to the other player
    assert "round_ended" in [e.type for e in events]
    state, _ = apply(library, state, state.turn, Pass())  # type: ignore[arg-type]
    state, events = apply(library, state, state.turn, Pass())  # type: ignore[arg-type]
    assert state.phase is Phase.MATCH_OVER and state.winner is None
    assert events[-1].type == "match_ended"
    with pytest.raises(IllegalIntent) as info:
        apply(library, state, 0, Pass())
    assert info.value.code == "match_over"


def test_winning_a_round_costs_the_loser_a_life(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state = _to_playing(library, starter_decks, seed=11)
    a = state.starter
    unit = next(
        i for i in legal_intents(library, state, a) if isinstance(i, PlayCard) and i.row is not None
    )
    state, _ = apply(library, state, a, unit)
    b = state.other(a)
    state, _ = apply(library, state, b, Pass())
    assert state.turn == a  # opponent passed, a keeps playing
    state, _ = apply(library, state, a, Pass())
    assert state.round == 2
    assert state.players[a].rounds_won == 1 and state.players[b].lives == 1
    assert state.starter == a
    assert all(u.card for p in state.players for u in p.discard) and all(
        not p.rows[row].units for p in state.players for row in p.rows
    )


def test_illegal_plays_are_rejected_with_codes(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state = _to_playing(library, starter_decks, seed=3)
    a = state.starter
    with pytest.raises(IllegalIntent) as info:
        apply(library, state, state.other(a), Pass())
    assert info.value.code == "not_your_turn"
    with pytest.raises(IllegalIntent) as info:
        apply(library, state, a, PlayCard("nope"))
    assert info.value.code == "unknown_instance"


def test_view_hides_the_opponents_hand(library: Library, starter_decks: tuple[Deck, Deck]) -> None:
    state = _to_playing(library, starter_decks, seed=3)
    view = player_view(library, state, 0)
    assert len(view["me"]["hand"]) == 10
    assert "hand" not in view["opponent"] and view["opponent"]["hand_count"] == 10
    assert view["opponent"]["deck_count"] == len(state.players[1].deck)
    assert view["turn"] == ("me" if state.turn == 0 else "opponent")
    assert isinstance(view["legal_intents"], list)
    assert view["me"]["leader"]["used"] is False


def test_player_with_no_cards_is_passed_automatically(library: Library) -> None:
    from tests.helpers import Builder, make_library

    lib = make_library()
    s = Builder(lib).state(hand0=["plain5"], hand1=[], turn=0)
    s, events = apply(lib, s, 0, PlayCard(s.players[0].hand[0].instance))
    # seat 1 had nothing and was passed for them; seat 0 then ran out too, so round 1 ended
    # 5-0, round 2 was passed by both and tied, and the match is over with seat 0 the winner.
    auto = [e for e in events if e.type == "player_passed" and e.data["auto"]]
    assert [e.data["seat"] for e in auto] == [1, 0, 0, 1]
    assert [(r.winner, r.scores) for r in s.rounds] == [(0, (5, 0)), (None, (0, 0))]
    assert s.phase is Phase.MATCH_OVER and s.winner == 0
