# ADR 0010: An unpredictable random stream for the rules core

- Status: accepted, 2026-09-23
- Deciders: project owner
- Supersedes: the PRNG clause of [ADR 0002](0002-rules-core-pure-python-package.md) (PCG32), and
  in [ADR 0009](0009-two-row-standalone-ruleset.md) the words that keep the deterministic PRNG and
  the replay record as they are. Refines ADR 0002's entity-id clause.
- Related: [ADR 0008](0008-match-scaling-stateless-workers.md)

## Context

A match is a seed plus an ordered list of intents, and the seed decides every shuffle. Since pull
request #10 the seed no longer reaches clients, but a client does not need to receive it to learn
it:

- the server draws it with `secrets.randbits(31)`, about 2.1 × 10⁹ candidates;
- PCG32 and the shuffle are published in this repository, and PCG32 was never designed to hide
  its seed from someone who sees its output;
- instance ids are handed out in deck-list order before the shuffle, so a player's own
  `card_drawn` events give the shuffled positions of their opening hand.

Measured on the starter decks (34 cards each): the positions of an opening hand carry 48.8 bits,
and the card identities in draw order alone still carry 41.5–43.7 bits — both well above the 31
bits of the seed, so one opening hand singles the seed out. Replaying the shuffle for every
candidate takes about eleven core-hours in pure Python and far less in compiled code, and a table
over all seeds can be computed once and reused for every match. With the seed a player knows the
order of both decks — in a bot match the bot's whole hand, since starter decks are public — and
the result of every later reshuffle.

The server-hosted bot is seeded from the match seed as well, so its visible choices are a second
way to test a guess. And `_bot_moves` builds a new bot on each call, which restarts the random
bot's stream after every human action.

The v2 ruleset (ADR 0009) raises the stakes: draws and redraws every round and random targets all
come from the same stream.

## Decision

This lands in the v2 core as part of ADR 0009 phase B, which already breaks replay of v1 records
and regenerates the golden. The v1 core is not patched; the owner accepts the exposure of a core
that phase B replaces.

- **Seed.** 256 bits from `secrets.token_bytes(32)`, stored and recorded as 64 lowercase hex
  characters. It stays on the server until the match is over; the replay record of a finished
  match is the only place it is returned.
- **Stream.** The core's generator becomes SHA-256 in counter mode: block `n` is
  `SHA-256(label ‖ seed ‖ n)` with `n` as eight big-endian bytes, and each block yields eight
  32-bit big-endian words in order. `below` keeps rejection sampling and `shuffle` stays
  Fisher-Yates, so the engine's call sites do not change. `hashlib` is standard library, so the
  zero-dependency rule of ADR 0002 holds. `MatchState` carries the block counter and the position
  inside the current block in place of PCG32's `state` and `inc`.
- **One stream per purpose.** The engine, instance ids and the bot each use their own `label`.
  Output of one stream says nothing about another.
- **Instance ids.** Still driven by a counter in the state, as ADR 0002 requires, but rendered
  through the id stream, so an id reveals neither a card's deck-list position nor when it was
  drawn. A collision is skipped deterministically. The client does not parse ids today.
- **Bot.** A server-hosted bot draws from its own stream, labelled with the index of the decision
  in the intent log. It keeps no state between calls (ADR 0008), its choices say nothing about the
  engine stream, and the per-call restart goes away. The simulator may keep integer seeds for its
  own bots.
- **Pinned by tests.** Phase B adds reference vectors for each stream to `test_rng.py` and a test
  that no event, view or error detail carries the seed. The exact label strings and id length are
  fixed there.

## Consequences

- A v1 record (`opengwt.record/1`) does not replay on the v2 core. Records become
  `opengwt.record/2` with a hex seed. This coincides with the deletion of the v1 golden in phase
  B, and the phase B pull request says so. Finished v1 matches stay in the database as history.
- `matches.seed` changes from an integer to a 64-character string, with a migration in phase B.
  Snapshots of live matches carry the new RNG fields, so deploying phase B drains or abandons the
  matches in flight — protocol v2 requires that anyway.
- Cost: dealing two 34-card decks and tossing the coin took 33.7 µs with the SHA-256 stream and
  36.0 µs with pure-Python PCG32 (Apple M1, Python 3.10); `hashlib` runs in C.
- Learning the seed from play becomes as hard as inverting SHA-256 or searching 2^256 seeds. What
  a player is shown — their own hand and draws — does not change; they only lose the ability to
  predict what they have not been shown.
- The seed is a secret the server keeps: not in logs, events, views or error details.
- Until phase B merges, `.agent/context/02-architecture.md` describes PCG32 as the v1 generator
  and this stream as the v2 one.

## Alternatives considered

- **Keep PCG32 and widen the seed to 63 bits.** No replay break and a one-column migration, and
  exhaustive search becomes about 4 × 10⁹ times harder. But PCG32's state is 64 bits with a fixed
  increment and makes no claim of unpredictability, so the result would rest on "no attack known"
  rather than on a primitive built for the job. It would have been the v1 stopgap; the owner chose
  not to patch v1.
- **Only hide positions: opaque ids, or an unordered hand.** Not enough on their own: card
  identities in draw order carry 41–44 bits, an unordered opening hand still 21–23, and every
  redraw and every card the opponent plays adds more. Opaque ids are kept as defence in depth.
- **BLAKE2b in keyed mode, or HMAC-DRBG.** As strong, and also in the standard library. SHA-256
  is chosen because every platform has it, .NET included, should a tool outside Python ever
  replay a record. ChaCha20 would do as well but is not in the standard library.
- **`secrets` or `random.SystemRandom` inside the core.** Unpredictable but not reproducible; it
  breaks the determinism contract.
- **Give the bot its own stored seed.** Works, but it is one more secret to store; a label on the
  match seed gives the same independence.
- **Fix it in v1 now.** Declined by the owner: phase B replaces the v1 core, data and golden.
