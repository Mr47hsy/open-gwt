"""Bots play the rules core directly: no network, no server."""

from opengwt.core.rng import Stream

from .base import Bot
from .greedy_bot import GreedyBot
from .random_bot import RandomBot
from .search_bot import SearchBot

BOT_NAMES = ("random", "greedy", "search")


def make_bot(name: str, rng: Stream, worlds: int | None = None, width: int | None = None) -> Bot:
    """A bot for one or more decisions. ``rng`` is its own random stream: a server-hosted bot
    gets a fresh one per decision from ``opengwt.core.rng.bot_stream`` (ADR 0010). ``worlds``
    and ``width`` size the search bot's search; the others ignore them."""
    if name == "random":
        return RandomBot(rng)
    if name == "greedy":
        return GreedyBot()
    if name == "search":
        options = {"worlds": worlds, "width": width}
        return SearchBot(rng, **{k: v for k, v in options.items() if v is not None})
    raise ValueError(f"unknown bot {name!r}; choose one of {', '.join(BOT_NAMES)}")


__all__ = ["BOT_NAMES", "Bot", "GreedyBot", "RandomBot", "SearchBot", "make_bot"]
