---
name: client-headless-check
description: Verify a change to the Unity client without opening the editor GUI — compile, EditMode tests, a PlayMode match against a temporary server, optional macOS build — and leave the tree clean. Use before every client pull request, and after regenerating fonts, the scene or the embedded strings.
---

# Client headless check

`UNITY` is the 6000.6.2f1 editor binary (`…/Unity.app/Contents/MacOS/Unity`); the owner's Hub knows
where it is. Run from the repository root. Each step writes a log; read it when the exit code is
not 0 — and read the assets when it is 255 (see `.agent/memory/client-workflow.md`).

## 1. Regenerate what the edit invalidated

- Strings (`data/i18n/*/ui.yaml`, `errors.yaml`):
  `cd server && uv run opengwt-data client-i18n --out ../client/Assets/OpenGwt/Resources/i18n`
- Fonts (new TTF): `"$UNITY" -batchmode -nographics -projectPath "$PWD/client" -executeMethod OpenGwt.Editor.FontSetup.Run -quit -logFile /tmp/fonts.log`
- Scene or settings code: same with `OpenGwt.Editor.ProjectSetup.Run`

## 2. Compile and EditMode

```bash
"$UNITY" -batchmode -nographics -projectPath "$PWD/client" -runTests -testPlatform EditMode -testResults /tmp/editmode.xml -logFile /tmp/editmode.log
grep -E "error CS" /tmp/editmode.log        # compiler errors abort the run before any test
```

`total`, `passed` and `failed` are attributes of the root element of the results XML.

## 3. PlayMode against a temporary server

```bash
cd server && OPENGWT_DATABASE_URL=sqlite+aiosqlite:////tmp/e2e.db OPENGWT_PORT=8765 uv run opengwt-server serve &
OPENGWT_TEST_SERVER=http://127.0.0.1:8765 "$UNITY" -batchmode -nographics -projectPath "$PWD/client" -runTests -testPlatform PlayMode -testResults /tmp/playmode.xml -logFile /tmp/playmode.log
```

`ClientMatchTests` plays a whole match through `MatchClient` and asserts the opponent's hand never
appears; `BoardViewTests` runs in the same pass without the server. Stop the server afterwards.

## 3b. Look at it, for any visual change

```bash
OPENGWT_TEST_SCREENSHOTS=/tmp/shots "$UNITY" -batchmode -projectPath "$PWD/client" -runTests -testPlatform PlayMode -testFilter BoardViewTests -testResults /tmp/board.xml -logFile /tmp/board.log
```

No `-nographics`: the board renders into a 1600×900 texture and each stage is written as a PNG.
Open them and check the change the way a player would see it. A run with graphics rewrites the
dynamic font assets (`Fonts/*-SDF.asset`); unless fonts were your change, restore them with
`git checkout -- client/Assets/OpenGwt/Fonts/`.

## 4. Optional macOS build

`-executeMethod OpenGwt.Editor.Builds.Mac` writes `client/Builds/macOS/open-gwt.app` (ignored).

## 5. Python side, if `data/` or `server/` changed

`server/scripts/check.sh` runs everything CI runs, in CI's order. Run it for **any** file under
`server/`, scripts included — CI lints the whole tree.

## 6. Clean up and commit

Remove `client/Temp`, `client/Logs`, `client/*.csproj`, `client/*.slnx`, `client/.vscode`,
`client/mono_crash.*`, `client/Builds`. Run `git add -n client` and confirm nothing from
`Library`, `UserSettings` or `Builds` is listed; confirm every new asset has its `.meta`.
Check `git branch --show-current` is your feature branch, not `develop`.
