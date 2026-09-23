"""Bots play the rules core directly: no network, no server."""

from .base import Bot
from .greedy_bot import GreedyBot
from .random_bot import RandomBot

BOT_NAMES = ("random", "greedy")


def make_bot(name: str, seed: int) -> Bot:
    if name == "random":
        return RandomBot(seed)
    if name == "greedy":
        return GreedyBot()
    raise ValueError(f"unknown bot {name!r}; choose one of {', '.join(BOT_NAMES)}")


__all__ = ["BOT_NAMES", "Bot", "GreedyBot", "RandomBot", "make_bot"]
