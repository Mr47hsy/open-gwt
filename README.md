# open-gwt

**English** · [简体中文](README.zh-CN.md) · [Русский](README.ru.md)

[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Assets: CC BY 4.0](https://img.shields.io/badge/assets-CC%20BY%204.0-green.svg)](LICENSE-ASSETS)
[![Unity 6.6](https://img.shields.io/badge/Unity-6.6%20(6000.6.2f1)-black.svg)](https://unity.com/)

An open-source, unofficial reimplementation of the Gwent rules — built around an engine-agnostic
rules core, with deterministic replay and server-authoritative multiplayer.

> This is an unofficial fan work and is not approved or endorsed by CD PROJEKT RED.

## Why this exists

Official content development for Gwent has ended, but its core design — no mana curve, three rows,
best-of-three rounds, and the tempo game built around *when to pass* — is still one of the most
interesting designs the card-game genre has produced. open-gwt carries that design forward as open
source, so anyone can play it, study it, fork it and extend it.

## Design principles

- **Engine-agnostic rules core.** All rules live in a pure library with no engine dependency. Unity
  is a rendering and input layer, never a place where rules are decided.
- **Deterministic replay.** A match is a seed plus an ordered list of actions. Replaying that log
  reproduces the match exactly — which is what makes tests, bug reports and bots practical.
- **Server-authoritative multiplayer.** The client sends intents and renders the state it gets back.
  Hidden information (hands, decks, upcoming draws) never leaves the server.

## Platforms

Windows · macOS · iOS · Android, built on Unity 6.6 (6000.6.2f1).

## Repository layout

```
client/   Unity project — open this directory with Unity Hub
server/   authoritative game server
docs/     rules notes, protocol and design documents
```

## Getting started

- **Working on the server:** the code lives in `server/`.
- **Working on the client:** open `client/` with Unity Hub, using Unity 6.6 (6000.6.2f1).

## Contributing

Contributions of every kind are welcome: rules, card effects, match bots, the client, documentation
and original art. Two rules keep the project legally clean, and they are non-negotiable:

1. **No CD PROJEKT RED assets.** Pull requests containing art, audio, models, card names, character
   names or flavour text extracted or imitated from Gwent or *The Witcher* will be closed.
2. **Clean-room implementations only.** Implement features from public rules descriptions and from
   observed in-game behaviour. Do not submit code decompiled or disassembled from an official client.

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

Code is released under the [MIT License](LICENSE). Original art and audio contributed to this
repository are licensed under [CC BY 4.0](LICENSE-ASSETS) unless an individual asset states otherwise.

## Disclaimer

This is an unofficial fan work and is not approved/endorsed by CD PROJEKT RED. Gwent and The Witcher
are trademarks of CD PROJEKT S.A. This project is not affiliated with CD PROJEKT RED in any way, and
ships no assets from their games.
