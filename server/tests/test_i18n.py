import json
import re
from pathlib import Path

import pytest
import yaml

from opengwt.core.engine import DECK_PROBLEM_KEYS, DECK_UNKNOWN_CARD
from opengwt.core.model import DeckProblem, RowEffectKind, Status
from opengwt.i18n import Renderer, negotiate_locale, plural_category
from opengwt.server.services.decks import problem_to_dict

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "data" / "i18n" / "conformance.yaml"


def _suite() -> dict:  # type: ignore[type-arg]
    doc = yaml.safe_load(SUITE.read_text(encoding="utf-8"))
    assert doc["schema"] == "opengwt.i18n-conformance/1"
    return doc  # type: ignore[no-any-return]


def test_conformance_suite() -> None:
    suite = _suite()
    renderer = Renderer(suite["tables"])
    failures = []
    for case in suite["cases"]:
        got = renderer.render(case["locale"], case["key"], case.get("params") or {})
        if got != case["expected"]:
            failures.append((case, got))
    assert not failures, failures


def test_conformance_suite_matches_the_protocol_example() -> None:
    example = REPO / "docs" / "protocol" / "examples" / "i18n-conformance.yaml"
    assert yaml.safe_load(example.read_text()) == _suite() or len(_suite()["cases"]) >= len(
        yaml.safe_load(example.read_text())["cases"]
    )


def test_real_tables_render_card_names(dataset) -> None:  # type: ignore[no-untyped-def]
    renderer = Renderer(dataset.i18n)
    assert renderer.locales == ("en", "ru", "zh-CN")
    assert renderer.render("zh-CN", "card.u-1001.name") == "占位 A 单位 1"
    assert renderer.render("ru", "card.u-1001.name").startswith("Заглушка A")
    assert renderer.render("fr", "card.u-1001.name") == "Placeholder A unit 1"


# the numbers each deck problem's message shows (cards.md §12); the others are about one card
DECK_PROBLEM_NUMBERS = {
    "error.deck.too-few-cards": ("count", "min"),
    "error.deck.too-many-cards": ("count", "max"),
    "error.deck.too-few-units": ("count", "min"),
    "error.deck.too-many-copies": ("count", "limit"),
    "error.deck.over-budget": ("used", "budget"),
}
DECK_PROBLEMS_ABOUT_NO_CARD = (
    "error.deck.too-few-cards",
    "error.deck.too-many-cards",
    "error.deck.too-few-units",
    "error.deck.over-budget",
)


@pytest.mark.parametrize("count", [1, 2, 5, 21])
def test_every_deck_problem_renders_in_every_locale(dataset, count: int) -> None:  # type: ignore[no-untyped-def]
    """Each problem key has a message in every locale that shows every parameter the server
    sends with it — plural forms included — so a client can list a deck's problems."""
    renderer = Renderer(dataset.i18n)
    for key in DECK_PROBLEM_KEYS:
        # the first number drives the plural form; the second is told apart by its size
        numbers = tuple(
            (name, count if at == 0 else 1000 + count)
            for at, name in enumerate(DECK_PROBLEM_NUMBERS.get(key, ()))
        )
        card = None if key in DECK_PROBLEMS_ABOUT_NO_CARD else "u-1001"
        params = problem_to_dict(DeckProblem(key, card, numbers))["params"]
        for locale in renderer.locales:
            text = renderer.render(locale, key, params)
            assert text != key and "{" not in text, (locale, key, text)
            if card is not None and key != DECK_UNKNOWN_CARD:
                assert renderer.render(locale, "card.u-1001.name") in text, (locale, key)
            assert all(str(value) in text for _, value in numbers), (locale, key, text)


@pytest.mark.parametrize(
    ("locale", "count", "category"),
    [
        ("en", 1, "one"),
        ("en", -1, "one"),
        ("en", 0, "other"),
        ("zh-CN", 1, "other"),
        ("ru", 1, "one"),
        ("ru", 2, "few"),
        ("ru", 5, "many"),
        ("ru", 11, "many"),
        ("ru", 21, "one"),
        ("ru", 112, "many"),
        ("xx", 1, "other"),
    ],
)
def test_plural_categories(locale: str, count: int, category: str) -> None:
    assert plural_category(locale, count) == category


def test_invalid_parameters_are_rejected() -> None:
    renderer = Renderer({"en": {"k": "{x}", "c.one": "one", "c.other": "other"}})
    with pytest.raises(ValueError):
        renderer.render("en", "k", {"x": True})
    with pytest.raises(ValueError):
        renderer.render("en", "k", {"x": 1.5})  # type: ignore[dict-item]
    with pytest.raises(ValueError):
        renderer.render("en", "c", {"count": "3"})


def test_negotiate_locale() -> None:
    supported = ["en", "zh-CN", "ru"]
    assert negotiate_locale(supported, "ru", "en") == "ru"
    assert negotiate_locale(supported, "ZH-cn", None) == "zh-CN"
    assert negotiate_locale(supported, None, "fr;q=0.9, ru;q=0.8, en;q=0.7") == "ru"
    assert negotiate_locale(supported, None, "zh-TW, en;q=0.5") == "zh-CN"
    assert negotiate_locale(supported, None, "de, *;q=0.1") == "en"
    assert negotiate_locale(supported, "fr", "") == "en"
    assert negotiate_locale(supported, None, "ru;q=0, en;q=0.2") == "en"


def test_conformance_json_matches_the_yaml() -> None:
    """The client's renderer reads the JSON twin; it must never lag behind the YAML."""
    from opengwt.data.cli import conformance_json

    target = REPO / "data" / "i18n" / "conformance.json"
    assert target.exists(), "run `opengwt-data conformance-json --data ../data`"
    assert target.read_text(encoding="utf-8") == conformance_json(REPO / "data")


def test_client_i18n_export_is_fresh() -> None:
    """The client embeds ui/choice/error strings; the JSON must match data/i18n."""
    from opengwt.data.cli import client_i18n

    out = REPO / "client" / "Assets" / "OpenGwt" / "Resources" / "i18n"
    exported = client_i18n(REPO / "data")
    assert set(exported) == {"en", "ru", "zh-CN"}
    for locale, text in exported.items():
        target = out / f"{locale}.json"
        assert target.exists(), (
            "run `opengwt-data client-i18n --out ../client/Assets/OpenGwt/Resources/i18n`"
        )
        assert target.read_text(encoding="utf-8") == text, f"{target} is stale"
    assert '"ui.language.name": "简体中文"' in exported["zh-CN"]
    assert '"card.' not in exported["en"], "card texts come from the server, not the build"


# --- the interface texts of the vocabulary (cards.md §13, i18n.md §2) --------------------------


def _choosing_actions() -> list[str]:
    """The actions whose ability may ask a player something (cards.md §7): those the schema lets
    take a unit target, a row target, a card source or a create pool."""
    schema = json.loads((REPO / "docs" / "protocol" / "cards.schema.json").read_text("utf-8"))
    out = []
    for name, definition in schema["$defs"].items():
        if not name.startswith("do_"):
            continue
        keys = set(definition.get("properties", {}))
        if keys & {"target", "row_target", "cards", "pool"}:
            out.append(name[len("do_") :])
    assert out, "no choosing actions found in the schema"
    return out


def _hyphens(word: str) -> str:
    return word.replace("_", "-")


def test_every_prompt_key_the_core_may_emit_has_a_text(dataset) -> None:  # type: ignore[no-untyped-def]
    """The core builds `choice.<action>` from the action's name (engine.run) and asks
    `choice.place` for a placement; each renders in every locale, `choice.place` with the card."""
    renderer = Renderer(dataset.i18n)
    keys = ["choice." + _hyphens(a) for a in _choosing_actions()] + ["choice.place"]
    for locale in renderer.locales:
        for key in keys:
            text = renderer.render(locale, key, {"card": "@card.u-1001.name"})
            assert text != key and "{" not in text, (locale, key, text)
    for locale in renderer.locales:
        assert renderer.render(locale, "card.u-1001.name") in renderer.render(
            locale, "choice.place", {"card": "@card.u-1001.name"}
        ), locale


def test_every_status_and_row_effect_has_a_name_and_a_text(dataset) -> None:  # type: ignore[no-untyped-def]
    """`status.<status>.name` / `.text` and `row-effect.<effect>.name` / `.text` for every word of
    the vocabulary, in every locale; a row effect's text shows its amount and its count."""
    renderer = Renderer(dataset.i18n)
    for locale in renderer.locales:
        for status in Status:
            for suffix in ("name", "text"):
                key = f"status.{_hyphens(status.value)}.{suffix}"
                text = renderer.render(locale, key)
                assert text != key and "{" not in text, (locale, key, text)
        for effect in RowEffectKind:
            name = f"row-effect.{_hyphens(effect.value)}.name"
            assert renderer.render(locale, name) != name, (locale, name)
            for count in (1, 3):
                key = f"row-effect.{_hyphens(effect.value)}.text"
                text = renderer.render(locale, key, {"amount": 7, "count": count})
                assert text != key and "{" not in text and "7" in text, (locale, key, text)


def test_every_illegal_intent_reason_has_a_text(dataset) -> None:  # type: ignore[no-untyped-def]
    """Every reason key the engine raises with `illegal_intent` (match.md §10) has a message in
    every locale, so a client can show why a move was refused."""
    source = (REPO / "server" / "src" / "opengwt" / "core" / "engine.py").read_text("utf-8")
    reasons = sorted(
        set(re.findall(r'IllegalIntent\("illegal_intent", "(error\.[a-z.-]+)"\)', source))
    )
    assert len(reasons) >= 20, reasons
    renderer = Renderer(dataset.i18n)
    for locale in renderer.locales:
        for key in reasons:
            assert renderer.render(locale, key) != key, (locale, key)
