"""Import a designer's card set into ``data/`` — docs/protocol/import.md.

A card set (``opengwt.cardset/1``, YAML or JSON, or a CSV of cards as a spreadsheet exports it)
names its cards by the designer's own keys, in the card protocol's vocabulary, with their names
and optional texts per locale, and optionally its factions, tags and decks. The importer
assigns every card without an id an opaque one, remembered in the set's manifest so a
re-import keeps it, turns the set into ``data/cards/<faction>.cards.yaml``, one translation
file per locale — with ``TODO`` stubs for every name a locale lacks — and ``data/decks/``
files, and validates the whole resulting tree exactly as the compiler does before it writes
anything.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from opengwt.data.loader import BASE_LOCALE, DataError, _schema_problems, load_data, load_library

CARDSET_SCHEMA = "opengwt.cardset/1"
MANIFEST_SCHEMA = "opengwt.import/1"
CARDS_SCHEMA = "opengwt.cards/2"
DECK_SCHEMA = "opengwt.deck/2"
MANIFEST_DIR = "import"
ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
TAG = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
NUMBERED_ID = re.compile(r"^[a-z]-(\d+)$")
TODO = "# TODO(i18n): translate"

# The fields of a card in a cards file, in the order cards.md §3 lists them.
CARD_FIELDS = (
    "kind",
    "color",
    "provisions",
    "provision_bonus",
    "token",
    "power",
    "armor",
    "rows",
    "side",
    "statuses",
    "tags",
    "activation",
    "abilities",
)
INT_FIELDS = frozenset({"provisions", "provision_bonus", "power", "armor"})
LIST_FIELDS = frozenset({"rows", "statuses", "tags"})
STRUCT_FIELDS = frozenset({"activation", "abilities"})
SET_FIELDS = frozenset({"key", "id", "faction", "name", "text"})
ABILITY_ORDER = ("when", "if", "do")
PREFIX_BY_KIND = {"unit": "u", "special": "s", "artifact": "a", "leader": "l", "stratagem": "g"}
TRUE = frozenset({"1", "true", "yes", "y", "x", "✓"})
FALSE = frozenset({"", "0", "false", "no", "n"})


class CardSetError(DataError):
    """A card set that cannot be imported; ``problems`` says why, each naming where."""


@dataclass
class CardEntry:
    key: str
    id: str | None
    faction: str
    fields: dict[str, Any]
    names: dict[str, str]
    texts: dict[str, str]
    where: str


@dataclass
class DeckEntry:
    id: str
    faction: str
    leader: str
    stratagem: str
    cards: list[tuple[str, int]]
    where: str


@dataclass
class CardSet:
    set_id: str
    source: Path
    cards: list[CardEntry] = field(default_factory=list)
    factions: dict[str, dict[str, str]] = field(default_factory=dict)
    tags: dict[str, dict[str, str]] = field(default_factory=dict)
    decks: list[DeckEntry] = field(default_factory=list)


@dataclass
class Plan:
    """What an import writes and deletes, relative to the data directory, and what it found."""

    set_id: str
    writes: dict[str, str] = field(default_factory=dict)
    deletes: list[str] = field(default_factory=list)
    ids: dict[str, str] = field(default_factory=dict)
    new_ids: dict[str, str] = field(default_factory=dict)
    stubs: dict[str, int] = field(default_factory=dict)
    generated: dict[str, int] = field(default_factory=dict)
    cards_by_faction: dict[str, int] = field(default_factory=dict)
    decks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


# --- reading a card set ----------------------------------------------------------------------


def read_cardset(path: Path, set_id: str | None = None) -> CardSet:
    """Parse a card set file: ``.yaml``/``.yml``/``.json`` (a whole set) or ``.csv`` (cards only;
    ``set_id`` then names the set). Raises ``CardSetError`` listing every problem."""
    problems: list[str] = []
    if path.suffix.lower() == ".csv":
        if not set_id:
            raise CardSetError([f"{path}: a CSV holds cards only; name the set with --set"])
        cardset = CardSet(set_id=set_id, source=path)
        cardset.cards = _csv_cards(path, problems)
    else:
        doc = _read_doc(path)
        if not isinstance(doc, dict):
            raise CardSetError([f"{path}: expected a mapping at the top level"])
        if doc.get("schema") != CARDSET_SCHEMA:
            problems.append(f"{path}: schema must be {CARDSET_SCHEMA}, not {doc.get('schema')!r}")
        known = {"schema", "set", "factions", "tags", "cards", "cards_csv", "decks"}
        problems.extend(f"{path}: unknown field {k!r}" for k in sorted(set(doc) - known))
        sid = set_id or doc.get("set")
        if not isinstance(sid, str):
            raise CardSetError([*problems, f"{path}: `set` names the set"])
        cardset = CardSet(set_id=sid, source=path)
        cardset.factions = _names_map(doc.get("factions"), "factions", path, problems, ID)
        cardset.tags = _names_map(doc.get("tags"), "tags", path, problems, TAG)
        cards = doc.get("cards")
        if isinstance(cards, dict):
            cards = [{"key": k, **(v or {})} for k, v in cards.items()]
        if cards is not None and not isinstance(cards, list):
            problems.append(f"{path}: cards must be a list or a mapping")
            cards = []
        for index, raw in enumerate(cards or []):
            entry = _card_entry(raw, f"{path}: cards[{index}]", problems)
            if entry is not None:
                cardset.cards.append(entry)
        csv_path = doc.get("cards_csv")
        if csv_path is not None:
            cardset.cards.extend(_csv_cards(path.parent / str(csv_path), problems))
        cardset.decks = _deck_entries(doc.get("decks"), path, problems)
    if not ID.match(cardset.set_id):
        problems.append(f"{path}: set id {cardset.set_id!r} must match {ID.pattern}")
    if not cardset.cards:
        problems.append(f"{path}: no cards")
    seen: dict[str, str] = {}
    for entry in cardset.cards:
        if entry.key in seen:
            problems.append(f"{entry.where}: key {entry.key!r} also used at {seen[entry.key]}")
        seen.setdefault(entry.key, entry.where)
    if problems:
        raise CardSetError(problems)
    return cardset


def _read_doc(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _localized(value: Any, where: str, problems: list[str]) -> dict[str, str]:
    """A name or text: one string (the base locale's) or a map of locale → string."""
    if value is None:
        return {}
    if isinstance(value, str):
        return {BASE_LOCALE: value} if value.strip() else {}
    if isinstance(value, dict):
        out: dict[str, str] = {}
        for locale, text in value.items():
            if not isinstance(text, str):
                problems.append(f"{where}: {locale}: must be a string")
            elif text.strip():
                out[str(locale)] = text
        return out
    problems.append(f"{where}: must be a string or a map of locale to string")
    return {}


def _names_map(
    raw: Any, what: str, path: Path, problems: list[str], pattern: re.Pattern[str]
) -> dict[str, dict[str, str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        problems.append(f"{path}: {what} must map an id to its names")
        return {}
    out: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        if not pattern.match(str(key)):
            problems.append(f"{path}: {what}: {key!r} must match {pattern.pattern}")
        name = value.get("name") if isinstance(value, dict) and "name" in value else value
        out[str(key)] = _localized(name, f"{path}: {what}.{key}.name", problems)
    return out


def _card_entry(raw: Any, where: str, problems: list[str]) -> CardEntry | None:
    if not isinstance(raw, dict):
        problems.append(f"{where}: a card must be a mapping")
        return None
    cid = raw.get("id")
    key = raw.get("key", cid)
    if key is None or not str(key).strip():
        problems.append(f"{where}: a card needs a `key` or an `id`")
        return None
    if cid is not None and not ID.match(str(cid)):
        problems.append(f"{where}: id {cid!r} must match {ID.pattern}")
    faction = raw.get("faction")
    if not isinstance(faction, str) or not ID.match(faction):
        problems.append(f"{where}: faction {faction!r} must be an id")
        faction = str(faction)
    fields = {k: v for k, v in raw.items() if k not in SET_FIELDS}
    return CardEntry(
        key=str(key),
        id=str(cid) if cid is not None else None,
        faction=faction,
        fields=fields,
        names=_localized(raw.get("name"), f"{where}: name", problems),
        texts=_localized(raw.get("text"), f"{where}: text", problems),
        where=f"{where} ({key})",
    )


def _csv_cards(path: Path, problems: list[str]) -> list[CardEntry]:
    """One card per row. List columns take items separated by commas, semicolons or spaces;
    ``activation`` and ``abilities`` hold YAML or JSON; ``name.<locale>`` and ``text.<locale>``
    (or ``name_<locale>``) the texts; empty cells are absent."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        problems.append(f"{path}: {e}")
        return []
    reader = csv.DictReader(io.StringIO(text))
    columns = reader.fieldnames or []
    allowed = SET_FIELDS | set(CARD_FIELDS)
    for column in columns:
        base = re.split(r"[._:]", column.strip(), maxsplit=1)[0]
        if column.strip() not in allowed and base not in ("name", "text"):
            problems.append(f"{path}: unknown column {column!r}")
    out: list[CardEntry] = []
    for number, row in enumerate(reader, start=2):
        where = f"{path}: row {number}"
        if not any(isinstance(v, str) and v.strip() for v in row.values()):
            continue
        raw: dict[str, Any] = {}
        names: dict[str, str] = {}
        texts: dict[str, str] = {}
        for column, cell in row.items():
            if column is None:
                problems.append(f"{where}: more cells than columns")
                continue
            name = column.strip()
            value = (cell or "").strip()
            if not value:
                continue
            parts = re.split(r"[._:]", name, maxsplit=1)
            head, locale = parts[0], parts[1] if len(parts) > 1 else BASE_LOCALE
            if head in ("name", "text"):
                (names if head == "name" else texts)[locale] = value
            elif name in INT_FIELDS:
                try:
                    raw[name] = int(value)
                except ValueError:
                    problems.append(f"{where}: {name} must be an integer, not {value!r}")
            elif name in LIST_FIELDS:
                raw[name] = [v for v in re.split(r"[,;\s|]+", value) if v]
            elif name in STRUCT_FIELDS:
                try:
                    raw[name] = yaml.safe_load(value)
                except yaml.YAMLError as e:
                    problems.append(f"{where}: {name} is not YAML or JSON: {e}")
            elif name == "token":
                lowered = value.lower()
                if lowered not in TRUE | FALSE:
                    problems.append(f"{where}: token must be true or false, not {value!r}")
                raw[name] = lowered in TRUE
            else:
                raw[name] = value
        entry = _card_entry(raw, where, problems)
        if entry is not None:
            entry.names.update(names)
            entry.texts.update(texts)
            out.append(entry)
    return out


def _deck_entries(raw: Any, path: Path, problems: list[str]) -> list[DeckEntry]:
    if raw is None:
        return []
    items = [{"id": k, **(v or {})} for k, v in raw.items()] if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        problems.append(f"{path}: decks must be a list or a mapping")
        return []
    out: list[DeckEntry] = []
    for index, deck in enumerate(items):
        where = f"{path}: decks[{index}]"
        if not isinstance(deck, dict):
            problems.append(f"{where}: a deck must be a mapping")
            continue
        missing = [k for k in ("id", "faction", "leader", "stratagem", "cards") if k not in deck]
        if missing:
            problems.append(f"{where}: missing {', '.join(missing)}")
            continue
        cards_raw = deck["cards"]
        cards: list[tuple[str, int]] = []
        if isinstance(cards_raw, dict):
            cards = [(str(k), int(v)) for k, v in cards_raw.items()]
        elif isinstance(cards_raw, list):
            for item in cards_raw:
                if isinstance(item, dict) and ("card" in item or "id" in item):
                    cards.append((str(item.get("card", item.get("id"))), int(item.get("count", 1))))
                else:
                    problems.append(f"{where}: a deck card is {{card, count}}, not {item!r}")
        else:
            problems.append(f"{where}: cards must be a list or a mapping")
        out.append(
            DeckEntry(
                id=str(deck["id"]),
                faction=str(deck["faction"]),
                leader=str(deck["leader"]),
                stratagem=str(deck["stratagem"]),
                cards=cards,
                where=f"{where} ({deck['id']})",
            )
        )
    return out


# --- planning --------------------------------------------------------------------------------


def manifest_path(set_id: str) -> str:
    return f"{MANIFEST_DIR}/{set_id}.yaml"


def read_manifest(data_dir: Path, set_id: str) -> dict[str, Any]:
    path = data_dir / manifest_path(set_id)
    if not path.exists():
        return {"ids": {}, "files": []}
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {"ids": dict(doc.get("ids") or {}), "files": list(doc.get("files") or [])}


def plan_import(
    cardset: CardSet, data_dir: Path, replace: bool = False, id_start: int | None = None
) -> Plan:
    """Everything the import would write and delete; ``Plan.problems`` lists what stops it,
    before any cross-file validation (``validate_plan``)."""
    plan = Plan(set_id=cardset.set_id)
    manifest = read_manifest(data_dir, cardset.set_id)
    own_files = set(manifest["files"])
    locales = sorted(p.name for p in (data_dir / "i18n").iterdir() if p.is_dir())
    if BASE_LOCALE not in locales:
        plan.problems.append(f"{data_dir}/i18n: no {BASE_LOCALE} locale")
        return plan
    for entry in cardset.cards:
        for what, texts in (("name", entry.names), ("text", entry.texts)):
            plan.problems.extend(
                f"{entry.where}: {what} in {loc!r}, which is not one of {', '.join(locales)}"
                for loc in texts
                if loc not in locales
            )
    for label, named in (("faction", cardset.factions), ("tag", cardset.tags)):
        for item, localized in named.items():
            plan.problems.extend(
                f"{cardset.source}: {label} {item}: name in {loc!r}, "
                f"which is not one of {', '.join(locales)}"
                for loc in localized
                if loc not in locales
            )
    existing = _existing_ids(data_dir, own_files)
    _assign_ids(cardset, manifest["ids"], existing, plan, id_start)
    if plan.problems:
        return plan

    # cards files, one per faction, cards in the set's order
    by_faction: dict[str, dict[str, Any]] = {}
    for entry in cardset.cards:
        mapping = _card_mapping(entry, plan.ids, plan)
        by_faction.setdefault(entry.faction, {})[plan.ids[entry.key]] = mapping
        plan.cards_by_faction[entry.faction] = plan.cards_by_faction.get(entry.faction, 0) + 1
    header = _header(cardset)
    for faction, cards in by_faction.items():
        doc: dict[str, Any] = {"schema": CARDS_SCHEMA, "faction": faction, "cards": cards}
        rel = f"cards/{faction}.cards.yaml"
        for problem in _schema_problems("cards.schema.json", doc, Path(rel)):
            plan.problems.append(_blame(problem, cardset, plan.ids))
        plan.writes[rel] = header + _dump(doc, flow=False)

    # decks
    for deck in cardset.decks:
        deck_doc: dict[str, Any] = {
            "schema": DECK_SCHEMA,
            "id": deck.id,
            "faction": deck.faction,
            "leader": plan.ids.get(deck.leader, deck.leader),
            "stratagem": plan.ids.get(deck.stratagem, deck.stratagem),
            "cards": [_Flow(id=plan.ids.get(c, c), count=n) for c, n in deck.cards],
        }
        rel = f"decks/{deck.id}.deck.yaml"
        plan.problems.extend(
            f"{deck.where}: {p}" for p in _schema_problems("decks.schema.json", deck_doc, Path(rel))
        )
        plan.writes[rel] = header + _dump(deck_doc, flow=False)
        plan.decks.append(deck.id)

    # translations: one file per locale; keys another file already holds stay there
    held = _held_keys(data_dir, locales, own_files)
    factions = list(dict.fromkeys([*cardset.factions, *by_faction]))
    tags = list(
        dict.fromkeys(
            [*cardset.tags, *(t for e in cardset.cards for t in _list(e.fields.get("tags")))]
        )
    )
    for locale in locales:
        lines: list[str] = []
        stubs = 0
        for entry in cardset.cards:
            cid = plan.ids[entry.key]
            stubs += _entry_line(lines, f"card.{cid}.name", entry.names, locale, entry.key)
            if locale in entry.texts:
                lines.append(f"card.{cid}.text: {_quote(entry.texts[locale])}")
        for kind, ids, names in (
            ("faction", factions, cardset.factions),
            ("tag", tags, cardset.tags),
        ):
            for item in ids:
                key = f"{kind}.{item}.name"
                if key in held[locale]:
                    if names.get(item, {}).get(locale):
                        plan.warnings.append(
                            f"{locale}: {key} is already in {held[locale][key]}; "
                            "the set's name is not used"
                        )
                    continue
                stubs += _entry_line(lines, key, names.get(item, {}), locale, item)
        plan.stubs[locale] = stubs
        rel = f"i18n/{locale}/{cardset.set_id}.cards.yaml"
        plan.writes[rel] = header + "\n".join(lines) + "\n"

    # the manifest, and what an earlier import wrote that this one no longer does
    files = sorted(plan.writes)
    plan.writes[manifest_path(cardset.set_id)] = _dump(
        {
            "schema": MANIFEST_SCHEMA,
            "set": cardset.set_id,
            "source": cardset.source.name,
            "ids": plan.ids,
            "files": files,
        },
        header="# Written by `opengwt-data import`: the ids this set's keys were given, and the\n"
        "# files it wrote. Commit it, so that a re-import keeps every id.\n",
        flow=False,
    )
    plan.deletes = sorted(f for f in own_files if f not in plan.writes)
    for rel in files:
        if (data_dir / rel).exists() and rel not in own_files and not replace:
            plan.problems.append(
                f"{data_dir / rel} exists and was not written by set {cardset.set_id}; "
                "pass --replace to overwrite it"
            )
    plan.generated = {loc: sum(1 for e in cardset.cards if loc not in e.texts) for loc in locales}
    return plan


def _list(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _existing_ids(data_dir: Path, own_files: set[str]) -> set[str]:
    ids: set[str] = set()
    for path in sorted((data_dir / "cards").glob("*.cards.yaml")):
        if f"cards/{path.name}" in own_files:
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        ids.update(str(k) for k in (doc.get("cards") or {}))
    return ids


def _assign_ids(
    cardset: CardSet,
    remembered: Mapping[str, str],
    existing: set[str],
    plan: Plan,
    id_start: int | None,
) -> None:
    """Explicit ids first, then the manifest's, then fresh ones: ``<prefix>-<number>`` from a
    block above every numbered id in use, skipping whatever is taken."""
    taken = set(existing)
    for entry in cardset.cards:
        if entry.id is not None:
            plan.ids[entry.key] = entry.id
            taken.add(entry.id)
    for entry in cardset.cards:
        if entry.id is None and entry.key in remembered:
            rid = str(remembered[entry.key])
            if rid in taken:
                plan.problems.append(f"{entry.where}: remembered id {rid} is now taken")
            plan.ids[entry.key] = rid
            taken.add(rid)
    if id_start is None:
        numbers = [int(m.group(1)) for i in existing if (m := NUMBERED_ID.match(i))]
        id_start = (max(numbers, default=0) // 1000 + 1) * 1000 + 1
    next_number: dict[str, int] = {}
    for entry in cardset.cards:
        if entry.key in plan.ids:
            continue
        kind = str(entry.fields.get("kind", "unit"))
        prefix = "t" if entry.fields.get("token") else PREFIX_BY_KIND.get(kind, "c")
        number = next_number.get(prefix, id_start)
        while f"{prefix}-{number:04d}" in taken:
            number += 1
        cid = f"{prefix}-{number:04d}"
        next_number[prefix] = number + 1
        taken.add(cid)
        plan.ids[entry.key] = cid
        plan.new_ids[entry.key] = cid


def _card_mapping(entry: CardEntry, ids: Mapping[str, str], plan: Plan) -> dict[str, Any]:
    """The card as a cards file holds it: fields in cards.md order, abilities' keys ``when``,
    ``if``, ``do`` first, and card keys in ``place_new_card`` resolved to ids."""
    out: dict[str, Any] = {}
    for name in CARD_FIELDS:
        if name in entry.fields and entry.fields[name] is not None:
            out[name] = entry.fields[name]
    out.update({k: v for k, v in entry.fields.items() if k not in out and v is not None})
    for name in ("activation", *LIST_FIELDS):
        if isinstance(out.get(name), dict | list):
            out[name] = _flow(out[name])
    abilities = out.get("abilities")
    if isinstance(abilities, list):
        resolved = []
        for ability in abilities:
            if not isinstance(ability, dict):
                resolved.append(ability)
                continue
            ordered = {k: _flow(ability[k]) for k in ABILITY_ORDER if k in ability}
            ordered.update({k: _flow(v) for k, v in ability.items() if k not in ordered})
            if ordered.get("do") == "place_new_card" and isinstance(ordered.get("card"), str):
                ordered["card"] = ids.get(ordered["card"], ordered["card"])
            resolved.append(ordered)
        out["abilities"] = resolved
    return out


def _entry_line(
    lines: list[str], key: str, names: Mapping[str, str], locale: str, handle: str
) -> int:
    """One translation line; a stub marked TODO, from the first locale that has the text, when
    this one lacks it. Returns 1 for a stub."""
    if names.get(locale):
        lines.append(f"{key}: {_quote(names[locale])}")
        return 0
    fallback = names.get(BASE_LOCALE) or next((names[k] for k in sorted(names)), None)
    lines.append(f"{key}: {_quote(fallback or f'TODO {handle}')}  {TODO}")
    return 1


def _held_keys(
    data_dir: Path, locales: Sequence[str], own_files: set[str]
) -> dict[str, dict[str, str]]:
    """Per locale, the keys translation files other than this set's hold, and where."""
    out: dict[str, dict[str, str]] = {}
    for locale in locales:
        out[locale] = {}
        for path in sorted((data_dir / "i18n" / locale).glob("*.yaml")):
            if f"i18n/{locale}/{path.name}" in own_files:
                continue
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(doc, dict):
                for key in doc:
                    out[locale][str(key)] = str(path)
    return out


def _blame(problem: str, cardset: CardSet, ids: Mapping[str, str]) -> str:
    """A schema problem about ``cards/<id>/…`` with the designer's key added."""
    keys = {cid: key for key, cid in ids.items()}
    match = re.search(r": cards/([a-z][a-z0-9-]*)(/|:)", problem)
    if match and match.group(1) in keys:
        return f"{problem} [key {keys[match.group(1)]}]"
    return problem


def _header(cardset: CardSet) -> str:
    return (
        f"# Written by `opengwt-data import` from {cardset.source.name} (set {cardset.set_id}).\n"
        "# Edit the source and import again; changes made here are overwritten.\n"
    )


def _quote(text: str) -> str:
    """A YAML double-quoted scalar: JSON's string syntax is a subset of it."""
    return json.dumps(text, ensure_ascii=False)


class _Flow(dict):  # type: ignore[type-arg]
    """A mapping written on one line, as the hand-written cards files write ability parameters."""


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        super().increase_indent(flow, False)  # lists indented under their key


def _represent_flow(dumper: yaml.SafeDumper, data: _Flow) -> yaml.Node:
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items(), flow_style=True)


class _FlowList(list):  # type: ignore[type-arg]
    """A list written on one line: ``rows``, ``statuses``, ``tags``."""


def _represent_flow_list(dumper: yaml.SafeDumper, data: _FlowList) -> yaml.Node:
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


_Dumper.add_representer(_Flow, _represent_flow)
_Dumper.add_representer(_FlowList, _represent_flow_list)


def _dump(doc: Mapping[str, Any], header: str = "", flow: bool | None = None) -> str:
    return header + yaml.dump(
        doc,
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=flow,
        width=100,
    )


def _flow(value: Any) -> Any:
    if isinstance(value, dict):
        return _Flow({k: _flow(v) for k, v in value.items()})
    if isinstance(value, list):
        return _FlowList(_flow(v) for v in value)
    return value


# --- validating and writing ------------------------------------------------------------------


def validate_plan(plan: Plan, data_dir: Path) -> list[str]:
    """Apply the plan to a copy of ``data_dir`` and compile it (cards.md §14): the schemas, the
    cross-file rules, deck legality and translation completeness, as ``load_data`` checks
    them. Problems name the real paths."""
    with tempfile.TemporaryDirectory(prefix="opengwt-import-") as tmp:
        copy = Path(tmp) / "data"
        shutil.copytree(data_dir, copy)
        _apply(plan, copy)
        try:
            load_data(copy)
        except DataError as e:
            return [p.replace(str(copy), str(data_dir)) for p in e.problems]
    return []


def apply_plan(plan: Plan, data_dir: Path) -> None:
    _apply(plan, data_dir)


def _apply(plan: Plan, data_dir: Path) -> None:
    for rel in plan.deletes:
        (data_dir / rel).unlink(missing_ok=True)
    for rel, text in plan.writes.items():
        target = data_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def import_cardset(
    source: Path,
    data_dir: Path,
    set_id: str | None = None,
    replace: bool = False,
    id_start: int | None = None,
    dry_run: bool = False,
) -> Plan:
    """Read, plan, validate and — unless ``dry_run`` or anything is wrong — write."""
    cardset = read_cardset(source, set_id)
    plan = plan_import(cardset, data_dir, replace, id_start)
    if not plan.problems:
        plan.problems.extend(validate_plan(plan, data_dir))
    if not plan.problems and not dry_run:
        apply_plan(plan, data_dir)
    return plan


def summary(plan: Plan, data_dir: Path) -> list[str]:
    """What an import did or would do, for people."""
    factions = ", ".join(f"{f} {n}" for f, n in plan.cards_by_faction.items())
    lines = [
        f"set {plan.set_id}: {sum(plan.cards_by_faction.values())} cards ({factions}), "
        f"{len(plan.decks)} decks"
    ]
    if plan.new_ids:
        lines.append("new ids: " + ", ".join(f"{k} → {v}" for k, v in plan.new_ids.items()))
    lines.append(
        "names to translate (TODO stubs): "
        + ", ".join(f"{loc} {n}" for loc, n in plan.stubs.items())
    )
    lines.append(
        "card texts generated from abilities: "
        + ", ".join(f"{loc} {n}" for loc, n in plan.generated.items())
    )
    lines.extend(f"write {data_dir / rel}" for rel in sorted(plan.writes))
    lines.extend(f"delete {data_dir / rel}" for rel in plan.deletes)
    lines.extend(f"warning: {w}" for w in plan.warnings)
    return lines


def preview_texts(plan: Plan, data_dir: Path, locale: str) -> list[str]:
    """The imported cards' texts in ``locale`` as the pack would carry them."""
    with tempfile.TemporaryDirectory(prefix="opengwt-import-") as tmp:
        copy = Path(tmp) / "data"
        shutil.copytree(data_dir, copy)
        _apply(plan, copy)
        data = load_data(copy)
        lib = load_library(copy / "cards")
    return [
        f"{cid} {data.i18n[locale].get(f'card.{cid}.name', '')}: "
        f"{data.i18n[locale].get(f'card.{cid}.text', '')}"
        for cid in plan.ids.values()
        if cid in lib
    ]
