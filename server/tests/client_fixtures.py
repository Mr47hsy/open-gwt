"""Protocol 2 fixtures for the Unity client's parsing tests (docs/protocol/match.md §7, §8).

What the server sends each seat, produced by the rules core itself rather than written by hand:
for every replay scenario under ``tests/replays/scenarios/`` and for the golden random match,
the ``events`` batch each seat receives after every accepted intent, and — at the steps worth
looking at — the ``view`` of each seat. The client's EditMode tests read these files, so its
models are proven against what the core really emits.

Regenerate from ``server/`` with ``uv run python -m tests.client_fixtures``;
``test_client_fixtures.py`` fails while the files on disk are stale. The fixtures follow the
core: a phase that changes the rules regenerates the golden and these with it.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from opengwt.core.engine import apply, new_match
from opengwt.core.events import Event, event_for_seat, event_to_dict
from opengwt.core.intents import Intent, intent_to_dict
from opengwt.core.model import Library, MatchState, Phase
from opengwt.core.replay import MatchRecord, record_from_dict
from opengwt.core.view import player_view
from opengwt.data import load_data
from tests.scenario import load_scenario, play_scenario, scenario_paths

REPO = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).parent / "replays" / "random-vs-random-seed-1.json"
DEFAULT_OUT = REPO / "client" / "Assets" / "OpenGwt" / "Tests" / "EditMode" / "Fixtures"
MATCH_ID = "fixture"
SEATS = (0, 1)

# A step whose events include one of these keeps both seats' views, and a step that asks a choice
# keeps the chooser's; every other step keeps its events only, which is what the client
# animates. The first and the last step always keep both views.
VIEW_WORTHY = frozenset({"mulligan_started", "match_ended"})


def _views(lib: Library, state: MatchState, seats: tuple[int, ...] = SEATS) -> dict[str, Any]:
    return {str(seat): player_view(lib, state, seat, MATCH_ID) for seat in seats}


def _step(seat: int | None, intent: Intent | None, events: list[Event]) -> dict[str, Any]:
    return {
        "seat": seat,
        "intent": None if intent is None else intent_to_dict(intent),
        "events": {str(s): [event_to_dict(event_for_seat(e, s)) for e in events] for s in SEATS},
    }


def steps(lib: Library, record: MatchRecord) -> list[dict[str, Any]]:
    """The record replayed one intent at a time: what each seat receives after each."""
    state, events = new_match(lib, record.decks, record.seed, record.rules, check_legality=False)
    first = _step(None, None, events)
    first["views"] = _views(lib, state)
    out = [first]
    for seat, intent in record.intents:
        state, events = apply(lib, state, seat, intent)
        step = _step(seat, intent, events)
        if any(e.type in VIEW_WORTHY for e in events) or state.phase is Phase.MATCH_OVER:
            step["views"] = _views(lib, state)
        elif state.pending is not None:
            step["views"] = _views(lib, state, (state.pending.seat,))
        out.append(step)
    out[-1].setdefault("views", _views(lib, state))
    return out


def _dump(doc: dict[str, Any]) -> str:
    """One line per step: readable in a diff, a third of the size of an indented dump."""
    steps_text = ",\n  ".join(
        json.dumps(step, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for step in doc["steps"]
    )
    return '{"source": ' + json.dumps(doc["source"]) + ',\n "steps": [\n  ' + steps_text + "\n ]}\n"


def build() -> dict[str, str]:
    """Every fixture file by name, as JSON text."""
    files: dict[str, str] = {}
    for path in scenario_paths():
        played = play_scenario(load_scenario(path))
        source = str(path.relative_to(REPO))
        files[path.stem + ".json"] = _dump(
            {"source": source, "steps": steps(played.lib, played.record)}
        )
    lib = load_data(REPO / "data").library
    record = record_from_dict(json.loads(GOLDEN.read_text(encoding="utf-8"))["record"])
    files["golden-random-match.json"] = _dump(
        {"source": str(GOLDEN.relative_to(REPO)), "steps": steps(lib, record)}
    )
    return files


def write(out: Path) -> list[Path]:
    """Write the fixtures, removing fixture files that are no longer built."""
    out.mkdir(parents=True, exist_ok=True)
    files = build()
    written: list[Path] = []
    for name, text in files.items():
        target = out / name
        target.write_text(text, encoding="utf-8")
        written.append(target)
    for stale in out.glob("*.json"):
        if stale.name not in files:
            stale.unlink()
            meta = stale.with_name(stale.name + ".meta")
            if meta.exists():
                meta.unlink()
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.client_fixtures", description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="directory to write into")
    args = parser.parse_args(argv)
    for path in write(args.out):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
