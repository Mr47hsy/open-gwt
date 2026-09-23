---
name: client-workflow
description: How to change the Unity client without the editor GUI — the headless command sequence, what must be regenerated after which edit, what never to commit, and the one known teardown crash.
metadata:
  type: project
---

Every client asset is text (C#, UXML, USS, TSS, asmdef, JSON, TTF plus generated `.asset` files),
so a session edits files and lets the editor verify them headless. The commands, with `UNITY` as
the editor binary registered in the owner's Hub, are listed in `client/README.md`; the skill
`.agent/skills/client-headless-check/` is the checklist.

Regenerate after editing:

| Edited | Then run | Enforced by |
| --- | --- | --- |
| `data/i18n/*/ui.yaml`, `errors.yaml` | `opengwt-data client-i18n --out ../client/Assets/OpenGwt/Resources/i18n` | `tests/test_i18n.py` fails when stale |
| `data/i18n/conformance.yaml` | `opengwt-data conformance-json` | same test file |
| a font TTF (via `server/scripts/fonts.py`) | `-executeMethod OpenGwt.Editor.FontSetup.Run` | nothing; check the `*-SDF.asset` files |
| scene, panel or player settings in code | `-executeMethod OpenGwt.Editor.ProjectSetup.Run` | nothing; it is idempotent |
| a new SVG under `UI/Art/` | any headless run (it imports as a VectorImage and writes the `.meta`) | `BoardViewTests` checks the art resolves |

Never commit `client/Library`, `Temp`, `Logs`, `UserSettings`, `Builds`, `*.csproj`, `*.slnx`,
`.vscode`, `mono_crash.*` (all ignored). Always commit the `.meta` next to a new asset; the editor
creates it on the next headless run, so run the editor once before `git add`.

Known: a headless `FontSetup.Run` once crashed the mono runtime while exiting, *after* saving
(exit code 255). Judge such a run by the assets it wrote, not by its exit code.

There is no CI for the client (Unity needs a licence); the headless checks are the gate.
`BoardViewTests` (PlayMode) needs no server; run without `-nographics` and with
`OPENGWT_TEST_SCREENSHOTS=<dir>` it writes PNGs of the board, which is how an agent looks at a
visual change. `WaitForEndOfFrame` never comes in a batch-mode editor — a test that waits for it
hangs; read the panel's render texture after `yield return null` instead.

**Why:** the owner runs the GUI editor; agents do not, and an agent that skips the editor run
ships assets without `.meta` files or a stale string export that fails the Python tests.

**How to apply:** run the checklist before opening a pull request; clean the generated artefacts
afterwards. See [[client-ui-toolkit]], [[i18n-shared-message-format]].
