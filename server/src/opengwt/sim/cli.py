"""``opengwt-sim``: run bot-versus-bot matches and verify replay determinism."""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections.abc import Sequence
from pathlib import Path

from opengwt.bots import BOT_NAMES, Bot, make_bot
from opengwt.core.engine import acting_seat, apply, legal_intents, new_match
from opengwt.core.intents import Intent
from opengwt.core.model import Deck, Library, MatchState, Phase
from opengwt.core.replay import MatchRecord, record_to_dict, replay
from opengwt.core.serialize import state_hash
from opengwt.data import DataError, load_data


def run_match(
    lib: Library,
    decks: tuple[Deck, Deck],
    seed: int,
    bots: tuple[Bot, Bot],
    max_steps: int = 2000,
) -> tuple[MatchRecord, MatchState, int]:
    state, _ = new_match(lib, decks, seed)
    intents: list[tuple[int, Intent]] = []
    while state.phase is not Phase.MATCH_OVER:
        seat = acting_seat(state)
        if seat is None:
            raise RuntimeError("nobody to act although the match is not over")
        legal = legal_intents(lib, state, seat)
        intent = bots[seat].choose(lib, state, seat, legal)
        state, _ = apply(lib, state, seat, intent)
        intents.append((seat, intent))
        if len(intents) > max_steps:
            raise RuntimeError(f"match did not finish within {max_steps} intents")
    return MatchRecord(seed, decks, tuple(intents)), state, len(intents)


def _find_data(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    here = Path.cwd()
    for candidate in (here / "data", here.parent / "data"):
        if (candidate / "cards").is_dir():
            return candidate
    raise SystemExit("cannot find data/; pass --data")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opengwt-sim", description=__doc__)
    parser.add_argument("--matches", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1, help="seed of the first match")
    parser.add_argument("--bot-a", choices=BOT_NAMES, default="greedy")
    parser.add_argument("--bot-b", choices=BOT_NAMES, default="random")
    parser.add_argument("--deck-a", default="starter-a")
    parser.add_argument("--deck-b", default="starter-b")
    parser.add_argument("--data", help="path to the data/ directory")
    parser.add_argument("--replay-check", type=int, default=0, help="replay the first N records")
    parser.add_argument("--write-record", help="write the first record and its final hash as JSON")
    parser.add_argument("--max-steps", type=int, default=2000)
    args = parser.parse_args(argv)

    try:
        data = load_data(_find_data(args.data))
    except DataError as e:
        print("data problems:", file=sys.stderr)
        for p in e.problems:
            print("  " + p, file=sys.stderr)
        return 2
    lib = data.library
    decks = (data.decks[args.deck_a], data.decks[args.deck_b])

    wins = [0, 0]
    draws = errors = total_rounds = total_steps = 0
    records: list[tuple[MatchRecord, str]] = []
    started = time.perf_counter()
    for i in range(args.matches):
        seed = args.seed + i
        bots = (make_bot(args.bot_a, seed * 2 + 1), make_bot(args.bot_b, seed * 2 + 2))
        try:
            record, final, steps = run_match(lib, decks, seed, bots, args.max_steps)
        except Exception:
            errors += 1
            if errors <= 3:
                print(f"match seed={seed} failed:", file=sys.stderr)
                traceback.print_exc()
            continue
        if final.winner is None:
            draws += 1
        else:
            wins[final.winner] += 1
        total_rounds += len(final.rounds)
        total_steps += steps
        if len(records) < max(args.replay_check, 1 if args.write_record else 0):
            records.append((record, state_hash(final)))
    elapsed = time.perf_counter() - started

    mismatches = 0
    for record, expected in records[: args.replay_check]:
        again, _ = replay(lib, record)
        if state_hash(again) != expected:
            mismatches += 1
            print(f"replay mismatch for seed={record.seed}", file=sys.stderr)

    if args.write_record and records:
        record, expected = records[0]
        Path(args.write_record).write_text(
            json.dumps({"record": record_to_dict(record), "final_hash": expected}, indent=1)
        )

    finished = args.matches - errors
    print(
        f"matches={args.matches} finished={finished} errors={errors} "
        f"wins[{args.bot_a}/{args.deck_a}]={wins[0]} wins[{args.bot_b}/{args.deck_b}]={wins[1]} "
        f"draws={draws} avg_rounds={total_rounds / finished if finished else 0:.2f} "
        f"avg_intents={total_steps / finished if finished else 0:.1f} "
        f"replay_checked={min(args.replay_check, len(records))} mismatches={mismatches} "
        f"time={elapsed:.1f}s"
    )
    return 1 if errors or mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
