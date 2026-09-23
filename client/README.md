# open-gwt client

The Unity thin client (ADR 0001, 0005): it renders the views and events the server sends, offers
exactly the server's legal intents, and sends what the player picks. No rule lives here.

Unity 6.6 (6000.6.2f1). UI Toolkit only, no third-party packages beyond Unity's Newtonsoft JSON
and the Test Framework; the SVG art goes through the engine's built-in Vector Graphics module
(`com.unity.modules.vectorgraphics`, a core module since Unity 6.3 — the separate
`com.unity.vectorgraphics` package is only needed for SVG sprites and uGUI). Always online — start
a server first.

## Run it

```bash
cd server && uv run opengwt-server            # http://127.0.0.1:8000, SQLite, memory backends
```

Then open `client/` from Unity Hub (Projects → Add → this directory) with 6000.6.2f1, open
`Assets/OpenGwt/Scenes/Main.unity` and press Play. The first screen takes the server URL, a name
and the language (remembered across runs); *Connect* signs in and shows the lobby with the deck
choice. *Play against the bot* starts a match, *Create a room* shows a room code a second client
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
made them, and it is idempotent. `FontSetup.Run` builds the SDF font assets and the fallback
chain from the TTFs in `Assets/OpenGwt/Fonts` (see the README there; the TTFs themselves come
from `server/scripts/fonts.py`). The EditMode tests include the i18n conformance suite
(`data/i18n/conformance.json`, generated from the YAML by `opengwt-data conformance-json`), which
the server's renderer runs too. `ClientMatchTests` (PlayMode) plays a whole match against the
server-hosted bot through `MatchClient` and needs a server at `OPENGWT_TEST_SERVER`;
`BoardViewTests` (PlayMode) needs no server — it feeds server messages to the real board and checks
the tokens, the vector art, the card motion and the preview. With `OPENGWT_TEST_SCREENSHOTS=<dir>`
and without `-nographics`, it also writes a PNG per stage, which is how to look at the board
without opening the editor.

## Layout

```
Assets/OpenGwt/
  Runtime/I18n/      MessageRenderer — opengwt.i18n/1, twin of the server's renderer
  Resources/i18n/    ui/choice/error strings per locale, exported by `opengwt-data client-i18n`
  Fonts/             Noto Sans / Serif (+ SC) static subsets, OFL, and their SDF assets
  Runtime/Net/       ServerApi (UnityWebRequest), MatchSocket (ClientWebSocket), message models
  Runtime/Match/     MatchClient — session, socket pump, latest view, events
  Runtime/UI/        BoardView (UI Toolkit controller, one event/view step at a time),
                     CardElement, CardPreview (hover / long press), BoardMotion (play, destroy, cast)
  Runtime/App.cs     scene entry point
  UI/                Board.uxml, Board.uss, Tokens.uss (design tokens), OpenGwtTheme.tss — all text
  UI/Art/            original SVG card frame, power badge and icons (CC BY 4.0), see its README
  Editor/            ProjectSetup, Builds, SvgImportSettings (SVG → VectorImage on import)
  Tests/             EditMode (renderer, models), PlayMode (the board without a server; a whole
                     match against a server)
  link.xml           keeps the JSON models whole under IL2CPP
```

## Cross-platform notes

- Networking is `UnityWebRequest` and `System.Net.WebSockets.ClientWebSocket`: desktop and
  IL2CPP mobile builds without plugins. WebGL would need a JavaScript WebSocket bridge and is out
  of scope for the MVP.
- `link.xml` preserves `OpenGwt.Client` and `Newtonsoft.Json` from IL2CPP stripping.
- The panel scales with the screen (reference 1600×900, match 0.5); input is UI Toolkit pointer
  events, so mouse and touch behave the same.
- Look: every colour, size, radius, type step and duration is a custom property in
  `UI/Tokens.uss`, imported by the theme; `Board.uss` refers to them with `var()`. Card art is
  vector (`UI/Art/`), tinted from USS, so one frame serves the board, the hand and the preview.
- Motion: `BoardView` shows the server's `events` + `view` batches one step at a time, holding a
  step whose cards move for about half a second, and jumps straight to the newest view when more
  than four are waiting (a resync). `BoardMotion` diffs two renders — a card that changed zone
  flies, a card that left burns out (destroyed) or fades, a played special flies to the middle —
  with USS transitions only; only the newest view offers legal intents.
- Text: Noto Sans for the interface and Noto Serif for card names and titles, each falling back
  to its SC companion (dynamic SDF atlases, so only the glyphs actually shown are rasterised).
  Interface strings ship inside the build; card texts arrive from the server. Adding a language
  means a translation directory under `data/i18n` and, if it needs new glyphs, one more Noto font
  in the chain.

This is an unofficial fan work and is not approved/endorsed by CD PROJEKT RED.
