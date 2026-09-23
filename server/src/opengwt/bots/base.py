from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from opengwt.core.intents import Intent
from opengwt.core.model import Library, MatchState


class Bot(Protocol):
    """Chooses one of the legal intents for ``seat``.

    A bot receives the full state for convenience of simulation, but it must only act on what
    ``view(state, seat)`` would show it: its own hand, the board, counts. Peeking at the
    opponent's hand or the deck order is cheating, and the server will one day hand bots the
    view only.
    """

    def choose(
        self, lib: Library, state: MatchState, seat: int, legal: Sequence[Intent]
    ) -> Intent: ...
