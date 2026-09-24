from pathlib import Path

import pytest
import yaml

from opengwt.core.engine import check_deck
from opengwt.core.model import (
    PHASE_C_ACTIONS,
    PHASE_C_TRIGGERS,
    PHASE_C_UNITS,
    Kind,
    Rules,
    Status,
    phase_c_words,
)
from opengwt.data import DataError, DataSet, load_data
from opengwt.data.loader import (
    check_i18n,
    check_references,
    load_cards_file,
    load_deck,
    load_library,
)

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "docs" / "protocol" / "examples"


def test_real_data_loads(dataset: DataSet) -> None:
    assert len(dataset.library) >= 30
    assert {"starter-a", "starter-b"} <= set(dataset.decks)
    assert set(dataset.i18n) == {"en", "zh-CN", "ru"}
    for deck in dataset.decks.values():
        assert check_deck(dataset.library, deck, Rules()) == []


def test_the_starter_decks_exercise_every_phase_c_word(dataset: DataSet) -> None:
    """ADR 0009 phase C: the starter decks, which the simulator and CI play, use every word phase
    C gave behaviour to, and activated abilities with charges, cooldowns and ready on play."""
    lib = dataset.library
    in_play = {
        cid
        for deck in (dataset.decks["starter-a"], dataset.decks["starter-b"])
        for cid in (*deck.cards, deck.leader, deck.stratagem)
    }
    used = {word for cid in in_play for word in phase_c_words(lib[cid])}
    assert used == {
        "card:activation",
        *(f"when:{t.value}" for t in PHASE_C_TRIGGERS),
        *(f"do:{a.value}" for a in PHASE_C_ACTIONS),
        *(f"units:{u.value}" for u in PHASE_C_UNITS),
        "row_target:chosen",
        "cards:chosen",
        "if:trigger_unit",
    }
    orders = [lib[cid] for cid in in_play if lib[cid].activation is not None]
    assert {d.kind for d in orders} >= {Kind.UNIT, Kind.ARTIFACT, Kind.LEADER, Kind.STRATAGEM}
    activations = [d.activation for d in orders if d.activation is not None]
    assert any(a.cooldown > 0 and a.charges is None for a in activations)
    assert any(a.ready_on_play for a in activations)
    assert any(a.charges is not None and a.charges > 1 for a in activations)


def test_protocol_examples_load() -> None:
    """The whole v2 vocabulary loads."""
    lib = load_library(EXAMPLES)
    assert lib["u-0029"].statuses == (Status.GUARDING,)
    assert phase_c_words(lib["u-0007"]) == ["card:activation", "when:on_activate"]
    assert phase_c_words(lib["g-0101"]) == []
    deck = load_deck(EXAMPLES / "starter-a.deck.yaml", lib)
    assert deck.leader == "l-0001" and deck.stratagem == "g-0101" and len(deck.cards) == 28
    assert check_deck(lib, deck, Rules()) == []


def test_schema_violation_is_reported_with_path(tmp_path: Path) -> None:
    bad = tmp_path / "x.cards.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "schema": "opengwt.cards/2",
                "faction": "test-x",
                "cards": {"u-1": {"kind": "unit", "color": "bronze", "provisions": 4}},
            }
        )
    )
    with pytest.raises(DataError) as info:
        load_cards_file(bad)
    assert any("u-1" in p and "power" in p for p in info.value.problems)


def test_v1_files_are_rejected(tmp_path: Path) -> None:
    old = tmp_path / "x.cards.yaml"
    old.write_text(
        yaml.safe_dump(
            {
                "schema": "opengwt.cards/1",
                "faction": "test-x",
                "cards": {"u-1": {"kind": "unit", "rows": ["siege"], "power": 3}},
            }
        )
    )
    with pytest.raises(DataError):
        load_cards_file(old)


def test_deck_with_foreign_card_is_rejected(dataset: DataSet, tmp_path: Path) -> None:
    deck = tmp_path / "x.deck.yaml"
    deck.write_text(
        yaml.safe_dump(
            {
                "schema": "opengwt.deck/2",
                "id": "test-x",
                "faction": "placeholder-a",
                "leader": "l-1001",
                "stratagem": "g-0001",
                "cards": [{"id": "u-2001", "count": 1}],
            }
        )
    )
    with pytest.raises(DataError) as info:
        load_deck(deck, dataset.library)
    assert any("belongs to placeholder-b" in p for p in info.value.problems)


def test_i18n_completeness_reports_missing_keys(dataset: DataSet) -> None:
    tables = {loc: dict(t) for loc, t in dataset.i18n.items()}
    del tables["ru"]["card.u-1001.name"]
    del tables["en"]["card.u-2001.text"]
    del tables["en"]["tag.tag-a.name"]
    problems = check_i18n(dataset.library, tables)
    assert "ru: card.u-1001.name" in problems
    assert "en: card.u-2001.text" in problems
    assert "en: tag.tag-a.name" in problems


def test_place_new_card_must_name_a_unit_or_artifact(dataset: DataSet) -> None:
    from dataclasses import replace

    lib = dict(dataset.library)
    maker = lib["u-2009"]
    lib["u-2009"] = replace(
        maker, abilities=tuple(replace(a, card="s-2001") for a in maker.abilities)
    )
    assert check_references(lib) == ["u-2009: place_new_card names s-2001, not a unit or artifact"]
    assert check_references(dataset.library) == []


def test_load_data_rejects_broken_tree(tmp_path: Path) -> None:
    (tmp_path / "cards").mkdir()
    with pytest.raises(DataError):
        load_data(tmp_path)
