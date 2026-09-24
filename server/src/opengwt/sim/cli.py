"""``opengwt-sim``: run bot-versus-bot matches, verify replay determinism, and report how much
each card contributes to winning (``opengwt.sim.balance``)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from collections.abc import Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from opengwt.bots import BOT_NAMES, Bot, make_bot
from opengwt.core.engine import acting_seat, apply, legal_intents, new_match
from opengwt.core.intents import Intent
from opengwt.core.model import Deck, Library, MatchState, Phase
from opengwt.core.replay import MatchRecord, record_to_dict, replay
from opengwt.core.rng import Stream, seed_from_int
from opengwt.core.serialize import state_hash
from opengwt.data import DataError, load_data
from opengwt.sim.balance import BalanceReport, MatchTrace, Tracer

SIM_BOT_LABEL = b"opengwt/sim-bot"


def sim_bot(name: str, bot_seed: int, worlds: int | None = None, width: int | None = None) -> Bot:
    """A simulator bot on its own stream; the simulator keeps integer seeds (ADR 0010)."""
    return make_bot(name, Stream(seed_from_int(bot_seed), SIM_BOT_LABEL), worlds, width)


def run_match(
    lib: Library,
    decks: tuple[Deck, Deck],
    seed: str,
    bots: tuple[Bot, Bot],
    max_steps: int = 2000,
    trace: MatchTrace | None = None,
) -> tuple[MatchRecord, MatchState, int]:
    """Play one match between two bots. ``seed`` is the match seed, 64 hex characters. With a
    ``trace``, record what the balance report needs as the match goes."""
    state, events = new_match(lib, decks, seed)
    tracer = Tracer(lib, trace) if trace is not None else None
    if tracer is not None:
        tracer.after(state, events)
    intents: list[tuple[int, Intent]] = []
    while state.phase is not Phase.MATCH_OVER:
        seat = acting_seat(state)
        if seat is None:
            raise RuntimeError("nobody to act although the match is not over")
        legal = legal_intents(lib, state, seat)
        intent = bots[seat].choose(lib, state, seat, legal)
        if tracer is not None:
            tracer.before(state, seat, intent)
        state, events = apply(lib, state, seat, intent)
        if tracer is not None:
            tracer.after(state, events)
        intents.append((seat, intent))
        if len(intents) > max_steps:
            raise RuntimeError(f"match did not finish within {max_steps} intents")
    return MatchRecord(seed, decks, tuple(intents)), state, len(intents)


@dataclass(frozen=True)
class Job:
    """One match: its number (which gives its seed and its bots' seeds) and its decks by seat."""

    number: int
    decks: tuple[str, str]
    bots: tuple[str, str]
    worlds: int | None
    width: int | None
    max_steps: int
    keep_record: bool


@dataclass
class Outcome:
    job: Job
    error: str | None = None
    winner: int | None = None
    starter: int = 0
    rounds: int = 0
    steps: int = 0
    record: MatchRecord | None = None
    final_hash: str | None = None
    trace: MatchTrace | None = None


_WORKER: tuple[Library, dict[str, Deck]] | None = None


def _init_worker(data_dir: str) -> None:
    global _WORKER
    data = load_data(Path(data_dir))
    _WORKER = (data.library, data.decks)


def _run_job(job: Job) -> Outcome:
    assert _WORKER is not None
    lib, decks = _WORKER
    return play_job(lib, decks, job)


def play_job(lib: Library, decks: dict[str, Deck], job: Job) -> Outcome:
    n = job.number
    bots = (
        sim_bot(job.bots[0], n * 2 + 1, job.worlds, job.width),
        sim_bot(job.bots[1], n * 2 + 2, job.worlds, job.width),
    )
    trace = MatchTrace()
    pair = (decks[job.decks[0]], decks[job.decks[1]])
    try:
        record, final, steps = run_match(lib, pair, seed_from_int(n), bots, job.max_steps, trace)
    except Exception:
        return Outcome(job, error=traceback.format_exc())
    return Outcome(
        job,
        winner=final.winner,
        starter=trace.starter if trace.starter is not None else final.starter,
        rounds=len(final.rounds),
        steps=steps,
        record=record if job.keep_record else None,
        final_hash=state_hash(final) if job.keep_record else None,
        trace=trace,
    )


def _find_data(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    here = Path.cwd()
    for candidate in (here / "data", here.parent / "data"):
        if (candidate / "cards").is_dir():
            return candidate
    raise SystemExit("cannot find data/; pass --data")


def _jobs(args: argparse.Namespace, deck_ids: list[str]) -> list[Job]:
    """``--matches`` per pairing. One pairing is ``--deck-a`` against ``--deck-b``; ``--decks``
    makes every pairing of the decks it lists, mirrors with ``--mirrors``. The decks swap seats
    every other match with ``--swap-seats`` and always with ``--decks``."""
    if args.decks:
        pairs = list(combinations(deck_ids, 2))
        if args.mirrors:
            pairs += [(d, d) for d in deck_ids]
    else:
        pairs = [(args.deck_a, args.deck_b)]
    swap = bool(args.swap_seats or args.decks)
    keep = max(args.replay_check, 1 if args.write_record else 0)
    jobs: list[Job] = []
    number = args.seed
    for a, b in pairs:
        for i in range(args.matches):
            decks = (b, a) if swap and i % 2 else (a, b)
            jobs.append(
                Job(
                    number,
                    decks,
                    (args.bot_a, args.bot_b),
                    args.search_worlds,
                    args.search_width,
                    args.max_steps,
                    len(jobs) < keep,
                )
            )
            number += 1
    return jobs


def _outcomes(
    jobs: list[Job], data_dir: Path, lib: Library, decks: dict[str, Deck], workers: int
) -> Iterator[Outcome]:
    """The outcomes in job order, played in ``workers`` processes (or here, for one)."""
    if workers <= 1:
        for job in jobs:
            yield play_job(lib, decks, job)
        return
    with ProcessPoolExecutor(workers, initializer=_init_worker, initargs=(str(data_dir),)) as pool:
        yield from pool.map(_run_job, jobs, chunksize=max(1, len(jobs) // (workers * 8)))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opengwt-sim", description=__doc__)
    parser.add_argument("--matches", type=int, default=100, help="matches per pairing of decks")
    parser.add_argument(
        "--seed", type=int, default=1, help="number of the first match; its seed is derived from it"
    )
    parser.add_argument("--bot-a", choices=BOT_NAMES, default="greedy")
    parser.add_argument("--bot-b", choices=BOT_NAMES, default="random")
    parser.add_argument("--deck-a", default="starter-a")
    parser.add_argument("--deck-b", default="starter-b")
    parser.add_argument(
        "--decks", help="comma-separated deck ids, or `all`: play every pairing of them"
    )
    parser.add_argument("--mirrors", action="store_true", help="with --decks, also each mirror")
    parser.add_argument(
        "--swap-seats", action="store_true", help="swap the decks' seats every other match"
    )
    parser.add_argument("--search-worlds", type=int, help="worlds the search bot samples")
    parser.add_argument("--search-width", type=int, help="candidates the search bot plays out")
    parser.add_argument("--jobs", type=int, default=1, help="processes; 0 for one per CPU")
    parser.add_argument("--data", help="path to the data/ directory")
    parser.add_argument("--replay-check", type=int, default=0, help="replay the first N records")
    parser.add_argument("--write-record", help="write the first record and its final hash as JSON")
    parser.add_argument("--max-steps", type=int, default=2000)
    parser.add_argument(
        "--card-report", action="store_true", help="print each card's win-rate contribution"
    )
    parser.add_argument("--report", help="write the balance report to a .json or .csv file")
    args = parser.parse_args(argv)
    if args.report and not args.report.endswith((".json", ".csv")):
        parser.error("--report must name a .json or .csv file")

    data_dir = _find_data(args.data)
    try:
        data = load_data(data_dir)
    except DataError as e:
        print("data problems:", file=sys.stderr)
        for p in e.problems:
            print("  " + p, file=sys.stderr)
        return 2
    lib = data.library
    deck_ids = sorted(data.decks) if args.decks == "all" else (args.decks or "").split(",")
    deck_ids = [d.strip() for d in deck_ids if d.strip()]
    unknown = [d for d in [*deck_ids, args.deck_a, args.deck_b] if d not in data.decks]
    if unknown:
        print(f"unknown decks: {', '.join(unknown)}", file=sys.stderr)
        return 2
    jobs = _jobs(args, deck_ids)
    workers = args.jobs if args.jobs > 0 else (os.cpu_count() or 1)

    wins = [0, 0]
    draws = errors = total_rounds = total_steps = 0
    records: list[tuple[MatchRecord, str]] = []
    report = BalanceReport()
    started = time.perf_counter()
    for outcome in _outcomes(jobs, data_dir, lib, data.decks, workers):
        if outcome.error is not None:
            errors += 1
            if errors <= 3:
                print(f"match seed={outcome.job.number} failed:", file=sys.stderr)
                print(outcome.error, file=sys.stderr)
            continue
        if outcome.winner is None:
            draws += 1
        else:
            wins[outcome.winner] += 1
        total_rounds += outcome.rounds
        total_steps += outcome.steps
        if outcome.record is not None and outcome.final_hash is not None:
            records.append((outcome.record, outcome.final_hash))
        if outcome.trace is not None:
            job = outcome.job
            pair = (data.decks[job.decks[0]], data.decks[job.decks[1]])
            report.add(job.decks, pair, outcome.winner, outcome.starter, outcome.trace)
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

    if args.card_report:
        for line in report.table(lib, data.decks):
            print(line)
    if args.report:
        meta = {
            "matches": len(jobs),
            "bots": [args.bot_a, args.bot_b],
            "first_seed": args.seed,
            "errors": errors,
        }
        text = (
            report.to_json(lib, data.decks, meta)
            if args.report.endswith(".json")
            else report.to_csv(lib, data.decks)
        )
        Path(args.report).write_text(text, encoding="utf-8")

    total = len(jobs)
    finished = total - errors
    swapped = bool(args.decks or args.swap_seats)
    label_a = args.bot_a if swapped else f"{args.bot_a}/{args.deck_a}"
    label_b = args.bot_b if swapped else f"{args.bot_b}/{args.deck_b}"
    print(
        f"matches={total} finished={finished} errors={errors} "
        f"wins[{label_a}]={wins[0]} wins[{label_b}]={wins[1]} "
        f"draws={draws} avg_rounds={total_rounds / finished if finished else 0:.2f} "
        f"avg_intents={total_steps / finished if finished else 0:.1f} "
        f"replay_checked={min(args.replay_check, len(records))} mismatches={mismatches} "
        f"time={elapsed:.1f}s"
    )
    return 1 if errors or mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
