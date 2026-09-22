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

**How to apply:** do not create uGUI canvases or prefab-based UI. Keep UI reachable only through the
presenter. See [[server-python-thin-client]].
