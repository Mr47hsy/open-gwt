from __future__ import annotations

from collections.abc import Sequence

from opengwt.core.engine import play_positions
from opengwt.core.intents import Intent, PlayCard
from opengwt.core.model import Library, MatchState
from opengwt.core.rng import Stream


class RandomBot:
    """Uniformly random legal play, at a random position; useful for fuzzing the rules and for
    replay checks. Its randomness is its own stream, never the match's."""

    def __init__(self, rng: Stream) -> None:
        self.rng = rng

    def choose(self, lib: Library, state: MatchState, seat: int, legal: Sequence[Intent]) -> Intent:
        if not legal:
            raise ValueError("no legal intents")
        intent = legal[self.rng.below(len(legal))]
        if isinstance(intent, PlayCard) and intent.row is not None:
            positions = play_positions(lib, state, seat, intent)
            return PlayCard(intent.card, intent.row, self.rng.below(positions))
        return intent
