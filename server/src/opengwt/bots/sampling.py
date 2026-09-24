"""Worlds consistent with what one player knows — the hidden-information sampling a search bot
plays out instead of the real match.

A player sees the board, every graveyard and banished zone, their own hand, the size of every
hand and deck, and knows their own deck's contents but not its order (cards.md §5, match.md §7).
They do not know the opponent's hand or deck, nor the match seed, which with the open-source
shuffle would tell every future draw and every random pick (ADR 0010). A sampled *world* keeps
all the first and replaces all the second: the player's own deck is reshuffled, the opponent's
hand and deck are redrawn from the cards their deck could plausibly hold, and the engine gets a
fresh seed. Nothing here reads the real hidden information to decide what to put in its place.
"""

from __future__ import annotations

from collections import Counter

from opengwt.core.engine import NEUTRAL
from opengwt.core.model import Color, Kind, Library, MatchState, PlayerState, Rules
from opengwt.core.rng import SEED_HEX_LENGTH, Stream

PLAYABLE = frozenset({Kind.UNIT, Kind.SPECIAL, Kind.ARTIFACT})


def deck_pool(lib: Library, faction: str, rules: Rules) -> list[str]:
    """Every copy a deck of ``faction`` may hold under the copy limits, by card id: the public
    model of a deck nobody has shown."""
    out: list[str] = []
    for cid, defn in lib.items():
        if defn.kind not in PLAYABLE or defn.token or defn.faction not in (faction, NEUTRAL):
            continue
        copies = rules.copies_gold if defn.color is Color.GOLD else rules.copies_bronze
        out.extend([cid] * copies)
    return sorted(out)


def seen_cards(lib: Library, state: MatchState, owner: int) -> Counter[str]:
    """The cards of ``owner``'s deck that have shown themselves: on the board on either side,
    in their graveyard or banished — created cards and tokens aside, which no deck held."""
    seen: Counter[str] = Counter()
    zones = [c for p in state.players for side in p.rows.values() for c in side.cards]
    zones += state.players[owner].graveyard + state.players[owner].banished
    for card in zones:
        defn = lib.get(card.card)
        if card.owner == owner and defn is not None and defn.kind in PLAYABLE and not defn.token:
            seen[card.card] += 1
    return seen


def fresh_seed(rng: Stream) -> str:
    return "".join(f"{rng.next_u32():08x}" for _ in range(SEED_HEX_LENGTH // 8))


def sample_world(lib: Library, state: MatchState, seat: int, rng: Stream) -> MatchState:
    """A copy of ``state`` in which everything ``seat`` cannot see is drawn anew from ``rng``."""
    world = state.clone()
    me, opponent = world.players[seat], world.players[1 - seat]
    # sorted first, so that nothing of the real order survives the shuffle
    me.deck.sort(key=lambda c: (c.card, c.instance))
    rng.shuffle(me.deck)
    _redeal(lib, world, opponent, rng)
    world.seed = fresh_seed(rng)
    world.rng_block = 0
    world.rng_pos = 0
    return world


def _redeal(lib: Library, world: MatchState, player: PlayerState, rng: Stream) -> None:
    """Give the hidden cards of ``player`` identities drawn without replacement from what their
    deck could still hold; the instances, and so every count, stay."""
    player.deck.sort(key=lambda c: c.instance)
    hidden = [*sorted(player.hand, key=lambda c: c.instance), *player.deck]
    if not hidden:
        return
    seen = seen_cards(lib, world, player.seat)
    remaining: list[str] = []
    for cid, copies in sorted(Counter(deck_pool(lib, player.faction, world.rules)).items()):
        remaining.extend([cid] * max(0, copies - seen[cid]))
    if not remaining:
        remaining = deck_pool(lib, player.faction, world.rules)
    if not remaining:
        return
    while len(remaining) < len(hidden):
        remaining = remaining + remaining
    rng.shuffle(remaining)
    for inst, cid in zip(hidden, remaining, strict=False):
        inst.card = cid
    # whether their starting deck held a neutral card is hidden too (cards.md §6.2): judge it
    # by this world's cards — the ones shown and the ones just dealt
    shown = [c for c in seen.elements() if lib[c].faction == NEUTRAL]
    player.deck_had_neutral = bool(shown) or any(lib[c.card].faction == NEUTRAL for c in hidden)
