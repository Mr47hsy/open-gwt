"""Every replay scenario under tests/replays/scenarios/ plays, replays identically and meets its
expectations — see tests/scenario.py for the file shape."""

from pathlib import Path

import pytest

from tests.scenario import check_scenario, load_scenario, play_scenario, scenario_paths


@pytest.mark.parametrize("path", scenario_paths(), ids=lambda p: p.stem)
def test_scenario(path: Path) -> None:
    spec = load_scenario(path)
    check_scenario(spec, play_scenario(spec))
