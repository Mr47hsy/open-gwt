from pathlib import Path

import pytest
import yaml

from opengwt.core.engine import check_deck
from opengwt.core.model import Deck, Kind, Rules
from opengwt.data import DataError, DataSet, load_data
from opengwt.data.loader import check_i18n, load_cards_file, load_deck

REPO = Path(__file__).resolve().parents[2]


def test_real_data_loads(dataset: DataSet) -> None:
    assert len(dataset.library) >= 30
    assert {"starter-a", "starter-b"} <= set(dataset.decks)
    assert set(dataset.i18n) == {"en", "zh-CN", "ru"}
    for deck in dataset.decks.values():
        assert check_deck(dataset.library, deck, Rules()) == []


def test_protocol_examples_load() -> None:
    examples = REPO / "docs" / "protocol" / "examples"
    lib = load_cards_file(examples / "placeholder-a.cards.yaml")
    assert lib["u-0002"].immune and lib["u-0002"].kind is Kind.UNIT
    deck = load_deck(examples / "starter-a.deck.yaml", lib)
    assert deck.leader == "l-0001" and len(deck.cards) == 22


def test_schema_violation_is_reported_with_path(tmp_path: Path) -> None:
    bad = tmp_path / "x.cards.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "schema": "opengwt.cards/1",
                "faction": "test-x",
                "cards": {"u-1": {"kind": "unit", "power": 3}},
            }
        )
    )
    with pytest.raises(DataError) as info:
        load_cards_file(bad)
    assert any("u-1" in p and "rows" in p for p in info.value.problems)


def test_deck_with_foreign_card_is_rejected(dataset: DataSet, tmp_path: Path) -> None:
    deck = tmp_path / "x.deck.yaml"
    deck.write_text(
        yaml.safe_dump(
            {
                "schema": "opengwt.deck/1",
                "id": "test-x",
                "faction": "placeholder-a",
                "cards": [{"id": "b-u-0001", "count": 1}],
            }
        )
    )
    with pytest.raises(DataError) as info:
        load_deck(deck, dataset.library)
    assert any("belongs to placeholder-b" in p for p in info.value.problems)


def test_i18n_completeness_reports_missing_keys(dataset: DataSet) -> None:
    tables = {loc: dict(t) for loc, t in dataset.i18n.items()}
    del tables["ru"]["card.a-u-0001.name"]
    del tables["en"]["card.b-u-0001.text"]
    problems = check_i18n(dataset.library, tables)
    assert "ru: card.a-u-0001.name" in problems
    assert "en: card.b-u-0001.text" in problems


def test_load_data_rejects_broken_tree(tmp_path: Path) -> None:
    (tmp_path / "cards").mkdir()
    with pytest.raises(DataError):
        load_data(tmp_path)


def test_check_deck_rules() -> None:
    from tests.helpers import make_library

    lib = make_library()
    deck = Deck("test", ("plain5",) * 21 + ("frost",) * 11, leader="plain5")
    problems = check_deck(lib, deck, Rules())
    assert "error.deck.too-few-units" in problems
    assert "error.deck.too-many-specials" in problems
    assert "error.deck.leader-not-leader:plain5" in problems
    assert check_deck(lib, Deck("test", ("plain5",) * 22, leader="leader-clear"), Rules()) == []
