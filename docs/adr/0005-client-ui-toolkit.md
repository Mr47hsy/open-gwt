# ADR 0005: UI Toolkit for the whole client UI

- Status: accepted, 2026-09-22
- Deciders: project owner
- Related: [ADR 0001](0001-python-server-unity-thin-client.md)

## Context

The Unity client is thin: it renders per-player views and event streams and collects input. Unity
offers two runtime UI systems, uGUI (Canvas, GameObjects, prefabs) and UI Toolkit (UXML, USS,
flexbox). A third option is to render the board as world-space sprites and use a UI system only
for the HUD.

The project expects a large share of its client code to be generated and reviewed by AI agents
and by contributors reading diffs. Prefab and scene files are YAML full of GUIDs and are not
reviewable in practice.

## Decision

- **UI Toolkit for everything in the MVP**: board, rows, hand, choice dialogs, menus.
- UI is authored as UXML and USS text files under `client/Assets/UI/`; the UI Builder may be
  used, but the files it writes are the artefact under review.
- Drag and drop is implemented with `PointerManipulator`; transitions with USS where they
  suffice. No third-party UI or tween dependency in the MVP. If one becomes necessary, it must
  be MIT-licensed and support UI Toolkit; PrimeTween and LitMotion qualify.
- The presentation layer consumes the server's event stream sequentially and drives the UI from
  it. Nothing in the UI reads match state directly; that isolates the UI technology behind one
  seam.

## Consequences

- All client UI is diffable text. Agents can write and review it.
- No GameObject per element; panels batch automatically, which suits mobile targets.
- Per-element custom shaders, particles and 3D objects inside the UI are harder than in uGUI.
  Card art in the MVP is flat: colour blocks and text. If the board later needs heavy effects,
  only the board is moved to world-space sprites; HUD and menus stay in UI Toolkit, and the
  event-driven presenter is unchanged.
- World-space rendering is available from Unity 6.2, so that later move is possible without
  leaving UI Toolkit for the HUD.

## Alternatives considered

- **uGUI.** The richest ecosystem and the most tutorials for card games, with per-image
  materials and easy particle layering. Rejected for the MVP because its artefacts are not
  reviewable text and it needs a tween library for basic feel.
- **World-space sprite board plus UI Toolkit HUD.** Highest ceiling for feel, largest amount of
  hand-written layout and input code. Deferred; the design keeps it reachable.
- **IMGUI.** Editor-only; not a runtime option.
