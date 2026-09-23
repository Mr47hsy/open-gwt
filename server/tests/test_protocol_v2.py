"""The normative v2 protocol in docs/protocol — schemas and examples. Validates with the docs' own
schemas; test_schema_parity keeps the packaged copies identical."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
PROTOCOL = REPO / "docs" / "protocol"
EXAMPLES = PROTOCOL / "examples"


def _schema(name: str) -> dict[str, Any]:
    schema: dict[str, Any] = json.loads((PROTOCOL / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def _yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _problems(schema: dict[str, Any], doc: Any) -> list[str]:
    return [e.message for e in Draft202012Validator(schema).iter_errors(doc)]


def _example_cards() -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for path in sorted(EXAMPLES.glob("*.cards.yaml")):
        cards.update(_yaml(path)["cards"])
    return cards


def test_examples_are_valid() -> None:
    cards_schema = _schema("cards.schema.json")
    for path in sorted(EXAMPLES.glob("*.cards.yaml")):
        assert _problems(cards_schema, _yaml(path)) == [], path.name
    deck = _yaml(EXAMPLES / "starter-a.deck.yaml")
    assert _problems(_schema("decks.schema.json"), deck) == []
    cards = _example_cards()
    assert all(entry["id"] in cards for entry in deck["cards"])


def test_examples_use_every_vocabulary_word() -> None:
    defs = _schema("cards.schema.json")["$defs"]
    vocabulary = {
        "when": set(defs["trigger"]["enum"]),
        "do": set(defs["ability"]["properties"]["do"]["enum"]),
        "status": set(defs["status"]["enum"]),
        "effect": set(defs["rowEffect"]["enum"]),
        "units": set(defs["unitTarget"]["properties"]["units"]["enum"]),
        "row pick": set(defs["rowTarget"]["properties"]["pick"]["enum"]),
        "cards pick": set(defs["cardSource"]["properties"]["pick"]["enum"]),
        "where": set(defs["where"]["properties"]),
        "if": set(defs["conditions"]["properties"]),
        "activation": set(defs["activation"]["properties"]),
        "card key": set(defs["card"]["properties"]),
    }
    vocabulary["only"] = set(defs["do_clear_row_effect"]["properties"]["only"]["enum"])
    used: dict[str, set[str]] = {key: set() for key in vocabulary}

    def filters(where: dict[str, Any]) -> None:
        used["where"].update(where)
        used["status"].update(where.get("statuses_any", ()))
        used["status"].update(where.get("statuses_none", ()))

    for card in _example_cards().values():
        used["card key"].update(card)
        used["status"].update(card.get("statuses", ()))
        used["activation"].update(card.get("activation", {}))
        for ability in card.get("abilities", ()):
            used["when"].add(ability["when"])
            used["do"].add(ability["do"])
            conditions = ability.get("if", {})
            used["if"].update(conditions)
            for key in ("trigger_unit", "this"):
                filters(conditions.get(key, {}))
            filters(conditions.get("units_at_least", {}).get("where", {}))
            filters(ability.get("pool", {}))
            used["status"].update([ability["status"]] if "status" in ability else [])
            used["status"].update(ability.get("statuses", ()))
            used["effect"].update([ability["effect"]] if "effect" in ability else [])
            used["only"].update([ability["only"]] if "only" in ability else [])
            if "target" in ability:
                used["units"].add(ability["target"]["units"])
                filters(ability["target"].get("where", {}))
            if "row_target" in ability:
                used["row pick"].add(ability["row_target"]["pick"])
            if "cards" in ability:
                used["cards pick"].add(ability["cards"]["pick"])
                filters(ability["cards"].get("where", {}))
    unused = {key: sorted(words - used[key]) for key, words in vocabulary.items()}
    assert {key: words for key, words in unused.items() if words} == {}


def test_example_translations_cover_the_example_cards() -> None:
    table = _yaml(EXAMPLES / "i18n-en-cards.yaml")
    cards = _example_cards()
    tags = {tag for card in cards.values() for tag in card.get("tags", ())}
    required = {f"card.{cid}.{field}" for cid in cards for field in ("name", "text")}
    required |= {f"tag.{tag}.name" for tag in tags}
    assert required <= set(table)


UNIT = {"kind": "unit", "color": "bronze", "provisions": 4, "power": 3}


@pytest.mark.parametrize(
    "card",
    [
        # a parameter that belongs to another action
        {**UNIT, "abilities": [{"when": "on_play", "do": "draw", "target": {"units": "this"}}]},
        # a player is only asked during on_play and on_activate
        {
            **UNIT,
            "abilities": [
                {
                    "when": "on_turn_start",
                    "do": "damage",
                    "amount": 1,
                    "target": {"units": "chosen", "side": "opponent"},
                }
            ],
        },
        # the trigger unit exists only for on_ally_played
        {
            **UNIT,
            "abilities": [
                {"when": "on_play", "do": "boost", "amount": 1, "target": {"units": "trigger_unit"}}
            ],
        },
        # the side a card stands on is the board's to say, never an action's
        {
            **UNIT,
            "abilities": [
                {
                    "when": "on_play",
                    "do": "add_status",
                    "status": "on_enemy_side",
                    "target": {"units": "this"},
                }
            ],
        },
        # a choice is only asked during on_play and on_activate: create offers a choice
        {
            **UNIT,
            "abilities": [{"when": "on_round_end", "do": "create", "pool": {"color": "gold"}}],
        },
        # a timed status without its timer
        {
            **UNIT,
            "abilities": [
                {
                    "when": "on_play",
                    "do": "add_status",
                    "status": "bleeding",
                    "target": {"units": "this"},
                }
            ],
        },
        # continuous effects only while on the board, and only there
        {
            **UNIT,
            "abilities": [
                {"when": "on_play", "do": "continuous_boost", "amount": 1, "scope": "row"}
            ],
        },
        # specials have no power; leaders only activate
        {**UNIT, "kind": "special", "abilities": [{"when": "on_play", "do": "draw"}]},
        {"kind": "leader", "provision_bonus": 15, "abilities": [{"when": "on_play", "do": "draw"}]},
        # a deck card needs a colour; activation needs an activated ability
        {"kind": "unit", "provisions": 4, "power": 3},
        {**UNIT, "activation": {"charges": 2}},
    ],
)
def test_schema_rejects(card: dict[str, Any]) -> None:
    doc = {"schema": "opengwt.cards/2", "faction": "test-x", "cards": {"u-0001": card}}
    assert _problems(_schema("cards.schema.json"), doc) != []
