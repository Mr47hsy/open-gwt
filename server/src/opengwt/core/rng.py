"""The rules core's random streams: SHA-256 in counter mode (ADR 0010).

Block ``n`` of a stream is ``SHA-256(label || seed || n)`` with ``n`` as eight big-endian bytes;
each block yields eight 32-bit big-endian words in order. The match seed is 256 bits, written as
64 lowercase hex characters. Streams with different labels are independent: what a player sees
of one says nothing about another. Owning the generator keeps replays independent of the
interpreter's ``random`` module, and ``hashlib`` is standard library.
"""

from __future__ import annotations

import hashlib
import struct
from typing import TypeVar

T = TypeVar("T")

SEED_HEX_LENGTH = 64
WORDS_PER_BLOCK = 8

LABEL_ENGINE = b"opengwt/engine"
LABEL_IDS = b"opengwt/ids"
LABEL_BOT = b"opengwt/bot/"
INSTANCE_ID_HEX = 12
INSTANCE_ID_PREFIX = "c"

_HEX = frozenset("0123456789abcdef")


def parse_seed(seed: str) -> bytes:
    """The 32 bytes of a seed written as 64 lowercase hex characters."""
    if len(seed) != SEED_HEX_LENGTH or not set(seed) <= _HEX:
        raise ValueError("a seed is 64 lowercase hex characters")
    return bytes.fromhex(seed)


def seed_from_int(n: int) -> str:
    """A seed from a small integer, for tests and the simulator. Never for a live match: the
    server draws its seeds from ``secrets.token_bytes(32)``."""
    if not 0 <= n < 1 << 256:
        raise ValueError("seed integer out of range")
    return n.to_bytes(32, "big").hex()


def _block(prefix: bytes, n: int) -> bytes:
    return hashlib.sha256(prefix + n.to_bytes(8, "big")).digest()


class Stream:
    """One labelled stream over a seed; ``block`` and ``pos`` are its whole state."""

    __slots__ = ("_cached", "_prefix", "_words", "block", "pos")

    def __init__(self, seed: str, label: bytes, block: int = 0, pos: int = 0) -> None:
        if block < 0 or not 0 <= pos < WORDS_PER_BLOCK:
            raise ValueError("stream position out of range")
        self._prefix = label + parse_seed(seed)
        self.block = block
        self.pos = pos
        self._cached = -1
        self._words: tuple[int, ...] = ()

    def next_u32(self) -> int:
        if self._cached != self.block:
            self._words = struct.unpack(">8I", _block(self._prefix, self.block))
            self._cached = self.block
        word = self._words[self.pos]
        self.pos += 1
        if self.pos == WORDS_PER_BLOCK:
            self.block += 1
            self.pos = 0
        return word

    def below(self, bound: int) -> int:
        """Uniform integer in ``[0, bound)`` without modulo bias (rejection sampling)."""
        if bound <= 0:
            raise ValueError("bound must be positive")
        threshold = ((1 << 32) - bound) % bound
        while True:
            r = self.next_u32()
            if r >= threshold:
                return r % bound

    def shuffle(self, items: list[T]) -> None:
        """In-place Fisher-Yates shuffle."""
        for i in range(len(items) - 1, 0, -1):
            j = self.below(i + 1)
            items[i], items[j] = items[j], items[i]


def engine_stream(seed: str, block: int = 0, pos: int = 0) -> Stream:
    """The stream every rule draws from: shuffles, starters, random picks, tie breaks."""
    return Stream(seed, LABEL_ENGINE, block, pos)


def bot_stream(seed: str, decision: int) -> Stream:
    """A server-hosted bot's stream for the decision at index ``decision`` of the intent log."""
    if decision < 0:
        raise ValueError("decision index must not be negative")
    return Stream(seed, LABEL_BOT + str(decision).encode("ascii"))


def instance_id(seed: str, counter: int) -> str:
    """The opaque id of the ``counter``-th instance: block ``counter`` of the id stream, cut to
    ``INSTANCE_ID_HEX`` hex characters. It reveals neither a deck position nor a draw order."""
    digest = _block(LABEL_IDS + parse_seed(seed), counter).hex()
    return INSTANCE_ID_PREFIX + digest[:INSTANCE_ID_HEX]
