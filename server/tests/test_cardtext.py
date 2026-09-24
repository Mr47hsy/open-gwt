"""Generated card text — docs/protocol/i18n.md §10: every card of data/ and of the protocol
examples gets a text in every locale from the ability templates, an explicit text wins, and a
locale lacking one gets its own generated text."""

import shutil
from pathlib import Path

import pytest
import yaml

from opengwt.core.model import Library, card_def_from_mapping
from opengwt.data import DataSet, load_data
from opengwt.data.cardtext import CardText, check_templates, fill_card_texts
from opengwt.data.loader import load_i18n, load_library

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
EXAMPLES = REPO / "docs" / "protocol" / "examples"
LOCALES = ("en", "ru", "zh-CN")


@pytest.fixture(scope="module")
def tables() -> dict[str, dict[str, str]]:
    return load_i18n(DATA / "i18n")


@pytest.fixture(scope="module")
def generator(tables: dict[str, dict[str, str]]) -> CardText:
    return CardText(tables)


def _every_card() -> Library:
    return {**load_library(DATA / "cards"), **load_library(EXAMPLES)}


@pytest.mark.parametrize("locale", LOCALES)
def test_every_card_renders_in_every_locale(generator: CardText, locale: str) -> None:
    """The placeholder set and the protocol examples use every word of the vocabulary."""
    for cid, defn in _every_card().items():
        text, missing = generator.text(locale, defn)
        assert missing == [], (cid, missing)
        assert "{" not in text and "}" not in text, (cid, text)
        assert "ability." not in text, (cid, text)
        if defn.abilities or defn.statuses or defn.armor:
            assert text, cid


def test_the_templates_render_whole_sentences(generator: CardText, library: Library) -> None:
    def text(locale: str, cid: str) -> str:
        return generator.text(locale, library[cid])[0]

    assert text("en", "u-1007") == (
        "When played: If it is on the melee row: Give itself 2 armour. "
        "If it is on the ranged row: Deal 1 damage to 2 random enemy units."
    )
    assert text("en", "l-1001") == (
        "Adds 15 to the provision budget. Activate, 2 charges: Boost an allied unit by 2."
    )
    assert text("en", "u-1019") == (
        "Activate, 2 charges: Give all allied units on a row of your choice 1 armour. "
        "Its ability can be used on the turn it is played."
    )
    assert text("en", "g-0002") == (
        "Starts on the ranged row. Activate once: "
        "Place 2 new copies of Placeholder N token 1 next to it."
    )
    assert text("en", "s-1004") == "Play one of 3 random units (4 power or less) from your deck."
    assert text("zh-CN", "u-2003") == "打出时：使一个敌方单位流血3回合。"  # noqa: RUF001
    assert text("zh-CN", "s-0001") == "从你的手牌中弃掉2张随机牌。抽2张牌。"
    assert text("ru", "u-2018") == (
        "При розыгрыше: Блокирует вражеский отряд (отряд или артефакт). "
        "Наносит той же цели 2 урона."
    )


def test_russian_puts_the_recipient_in_the_dative(generator: CardText, library: Library) -> None:
    """Damage goes to the recipient twin; a boost names its object."""
    assert generator.text("ru", library["u-2002"])[0] == (
        "При розыгрыше: Наносит вражескому отряду 2 урона."
    )
    assert generator.text("ru", library["l-1001"])[0].endswith("Усиливает союзный отряд на 2.")
    # a locale without twins uses the plain phrase
    zh = generator.text("zh-CN", library["u-2002"])[0]
    assert zh == "打出时：对一个敌方单位造成2点伤害。"  # noqa: RUF001


def test_plural_forms_follow_the_counted_number(generator: CardText) -> None:
    def draw(n: int) -> dict[str, str]:
        defn = card_def_from_mapping(
            "s-9",
            "neutral",
            {"kind": "special", "abilities": [{"when": "on_play", "do": "draw", "count": n}]},
        )
        return {loc: generator.text(loc, defn)[0] for loc in LOCALES}

    assert draw(1) == {"en": "Draw a card.", "ru": "Возьмите карту.", "zh-CN": "抽1张牌。"}
    assert draw(3)["ru"] == "Возьмите 3 карты."
    assert draw(5)["ru"] == "Возьмите 5 карт."
    assert draw(5)["en"] == "Draw 5 cards."


def test_an_explicit_text_wins_and_a_missing_locale_is_generated(
    tables: dict[str, dict[str, str]], library: Library
) -> None:
    partial = {loc: dict(t) for loc, t in tables.items()}
    del partial["ru"]["card.u-2002.text"]
    filled, problems = fill_card_texts(library, partial)
    assert problems == []
    assert filled["en"]["card.u-2002.text"] == tables["en"]["card.u-2002.text"]
    assert filled["ru"]["card.u-2002.text"] == "При розыгрыше: Наносит вражескому отряду 2 урона."


def test_a_missing_template_is_reported(
    tables: dict[str, dict[str, str]], library: Library
) -> None:
    broken = {loc: dict(t) for loc, t in tables.items()}
    for table in broken.values():
        table.pop("ability.add-status.poisoned.text", None)
        table.pop("card.u-2004.text", None)
    _, problems = fill_card_texts(library, broken)
    assert problems == ["en: ability.add-status.poisoned.text (card text of u-2004)"]


def test_a_locale_with_recipient_twins_needs_all_of_them(
    tables: dict[str, dict[str, str]],
) -> None:
    assert check_templates(tables) == []
    partial = {loc: dict(t) for loc, t in tables.items()}
    del partial["ru"]["ability.target-to.weakest.both"]
    assert check_templates(partial) == [
        "ru: ability.target-to.weakest.both (a locale with recipient twins needs all)"
    ]


def test_a_rendered_phrase_is_never_read_as_a_reference(
    tables: dict[str, dict[str, str]],
) -> None:
    odd = {loc: dict(t) for loc, t in tables.items()}
    odd["en"]["tag.tag-x.name"] = "@ui.title"
    defn = card_def_from_mapping(
        "u-9",
        "neutral",
        {
            "kind": "unit",
            "color": "bronze",
            "provisions": 4,
            "power": 3,
            "abilities": [
                {
                    "when": "on_play",
                    "do": "destroy",
                    "target": {
                        "units": "all",
                        "side": "opponent",
                        "where": {"tags_any": ["tag-x"]},
                    },
                }
            ],
        },
    )
    assert CardText(odd).text("en", defn)[0] == "When played: Destroy all enemy units (@ui.title)."


def test_load_data_generates_the_texts_it_lacks(tmp_path: Path, dataset: DataSet) -> None:
    """A tree without any card text loads, with the texts generated into the pack's tables."""
    shutil.copytree(DATA, tmp_path / "data")
    for locale in LOCALES:
        path = tmp_path / "data" / "i18n" / locale / "cards.yaml"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        path.write_text(
            yaml.safe_dump({k: v for k, v in doc.items() if not k.endswith(".text")}),
            encoding="utf-8",
        )
    data = load_data(tmp_path / "data")
    for locale in LOCALES:
        assert (
            data.i18n[locale]["card.u-2002.text"]
            == CardText(dataset.i18n).text(locale, data.library["u-2002"])[0]
        )
    assert data.i18n["en"]["card.u-0001.text"] == ""  # a plain unit has nothing to say


def test_the_card_text_command_prints_both_sources() -> None:
    from opengwt.data.cli import card_texts

    lines = card_texts(DATA, ["en"], ["u-2002"])
    assert lines[0].startswith("u-2002 en explicit: ")
    lines = card_texts(DATA, ["en"], ["u-2002"], ignore_explicit=True)
    assert lines == ["u-2002 en generated: When played: Deal 2 damage to an enemy unit."]
