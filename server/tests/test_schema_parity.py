"""The schemas shipped in the package are byte-identical to the normative ones in docs/protocol."""

import json
from pathlib import Path

from opengwt.data.loader import SCHEMA_DIR

REPO = Path(__file__).resolve().parents[2]


def test_packaged_schemas_match_docs() -> None:
    for name in ("cards.schema.json", "decks.schema.json"):
        packaged = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        normative = json.loads((REPO / "docs" / "protocol" / name).read_text(encoding="utf-8"))
        assert packaged == normative, name
