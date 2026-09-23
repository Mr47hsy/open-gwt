# open-gwt client

The Unity thin client (ADR 0001, 0005): it renders the views and events the server sends, offers
exactly the server's legal intents, and sends what the player picks. No rule lives here.

Unity 6.6 (6000.6.2f1). UI Toolkit only, no third-party packages beyond Unity's Newtonsoft JSON
and the Test Framework. Always online — start a server first.

## Run it

```bash
cd server && uv run opengwt-server            # http://127.0.0.1:8000, SQLite, memory backends
```

Then open `client/` from Unity Hub (Projects → Add → this directory) with 6000.6.2f1, open
`Assets/OpenGwt/Scenes/Main.unity` and press Play. The first screen takes the server URL and a
name; *Play against the bot* starts a match, *Create a room* shows a room code a second client
joins with *Join*.

## Headless commands

`UNITY` is `…/6000.6.2f1/Unity.app/Contents/MacOS/Unity`; run these from the repository root.

```bash
"$UNITY" -batchmode -nographics -projectPath "$PWD/client" -executeMethod OpenGwt.Editor.ProjectSetup.Run -quit -logFile -
"$UNITY" -batchmode -nographics -projectPath "$PWD/client" -runTests -testPlatform EditMode -testResults /tmp/editmode.xml -logFile -
OPENGWT_TEST_SERVER=http://127.0.0.1:8765 "$UNITY" -batchmode -nographics -projectPath "$PWD/client" -runTests -testPlatform PlayMode -testResults /tmp/playmode.xml -logFile -
"$UNITY" -batchmode -nographics -projectPath "$PWD/client" -executeMethod OpenGwt.Editor.Builds.Mac -quit -logFile -
```

`ProjectSetup.Run` (re)creates the scene, the panel settings and the player settings; it is what
made them, and it is idempotent. The EditMode tests include the i18n conformance suite
(`data/i18n/conformance.json`, generated from the YAML by `opengwt-data conformance-json`), which
the server's renderer runs too. The PlayMode test plays a whole match against the server-hosted
bot through `MatchClient` and needs a server at `OPENGWT_TEST_SERVER`.

## Layout

```
Assets/OpenGwt/
  Runtime/I18n/      MessageRenderer — opengwt.i18n/1, twin of the server's renderer
  Runtime/Net/       ServerApi (UnityWebRequest), MatchSocket (ClientWebSocket), message models
  Runtime/Match/     MatchClient — session, socket pump, latest view, events
  Runtime/UI/        BoardView (UI Toolkit controller), CardElement
  Runtime/App.cs     scene entry point
  UI/                Board.uxml, Board.uss, OpenGwtTheme.tss — all text, all reviewable
  Editor/            ProjectSetup, Builds
  Tests/             EditMode (renderer, models), PlayMode (end to end against a server)
  link.xml           keeps the JSON models whole under IL2CPP
```

## Cross-platform notes

- Networking is `UnityWebRequest` and `System.Net.WebSockets.ClientWebSocket`: desktop and
  IL2CPP mobile builds without plugins. WebGL would need a JavaScript WebSocket bridge and is out
  of scope for the MVP.
- `link.xml` preserves `OpenGwt.Client` and `Newtonsoft.Json` from IL2CPP stripping.
- The panel scales with the screen (reference 1600×900, match 0.5); input is UI Toolkit pointer
  events, so mouse and touch behave the same.
- Card names come from the server's translation tables; the default runtime theme font has no CJK
  glyphs yet, so `zh-CN` needs a font fallback before it is presentable. Tracked for M3.

This is an unofficial fan work and is not approved/endorsed by CD PROJEKT RED.
