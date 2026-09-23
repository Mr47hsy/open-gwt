---
name: client-ui-toolkit
description: The Unity client uses UI Toolkit for all UI in the MVP; UXML/USS text files, no third-party UI or tween dependency.
metadata:
  type: project
---

Decided 2026-09-22 (`docs/adr/0005`): board, hand, dialogs and menus are UI Toolkit. UI is authored
as UXML and USS under `client/Assets/UI/`; drag and drop uses `PointerManipulator`; a presenter
drives the UI from the server's event stream. No third-party UI or tween library in the MVP; if one
is ever added it must be MIT and support UI Toolkit. A later move of the board to world-space
sprites is allowed and keeps the HUD in UI Toolkit.

**Why:** most client code will be written and reviewed by agents and by people reading diffs, and
prefab/scene YAML is not reviewable. uGUI's richer effects are not needed for a thin client with
flat placeholder art.

Look (visual baseline, 2026-09-23): every colour, size, radius, type step and duration is a
custom property in `UI/Tokens.uss`, imported by the theme; `Board.uss` uses `var()` and holds no
literal colour. Art is original SVG under `UI/Art/`, imported as UI Toolkit `VectorImage` by the
built-in Vector Graphics module (no package) and tinted from USS — the two rows, specials and
the `immune` status so far. Card faces read kind, rows and statuses from the pack; a status shows
its `status.<id>.name` once the tables have it (phase E adds them). Motion is USS transitions
started by `BoardMotion`; `BoardView` plays event/view batches one step at a time and only the
newest view offers legal intents.

**How to apply:** do not create uGUI canvases or prefab-based UI. Keep UI reachable only through the
presenter. Add a colour or duration as a token first, then use it; add art as a white SVG in
`UI/Art/` and tint it. See [[server-python-thin-client]].
