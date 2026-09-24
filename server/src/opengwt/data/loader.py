"""Load ``data/`` — docs/protocol/cards.md §13 and §14. The schemas in ``schemas/`` are the copies
that ship with the package; a test keeps them identical to ``docs/protocol/``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from opengwt.core.engine import check_deck
from opengwt.core.model import (
    DEFAULT_RULES,
    Action,
    CardDef,
    Deck,
    Kind,
    Library,
    Rules,
    card_def_from_mapping,
)
from opengwt.data.cardtext import fill_card_texts

SCHEMA_DIR = Path(__file__).parent / "schemas"
NEUTRAL = "neutral"
BASE_LOCALE = "en"


class DataError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass
class DataSet:
    library: Library
    decks: dict[str, Deck]
    i18n: dict[str, dict[str, str]]


@cache
def _validator(name: str) -> Draft202012Validator:
    with open(SCHEMA_DIR / name, encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _read_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _schema_problems(name: str, doc: Any, source: Path) -> list[str]:
    out = []
    for err in sorted(
        _validator(name).iter_errors(doc), key=lambda e: list(map(str, e.absolute_path))
    ):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"{source}: {where}: {err.message}")
    return out


def load_cards_file(path: Path) -> dict[str, CardDef]:
    doc = _read_yaml(path)
    problems = _schema_problems("cards.schema.json", doc, path)
    if problems:
        raise DataError(problems)
    faction = str(doc["faction"])
    return {cid: card_def_from_mapping(cid, faction, m) for cid, m in doc["cards"].items()}


def load_cards_raw(cards_dir: Path) -> dict[str, dict[str, Any]]:
    """Validated card mappings by id, each with its ``faction`` added: what the content pack
    ships to clients (docs/protocol/cards.md §14)."""
    raw: dict[str, dict[str, Any]] = {}
    for path in sorted(cards_dir.glob("*.cards.yaml")):
        doc = _read_yaml(path)
        problems = _schema_problems("cards.schema.json", doc, path)
        if problems:
            raise DataError(problems)
        for cid, mapping in doc["cards"].items():
            raw[cid] = {"faction": str(doc["faction"]), **mapping}
    return dict(sorted(raw.items()))


def load_library(cards_dir: Path) -> Library:
    lib: Library = {}
    problems: list[str] = []
    for path in sorted(cards_dir.glob("*.cards.yaml")):
        try:
            cards = load_cards_file(path)
        except DataError as e:
            problems.extend(e.problems)
            continue
        for cid, defn in cards.items():
            if cid in lib:
                problems.append(f"{path}: duplicate card id {cid}")
            lib[cid] = defn
    if not lib:
        problems.append(f"{cards_dir}: no *.cards.yaml files")
    if problems:
        raise DataError(problems)
    return dict(sorted(lib.items()))


def load_deck(path: Path, lib: Library) -> Deck:
    doc = _read_yaml(path)
    problems = _schema_problems("decks.schema.json", doc, path)
    if problems:
        raise DataError(problems)
    faction = str(doc["faction"])
    cards: list[str] = []
    for entry in doc["cards"]:
        cid = str(entry["id"])
        defn = lib.get(cid)
        if defn is None:
            problems.append(f"{path}: unknown card {cid}")
        elif defn.faction not in (faction, NEUTRAL):
            problems.append(f"{path}: {cid} belongs to {defn.faction}, not {faction} or neutral")
        cards.extend([cid] * int(entry["count"]))
    leader = str(doc["leader"])
    if leader not in lib:
        problems.append(f"{path}: unknown leader {leader}")
    stratagem = str(doc["stratagem"])
    if stratagem not in lib:
        problems.append(f"{path}: unknown stratagem {stratagem}")
    if problems:
        raise DataError(problems)
    return Deck(faction=faction, cards=tuple(cards), leader=leader, stratagem=stratagem)


def load_decks(decks_dir: Path, lib: Library, rules: Rules = DEFAULT_RULES) -> dict[str, Deck]:
    """Every deck file, each legal under ``rules`` (cards.md §12)."""
    decks: dict[str, Deck] = {}
    problems: list[str] = []
    for path in sorted(decks_dir.glob("*.deck.yaml")):
        try:
            deck = load_deck(path, lib)
        except DataError as e:
            problems.extend(e.problems)
            continue
        deck_id = str(_read_yaml(path)["id"])
        if deck_id in decks:
            problems.append(f"{path}: duplicate deck id {deck_id}")
        problems.extend(f"{path}: {p}" for p in check_deck(lib, deck, rules))
        decks[deck_id] = deck
    if problems:
        raise DataError(problems)
    return decks


def load_i18n(i18n_dir: Path) -> dict[str, dict[str, str]]:
    tables: dict[str, dict[str, str]] = {}
    problems: list[str] = []
    for locale_dir in sorted(p for p in i18n_dir.iterdir() if p.is_dir()):
        table: dict[str, str] = {}
        for path in sorted(locale_dir.glob("*.yaml")):
            doc = _read_yaml(path) or {}
            if not isinstance(doc, dict):
                problems.append(f"{path}: not a flat map")
                continue
            for key, value in doc.items():
                if not isinstance(value, str):
                    problems.append(f"{path}: {key}: value must be a string")
                elif key in table:
                    problems.append(f"{path}: duplicate key {key}")
                else:
                    table[str(key)] = value
        tables[locale_dir.name] = table
    if problems:
        raise DataError(problems)
    return tables


PLURAL_SUFFIXES = (".zero", ".one", ".two", ".few", ".many", ".other")


def plural_base(key: str) -> str:
    """``ui.hand.count`` for ``ui.hand.count.other``; the key itself when it has no suffix."""
    for suffix in PLURAL_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)]
    return key


def check_references(lib: Library) -> list[str]:
    """Cross-file rules on card references (cards.md §14): ``place_new_card`` names an existing
    unit or artifact."""
    problems: list[str] = []
    for defn in lib.values():
        for ability in defn.abilities:
            if ability.do is not Action.PLACE_NEW_CARD:
                continue
            target = lib.get(ability.card or "")
            if target is None:
                problems.append(f"{defn.id}: place_new_card names unknown card {ability.card}")
            elif not target.placed:
                problems.append(
                    f"{defn.id}: place_new_card names {ability.card}, not a unit or artifact"
                )
    return problems


def check_leaders(lib: Library) -> list[str]:
    """No leader is neutral: a leader belongs to the faction whose decks it leads (cards.md §12,
    §14)."""
    return [
        f"{defn.id}: a leader belongs to a faction, not to {NEUTRAL}"
        for defn in lib.values()
        if defn.kind is Kind.LEADER and defn.faction == NEUTRAL
    ]


def check_i18n(lib: Library, tables: dict[str, dict[str, str]]) -> list[str]:
    """Missing keys, as ``locale: key`` strings — docs/protocol/i18n.md §2, §7 and ADR 0006.

    ``tables`` are expected to carry the generated card texts already (``fill_card_texts``), so
    a missing ``card.<id>.text`` means it was not generated. Plural variants are compared by
    their base key: a locale that has any variant (or the bare base key) of an English plural
    counts as complete, and a locale with variants must have ``.other``.
    """
    problems: list[str] = []
    base = tables.get(BASE_LOCALE)
    if base is None:
        return [f"missing base locale {BASE_LOCALE}"]
    required = {f"card.{cid}.{k}" for cid in lib for k in ("name", "text")}
    required |= {f"faction.{d.faction}.name" for d in lib.values()}
    required |= {f"tag.{tag}.name" for d in lib.values() for tag in d.tags}
    problems.extend(f"{BASE_LOCALE}: {k}" for k in sorted(required - set(base)))
    base_keys = {plural_base(k) for k in base}
    for locale, table in sorted(tables.items()):
        present = {plural_base(k) for k in table}
        if locale != BASE_LOCALE:
            problems.extend(f"{locale}: {k}" for k in sorted(base_keys - present))
        variant_bases = {plural_base(k) for k in table if plural_base(k) != k}
        for vb in sorted(variant_bases):
            if f"{vb}.other" not in table:
                problems.append(f"{locale}: {vb}.other (a plural needs its other form)")
    return problems


def load_data(data_dir: Path, rules: Rules = DEFAULT_RULES) -> DataSet:
    """Everything under ``data/``, validated, the decks legal under ``rules`` — the ``Rules``
    the pack will carry (cards.md §14) — and every card text a locale lacks generated from the
    card's abilities (docs/protocol/i18n.md §10). Raises ``DataError`` listing every problem
    found."""
    lib = load_library(data_dir / "cards")
    problems: list[str] = check_references(lib) + check_leaders(lib)
    decks: dict[str, Deck] = {}
    tables: dict[str, dict[str, str]] = {}
    try:
        decks = load_decks(data_dir / "decks", lib, rules)
    except DataError as e:
        problems.extend(e.problems)
    try:
        tables, text_problems = fill_card_texts(lib, load_i18n(data_dir / "i18n"), rules)
        problems.extend(text_problems)
        problems.extend(check_i18n(lib, tables))
    except DataError as e:
        problems.extend(e.problems)
    if problems:
        raise DataError(problems)
    return DataSet(library=lib, decks=decks, i18n=tables)
