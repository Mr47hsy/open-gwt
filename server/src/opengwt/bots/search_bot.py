from __future__ import annotations

import math
from collections.abc import Sequence

from opengwt.core.engine import acting_seat, apply, legal_intents, play_positions
from opengwt.core.intents import EndMulligan, EndTurn, Intent, Mulligan, Pass, PlayCard
from opengwt.core.model import Action, Library, MatchState, Phase, Scope, Side, Units
from opengwt.core.power import score
from opengwt.core.rng import Stream

from .greedy_bot import GreedyBot
from .sampling import sample_world

# Win probability, in thousandths, of a position at the end of a round: logistic in the round
# lead and the card lead the next rounds are played with (cards.md §11.5).
SCALE = 1000
ROUND_WEIGHT = 12
CARD_WEIGHT = 4
POINT_WEIGHT = 1  # per point, for a playout cut short mid-round
WEIGHT_UNIT = 10
LOGISTIC: list[int] = [round(SCALE / (1 + math.exp(-x / WEIGHT_UNIT))) for x in range(-60, 61)]


def win_chance(logit: int) -> int:
    """``SCALE / (1 + e^(-logit / WEIGHT_UNIT))``, from a table: integers in, integers out."""
    return LOGISTIC[max(-60, min(60, logit)) + 60]


class SearchBot:
    """Determinized Monte-Carlo search over the turn's main decision.

    For the card to play, the ability to use or whether to pass, it keeps the ``width`` best
    candidates by the greedy bot's one-ply value, plus the pass, and plays each out in ``worlds``
    worlds sampled from what it can see (``sampling.sample_world``) — every candidate in the same
    worlds — to the end of the round, both players then following the greedy bot. It scores a
    finished match by its result and a finished round by the round lead and the card lead the
    next round starts with, and takes the candidate with the best total. Mulligans redraw a card
    whose provisions are well below the average left in its deck; choices and what follows the
    turn's card are left to the greedy bot. Its randomness is its own stream, never the match's.
    """

    def __init__(
        self, rng: Stream, worlds: int = 6, width: int = 3, rollout_steps: int = 300
    ) -> None:
        self.rng = rng
        self.worlds = worlds
        self.width = width
        self.rollout_steps = rollout_steps
        self.greedy = GreedyBot()

    def choose(self, lib: Library, state: MatchState, seat: int, legal: Sequence[Intent]) -> Intent:
        if not legal:
            raise ValueError("no legal intents")
        if state.phase is Phase.MULLIGAN:
            return self._mulligan(lib, state, seat, legal)
        if state.phase is not Phase.PLAYING or EndTurn() in legal:
            return self.greedy.choose(lib, state, seat, legal)
        candidates = self._candidates(lib, state, seat, legal)
        if len(candidates) == 1:
            return candidates[0]
        totals = [0] * len(candidates)
        for _ in range(self.worlds):
            world = sample_world(lib, state, seat, self.rng)
            for index, intent in enumerate(candidates):
                after, _ = apply(lib, world, seat, intent)
                totals[index] += self._playout(lib, after, seat, state.round)
        best = max(range(len(candidates)), key=lambda i: (totals[i], -i))
        return candidates[best]

    # --- candidates ------------------------------------------------------------------------------

    def _candidates(
        self, lib: Library, state: MatchState, seat: int, legal: Sequence[Intent]
    ) -> list[Intent]:
        """The pass if it is legal, and the ``width`` intents the greedy bot values most — every
        position of a play where adjacency can matter, the right end otherwise."""
        moves: list[Intent] = []
        for intent in legal:
            if isinstance(intent, Pass):
                continue
            if isinstance(intent, PlayCard) and intent.row is not None:
                positions = play_positions(lib, state, seat, intent)
                spots = (
                    range(positions) if _adjacency(lib, state, seat, intent) else [positions - 1]
                )
                moves.extend(PlayCard(intent.card, intent.row, p) for p in spots)
            else:
                moves.append(intent)
        valued = sorted(
            enumerate(moves),
            key=lambda m: (-self.greedy.value(lib, state, seat, m[1]), m[0]),
        )
        kept = [intent for _, intent in valued[: self.width]]
        if Pass() in legal:
            kept.append(Pass())
        return kept or list(legal)

    # --- playouts --------------------------------------------------------------------------------

    def _playout(self, lib: Library, state: MatchState, seat: int, round_: int) -> int:
        """Both players follow the greedy bot until the round is over; then the position's value
        for ``seat`` in thousandths of a win."""
        steps = 0
        while state.phase is not Phase.MATCH_OVER and state.round == round_:
            actor = acting_seat(state)
            if actor is None or steps >= self.rollout_steps:
                break
            intent = self.greedy.choose(lib, state, actor, legal_intents(lib, state, actor))
            state, _ = apply(lib, state, actor, intent)
            steps += 1
        return evaluate(lib, state, seat, round_)

    # --- mulligan --------------------------------------------------------------------------------

    def _mulligan(
        self, lib: Library, state: MatchState, seat: int, legal: Sequence[Intent]
    ) -> Intent:
        """Redraw the cheapest card in hand while it costs at least two provisions less than the
        average card left in the deck — provisions are what a designer prices a card's strength
        in — and the deck holds something else."""
        player = state.players[seat]
        redraws = {i.card for i in legal if isinstance(i, Mulligan)}
        if not redraws or not player.deck:
            return EndMulligan()
        returned = set(player.mulligan.returned if player.mulligan else [])
        deck = [lib[c.card].provisions for c in player.deck if c.card not in returned]
        if not deck:
            return EndMulligan()
        average_x10 = sum(deck) * 10 // len(deck)
        hand = [c for c in player.hand if c.instance in redraws]
        cheapest = min(hand, key=lambda c: (lib[c.card].provisions, c.card, c.instance))
        if lib[cheapest.card].provisions * 10 <= average_x10 - 20:
            return Mulligan(cheapest.instance)
        return EndMulligan()


def evaluate(lib: Library, state: MatchState, seat: int, round_: int) -> int:
    """The chance ``seat`` wins from ``state``, in thousandths: exact once the match is over;
    after round ``round_``, from the round lead and the card lead; mid-round, from the score
    lead and the card lead."""
    if state.phase is Phase.MATCH_OVER:
        if state.winner is None:
            return SCALE // 2
        return SCALE if state.winner == seat else 0
    me, opponent = state.players[seat], state.players[1 - seat]
    cards = len(me.hand) - len(opponent.hand)
    if state.round != round_:
        rounds = me.rounds_won - opponent.rounds_won
        return win_chance(ROUND_WEIGHT * rounds + CARD_WEIGHT * cards)
    points = score(lib, state, seat) - score(lib, state, 1 - seat)
    return win_chance(CARD_WEIGHT * cards + POINT_WEIGHT * points)


def _adjacency(lib: Library, state: MatchState, seat: int, intent: PlayCard) -> bool:
    """Whether where on the row a card lands can matter: it, or a card already on that
    row-side, acts on its neighbours."""
    player = state.players[seat]
    card = next(c for c in player.hand if c.instance == intent.card)
    if intent.row is None:
        return False
    land = state.players[1 - seat] if lib[card.card].side is Side.OPPONENT else player
    neighbours = [c.card for c in land.rows[intent.row].cards]
    return any(_acts_on_neighbours(lib, cid) for cid in [card.card, *neighbours])


def _acts_on_neighbours(lib: Library, card_id: str) -> bool:
    for ability in lib[card_id].abilities:
        if ability.do is Action.CONTINUOUS_BOOST and ability.scope is Scope.ADJACENT:
            return True
        if ability.target is not None and ability.target.units is Units.ADJACENT:
            return True
    return False
