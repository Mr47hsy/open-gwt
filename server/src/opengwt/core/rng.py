"""Deterministic PRNG for the rules core: PCG32 (XSH RR, 64/32) on Python integers.

Owning the generator keeps replays independent of the interpreter's ``random`` module.
"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")

MASK64 = (1 << 64) - 1
MASK32 = (1 << 32) - 1
MULTIPLIER = 6364136223846793005
DEFAULT_SEQUENCE = 54


class Pcg32:
    """Minimal PCG32 as published by M. O'Neill; ``state`` and ``inc`` are the whole state."""

    __slots__ = ("inc", "state")

    def __init__(self, seed: int, sequence: int = DEFAULT_SEQUENCE) -> None:
        self.inc = ((sequence << 1) | 1) & MASK64
        self.state = 0
        self.next_u32()
        self.state = (self.state + seed) & MASK64
        self.next_u32()

    @classmethod
    def from_state(cls, state: int, inc: int) -> Pcg32:
        rng = cls.__new__(cls)
        rng.state = state & MASK64
        rng.inc = inc & MASK64
        return rng

    def next_u32(self) -> int:
        old = self.state
        self.state = (old * MULTIPLIER + self.inc) & MASK64
        xorshifted = (((old >> 18) ^ old) >> 27) & MASK32
        rot = old >> 59
        return ((xorshifted >> rot) | (xorshifted << ((-rot) & 31))) & MASK32

    def below(self, bound: int) -> int:
        """Uniform integer in ``[0, bound)`` without modulo bias."""
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
