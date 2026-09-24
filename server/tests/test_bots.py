"""Bots — the greedy bot weighs activated abilities (ADR 0009 phase C acceptance); the random
bot picks any legal intent, orders and end_turn included; the search bot plays out worlds
sampled from what it can see, and nothing it cannot see changes them."""

from collections import Counter

from opengwt.bots import GreedyBot, SearchBot
from opengwt.bots.sampling import deck_pool, sample_world
from opengwt.core.engine import acting_seat, apply, legal_intents, new_match
from opengwt.core.intents import EndMulligan, EndTurn, Mulligan, Pass, PlayCard, UseOrder
from opengwt.core.model import Deck, Library, MatchState, RoundResult, Row
from opengwt.core.replay import replay
from opengwt.core.rng import Stream, seed_from_int
from opengwt.core.serialize import state_hash
from opengwt.sim.cli import run_match, sim_bot
from tests.helpers import Builder, make_library, play

LIB = make_library()


def test_the_greedy_bot_uses_an_order_that_beats_its_cards_first() -> None:
    """The leader boosts an ally by 2; the only card is a unit of 1."""
    s = Builder(LIB).state(
        hand0=["spare", "spare"],
        board0={"melee": ["plain5"]},
        board1={"melee": ["plain8"]},
        leaders=("leader", None),
    )
    bot = GreedyBot()
    intent = bot.choose(LIB, s, 0, legal_intents(LIB, s, 0))
    assert isinstance(intent, UseOrder)
    s, _ = apply(LIB, s, 0, intent)
    s, _ = apply(LIB, s, 0, bot.choose(LIB, s, 0, legal_intents(LIB, s, 0)))  # the ally
    assert Pass() not in legal_intents(LIB, s, 0)
    assert isinstance(bot.choose(LIB, s, 0, legal_intents(LIB, s, 0)), PlayCard)


def test_the_greedy_bot_uses_its_orders_after_its_card_then_ends_the_turn() -> None:
    s = Builder(LIB).state(
        hand0=["plain8", "spare"],
        board0={"melee": ["plain5"]},
        board1={"melee": ["plain8"]},
        leaders=("leader", None),
    )
    bot = GreedyBot()
    first = bot.choose(LIB, s, 0, legal_intents(LIB, s, 0))
    assert isinstance(first, PlayCard)  # 8 beats the leader's 2
    s, _ = play(LIB, s, 0, "plain8", end=False)
    order = bot.choose(LIB, s, 0, legal_intents(LIB, s, 0))
    assert isinstance(order, UseOrder)
    s, _ = apply(LIB, s, 0, order)
    s, _ = apply(LIB, s, 0, bot.choose(LIB, s, 0, legal_intents(LIB, s, 0)))
    assert bot.choose(LIB, s, 0, legal_intents(LIB, s, 0)) == EndTurn()


def test_greedy_bots_use_activated_abilities_in_real_matches(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    used = 0
    for n in range(1, 6):
        bots = (sim_bot("greedy", 1), sim_bot("greedy", 2))
        record, _, _ = run_match(library, starter_decks, seed_from_int(n), bots)
        _, events = replay(library, record)
        used += sum(1 for e in events if e.type == "order_used")
    assert used > 0


# --- the search bot (hidden-information sampling) -------------------------------------------------


def _stream(n: int) -> Stream:
    return Stream(seed_from_int(n), b"test/bot")


def _mid_match(library: Library, starter_decks: tuple[Deck, Deck]) -> MatchState:
    """A real match a few turns in, greedy against greedy."""
    state, _ = new_match(library, starter_decks, seed_from_int(11))
    bot = GreedyBot()
    for _ in range(12):
        seat = acting_seat(state)
        assert seat is not None
        intent = bot.choose(library, state, seat, legal_intents(library, state, seat))
        state, _ = apply(library, state, seat, intent)
    return state


def test_a_sampled_world_keeps_what_the_player_sees(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state = _mid_match(library, starter_decks)
    world = sample_world(library, state, 0, _stream(1))
    me, opponent = state.players
    w_me, w_opponent = world.players
    assert [c.card for c in w_me.hand] == [c.card for c in me.hand]
    assert Counter(c.card for c in w_me.deck) == Counter(c.card for c in me.deck)
    assert (len(w_opponent.hand), len(w_opponent.deck)) == (len(opponent.hand), len(opponent.deck))
    for row in state.rules.rows:
        for seat in (0, 1):
            assert [c.card for c in world.players[seat].rows[row].cards] == [
                c.card for c in state.players[seat].rows[row].cards
            ]
    assert [c.card for c in w_opponent.graveyard] == [c.card for c in opponent.graveyard]
    assert world.seed != state.seed and (world.rng_block, world.rng_pos) == (0, 0)
    pool = set(deck_pool(library, opponent.faction, state.rules))
    assert {c.card for c in [*w_opponent.hand, *w_opponent.deck]} <= pool


def test_a_sampled_world_ignores_what_the_player_cannot_see(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    """Two matches that differ only in the opponent's hidden cards, the player's deck order and
    the seed give the same world: nothing hidden leaks into the search."""
    state = _mid_match(library, starter_decks)
    other = state.clone()
    opponent = other.players[1]
    for card, replacement in zip(opponent.hand, reversed(opponent.deck), strict=False):
        card.card = replacement.card
    other.players[0].deck.reverse()
    other.seed = seed_from_int(99)
    assert state_hash(sample_world(library, state, 0, _stream(5))) == state_hash(
        sample_world(library, other, 0, _stream(5))
    )


def test_the_search_bot_finds_the_winning_place_the_greedy_bot_misses() -> None:
    """Round three, one round each, the opponent passed at 15. The ally that boosts its
    neighbours by 2 wins between two 5s (16) and loses at the end of the row (14): the greedy
    bot, which only plays at the end, concedes; the search bot plays it in the middle."""
    s = Builder(LIB).state(
        hand0=["aura-adj"],
        board0={"melee": ["plain5", "plain5"]},
        board1={"melee": ["plain5", "plain5", "plain5"]},
    )
    s.round = 3
    s.rounds = [RoundResult(1, (0,), (10, 5)), RoundResult(2, (1,), (5, 10))]
    for player in s.players:
        player.rounds_won = 1
    s.players[1].passed = True
    legal = legal_intents(LIB, s, 0)
    assert GreedyBot().choose(LIB, s, 0, legal) == Pass()
    card = s.players[0].hand[0].instance
    assert SearchBot(_stream(3), worlds=2).choose(LIB, s, 0, legal) == PlayCard(card, Row.MELEE, 1)


def test_the_search_bot_redraws_its_cheapest_card_only_when_the_deck_is_better(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    state, _ = new_match(library, starter_decks, seed_from_int(3))
    seat = state.starter
    bot = SearchBot(_stream(1))
    player = state.players[seat]
    for card in player.hand:
        card.card = "u-1001"  # provisions 4
    for card in player.deck:
        card.card = "u-1014"  # provisions 9
    intent = bot.choose(library, state, seat, legal_intents(library, state, seat))
    assert isinstance(intent, Mulligan)
    for card in player.deck:
        card.card = "u-1002"  # provisions 5: not worth a redraw
    assert bot.choose(library, state, seat, legal_intents(library, state, seat)) == EndMulligan()


def test_the_search_bot_is_deterministic_and_legal(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    bots = (
        SearchBot(_stream(1), worlds=1, width=2),
        SearchBot(_stream(2), worlds=1, width=2),
    )
    record, final, _ = run_match(library, starter_decks, seed_from_int(4), bots)
    again, _ = replay(library, record)
    assert state_hash(again) == state_hash(final)
    bots = (
        SearchBot(_stream(1), worlds=1, width=2),
        SearchBot(_stream(2), worlds=1, width=2),
    )
    second, _, _ = run_match(library, starter_decks, seed_from_int(4), bots)
    assert second.intents == record.intents
