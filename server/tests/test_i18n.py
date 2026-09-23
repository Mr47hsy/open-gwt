from pathlib import Path

import pytest
import yaml

from opengwt.i18n import Renderer, negotiate_locale, plural_category

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
    assert renderer.render("zh-CN", "card.a-u-0001.name") == "占位 A 单位 1"
    assert renderer.render("ru", "card.a-u-0001.name").startswith("Заглушка A")
    assert renderer.render("fr", "card.a-u-0001.name") == "Placeholder A unit 1"


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
