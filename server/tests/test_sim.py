"""``opengwt-sim`` and its balance report: each card's win-rate contribution, the same whatever
the number of processes."""

import csv
import json
from pathlib import Path

import pytest

from opengwt.core.model import Deck, Library
from opengwt.core.rng import seed_from_int
from opengwt.sim.balance import BalanceReport, MatchTrace
from opengwt.sim.cli import main, run_match, sim_bot

REPO = Path(__file__).resolve().parents[2]
DATA = str(REPO / "data")


def test_a_trace_sees_every_draw_and_play(
    library: Library, starter_decks: tuple[Deck, Deck]
) -> None:
    trace = MatchTrace()
    bots = (sim_bot("greedy", 1), sim_bot("greedy", 2))
    _, final, _ = run_match(library, starter_decks, seed_from_int(2), bots, trace=trace)
    assert trace.starter in (0, 1)
    for seat in (0, 1):
        # round one alone draws ten, and a hand is played from
        assert len(trace.drawn[seat]) >= 8
        assert trace.played[seat] <= set(library)
    assert trace.plays and all(seat in (0, 1) for seat, _, _ in trace.plays)
    report = BalanceReport()
    report.add(("starter-a", "starter-b"), starter_decks, final.winner, trace.starter, trace)
    rows = report.rows(library, {"starter-a": starter_decks[0], "starter-b": starter_decks[1]})
    ids = {(r["deck"], r["card"]) for r in rows}
    assert ("starter-a", "u-1001") in ids and ("starter-b", starter_decks[1].leader) in ids
    assert all(r["games"] == 1 for r in rows)


def test_the_report_is_the_same_in_one_or_several_processes(tmp_path: Path) -> None:
    one, two = tmp_path / "one.json", tmp_path / "two.json"
    common = ["--matches", "6", "--bot-a", "greedy", "--bot-b", "greedy", "--data", DATA]
    assert main([*common, "--swap-seats", "--report", str(one)]) == 0
    assert main([*common, "--swap-seats", "--report", str(two), "--jobs", "2"]) == 0
    first, second = json.loads(one.read_text()), json.loads(two.read_text())
    assert first == second
    assert {d["deck"] for d in first["decks"]} == {"starter-a", "starter-b"}
    assert sum(d["games"] for d in first["decks"]) == 12
    card = next(r for r in first["cards"] if r["card"] == "u-1014")
    assert card["games"] == 6 and 0 <= card["drawn_rate"] <= 1
    assert card["plays"] == 0 or card["value_per_provision"] is not None


def test_a_csv_report_and_the_card_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "cards.csv"
    args = ["--matches", "4", "--bot-b", "greedy", "--data", DATA, "--card-report"]
    assert main([*args, "--report", str(path)]) == 0
    rows = list(csv.DictReader(path.read_text().splitlines()))
    assert rows and {"deck", "card", "contribution", "margin", "value_per_provision"} <= set(
        rows[0]
    )
    out = capsys.readouterr().out
    assert "deck starter-a: games=4" in out and "contrib" in out
    assert "wins[greedy/starter-a]=" in out  # the summary line CI reads is unchanged


def test_every_pairing_of_decks(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--decks", "all", "--mirrors", "--matches", "2", "--data", DATA]) == 0
    assert "matches=6 finished=6" in capsys.readouterr().out  # a-b, a-a, b-b


def test_the_search_bot_in_the_simulator(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["--bot-a", "search", "--bot-b", "greedy", "--matches", "1", "--data", DATA]
    assert main([*args, "--search-worlds", "1", "--search-width", "1", "--replay-check", "1"]) == 0
    assert "mismatches=0" in capsys.readouterr().out
