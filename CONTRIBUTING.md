# Contributing to open-gwt

**English** · [简体中文](CONTRIBUTING.zh-CN.md) · [Русский](CONTRIBUTING.ru.md)

Contributions of every kind are welcome: rules, card effects, match bots, the client, documentation
and original art.

## 1. The two non-negotiable rules

These keep the project legally clean. A pull request that breaks either of them is closed, no
discussion needed.

### No CD PROJEKT RED assets

Pull requests containing art, audio, models, card names, character names or flavour text extracted
or imitated from Gwent or *The Witcher* will be closed.

- **Not accepted:** ripped card art, sound effects or music; copied card names, character names,
  faction names or flavour text; art drawn to imitate a specific official card or character.
- **Accepted:** original art and audio you made yourself, and original names and flavour text
  written for this project.

### Clean-room implementations only

Implement features from public rules descriptions and from observed in-game behaviour. Do not submit
code decompiled or disassembled from an official client.

- **Not accepted:** decompiled or disassembled code, dumped data files, internal identifiers or
  constants taken from official binaries.
- **Accepted:** implementations written from public wikis, patch notes, rules explanations, videos
  and your own play experience — mechanics themselves are not copyrightable, specific expression is.

If you are unsure whether something crosses the line, open an issue and ask *before* writing the code.

## 2. Where to start

- **Rules core** — card and ability mechanics in the engine-agnostic core, with tests.
- **Card effects** — individual effects expressed in terms of the core's primitives.
- **Bots** — opponents that play the game; they run against the same core the server runs.
- **Client** — the Unity front end: rendering, input, UX, platform support.
- **Docs** — rules notes, the client/server protocol, design decisions.
- **Art & audio** — original work only, see the licensing section below.

Good first steps: open an issue describing what you want to work on, so nobody duplicates effort.

## 3. Development conventions

- **Keep rules out of the engine.** The rules core has no engine dependency. Unity code renders
  state and sends intents; it never decides an outcome.
- **Keep the core deterministic.** No wall-clock time, no unseeded randomness, no iteration over
  unordered collections in ways that affect results, no floating-point where integers will do. A
  seed plus an action log must reproduce a match exactly.
- **The server is authoritative.** The client may predict for responsiveness, but the server's
  result wins. Hidden information (hands, decks, upcoming draws) never gets sent to a client that
  should not see it.
- **Tests come with rules changes.** A new card effect or rules fix should come with a test that
  fails before the change and passes after it.

## 4. Pull requests

1. Fork the repository and create a branch off `develop`. Open your pull request against
   `develop` — never against `release`.
2. Keep each pull request focused on one thing; a rules change and a client refactor belong in
   separate pull requests.
3. Describe *what* changed and *why*. For a rules change, say which public source or observed
   behaviour you based it on.
4. Make sure the build and tests pass before asking for review.
5. Every pull request needs the owner's approving review before it can be merged. Neither branch
   accepts direct pushes.

### Branches

| Branch | Purpose |
| --- | --- |
| `develop` | Integration branch. All work lands here first, by pull request. |
| `release` | Publish branch. Only `develop` is merged into it, at release time. |

Release tags look like `release-1.2.3` and are created by the owner on `release`. The full policy,
including how it is enforced, is in
[`.github/BRANCH_POLICY.md`](.github/BRANCH_POLICY.md).

## 5. Reporting bugs

A rules bug report is much easier to act on with a replay: include the seed and the action log, plus
what you expected to happen and what happened instead. For client bugs, add your platform, Unity
version and a screenshot or short recording.

## 6. Licensing of contributions

By submitting a contribution you agree that:

- your **code** is released under the [MIT License](LICENSE);
- your **original art and audio** are released under [CC BY 4.0](LICENSE-ASSETS), unless you mark an
  individual asset otherwise in the pull request;
- you have the right to license the material you submit — it is your own work, or it is material you
  are otherwise permitted to contribute under those licenses.
