"""The schemas shipped in the package are byte-identical to the normative ones in docs/protocol."""

import json
from pathlib import Path

import pytest

from opengwt.data.loader import SCHEMA_DIR

REPO = Path(__file__).resolve().parents[2]


# ADR 0009 phase A wrote protocol v2 into docs/protocol before the code; the package keeps the v1
# schemas until phase B. Strict: once they match again this fails, and the marker must go.
@pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="docs are v2, package v1 until ADR 0009 phase B"
)
def test_packaged_schemas_match_docs() -> None:
    for name in ("cards.schema.json", "decks.schema.json"):
        packaged = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        normative = json.loads((REPO / "docs" / "protocol" / name).read_text(encoding="utf-8"))
        assert packaged == normative, name
