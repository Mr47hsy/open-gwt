"""The balance report of ``opengwt-sim``: how much each card of each deck contributes to winning.

The main measure is the **win-rate contribution** of a card, known elsewhere as *improvement when
drawn*: the win rate of the matches in which its deck's player drew it, minus the win rate of the
matches in which they did not. Draws are random, so the difference is the card's effect rather
than the bot's taste; a card the bots never play shows up anyway. Next to it the report gives
how often the card is played, the win rate when it is, and the points it is worth when played
from hand — the lead gained over the opponent once it and everything it set off resolved — in
total and per provision, which is the number a designer prices a card with (cards.md §3).

A draw counts half a win throughout. The margin is the half-width of a 95 % normal interval on
the contribution; a contribution smaller than its margin is noise.
"""

from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass, field
from typing import Any

from opengwt.core.intents import Intent, PlayCard, UseOrder
from opengwt.core.model import Deck, Library, MatchState
from opengwt.core.power import score

Z95 = 1.96


@dataclass
class MatchTrace:
    """What one match tells the report, per seat: the cards drawn and played, and the lead each
    play from hand and each activated ability gained; and who started round one."""

    drawn: tuple[set[str], set[str]] = field(default_factory=lambda: (set(), set()))
    played: tuple[set[str], set[str]] = field(default_factory=lambda: (set(), set()))
    plays: list[tuple[int, str, int]] = field(default_factory=list)
    orders: list[tuple[int, str, int]] = field(default_factory=list)
    starter: int | None = None


class Tracer:
    """Fills a ``MatchTrace`` from the states and events of a match as it is played."""

    def __init__(self, lib: Library, trace: MatchTrace) -> None:
        self.lib = lib
        self.trace = trace
        self._open: tuple[int, str, int, bool] | None = None

    def before(self, state: MatchState, seat: int, intent: Intent) -> None:
        card = _acting_card(state, seat, intent)
        if card is not None:
            self._open = (seat, card, _lead(self.lib, state, seat), isinstance(intent, UseOrder))

    def after(self, state: MatchState, events: list[Any]) -> None:
        for event in events:
            seat = event.data.get("seat")
            if event.type == "match_started":
                self.trace.starter = int(event.data["starter"])
            elif event.type == "card_drawn" and isinstance(seat, int):
                self.trace.drawn[seat].add(str(event.data["card"]))
            elif event.type == "card_played" and isinstance(seat, int):
                self.trace.played[seat].add(str(event.data["card"]))
        if self._open is not None and state.pending is None:
            seat, card, before, order = self._open
            gained = _lead(self.lib, state, seat) - before
            (self.trace.orders if order else self.trace.plays).append((seat, card, gained))
            self._open = None


def _acting_card(state: MatchState, seat: int, intent: Intent) -> str | None:
    player = state.players[seat]
    if isinstance(intent, PlayCard):
        return next((c.card for c in player.hand if c.instance == intent.card), None)
    if isinstance(intent, UseOrder):
        if player.leader is not None and player.leader.instance == intent.instance:
            return player.leader.card
        for side in player.rows.values():
            for card in side.cards:
                if card.instance == intent.instance:
                    return card.card
    return None


def _lead(lib: Library, state: MatchState, seat: int) -> int:
    return score(lib, state, seat) - score(lib, state, 1 - seat)


@dataclass
class CardStats:
    """One card of one deck. ``*_points`` count two per win and one per draw."""

    games: int = 0
    drawn: int = 0
    drawn_points: int = 0
    undrawn_points: int = 0
    played_games: int = 0
    played_points: int = 0
    plays: int = 0
    play_value: int = 0
    uses: int = 0
    use_value: int = 0


@dataclass
class DeckStats:
    games: int = 0
    points: int = 0
    started: int = 0
    started_points: int = 0


@dataclass
class BalanceReport:
    stats: dict[tuple[str, str], CardStats] = field(default_factory=dict)
    decks: dict[str, DeckStats] = field(default_factory=dict)

    def add(
        self,
        deck_ids: tuple[str, str],
        decks: tuple[Deck, Deck],
        winner: int | None,
        starter: int,
        trace: MatchTrace,
    ) -> None:
        for seat in (0, 1):
            points = 1 if winner is None else 2 if winner == seat else 0
            deck_id, deck = deck_ids[seat], decks[seat]
            summary = self.decks.setdefault(deck_id, DeckStats())
            summary.games += 1
            summary.points += points
            if starter == seat:
                summary.started += 1
                summary.started_points += points
            for cid in [*sorted(set(deck.cards)), deck.leader, deck.stratagem]:
                stats = self.stats.setdefault((deck_id, cid), CardStats())
                stats.games += 1
                if cid in trace.drawn[seat]:
                    stats.drawn += 1
                    stats.drawn_points += points
                else:
                    stats.undrawn_points += points
                if cid in trace.played[seat]:
                    stats.played_games += 1
                    stats.played_points += points
            for who, cid, value in trace.plays:
                if who == seat and (deck_id, cid) in self.stats:
                    self.stats[deck_id, cid].plays += 1
                    self.stats[deck_id, cid].play_value += value
            for who, cid, value in trace.orders:
                if who == seat and (deck_id, cid) in self.stats:
                    self.stats[deck_id, cid].uses += 1
                    self.stats[deck_id, cid].use_value += value

    def rows(self, lib: Library, decks: dict[str, Deck]) -> list[dict[str, Any]]:
        """One row per deck and card, the strongest contribution first within each deck."""
        out: list[dict[str, Any]] = []
        for (deck_id, cid), s in self.stats.items():
            defn = lib[cid]
            deck = decks[deck_id]
            undrawn = s.games - s.drawn
            gih = _rate(s.drawn_points, s.drawn)
            gns = _rate(s.undrawn_points, undrawn)
            contribution = margin = None
            if gih is not None and gns is not None:
                contribution = gih - gns
                margin = Z95 * math.sqrt(gih * (1 - gih) / s.drawn + gns * (1 - gns) / undrawn)
            value = s.play_value / s.plays if s.plays else None
            out.append(
                {
                    "deck": deck_id,
                    "card": cid,
                    "kind": defn.kind.value,
                    "color": defn.color.value if defn.color is not None else None,
                    "provisions": defn.provisions,
                    "copies": deck.cards.count(cid),
                    "games": s.games,
                    "drawn_rate": _round(s.drawn / s.games if s.games else None),
                    "win_rate_drawn": _round(gih),
                    "win_rate_not_drawn": _round(gns),
                    "contribution": _round(contribution),
                    "margin": _round(margin),
                    "played_rate": _round(s.played_games / s.games if s.games else None),
                    "win_rate_played": _round(_rate(s.played_points, s.played_games)),
                    "plays": s.plays,
                    "value_per_play": _round(value),
                    "value_per_provision": _round(
                        value / defn.provisions if value is not None and defn.provisions else None
                    ),
                    "uses": s.uses,
                    "value_per_use": _round(s.use_value / s.uses if s.uses else None),
                }
            )
        out.sort(
            key=lambda r: (
                r["deck"],
                r["contribution"] is None,
                -(r["contribution"] or 0.0),
                r["card"],
            )
        )
        return out

    def deck_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "deck": deck_id,
                "games": d.games,
                "win_rate": _round(_rate(d.points, d.games)),
                "started": d.started,
                "win_rate_starting": _round(_rate(d.started_points, d.started)),
                "win_rate_second": _round(_rate(d.points - d.started_points, d.games - d.started)),
            }
            for deck_id, d in sorted(self.decks.items())
        ]

    def to_json(self, lib: Library, decks: dict[str, Deck], meta: dict[str, Any]) -> str:
        doc = {
            "schema": "opengwt.balance/1",
            **meta,
            "decks": self.deck_rows(),
            "cards": self.rows(lib, decks),
        }
        return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"

    def to_csv(self, lib: Library, decks: dict[str, Deck]) -> str:
        rows = self.rows(lib, decks)
        buffer = io.StringIO()
        if rows:
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return buffer.getvalue()

    def table(self, lib: Library, decks: dict[str, Deck]) -> list[str]:
        """The report as text, one deck after another."""
        lines = []
        for d in self.deck_rows():
            lines.append(
                f"deck {d['deck']}: games={d['games']} win_rate={_pct(d['win_rate'])} "
                f"starting={_pct(d['win_rate_starting'])} second={_pct(d['win_rate_second'])}"
            )
        header = (
            f"{'card':<10} {'prov':>4} {'n':>2} {'drawn':>6} {'wr+':>6} {'wr-':>6} "
            f"{'contrib':>8} {'±':>6} {'played':>6} {'value':>6} {'v/prov':>6} {'uses':>5}"
        )
        deck = None
        for r in self.rows(lib, decks):
            if r["deck"] != deck:
                deck = r["deck"]
                lines.extend(["", f"{deck}", header])
            lines.append(
                f"{r['card']:<10} {r['provisions']:>4} {r['copies']:>2} "
                f"{_pct(r['drawn_rate']):>6} {_pct(r['win_rate_drawn']):>6} "
                f"{_pct(r['win_rate_not_drawn']):>6} {_pp(r['contribution']):>8} "
                f"{_pp(r['margin']):>6} {_pct(r['played_rate']):>6} "
                f"{_num(r['value_per_play']):>6} {_num(r['value_per_provision']):>6} "
                f"{r['uses']:>5}"
            )
        return lines


def _rate(points: int, games: int) -> float | None:
    return points / (2 * games) if games else None


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{100 * value:.1f}%"


def _pp(value: float | None) -> str:
    return "-" if value is None else f"{100 * value:+.1f}"


def _num(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


__all__ = ["BalanceReport", "CardStats", "DeckStats", "MatchTrace", "Tracer"]
