# Project memory index

Durable facts about open-gwt: decisions taken, status, and questions still open. One fact per file.
Background that is not a decision lives in `../context/` instead.

- [Project status](project-status.md) — docs-only repository; decisions and protocols written, `client/`, `server/`, `data/` not created yet
- [Server: Python, client: thin](server-python-thin-client.md) — rules core is a Python package in the server; the Unity client runs no rules and needs a server
- [Card protocol in YAML](card-protocol-yaml.md) — closed vocabulary, JSON Schema, compiled to a content pack the server serves
- [Optional backends, no Nacos](server-optional-backends.md) — layered config; SQLite / memory defaults; PostgreSQL, MySQL, Redis as extras; single worker
- [Client UI Toolkit](client-ui-toolkit.md) — all client UI as UXML/USS, no third-party UI dependency in the MVP
- [MVP order](mvp-order.md) — core → server → client, with acceptance criteria per milestone
- [Branch strategy](branch-strategy.md) — git-flow: `release` is the default publish branch, `develop` the integration branch
- [Branch protection](branch-protection.md) — how the policy is enforced; two rules need CI because GitHub cannot express them
- [Licensing split](licensing-split.md) — MIT for code, CC BY 4.0 for original assets
- [Trilingual docs](docs-trilingual.md) — en / zh-CN / ru, English is the source of truth
- [Legal red lines](legal-red-lines.md) — no CDPR assets, clean-room only; non-negotiable

Update a file when reality changes, and delete it when it stops being true. Keep entries here to one
line each.
