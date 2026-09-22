# ADR 0004: Layered configuration and optional backends, no Nacos

- Status: accepted, 2026-09-22
- Deciders: project owner
- Related: [ADR 0001](0001-python-server-unity-thin-client.md)

## Context

This is an open-source game whose players and contributors run the server themselves, often on a
laptop, to play or to test a change. The owner's reference backend uses Nacos as a configuration
centre, Redis as a Celery broker and MySQL as the database. Nacos is a Java service; requiring it
to start a game server is too heavy for that audience, and the owner asked for something lighter
with every infrastructure dependency optional and switchable.

## Decision

### Configuration

Three layers, later ones override earlier ones:

1. defaults in code;
2. an optional YAML file, path given by `OPENGWT_CONFIG` (default: none);
3. environment variables with the prefix `OPENGWT_`, nested keys joined by `__`.

Implemented with pydantic-settings and its YAML source. No configuration service. Hot reload is
not an MVP feature; if it is ever needed it is a file watcher, and a remote provider such as Nacos
could be added behind the same settings model as an optional layer — it is not built now.

### Backends chosen by URL

| Concern | Setting | Default | Optional |
| --- | --- | --- | --- |
| Database | `database_url` | `sqlite+aiosqlite:///./opengwt.db` | PostgreSQL via `asyncpg`, MySQL via `asyncmy` |
| Cache | `cache_url` | `memory://` | `redis://…` |
| Background tasks | `tasks` | `inline` (asyncio in-process) | a queue such as Taskiq or Celery, later |
| Live match state | `match_store` | `memory` | a shared store, later |

- Database access goes through SQLAlchemy 2.0 async; one URL selects the dialect. Migrations
  (Alembic) use only portable column types, store structured data in a generic `JSON` column, and
  are run against SQLite **and** PostgreSQL in CI so that nothing dialect-specific slips in.
- Cache and task runner are small interfaces with a memory implementation and, where it exists,
  a Redis-backed one. Selection is by URL scheme or by name; no code outside the backend module
  knows which one is active.
- Optional drivers are packaging extras (`postgres`, `mysql`, `redis`). The default install has
  no service dependency at all: one command starts a server you can play against.

### Process model

Live matches are held in memory by the process that hosts them. Until a shared match store
exists, **the server runs as a single worker process**. Multi-worker deployment (several uvicorn
or gunicorn workers) would split matches across processes that cannot see each other; this
constraint is documented in the deployment notes and enforced by the default run command.

## Consequences

- `git clone`, `uv sync`, run — no Docker, no database server, no config centre.
- Production deployments switch to PostgreSQL and Redis by changing two URLs.
- Horizontal scaling of live matches is deliberately deferred; the pure core (ADR 0002) makes a
  later move to a shared store or a dedicated match-worker process a server change only.
- Celery is not part of the MVP. The reference backend's rule that a process must not fork after
  loading configuration is therefore moot here for now; it returns if a forking worker is added.

## Alternatives considered

- **Nacos as in the reference backend.** Proven in the owner's other project, but a Java service
  is the wrong entry price for an open-source game server. Rejected.
- **Celery from day one.** There is no MVP task that needs a broker; replay verification and
  statistics run inline. Rejected for now, easy to add behind the `tasks` setting.
- **Environment variables only, no file.** Simpler, but a checked-in example YAML is a better
  onboarding document than a list of variable names. Both are kept.
