"""Bots — the greedy bot weighs activated abilities (ADR 0009 phase C acceptance); the random
bot picks any legal intent, orders and end_turn included."""

from opengwt.bots import GreedyBot
from opengwt.core.engine import apply, legal_intents
from opengwt.core.intents import EndTurn, Pass, PlayCard, UseOrder
from opengwt.core.model import Deck, Library
from opengwt.core.replay import replay
from opengwt.core.rng import seed_from_int
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
