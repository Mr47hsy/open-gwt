"""``opengwt-data``: content tooling that does not belong in the server process."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

CONFORMANCE_SCHEMA = "opengwt.i18n-conformance/1"


def conformance_json(data_dir: Path) -> str:
    """The conformance suite as JSON, exactly the YAML's content, for renderers without YAML."""
    doc = yaml.safe_load((data_dir / "i18n" / "conformance.yaml").read_text(encoding="utf-8"))
    if doc.get("schema") != CONFORMANCE_SCHEMA:
        raise ValueError(f"unexpected conformance schema {doc.get('schema')!r}")
    return json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


CLIENT_PREFIXES = ("ui.", "choice.", "error.")


def client_i18n(data_dir: Path) -> dict[str, str]:
    """Per locale, the strings the client needs before it has a server, as JSON text."""
    from opengwt.data.loader import load_i18n

    out: dict[str, str] = {}
    for locale, table in sorted(load_i18n(data_dir / "i18n").items()):
        subset = {k: v for k, v in sorted(table.items()) if k.startswith(CLIENT_PREFIXES)}
        out[locale] = json.dumps(subset, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opengwt-data", description=__doc__)
    parser.add_argument("--data", default=None, help="path to the data/ directory")
    sub = parser.add_subparsers(dest="command", required=True)
    conf = sub.add_parser("conformance-json", help="write data/i18n/conformance.json from the YAML")
    conf.add_argument("--check", action="store_true", help="fail if the JSON is stale instead")
    conf.add_argument("--data", dest="data_sub", default=None, help=argparse.SUPPRESS)
    client = sub.add_parser(
        "client-i18n", help="export the ui/error/choice strings as JSON for the client build"
    )
    client.add_argument("--out", required=True, help="directory for <locale>.json files")
    client.add_argument("--check", action="store_true", help="fail if any file is stale instead")
    client.add_argument("--data", dest="data_sub", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    explicit = args.data or getattr(args, "data_sub", None)
    data_dir = Path(explicit) if explicit else _find_data()
    if args.command == "conformance-json":
        target = data_dir / "i18n" / "conformance.json"
        fresh = conformance_json(data_dir)
        if args.check:
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            if current != fresh:
                print(f"{target} is stale; run `opengwt-data conformance-json`", file=sys.stderr)
                return 1
            print(f"{target} is up to date")
            return 0
        target.write_text(fresh, encoding="utf-8")
        print(f"wrote {target}")
    elif args.command == "client-i18n":
        out = Path(args.out)
        stale = []
        for locale, text in client_i18n(data_dir).items():
            target = out / f"{locale}.json"
            if args.check:
                current = target.read_text(encoding="utf-8") if target.exists() else ""
                if current != text:
                    stale.append(str(target))
                continue
            out.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            print(f"wrote {target}")
        if stale:
            print(
                "stale: " + ", ".join(stale) + "; run `opengwt-data client-i18n`", file=sys.stderr
            )
            return 1
    return 0


def _find_data() -> Path:
    for candidate in (Path("data"), Path("..") / "data"):
        if (candidate / "cards").is_dir():
            return candidate
    raise SystemExit("cannot find data/; pass --data")


if __name__ == "__main__":
    sys.exit(main())
