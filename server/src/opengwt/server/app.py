"""Application assembly. ``create_app`` wires settings, content, database, backends and routers;
``app_factory`` is what ``uvicorn --factory`` and the CLI use."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from opengwt.server.backends import InlineTaskRunner, make_cache, make_event_bus, make_match_store
from opengwt.server.config import Settings
from opengwt.server.db.session import make_engine, make_session_factory, upgrade_to_head
from opengwt.server.errors import register_exception_handlers
from opengwt.server.routers import auth, content, decks, health, matches, ws
from opengwt.server.services.content import load_content
from opengwt.server.services.matches import MatchService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logging.basicConfig(level=settings.log_level.upper())
    loaded = load_content(settings.resolved_data_dir())
    app.state.content = loaded
    app.state.renderer = loaded.renderer
    engine = make_engine(settings.database_url)
    if settings.auto_migrate:
        await upgrade_to_head(engine)
    app.state.engine = engine
    app.state.sessions = make_session_factory(engine)
    tasks = InlineTaskRunner()
    app.state.tasks = tasks
    app.state.cache = make_cache(settings.cache_url)
    service = MatchService(
        content=loaded,
        store=make_match_store(settings.match_store_url),
        bus=make_event_bus(settings.event_bus_url, settings.event_history),
        sessions=app.state.sessions,
        tasks=tasks,
        settings=settings,
    )
    app.state.matches = service
    if settings.turn_timeout_seconds > 0:
        interval = min(1.0, settings.turn_timeout_seconds)
        tasks.spawn(service.run_timers(interval), name="turn-timers")
    logger.info(
        "open-gwt server: env=%s db=%s store=%s bus=%s pack=%s",
        settings.env,
        settings.database_url.split("://")[0],
        settings.match_store_url,
        settings.event_bus_url,
        loaded.pack_hash[:19],
    )
    try:
        yield
    finally:
        await tasks.shutdown()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.validate_deployment()
    app = FastAPI(title="open-gwt", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    register_exception_handlers(app)
    for module in (health, auth, content, decks, matches, ws):
        app.include_router(module.router)
    return app


def app_factory() -> FastAPI:
    return create_app()
