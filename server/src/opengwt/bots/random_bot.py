from __future__ import annotations

from collections.abc import Sequence

from opengwt.core.intents import Intent, Mulligan
from opengwt.core.model import Library, MatchState, Phase
from opengwt.core.rng import Pcg32


class RandomBot:
    """Uniformly random legal play; useful for fuzzing the rules and for replay checks."""

    def __init__(self, seed: int) -> None:
        self.rng = Pcg32(seed, sequence=7)

    def choose(self, lib: Library, state: MatchState, seat: int, legal: Sequence[Intent]) -> Intent:
        if state.phase is Phase.MULLIGAN:
            hand = list(state.players[seat].hand)
            count = self.rng.below(min(state.rules.mulligan_max, len(hand)) + 1)
            self.rng.shuffle(hand)
            return Mulligan(tuple(u.instance for u in hand[:count]))
        if not legal:
            raise ValueError("no legal intents")
        return legal[self.rng.below(len(legal))]
