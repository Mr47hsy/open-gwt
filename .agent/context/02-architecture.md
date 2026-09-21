# Intended architecture

> **Status: design intent.** No code exists yet (2026-09-22). This file records the shape the
> project is meant to take, so that early commits do not paint it into a corner. When code lands and
> disagrees with this file, the code wins — update this file in the same pull request.

## Three layers

```
rules core   pure library, no engine dependency, no I/O, no clock, no ambient randomness
    ↑
server       authoritative: owns the match, hides hidden information, validates every action
    ↑
client       Unity: renders state, collects input, sends intents. Decides nothing.
```

The direction of the arrows is the whole point: the client may *predict* an outcome for
responsiveness, but the server's result overwrites the prediction, and the rules core is the only
place that knows what the rules are.

## The determinism contract

A match is **a seed plus an ordered list of actions**. Replaying that log against the same core
version must reproduce the match exactly — same board, same hands, same result.

This is what makes tests, bug reports and bots practical, so the core must avoid everything that
breaks it:

- no wall-clock time (`DateTime.Now`, `Time.deltaTime`, timers) inside rules evaluation;
- no unseeded randomness — all randomness comes from the seeded PRNG the match carries;
- no iteration over unordered collections (hash sets, dictionaries) in a way that affects results;
- no floating point where integers will do;
- no dependency on machine locale, culture or platform;
- no reference-identity or allocation-order dependence.

A rules change that breaks replay of existing logs is a breaking change and must be called out in
the pull request.

## Hidden information

Hands, decks and upcoming draws live on the server and are never sent to a client that should not
see them. "The client filters it out before rendering" is not acceptable — a modified client would
then see everything. Serialise per-recipient views on the server.

## Where things belong

| Concern | Layer |
| --- | --- |
| What a card does | rules core |
| Whether a play is legal | rules core, enforced again on the server |
| Round/pass/tempo logic | rules core |
| Matchmaking, sessions, reconnect | server |
| Hidden-information filtering | server |
| Animation, layout, input, audio | client |
| Card art and text | client assets + data files |

If you find yourself writing a rule inside a `MonoBehaviour`, stop: it belongs in the core.
