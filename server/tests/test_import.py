"""Card set import — docs/protocol/import.md: a designer's set becomes data/ files, validated as
the compiler validates data/ before anything is written, with stable ids across re-imports."""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from opengwt.core.rng import seed_from_int
from opengwt.data import load_data
from opengwt.data.cli import main
from opengwt.data.importer import CardSetError, import_cardset, plan_import, read_cardset
from opengwt.sim.cli import run_match, sim_bot

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "docs" / "protocol" / "examples"


@pytest.fixture
def data(tmp_path: Path) -> Path:
    copy = tmp_path / "data"
    shutil.copytree(REPO / "data", copy)
    return copy


def _set(tmp_path: Path, cards: list[dict], name: str = "set.yaml", **extra: object) -> Path:  # type: ignore[type-arg]
    path = tmp_path / name
    doc = {"schema": "opengwt.cardset/1", "set": "test-set", "cards": cards, **extra}
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _unit(key: str, faction: str = "test-f", **fields: object) -> dict:  # type: ignore[type-arg]
    return {
        "key": key,
        "faction": faction,
        "kind": "unit",
        "color": "bronze",
        "provisions": 4,
        "power": 3,
        "name": {"en": f"Test {key}"},
        **fields,
    }


def test_the_example_set_imports_compiles_and_plays(data: Path) -> None:
    plan = import_cardset(EXAMPLES / "cardset.yaml", data)
    assert plan.problems == []
    dataset = load_data(data)
    lib = dataset.library
    assert lib["u-3001"].faction == "sample-c"
    assert lib["u-3010"].abilities[0].card == "t-3001"  # a key resolved to its id
    deck = dataset.decks["sample-c-starter"]
    assert (deck.leader, deck.stratagem, len(deck.cards)) == ("l-3001", "g-3001", 25)
    # names: given, or stubbed from the base locale and marked
    ru = (data / "i18n" / "ru" / "sample-c.cards.yaml").read_text(encoding="utf-8")
    assert 'card.u-3001.name: "Образец C: солдат"\n' in ru
    assert 'card.u-3004.name: "Sample C healer"  # TODO(i18n): translate' in ru
    assert 'tag.sample-tag.name: "Sample tag"  # TODO(i18n): translate' in ru
    assert plan.stubs == {"en": 0, "ru": 2, "zh-CN": 1}
    # texts: explicit where the set gives one, generated elsewhere
    assert dataset.i18n["en"]["card.s-3002.text"] == "Boost every allied unit by 1."
    assert dataset.i18n["ru"]["card.s-3002.text"] == "Усиливает все союзные отряды на 1."
    assert dataset.i18n["en"]["card.u-3002.text"] == (
        "Ranged row only. When played: Deal 2 damage to an enemy unit."
    )
    # and the imported deck plays
    bots = (sim_bot("greedy", 1), sim_bot("random", 2))
    decks = (deck, dataset.decks["starter-a"])
    _, final, _ = run_match(lib, decks, seed_from_int(7), bots)
    assert final.rounds


def test_a_reimport_keeps_every_id(data: Path, tmp_path: Path) -> None:
    first = import_cardset(_set(tmp_path, [_unit("alpha"), _unit("beta")]), data)
    assert first.problems == [] and first.ids == {"alpha": "u-3001", "beta": "u-3002"}
    again = _set(tmp_path, [_unit("gamma"), _unit("beta"), _unit("alpha")])
    second = import_cardset(again, data)
    assert second.problems == []
    assert second.ids == {"gamma": "u-3003", "beta": "u-3002", "alpha": "u-3001"}
    assert second.new_ids == {"gamma": "u-3003"}


def test_explicit_ids_and_the_id_start_are_honoured(data: Path, tmp_path: Path) -> None:
    cards = [_unit("alpha", id="u-7777"), _unit("beta"), {**_unit("gamma"), "kind": "special"}]
    del cards[2]["power"]
    cards[2]["abilities"] = [{"when": "on_play", "do": "draw", "count": 1}]
    plan = import_cardset(_set(tmp_path, cards), data, id_start=5001)
    assert plan.problems == []
    assert plan.ids == {"alpha": "u-7777", "beta": "u-5001", "gamma": "s-5001"}


def test_a_csv_alone_imports_with_a_set_id(data: Path) -> None:
    with pytest.raises(CardSetError):
        read_cardset(EXAMPLES / "cardset.csv")
    plan = import_cardset(EXAMPLES / "cardset.csv", data, set_id="sample-c")
    assert plan.problems == [] and plan.decks == []
    en = (data / "i18n" / "en" / "sample-c.cards.yaml").read_text(encoding="utf-8")
    assert 'faction.sample-c.name: "TODO sample-c"  # TODO(i18n): translate' in en


def test_yaml_json_and_csv_give_the_same_files(data: Path, tmp_path: Path) -> None:
    from_csv = read_cardset(EXAMPLES / "cardset.csv", set_id="sample-c")
    cards = [
        {
            "key": e.key,
            "faction": e.faction,
            **e.fields,
            "name": e.names,
            **({"text": e.texts} if e.texts else {}),
        }
        for e in from_csv.cards
    ]
    as_yaml = _set(tmp_path, cards, "cards.yaml", set="sample-c")
    as_json = tmp_path / "cards.json"
    as_json.write_text(json.dumps(yaml.safe_load(as_yaml.read_text(encoding="utf-8"))))
    plans = [
        plan_import(read_cardset(path, "sample-c"), data)
        for path in (EXAMPLES / "cardset.csv", as_yaml, as_json)
    ]

    def body(text: str) -> str:
        return text.split("\n", 1)[1]  # the header names the source file

    files = [
        {k: body(v) for k, v in p.writes.items() if not k.startswith("import/")} for p in plans
    ]
    assert files[0] == files[1] == files[2]


def test_a_schema_problem_names_the_key_and_writes_nothing(data: Path, tmp_path: Path) -> None:
    bad = _unit("broken")
    del bad["power"]
    plan = import_cardset(_set(tmp_path, [_unit("fine"), bad]), data)
    assert any("power" in p and "[key broken]" in p for p in plan.problems), plan.problems
    assert not (data / "cards" / "test-f.cards.yaml").exists()
    assert not (data / "import").exists()


def test_cross_file_rules_stop_the_import(data: Path, tmp_path: Path) -> None:
    maker = _unit(
        "maker",
        abilities=[{"when": "on_play", "do": "place_new_card", "card": "nobody", "count": 1}],
    )
    plan = import_cardset(_set(tmp_path, [maker]), data)
    assert any("place_new_card names unknown card nobody" in p for p in plan.problems)
    deck = {
        "id": "test-deck",
        "faction": "test-f",
        "leader": "l-1001",
        "stratagem": "g-0001",
        "cards": {"alpha": 25},
    }
    plan = import_cardset(_set(tmp_path, [_unit("alpha")], decks=[deck]), data)
    assert any(
        "l-1001 belongs to placeholder-a" in p or "wrong-faction" in p for p in plan.problems
    )
    assert not (data / "decks" / "test-deck.deck.yaml").exists()


def test_files_the_set_did_not_write_need_replace(data: Path, tmp_path: Path) -> None:
    source = _set(tmp_path, [_unit("alpha", faction="neutral")])
    plan = import_cardset(source, data)
    assert any("pass --replace" in p for p in plan.problems)
    # replacing the neutral cards breaks the starter decks that use them: still nothing written
    plan = import_cardset(source, data, replace=True)
    assert any("unknown" in p for p in plan.problems), plan.problems
    assert "u-3001" not in (data / "cards" / "neutral.cards.yaml").read_text(encoding="utf-8")


def test_a_faction_dropped_from_the_set_loses_its_file(data: Path, tmp_path: Path) -> None:
    both = [_unit("alpha"), _unit("beta", faction="test-g")]
    assert import_cardset(_set(tmp_path, both), data).problems == []
    assert (data / "cards" / "test-g.cards.yaml").exists()
    plan = import_cardset(_set(tmp_path, [_unit("alpha")]), data)
    assert plan.problems == [] and plan.deletes == ["cards/test-g.cards.yaml"]
    assert not (data / "cards" / "test-g.cards.yaml").exists()
    load_data(data)


def test_a_name_another_file_holds_is_left_there(data: Path, tmp_path: Path) -> None:
    source = _set(
        tmp_path,
        [_unit("alpha", faction="neutral", id="u-0901")],
        factions={"neutral": {"name": {"en": "Another neutral"}}},
    )
    plan = plan_import(read_cardset(source), data, replace=False)
    en = plan.writes["i18n/en/test-set.cards.yaml"]
    assert "faction.neutral.name" not in en
    assert any("faction.neutral.name is already in" in w for w in plan.warnings)


def test_csv_problems_name_their_row(tmp_path: Path) -> None:
    path = tmp_path / "cards.csv"
    path.write_text(
        "key,faction,kind,powr,provisions,abilities\n"
        "a,test-f,unit,3,four,\n"
        'b,test-f,unit,3,4,"[{when: on_play, do: [}"\n',
        encoding="utf-8",
    )
    with pytest.raises(CardSetError) as info:
        read_cardset(path, "test-set")
    problems = "\n".join(info.value.problems)
    assert "unknown column 'powr'" in problems
    assert "row 2: provisions must be an integer" in problems
    assert "row 3: abilities is not YAML or JSON" in problems


def test_a_name_in_an_unknown_locale_is_refused(data: Path, tmp_path: Path) -> None:
    plan = import_cardset(_set(tmp_path, [_unit("alpha", name={"en": "A", "zh": "甲"})]), data)
    assert any("name in 'zh', which is not one of en, ru, zh-CN" in p for p in plan.problems)


def test_ids_with_a_trailing_newline_are_refused(tmp_path: Path) -> None:
    """`$` matches before a final newline; ids are matched whole, or a file name would get one."""
    deck = {"id": "odd\n", "faction": "test-f", "leader": "x", "stratagem": "y", "cards": {"a": 1}}
    with pytest.raises(CardSetError) as info:
        read_cardset(_set(tmp_path, [_unit("a", id="u-1\n")], decks=[deck]))
    problems = "\n".join(info.value.problems)
    assert "id 'u-1\\n' must match" in problems
    assert "deck id 'odd\\n' must match" in problems


def test_duplicate_keys_are_refused(tmp_path: Path) -> None:
    with pytest.raises(CardSetError) as info:
        read_cardset(_set(tmp_path, [_unit("alpha"), _unit("alpha")]))
    assert any("key 'alpha' also used" in p for p in info.value.problems)


def test_the_import_command(data: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = str(EXAMPLES / "cardset.yaml")
    assert main(["import", source, "--data", str(data), "--dry-run"]) == 0
    assert not (data / "cards" / "sample-c.cards.yaml").exists()
    out = capsys.readouterr().out
    assert "sc-soldier → u-3001" in out and "dry run" in out
    assert main(["import", source, "--data", str(data), "--preview", "en"]) == 0
    assert "u-3002 Sample C archer: Ranged row only." in capsys.readouterr().out
    assert (data / "import" / "sample-c.yaml").exists()
