"""The rules core imports the standard library and itself, nothing else (ADR 0002)."""

import ast
import sys
from pathlib import Path

import opengwt.core

CORE = Path(opengwt.core.__file__).parent


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_core_imports_only_stdlib() -> None:
    offenders: dict[str, set[str]] = {}
    for path in CORE.glob("*.py"):
        bad = {n for n in _imports(path) if n not in sys.stdlib_module_names and n != "opengwt"}
        if bad:
            offenders[path.name] = bad
    assert not offenders, offenders


def test_core_does_not_import_other_layers() -> None:
    for path in CORE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for layer in ("opengwt.data", "opengwt.bots", "opengwt.sim", "opengwt.server"):
            assert layer not in text, f"{path.name} mentions {layer}"
