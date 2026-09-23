"""``opengwt-server``: serve, migrate, or print the effective configuration."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from opengwt.server.config import ConfigError, Settings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opengwt-server", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the server (default)")
    sub.add_parser("migrate", help="apply database migrations and exit")
    sub.add_parser("config", help="print the effective configuration")
    args = parser.parse_args(argv)
    command = args.command or "serve"

    try:
        settings = Settings()
        settings.validate_deployment()
    except ConfigError as e:
        print(f"configuration error: {e}", file=sys.stderr)
        return 2

    if command == "config":
        for name, value in settings.model_dump().items():
            shown = "***" if name == "auth_secret" else value
            print(f"{name} = {shown}")
        return 0
    if command == "migrate":
        from opengwt.server.db.session import make_engine, upgrade_to_head

        async def _migrate() -> None:
            engine = make_engine(settings.database_url)
            try:
                await upgrade_to_head(engine)
            finally:
                await engine.dispose()

        asyncio.run(_migrate())
        print("migrations applied")
        return 0

    import uvicorn

    uvicorn.run(
        "opengwt.server.app:app_factory",
        factory=True,
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        log_level=settings.log_level.lower(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
