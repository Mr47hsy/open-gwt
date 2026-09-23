from __future__ import annotations

from pathlib import Path

import pytest

from opengwt.core.model import Deck, Library
from opengwt.data import DataSet, load_data

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def dataset() -> DataSet:
    return load_data(REPO / "data")


@pytest.fixture(scope="session")
def library(dataset: DataSet) -> Library:
    return dataset.library


@pytest.fixture(scope="session")
def starter_decks(dataset: DataSet) -> tuple[Deck, Deck]:
    return dataset.decks["starter-a"], dataset.decks["starter-b"]
