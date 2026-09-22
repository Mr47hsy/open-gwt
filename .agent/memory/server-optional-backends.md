---
name: server-optional-backends
description: Server config is defaults → optional YAML → env vars, no Nacos; database, cache, tasks and match store are chosen by URL with zero-dependency defaults.
metadata:
  type: project
---

Decided 2026-09-22 (`docs/adr/0004`): pydantic-settings with code defaults, an optional YAML file
(`OPENGWT_CONFIG`) and `OPENGWT_`-prefixed environment variables. Backends by URL: SQLite by
default with PostgreSQL and MySQL as extras; `memory://` cache with Redis optional; inline asyncio
tasks with a queue optional later; in-memory match store. Live matches require a single worker
process until a shared store exists. Migrations use portable types and run on SQLite and PostgreSQL
in CI.

**Why:** players and contributors run the server on a laptop; Nacos (a Java service) and a Celery
broker are the wrong entry price. The owner asked for every infrastructure dependency to be optional
and switchable.

**How to apply:** do not add a required service. New infrastructure goes behind a small interface
with a memory implementation first. Do not add multi-worker run commands. See
[[server-python-thin-client]].
