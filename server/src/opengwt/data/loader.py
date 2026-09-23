"""Load ``data/`` — docs/protocol/cards.md §9. The schemas in ``schemas/`` are the copies that
ship with the package; a test keeps them identical to ``docs/protocol/``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from opengwt.core.model import CardDef, Deck, Library, card_def_from_mapping

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
    leader = doc.get("leader")
    if leader is not None and leader not in lib:
        problems.append(f"{path}: unknown leader {leader}")
    if problems:
        raise DataError(problems)
    return Deck(faction=faction, cards=tuple(cards), leader=leader)


def load_decks(decks_dir: Path, lib: Library) -> dict[str, Deck]:
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


def check_i18n(lib: Library, tables: dict[str, dict[str, str]]) -> list[str]:
    """Missing keys, as ``locale: key`` strings — docs/protocol/i18n.md §7 and ADR 0006."""
    problems: list[str] = []
    base = tables.get(BASE_LOCALE)
    if base is None:
        return [f"missing base locale {BASE_LOCALE}"]
    required = {f"card.{cid}.{k}" for cid in lib for k in ("name", "text")}
    required |= {f"faction.{d.faction}.name" for d in lib.values()}
    problems.extend(f"{BASE_LOCALE}: {k}" for k in sorted(required - set(base)))
    for locale, table in sorted(tables.items()):
        if locale == BASE_LOCALE:
            continue
        problems.extend(f"{locale}: {k}" for k in sorted(set(base) - set(table)))
    return problems


def load_data(data_dir: Path) -> DataSet:
    """Everything under ``data/``, validated. Raises ``DataError`` listing every problem found."""
    lib = load_library(data_dir / "cards")
    problems: list[str] = []
    decks: dict[str, Deck] = {}
    tables: dict[str, dict[str, str]] = {}
    try:
        decks = load_decks(data_dir / "decks", lib)
    except DataError as e:
        problems.extend(e.problems)
    try:
        tables = load_i18n(data_dir / "i18n")
        problems.extend(check_i18n(lib, tables))
    except DataError as e:
        problems.extend(e.problems)
    if problems:
        raise DataError(problems)
    return DataSet(library=lib, decks=decks, i18n=tables)
