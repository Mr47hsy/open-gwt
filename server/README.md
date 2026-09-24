# open-gwt server code base

Python 3.10.15 or newer, uv 0.12.5 or newer. Layers, enforced by import-linter:
`opengwt.core` (rules, standard library only) ← `opengwt.data` (YAML loading and validation)
← `opengwt.bots` ← `opengwt.sim` ← `opengwt.server` (M2).

```bash
uv sync                                   # environment and lockfile
scripts/check.sh                          # everything CI runs, in CI's order
uv run pytest -q                          # tests
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run opengwt-sim --matches 200 --replay-check 20 --data ../data
uv run opengwt-data card-text --data ../data             # every card's text, explicit or generated
uv run opengwt-data import set.yaml --data ../data --dry-run   # import a card set (docs/protocol/import.md)
uv run opengwt-server                     # serve on 127.0.0.1:8000 with SQLite and memory backends
uv run opengwt-server migrate             # apply migrations and exit
uv run opengwt-server config              # print the effective configuration
```

Configuration is three layers: defaults, an optional YAML file named by `OPENGWT_CONFIG`, and
`OPENGWT_*` environment variables (ADR 0004). The zero-dependency default runs one worker process;
`OPENGWT_DATABASE_URL=postgresql+asyncpg://…` needs `uv sync --extra postgres`. The server refuses
to start with more than one worker while the match store or the event bus is `memory://`.

Quick check once it runs:

```bash
curl -s -X POST localhost:8000/auth/guest -H 'content-type: application/json' -d '{}'
```

Design: `docs/adr/` and `docs/protocol/` at the repository root.

Bots and balance: `opengwt-sim` plays `random`, `greedy` or `search` bots — the last samples
worlds consistent with what its player sees and plays its best candidates out to the round's
end (`--search-worlds`, `--search-width`). With `--card-report` or `--report balance.csv` it
reports each card's win-rate contribution — the win rate when drawn minus when not drawn — its
play rate and its points per play and per provision; `--decks all --mirrors` plays every pairing
of the decks and `--jobs 0` uses every CPU.

```bash
uv run opengwt-sim --bot-a search --bot-b greedy --matches 40 --jobs 0 --data ../data
uv run opengwt-sim --bot-a greedy --bot-b greedy --decks all --mirrors --matches 500 \
    --jobs 0 --card-report --report balance.csv --data ../data
```
