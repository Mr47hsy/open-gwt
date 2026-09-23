// Drives the real board (Board.uxml, the theme, BoardView) with server messages fed straight to
// MatchClient — no server, no socket — and checks what a player would see: the design tokens
// and vector art resolve, a played card travels from the hand to its row, a destroyed card burns
// out, ghosts never outlive their motion, and the preview shows a card in full. Set
// OPENGWT_TEST_SCREENSHOTS to a directory to also write a PNG per stage (needs graphics, so not
// with -nographics). Card definitions have the shape of the pack the server serves
// (`opengwt.pack/2`); views and events are protocol 1, which the client speaks until ADR 0009
// phase E moves it to protocol 2.
using System;
using System.Collections;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using OpenGwt.Match;
using OpenGwt.UI;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace OpenGwt.Tests
{
    public class BoardViewTests
    {
        private const string Unit = "t-u-0001";
        private const string Guard = "t-u-0002";
        private const string Special = "t-s-0001";

        private GameObject host;
        private RenderTexture target;
        private MatchClient client;
        private BoardView board;
        private VisualElement root;
        private int seq;

        [UnitySetUp]
        public IEnumerator SetUp()
        {
#if UNITY_EDITOR
            var settings = UnityEngine.Object.Instantiate(AssetDatabase.LoadAssetAtPath<PanelSettings>("Assets/OpenGwt/Settings/PanelSettings.asset"));
            var tree = AssetDatabase.LoadAssetAtPath<VisualTreeAsset>("Assets/OpenGwt/UI/Board.uxml");
#else
            PanelSettings settings = null;
            VisualTreeAsset tree = null;
            Assert.Ignore("needs the editor's asset database");
#endif
            // A fixed-size target keeps the layout identical on every machine, windowed or not.
            target = new RenderTexture(1600, 900, 24);
            settings.targetTexture = target;
            host = new GameObject("board-under-test");
            var document = host.AddComponent<UIDocument>();
            document.panelSettings = settings;
            document.visualTreeAsset = tree;
            yield return null;

            client = new MatchClient();
            client.Cards[Unit] = JObject.Parse("{\"id\":\"t-u-0001\",\"kind\":\"unit\",\"rows\":[\"melee\"],\"power\":5}");
            client.Cards[Guard] = JObject.Parse("{\"id\":\"t-u-0002\",\"kind\":\"unit\",\"rows\":[\"melee\",\"ranged\"],\"power\":7,\"statuses\":[\"immune\",\"banish_on_leave\"]}");
            client.Cards[Special] = JObject.Parse("{\"id\":\"t-s-0001\",\"kind\":\"special\"}");
            client.I18n.MergeTable("en", new System.Collections.Generic.Dictionary<string, string>
            {
                ["card.t-u-0001.name"] = "Test unit",
                ["card.t-u-0001.text"] = "A plain unit.",
                ["card.t-u-0002.name"] = "Test guard",
                ["card.t-u-0002.text"] = "A unit that cannot be targeted.",
                ["card.t-s-0001.name"] = "Test special",
                ["card.t-s-0001.text"] = "Does something once.",
                // Status names arrive with phase E's interface texts; until then only those in the tables show.
                ["status.immune.name"] = "Test immune",
            });
            root = document.rootVisualElement;
            board = new BoardView(root, client, "http://127.0.0.1:1");
            root.Q("connect-panel").AddToClassList("hidden");
            root.Q("match").RemoveFromClassList("hidden");
            seq = 0;
            client.Receive("{\"type\":\"hello\",\"protocol\":1,\"pack_hash\":\"test\",\"match_id\":\"m\",\"player_id\":\"p\",\"seat\":0,\"locale\":\"en\"}");
        }

        [TearDown]
        public void TearDown()
        {
            board?.Dispose();
            client?.Dispose();
            if (host != null) UnityEngine.Object.Destroy(host);
            if (target != null) target.Release();
        }

        [UnityTest]
        public IEnumerator TokensAndVectorArtResolve()
        {
            Show(View(hand: new[] { ("h1", Unit), ("h2", Special) }, plays: new[] { ("h1", "melee") }));
            yield return Frames(3);

            var card = HandCard("h1");
            var fill = card.resolvedStyle.backgroundColor;
            Assert.AreEqual(52 / 255f, fill.r, 0.002f, "--color-card-unit from Tokens.uss");
            Assert.AreEqual(58 / 255f, fill.g, 0.002f);
            Assert.AreEqual(70 / 255f, fill.b, 0.002f);
            Assert.IsNotNull(card.resolvedStyle.backgroundImage.vectorImage, "the frame is an SVG imported as a VectorImage");
            Assert.IsTrue(card.ClassListContains("card--playable"));
            var icon = root.Q("my-row-melee").Q("icon");
            Assert.IsNotNull(icon.resolvedStyle.backgroundImage.vectorImage, "row icons are vector images");
            Assert.IsTrue(HandCard("h2").ClassListContains("card--special"));
            Assert.IsTrue(HandCard("h1").ClassListContains("card--unit"));
            Assert.IsTrue(HandCard("h2").Q(className: "card__power").ClassListContains("card__power--none"));
            yield return Seconds(0.3f);
            yield return Screenshot("01-hand");
        }

        [UnityTest]
        public IEnumerator PlayedCardTravelsAndDestroyedCardBurnsOut()
        {
            Show(View(hand: new[] { ("h1", Unit), ("h2", Special) }, plays: new[] { ("h1", "melee") }));
            yield return Frames(3);

            // Played: the new row element waits hidden while a ghost flies in from the hand.
            Show(View(hand: new[] { ("h2", Special) }, mine: new[] { ("h1", Unit, 5, 5) }),
                Event("card_played", 0, "h1", Unit, ("row", "melee")));
            yield return Frames(2);
            var placed = RowCard("my-row-melee", "h1");
            Assert.IsNotNull(placed);
            Assert.IsTrue(placed.ClassListContains("card--pending"), "hidden until the ghost lands");
            var ghost = Ghosts().Single();
            Assert.IsTrue(ghost.ClassListContains("card--travel"));
            yield return Seconds(0.15f);
            yield return Screenshot("02-travelling");
            yield return Seconds(1.2f);
            Assert.IsEmpty(Ghosts(), "the ghost is gone once it landed");
            Assert.IsFalse(RowCard("my-row-melee", "h1").ClassListContains("card--pending"));
            Assert.AreEqual(1f, RowCard("my-row-melee", "h1").resolvedStyle.opacity, 0.001f);

            // Destroyed: the element is gone at once, its ghost burns out where it stood.
            Show(View(hand: new[] { ("h2", Special) }), Event("unit_destroyed", 0, "h1", Unit, ("row", "melee")));
            yield return Frames(3);
            Assert.IsNull(RowCard("my-row-melee", "h1"));
            Assert.IsTrue(Ghosts().Single().ClassListContains("card--destroyed"));
            yield return Seconds(0.25f);
            yield return Screenshot("03-destroyed");
            yield return Seconds(1.5f);
            Assert.IsEmpty(Ghosts());
        }

        [UnityTest]
        public IEnumerator StepsAreShownOneAtATime()
        {
            Show(View(hand: new[] { ("h1", Unit), ("h2", Special) }, plays: new[] { ("h1", "melee") }));
            yield return Frames(3);

            // My card and the opponent's answer arrive in the same frame.
            Show(View(hand: new[] { ("h2", Special) }, mine: new[] { ("h1", Unit, 5, 5) }, plays: new[] { ("h2", (string)null) }),
                Event("card_played", 0, "h1", Unit, ("row", "melee")));
            Show(View(hand: new[] { ("h2", Special) }, mine: new[] { ("h1", Unit, 5, 5) }, theirs: new[] { ("o1", Guard, 7, 7) },
                    plays: new[] { ("h2", (string)null) }),
                Event("card_played", 1, "o1", Guard, ("row", "melee")));
            yield return Frames(2);
            Assert.IsNotNull(RowCard("my-row-melee", "h1"), "the first step is on screen");
            Assert.IsNull(RowCard("opp-row-melee", "o1"), "the second waits for it");
            Assert.IsFalse(HandCard("h2").ClassListContains("card--playable"), "only the newest view offers intents");

            yield return Seconds(0.8f);
            Assert.IsNotNull(RowCard("opp-row-melee", "o1"), "then the opponent's card follows");
            Assert.IsTrue(HandCard("h2").ClassListContains("card--playable"));
            yield return Seconds(1.2f);
            Assert.IsEmpty(Ghosts());

            // A special resolves in the middle of the board and leaves nothing behind.
            Show(View(mine: new[] { ("h1", Unit, 5, 5) }, theirs: new[] { ("o1", Guard, 7, 7) }),
                Event("card_played", 0, "h2", Special));
            yield return Frames(3);
            Assert.IsTrue(Ghosts().Single().ClassListContains("card--cast"));
            yield return Seconds(0.3f);
            yield return Screenshot("04-cast");
            yield return Seconds(1.5f);
            Assert.IsEmpty(Ghosts());
        }

        [UnityTest]
        public IEnumerator FarBehindJumpsToTheNewestView()
        {
            Show(View(hand: new[] { ("h1", Unit), ("h2", Special) }, plays: new[] { ("h1", "melee") }));
            yield return Frames(3);

            // A resync after a reconnect: many batches at once are shown as their last view.
            for (var i = 0; i < 6; i++)
            {
                Show(View(hand: new[] { ("h2", Special) }, mine: new[] { ("h1", Unit, 5 + i, 5) }), Event("power_changed", 0, "h1", Unit));
            }
            yield return Frames(2);
            Assert.AreEqual("10", RowCard("my-row-melee", "h1").Q<Label>(className: "card__power").text);
            Assert.IsEmpty(Ghosts(), "no motion while catching up");
            Assert.IsFalse(RowCard("my-row-melee", "h1").ClassListContains("card--pending"));

            // And the step after it moves again.
            Show(View(hand: new[] { ("h2", Special) }), Event("unit_destroyed", 0, "h1", Unit, ("row", "melee")));
            yield return Frames(3);
            Assert.IsTrue(Ghosts().Single().ClassListContains("card--destroyed"));
        }

        [UnityTest]
        public IEnumerator PreviewShowsTheCardInFull()
        {
            Show(View(mine: new[] { ("b1", Guard, 9, 7) }));
            yield return Frames(3);

            var card = RowCard("my-row-melee", "b1");
            using (var enter = PointerEnterEvent.GetPooled(new Event { type = EventType.MouseMove, mousePosition = card.worldBound.center }))
            {
                enter.target = card;
                card.SendEvent(enter);
            }
            yield return Frames(3);

            var preview = root.Q("card-preview");
            Assert.IsTrue(preview.ClassListContains("preview--visible"));
            var texts = preview.Query<Label>().ToList().Select(l => l.text).ToList();
            CollectionAssert.Contains(texts, "Test guard");
            CollectionAssert.Contains(texts, "A unit that cannot be targeted.");
            CollectionAssert.Contains(texts, "Test immune", "a status name the tables have");
            Assert.IsNotNull(preview.Q(className: "preview__details").Q(className: "icon--immune"), "and its icon");
            Assert.IsFalse(texts.Any(t => t.StartsWith("status.")), "a status without a name shows no key");
            CollectionAssert.Contains(texts, client.Text("ui.preview.base-power", MatchClient.P("power", 7)));
            Assert.IsTrue(preview.Q<CardElement>().ClassListContains("card--large"));
            yield return Seconds(0.3f);
            yield return Screenshot("05-preview");

            // A new view keeps the preview on the same card, with its new power.
            Show(View(mine: new[] { ("b1", Guard, 11, 7) }));
            yield return Frames(3);
            Assert.IsTrue(preview.ClassListContains("preview--visible"));
            Assert.AreEqual("11", preview.Q<CardElement>().Q<Label>(className: "card__power").text);
        }

        // --- server messages ------------------------------------------------------------------

        private void Show(JObject view, params JObject[] events)
        {
            if (events.Length > 0)
            {
                client.Receive(new JObject { ["type"] = "events", ["from_seq"] = seq + 1, ["events"] = new JArray(events.Cast<object>().ToArray()) }.ToString());
                seq += events.Length;
            }
            view["seq"] = seq;
            client.Receive(new JObject { ["type"] = "view", ["seq"] = seq, ["view"] = view }.ToString());
        }

        private static JObject Event(string type, int seat, string instance, string card, params (string key, string value)[] extra)
        {
            var evt = new JObject { ["type"] = type, ["seat"] = seat, ["instance"] = instance, ["card"] = card };
            foreach (var (key, value) in extra) evt[key] = value;
            return evt;
        }

        private static JObject View(
            (string instance, string card)[] hand = null,
            (string instance, string card, int power, int basePower)[] mine = null,
            (string instance, string card, int power, int basePower)[] theirs = null,
            (string instance, string row)[] plays = null,
            string turn = "me")
        {
            var intents = new JArray();
            foreach (var (instance, row) in plays ?? Array.Empty<(string, string)>())
            {
                var intent = new JObject { ["kind"] = "play_card", ["card"] = instance };
                if (row != null) intent["row"] = row;
                intents.Add(intent);
            }
            intents.Add(new JObject { ["kind"] = "pass" });
            var me = Side(0, mine);
            me["hand"] = new JArray((hand ?? Array.Empty<(string, string)>()).Select(c => new JObject { ["instance"] = c.instance, ["card"] = c.card }));
            var opponent = Side(1, theirs);
            opponent["hand_count"] = 5;
            return new JObject
            {
                ["protocol"] = 1,
                ["phase"] = "playing",
                ["round"] = 1,
                ["turn"] = turn,
                ["me"] = me,
                ["opponent"] = opponent,
                ["legal_intents"] = turn == "me" ? intents : new JArray(),
            };
        }

        private static JObject Side(int seat, (string instance, string card, int power, int basePower)[] melee)
        {
            var rows = new JObject();
            foreach (var row in new[] { "melee", "ranged", "siege" }) rows[row] = new JObject { ["effects"] = new JArray(), ["units"] = new JArray() };
            foreach (var (instance, card, power, basePower) in melee ?? Array.Empty<(string, string, int, int)>())
            {
                ((JArray)rows["melee"]["units"]).Add(new JObject { ["instance"] = instance, ["card"] = card, ["owner"] = seat, ["power"] = power, ["base"] = basePower });
            }
            return new JObject
            {
                ["seat"] = seat,
                ["faction"] = "test",
                ["score"] = 0,
                ["lives"] = 2,
                ["rounds_won"] = 0,
                ["passed"] = false,
                ["deck_count"] = 10,
                ["rows"] = rows,
                ["mulligan_done"] = true,
            };
        }

        // --- looking at the board -------------------------------------------------------------

        private CardElement HandCard(string instance) =>
            root.Q<ScrollView>("hand").Children().OfType<CardElement>().FirstOrDefault(c => c.Instance == instance);

        private CardElement RowCard(string row, string instance) =>
            root.Q(row).Q("units").Children().OfType<CardElement>().FirstOrDefault(c => c.Instance == instance);

        private System.Collections.Generic.List<VisualElement> Ghosts() => root.Q("fx-layer").Children().ToList();

        private IEnumerator Frames(int count)
        {
            for (var i = 0; i < count; i++)
            {
                board.Tick();
                yield return null;
            }
        }

        private IEnumerator Seconds(float seconds)
        {
            var until = Time.realtimeSinceStartup + seconds;
            while (Time.realtimeSinceStartup < until)
            {
                board.Tick();
                yield return null;
            }
        }

        private IEnumerator Screenshot(string name)
        {
            var directory = Environment.GetEnvironmentVariable("OPENGWT_TEST_SCREENSHOTS");
            if (string.IsNullOrEmpty(directory) || SystemInfo.graphicsDeviceType == UnityEngine.Rendering.GraphicsDeviceType.Null) yield break;
            // The panel repaints its target every frame; WaitForEndOfFrame never comes in batch mode.
            board.Tick();
            yield return null;
            var previous = RenderTexture.active;
            RenderTexture.active = target;
            var image = new Texture2D(target.width, target.height, TextureFormat.RGBA32, false);
            image.ReadPixels(new Rect(0, 0, target.width, target.height), 0, 0);
            image.Apply();
            RenderTexture.active = previous;
            Directory.CreateDirectory(directory);
            File.WriteAllBytes(Path.Combine(directory, name + ".png"), image.EncodeToPNG());
            UnityEngine.Object.Destroy(image);
        }
    }
}
