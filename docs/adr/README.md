# Architecture decision records

One file per decision. A record is written once and not rewritten afterwards; when a decision
changes, a new record supersedes it and the old one's status line says so. Each record has the
same four sections: **Context**, **Decision**, **Consequences**, **Alternatives considered**.

Records are numbered in the order they were accepted. Numbers are never reused.

| # | Title | Status |
| --- | --- | --- |
| [0001](0001-python-server-unity-thin-client.md) | Python server, Unity thin client | accepted |
| [0002](0002-rules-core-pure-python-package.md) | Rules core as a zero-dependency Python package | accepted; PRNG clause superseded by 0010, testing on the newest Python superseded by 0012 |
| [0003](0003-card-effect-protocol-yaml.md) | Card effects as a YAML protocol with a closed vocabulary | accepted |
| [0004](0004-server-config-and-optional-backends.md) | Layered config and optional backends, no Nacos | accepted |
| [0005](0005-client-ui-toolkit.md) | UI Toolkit for the whole client UI | accepted |
| [0006](0006-i18n-keys-and-unity-localization.md) | Keys-only i18n with one message format rendered on both sides | accepted |
| [0007](0007-mvp-order-and-acceptance.md) | MVP order: core, then server, then client | accepted |
| [0008](0008-match-scaling-stateless-workers.md) | Match scaling: stateless workers over a shared match store | accepted |
| [0009](0009-two-row-standalone-ruleset.md) | Adopt the two-row standalone ruleset as the game's shape | accepted; PRNG clause superseded by 0010, compensation left out superseded by 0011 |
| [0010](0010-unpredictable-random-stream.md) | An unpredictable random stream for the rules core | accepted |
| [0011](0011-first-player-compensation.md) | Compensate the player who goes first: an extra redraw and a stratagem | accepted |
| [0012](0012-ci-on-the-python-floor-only.md) | Run the server's CI on the Python floor only | accepted |

## Writing a new record

1. Copy the section layout of an existing record.
2. Take the next number.
3. Add a row to the table above.
4. If the record changes a rule an agent relies on, update `.agent/context/` in the same pull
   request — those files summarise the current state, this directory records how it got there.
