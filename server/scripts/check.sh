#!/usr/bin/env sh
# Every check CI runs on the server code base, in CI's order. Run from server/ before a pull request.
set -eu
cd "$(dirname "$0")/.."
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest -q
uv run opengwt-data conformance-json --data ../data --check
uv run opengwt-data client-i18n --data ../data --out ../client/Assets/OpenGwt/Resources/i18n --check
