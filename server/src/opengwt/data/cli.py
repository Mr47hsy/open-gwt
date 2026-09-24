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


def card_texts(
    data_dir: Path,
    locales: Sequence[str] = (),
    cards: Sequence[str] = (),
    ignore_explicit: bool = False,
) -> list[str]:
    """One line per card and locale: the text the content pack carries, and whether it is the
    explicit one of ``data/i18n`` or generated from the card's abilities (i18n.md §10)."""
    from opengwt.data.cardtext import CardText
    from opengwt.data.loader import load_i18n, load_library

    lib = load_library(data_dir / "cards")
    tables = load_i18n(data_dir / "i18n")
    generator = CardText(tables)
    lines: list[str] = []
    for cid in cards or list(lib):
        if cid not in lib:
            raise SystemExit(f"unknown card {cid}")
        for locale in locales or sorted(tables):
            explicit = tables.get(locale, {}).get(f"card.{cid}.text")
            if explicit is not None and not ignore_explicit:
                lines.append(f"{cid} {locale} explicit: {explicit}")
                continue
            text, missing = generator.text(locale, lib[cid])
            note = f"  [missing: {', '.join(missing)}]" if missing else ""
            lines.append(f"{cid} {locale} generated: {text}{note}")
    return lines


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
    texts = sub.add_parser(
        "card-text", help="print each card's text: explicit, or generated from its abilities"
    )
    texts.add_argument("--locale", action="append", default=[], help="only this locale")
    texts.add_argument("--card", action="append", default=[], help="only this card id")
    texts.add_argument(
        "--ignore-explicit",
        action="store_true",
        help="generate even where data/i18n has an explicit text, to compare the two",
    )
    texts.add_argument("--data", dest="data_sub", default=None, help=argparse.SUPPRESS)
    imp = sub.add_parser(
        "import",
        help="turn a card set (YAML, JSON or CSV) into data/ files, validated before writing",
    )
    imp.add_argument("source", help="the card set file: .yaml, .yml, .json or .csv")
    imp.add_argument("--set", dest="set_id", default=None, help="set id (required for a CSV)")
    imp.add_argument("--dry-run", action="store_true", help="validate and report, write nothing")
    imp.add_argument(
        "--replace", action="store_true", help="overwrite files this set did not write before"
    )
    imp.add_argument("--id-start", type=int, default=None, help="first number of new card ids")
    imp.add_argument("--preview", default=None, help="print the imported cards' texts in LOCALE")
    imp.add_argument("--data", dest="data_sub", default=None, help=argparse.SUPPRESS)
    check = sub.add_parser(
        "check-set",
        help="check each card of a set on its own: schema problems and generated text, as JSON",
    )
    check.add_argument("source", help="the card set file: .yaml, .yml, .json or .csv")
    check.add_argument("--set", dest="set_id", default="draft", help="set id for a CSV")
    check.add_argument("--locale", action="append", default=[], help="only this locale")
    check.add_argument("--data", dest="data_sub", default=None, help=argparse.SUPPRESS)
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
    elif args.command == "import":
        return _import(args, data_dir)
    elif args.command == "check-set":
        return _check_set(args, data_dir)
    elif args.command == "card-text":
        for line in card_texts(data_dir, args.locale, args.card, args.ignore_explicit):
            print(line)
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


def _import(args: argparse.Namespace, data_dir: Path) -> int:
    from opengwt.data.importer import CardSetError, import_cardset, preview_texts, summary

    try:
        plan = import_cardset(
            Path(args.source),
            data_dir,
            set_id=args.set_id,
            replace=args.replace,
            id_start=args.id_start,
            dry_run=args.dry_run,
        )
    except CardSetError as e:
        print("the card set cannot be read:", file=sys.stderr)
        for problem in e.problems:
            print("  " + problem, file=sys.stderr)
        return 2
    for line in summary(plan, data_dir):
        print(line)
    if plan.problems:
        print("nothing was written; problems:", file=sys.stderr)
        for problem in plan.problems:
            print("  " + problem, file=sys.stderr)
        return 1
    if args.preview:
        for line in preview_texts(plan, data_dir, args.preview):
            print(line)
    print("dry run: nothing was written" if args.dry_run else "done; names must be original")
    return 0


def _check_set(args: argparse.Namespace, data_dir: Path) -> int:
    from opengwt.data.importer import CardSetError, check_cards, read_cardset

    try:
        cardset = read_cardset(Path(args.source), args.set_id)
    except CardSetError as e:
        print(json.dumps({"read_problems": e.problems}, ensure_ascii=False, indent=1))
        return 2
    cards = check_cards(cardset, data_dir, args.locale)
    print(json.dumps({"cards": cards}, ensure_ascii=False, indent=1))
    return 1 if any(c["problems"] for c in cards) else 0


def _find_data() -> Path:
    for candidate in (Path("data"), Path("..") / "data"):
        if (candidate / "cards").is_dir():
            return candidate
    raise SystemExit("cannot find data/; pass --data")


if __name__ == "__main__":
    sys.exit(main())
