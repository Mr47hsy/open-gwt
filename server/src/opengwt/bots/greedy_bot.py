from __future__ import annotations

from collections.abc import Sequence

from opengwt.core.engine import apply, play_positions
from opengwt.core.intents import Choose, EndMulligan, Intent, Pass, PlayCard
from opengwt.core.model import Library, MatchState, Phase
from opengwt.core.power import score


class GreedyBot:
    """One-ply greedy opponent: keeps its hand, plays whatever raises its lead the most (at the
    right end of a row), passes when it leads against a passed opponent, and concedes a round it
    cannot overtake with one card."""

    def choose(self, lib: Library, state: MatchState, seat: int, legal: Sequence[Intent]) -> Intent:
        if state.phase is Phase.MULLIGAN:
            return EndMulligan()
        if state.phase is Phase.CHOOSING:
            options = [i for i in legal if isinstance(i, Choose)]
            return max(options, key=lambda i: self._value(lib, state, seat, i))
        me, opp = state.players[seat], state.players[state.other(seat)]
        plays = [self._concrete(lib, state, seat, i) for i in legal if not isinstance(i, Pass)]
        if not plays:
            return Pass()
        lead = score(lib, state, seat) - score(lib, state, opp.seat)
        gains = [(self._value(lib, state, seat, i) - lead, i) for i in plays]
        best_gain, best = max(gains, key=lambda g: g[0])
        if opp.passed:
            if lead > 0:
                return Pass()
            return best if lead + best_gain > 0 else Pass()
        if best_gain <= 0:
            return Pass()
        if lead > 0 and len(me.hand) > len(opp.hand) + 1 and state.round < 3:
            return Pass()
        return best

    @staticmethod
    def _concrete(lib: Library, state: MatchState, seat: int, intent: Intent) -> Intent:
        if isinstance(intent, PlayCard) and intent.row is not None:
            last = play_positions(lib, state, seat, intent) - 1
            return PlayCard(intent.card, intent.row, last)
        return intent

    def _value(self, lib: Library, state: MatchState, seat: int, intent: Intent) -> int:
        """Lead after the intent, resolving any choice it opens greedily, one level deep."""
        new, _ = apply(lib, state, seat, intent)
        for _ in range(8):
            pending = new.pending
            if new.phase is not Phase.CHOOSING or pending is None or pending.seat != seat:
                break
            candidates = [apply(lib, new, seat, Choose(i))[0] for i in range(len(pending.options))]
            new = max(candidates, key=lambda s: self._lead(lib, s, seat))
        return self._lead(lib, new, seat)

    @staticmethod
    def _lead(lib: Library, state: MatchState, seat: int) -> int:
        if state.rounds and (
            state.phase is Phase.MATCH_OVER or state.round != state.rounds[-1].round
        ):
            last = state.rounds[-1]
            return last.scores[seat] - last.scores[1 - seat]
        return score(lib, state, seat) - score(lib, state, 1 - seat)
