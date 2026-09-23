# open-gwt server code base

Python 3.10.15 or newer, uv 0.12.5 or newer. Layers, enforced by import-linter:
`opengwt.core` (rules, standard library only) ← `opengwt.data` (YAML loading and validation)
← `opengwt.bots` ← `opengwt.sim` ← `opengwt.server` (M2).

```bash
uv sync                                   # environment and lockfile
uv run pytest -q                          # tests
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run opengwt-sim --matches 200 --replay-check 20 --data ../data
```

Design: `docs/adr/` and `docs/protocol/` at the repository root.
