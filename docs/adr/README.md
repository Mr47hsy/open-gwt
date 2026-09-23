# Architecture decision records

One file per decision. A record is written once and not rewritten afterwards; when a decision
changes, a new record supersedes it and the old one's status line says so. Each record has the
same four sections: **Context**, **Decision**, **Consequences**, **Alternatives considered**.

Records are numbered in the order they were accepted. Numbers are never reused.

| # | Title | Status |
| --- | --- | --- |
| [0001](0001-python-server-unity-thin-client.md) | Python server, Unity thin client | accepted |
| [0002](0002-rules-core-pure-python-package.md) | Rules core as a zero-dependency Python package | accepted |
| [0003](0003-card-effect-protocol-yaml.md) | Card effects as a YAML protocol with a closed vocabulary | accepted |
| [0004](0004-server-config-and-optional-backends.md) | Layered config and optional backends, no Nacos | accepted |
| [0005](0005-client-ui-toolkit.md) | UI Toolkit for the whole client UI | accepted |
| [0006](0006-i18n-keys-and-unity-localization.md) | Keys-only i18n with one message format rendered on both sides | accepted |
| [0007](0007-mvp-order-and-acceptance.md) | MVP order: core, then server, then client | accepted |
| [0008](0008-match-scaling-stateless-workers.md) | Match scaling: stateless workers over a shared match store | accepted |

## Writing a new record

1. Copy the section layout of an existing record.
2. Take the next number.
3. Add a row to the table above.
4. If the record changes a rule an agent relies on, update `.agent/context/` in the same pull
   request — those files summarise the current state, this directory records how it got there.
