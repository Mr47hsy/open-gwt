"""Bots play the rules core directly: no network, no server."""

from opengwt.core.rng import Stream

from .base import Bot
from .greedy_bot import GreedyBot
from .random_bot import RandomBot

BOT_NAMES = ("random", "greedy")


def make_bot(name: str, rng: Stream) -> Bot:
    """A bot for one or more decisions. ``rng`` is its own random stream: a server-hosted bot
    gets a fresh one per decision from ``opengwt.core.rng.bot_stream`` (ADR 0010)."""
    if name == "random":
        return RandomBot(rng)
    if name == "greedy":
        return GreedyBot()
    raise ValueError(f"unknown bot {name!r}; choose one of {', '.join(BOT_NAMES)}")


__all__ = ["BOT_NAMES", "Bot", "GreedyBot", "RandomBot", "make_bot"]
