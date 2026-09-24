// Drives the real board (Board.uxml, the theme, BoardView) with server messages fed straight to
// MatchClient — no server, no socket — and checks what a player would see: the design tokens
// and vector art resolve, a played card travels from the hand to its row, a destroyed card burns
// out, ghosts never outlive their motion, and the preview shows a card in full. Set
// OPENGWT_TEST_SCREENSHOTS to a directory to also write a PNG per stage (needs graphics, so not
// with -nographics). Card definitions have the shape of the pack the server serves
// (`opengwt.pack/2`); views and events are protocol 2 (docs/protocol/match.md §7, §8).
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
        private const string Artifact = "t-a-0001";
        private const string Leader = "t-l-0001";
        private const string Stratagem = "t-g-0001";
        private const string Spy = "t-u-0003";

        private GameObject host;
        private RenderTexture target;
        private MatchClient client;
        private BoardView board;
        private VisualElement root;
        private int seq;
        private System.Collections.Generic.List<JObject> sent;

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
            client.SetLocale("en");
            client.Cards[Unit] = JObject.Parse("{\"id\":\"t-u-0001\",\"kind\":\"unit\",\"rows\":[\"melee\"],\"power\":5}");
            client.Cards[Guard] = JObject.Parse("{\"id\":\"t-u-0002\",\"kind\":\"unit\",\"rows\":[\"melee\",\"ranged\"],\"power\":7,\"statuses\":[\"immune\",\"banish_on_leave\"]}");
            client.Cards[Special] = JObject.Parse("{\"id\":\"t-s-0001\",\"kind\":\"special\",\"color\":\"gold\",\"provisions\":9}");
            client.Cards[Artifact] = JObject.Parse("{\"id\":\"t-a-0001\",\"kind\":\"artifact\",\"activation\":{\"charges\":2}}");
            client.Cards[Leader] = JObject.Parse("{\"id\":\"t-l-0001\",\"kind\":\"leader\",\"provision_bonus\":15,\"activation\":{\"charges\":2}}");
            client.Cards[Spy] = JObject.Parse("{\"id\":\"t-u-0003\",\"kind\":\"unit\",\"side\":\"opponent\",\"power\":4}");
            client.Cards[Stratagem] = JObject.Parse("{\"id\":\"t-g-0001\",\"kind\":\"stratagem\",\"rows\":[\"melee\"]}");
            client.I18n.MergeTable("en", new System.Collections.Generic.Dictionary<string, string>
            {
                ["card.t-u-0001.name"] = "Test unit",
                ["card.t-u-0001.text"] = "A plain unit.",
                ["card.t-u-0002.name"] = "Test guard",
                ["card.t-u-0002.text"] = "A unit that cannot be targeted.",
                ["card.t-s-0001.name"] = "Test special",
                ["card.t-s-0001.text"] = "Does something once.",
                ["card.t-a-0001.name"] = "Test relic",
                ["card.t-a-0001.text"] = "An artifact with an ability.",
                ["card.t-l-0001.name"] = "Test leader",
                ["card.t-l-0001.text"] = "Leads.",
                ["card.t-g-0001.name"] = "Test stratagem",
                ["card.t-g-0001.text"] = "Used once.",
                ["card.t-u-0003.name"] = "Test spy",
                ["card.t-u-0003.text"] = "Lands on the other side.",
                // The tables the tests need of the phase E interface texts (the real ones are in data/i18n).
                ["status.immune.name"] = "Test immune",
                ["status.bleeding.name"] = "Test bleeding",
                ["status.bleeding.text"] = "Loses 1 each turn end.",
                ["status.shielded.name"] = "Test shielded",
                ["row-effect.damage-weakest.name"] = "Test frost",
                ["row-effect.damage-weakest.text"] = "The weakest unit takes {amount} damage.",
            });
            root = document.rootVisualElement;
            sent = new System.Collections.Generic.List<JObject>();
            client.IntentSent += intent => sent.Add(intent);
            board = new BoardView(root, client, "http://127.0.0.1:1");
            root.Q("connect-panel").AddToClassList("hidden");
            root.Q("match").RemoveFromClassList("hidden");
            seq = 0;
            client.Receive("{\"type\":\"hello\",\"protocol\":2,\"pack_hash\":\"test\",\"match_id\":\"m\",\"player_id\":\"p\",\"seat\":0,\"locale\":\"en\"}");
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
                Event("card_played", 0, "h1", Unit, ("row", "melee"), ("from", "hand")));
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
            Show(View(hand: new[] { ("h2", Special) }), Destroyed(0, "h1", Unit));
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
                Event("card_played", 0, "h1", Unit, ("row", "melee"), ("from", "hand")));
            Show(View(hand: new[] { ("h2", Special) }, mine: new[] { ("h1", Unit, 5, 5) }, theirs: new[] { ("o1", Guard, 7, 7) },
                    plays: new[] { ("h2", (string)null) }),
                Event("card_played", 1, "o1", Guard, ("row", "melee"), ("from", "hand")));
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
                Event("card_played", 0, "h2", Special, ("from", "hand")));
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
            Show(View(hand: new[] { ("h2", Special) }), Destroyed(0, "h1", Unit));
            yield return Frames(3);
            Assert.IsTrue(Ghosts().Single().ClassListContains("card--destroyed"));
        }

        [UnityTest]
        public IEnumerator PreviewShowsTheCardInFull()
        {
            // On the board a card's statuses come from the view, innate ones included (cards.md §9).
            var view = View(mine: new[] { ("b1", Guard, 9, 7) });
            view["me"]["rows"]["melee"]["cards"][0]["statuses"] = new JArray(new JObject { ["status"] = "immune" }, new JObject { ["status"] = "banish_on_leave" });
            Show(view);
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
            view = View(mine: new[] { ("b1", Guard, 11, 7) });
            view["me"]["rows"]["melee"]["cards"][0]["statuses"] = new JArray(new JObject { ["status"] = "immune" }, new JObject { ["status"] = "banish_on_leave" });
            Show(view);
            yield return Frames(3);
            Assert.IsTrue(preview.ClassListContains("preview--visible"));
            Assert.AreEqual("11", preview.Q<CardElement>().Q<Label>(className: "card__power").text);
        }

        [UnityTest]
        public IEnumerator CardsShowArmourStatusesAndAbilities()
        {
            // A boosted unit with armour and two statuses, an artifact with a ready ability, the
            // opponent's artifact with one on cooldown, and the leader in the bottom bar.
            var view = View(mine: new[] { ("b1", Unit, 6, 4) }, theirs: new[] { ("o1", Guard, 7, 7) });
            var mine = (JObject)view["me"]["rows"]["melee"]["cards"][0];
            mine["aura"] = 1;
            mine["armor"] = 2;
            mine["statuses"] = new JArray(new JObject { ["status"] = "bleeding", ["turns"] = 2 }, new JObject { ["status"] = "shielded" });
            ((JArray)view["me"]["rows"]["melee"]["cards"]).Add(BoardCard("b2", Artifact, 0, ready: true, charges: 2, cooldown: 0));
            ((JArray)view["opponent"]["rows"]["ranged"]["cards"]).Add(BoardCard("o2", Artifact, 1, ready: false, charges: 1, cooldown: 2));
            view["me"]["leader"] = new JObject
            {
                ["instance"] = "l1", ["card"] = Leader,
                ["order"] = new JObject { ["ready"] = true, ["charges"] = 2, ["cooldown"] = 0 },
            };
            ((JArray)view["legal_intents"]).Add(new JObject { ["kind"] = "use_order", ["instance"] = "b2" });
            ((JArray)view["legal_intents"]).Add(new JObject { ["kind"] = "use_order", ["instance"] = "l1" });
            Show(view);
            yield return Frames(3);

            var unit = RowCard("my-row-melee", "b1");
            Assert.AreEqual("6", unit.Q<Label>(className: "card__power").text, "power includes the aura");
            Assert.IsTrue(unit.Q(className: "card__power").ClassListContains("card__power--boosted"), "5 own power over a base of 4");
            Assert.AreEqual("2", unit.Q<Label>(className: "card__armor").text);
            Assert.IsNotNull(unit.Q(className: "icon--bleeding"));
            Assert.IsNotNull(unit.Q(className: "icon--shielded"));
            Assert.AreEqual("2", unit.Q<Label>(className: "card__icon-timer").text, "the timed status shows its turns");
            Assert.IsNull(unit.OrderButton, "a card without an ability has no button");
            Assert.IsNotNull(unit.resolvedStyle.backgroundImage.vectorImage);

            var artifact = RowCard("my-row-melee", "b2");
            Assert.IsNull(artifact.Q<Label>(className: "card__armor"), "no armour badge without armour");
            Assert.IsTrue(artifact.Q(className: "card__power").ClassListContains("card__power--none"), "an artifact has no power");
            Assert.IsNotNull(artifact.OrderButton);
            Assert.IsTrue(artifact.OrderButton.enabledSelf, "use_order for it is legal");
            Assert.IsTrue(artifact.OrderButton.ClassListContains("card__order--ready"));
            Assert.AreEqual("2", artifact.OrderButton.Q<Label>(className: "card__order-charges").text);
            Assert.IsNull(artifact.OrderButton.Q<Label>(className: "card__order-cooldown"));
            Assert.IsNotNull(artifact.Q(className: "icon--artifact"), "the kind's icon");

            var theirs = RowCard("opp-row-ranged", "o2");
            Assert.IsFalse(theirs.OrderButton.enabledSelf, "not offered by legal_intents");
            Assert.AreEqual("·2", theirs.OrderButton.Q<Label>(className: "card__order-cooldown").text);

            var leader = root.Q("leader-slot").Q<CardElement>();
            Assert.IsNotNull(leader, "the leader is a small card in the bar");
            Assert.IsTrue(leader.ClassListContains("card--mini"));
            Assert.IsTrue(leader.OrderButton.enabledSelf);
            Assert.IsNotNull(leader.Q(className: "icon--leader"));
            yield return Seconds(0.3f);
            yield return Screenshot("06-card-details");

            // The preview explains the numbers and the statuses.
            Hover(unit);
            yield return Frames(3);
            var texts = root.Q("card-preview").Query<Label>().ToList().Select(l => l.text).ToList();
            CollectionAssert.Contains(texts, client.Text("ui.card.boosted", MatchClient.P("amount", 1)));
            CollectionAssert.Contains(texts, client.Text("ui.preview.base-power", MatchClient.P("power", 4)));
            CollectionAssert.Contains(texts, client.Text("ui.card.aura", MatchClient.P("amount", 1)));
            CollectionAssert.Contains(texts, client.Text("ui.card.armor", MatchClient.P("count", 2)));
            CollectionAssert.Contains(texts, "Test bleeding · " + client.Text("ui.card.turns", MatchClient.P("count", 2)));
            CollectionAssert.Contains(texts, "Loses 1 each turn end.");
            CollectionAssert.Contains(texts, "Test shielded");
            yield return Seconds(0.2f);
            yield return Screenshot("07-preview-statuses");
        }

        [UnityTest]
        public IEnumerator RowEffectsAndTheStratagemShow()
        {
            var view = View(mine: new[] { ("b1", Unit, 5, 5) });
            view["me"]["rows"]["ranged"]["effect"] = new JObject { ["effect"] = "damage_weakest", ["amount"] = 2 };
            view["opponent"]["rows"]["melee"]["effect"] = new JObject { ["effect"] = "boost_random", ["amount"] = 1, ["count"] = 2 };
            ((JArray)view["me"]["rows"]["melee"]["cards"]).Insert(0, BoardCard("g1", Stratagem, 0, ready: true, charges: 1, cooldown: 0));
            ((JArray)view["legal_intents"]).Add(new JObject { ["kind"] = "use_order", ["instance"] = "g1" });
            view["me"]["graveyard"] = new JArray(new JObject { ["instance"] = "d1", ["card"] = Special });
            Show(view);
            yield return Frames(3);

            var effect = root.Q("my-row-ranged").Q<Label>("effects");
            Assert.AreEqual("Test frost 2", effect.text);
            Assert.IsTrue(effect.ClassListContains("row__effects--damage-weakest"));
            var boon = root.Q("opp-row-melee").Q<Label>("effects");
            Assert.AreEqual("1×2", boon.text, "an effect without a name yet shows its numbers");
            Assert.IsTrue(boon.ClassListContains("row__effects--boost-random"));
            Assert.AreEqual("", root.Q("my-row-melee").Q<Label>("effects").text);

            var stratagem = RowCard("my-row-melee", "g1");
            Assert.IsTrue(stratagem.ClassListContains("card--stratagem"));
            Assert.IsTrue(stratagem.OrderButton.enabledSelf);
            Assert.IsNotNull(stratagem.Q(className: "icon--stratagem"));

            Hover(effect);
            yield return Frames(3);
            var texts = root.Q("card-preview").Query<Label>().ToList().Select(l => l.text).ToList();
            CollectionAssert.Contains(texts, "Test frost 2");
            CollectionAssert.Contains(texts, "The weakest unit takes 2 damage.");
            yield return Seconds(0.3f);
            yield return Screenshot("08-row-effect");

            // The graveyard count opens the zone.
            var count = root.Q<Label>("my-graveyard");
            Assert.AreEqual(client.Text("ui.board.zone", MatchClient.P("zone", "@ui.zone.graveyard", "count", 1)), count.text);
            Click(count);
            yield return Frames(2);
            Assert.IsFalse(root.Q("modal").ClassListContains("hidden"));
            Assert.AreEqual(Special, root.Q("modal-options").Q<CardElement>().Card);
            yield return Screenshot("09-graveyard");
        }

        [UnityTest]
        public IEnumerator MulliganRedrawsOneCardAtATimeFromTheHand()
        {
            var view = View(hand: new[] { ("h1", Unit), ("h2", Special) }, turn: null);
            view["phase"] = "mulligan";
            view["me"]["mulligan"] = new JObject { ["remaining"] = 2, ["done"] = false };
            view["opponent"]["mulligan"] = new JObject { ["remaining"] = 3, ["done"] = false };
            view["legal_intents"] = new JArray(
                new JObject { ["kind"] = "mulligan", ["card"] = "h1" },
                new JObject { ["kind"] = "mulligan", ["card"] = "h2" },
                new JObject { ["kind"] = "end_mulligan" });
            Show(view);
            yield return Frames(3);

            Assert.IsTrue(root.Q("modal").ClassListContains("hidden"), "no modal: the hand itself is the mulligan");
            Assert.IsTrue(HandCard("h1").ClassListContains("card--redrawable"));
            Assert.IsFalse(HandCard("h1").ClassListContains("card--playable"));
            var prompt = root.Q("prompt");
            Assert.IsFalse(prompt.ClassListContains("hidden"));
            Assert.AreEqual(client.Text("ui.board.redraws-left", MatchClient.P("count", 2)), root.Q<Label>("prompt-text").text);
            var endMulligan = root.Q<Button>("btn-end-mulligan");
            Assert.IsFalse(endMulligan.ClassListContains("hidden"));
            Assert.IsTrue(endMulligan.enabledSelf);
            Assert.IsFalse(root.Q<Button>("btn-end-turn").enabledSelf);
            Assert.IsFalse(root.Q<Button>("btn-pass").enabledSelf);
            Assert.AreEqual(client.Text("ui.turn.your-mulligan"), root.Q<Label>("turn-label").text);
            yield return Seconds(0.3f);
            yield return Screenshot("10-mulligan");

            Click(HandCard("h1"));
            Assert.AreEqual(1, sent.Count);
            Assert.AreEqual("mulligan", (string)sent[0]["kind"]);
            Assert.AreEqual("h1", (string)sent[0]["card"]);
            Click(endMulligan);
            Assert.AreEqual("end_mulligan", (string)sent[1]["kind"]);

            // Done: nothing to click, waiting for the opponent.
            view["me"]["mulligan"] = new JObject { ["remaining"] = 1, ["done"] = true };
            view["legal_intents"] = new JArray();
            Show(view);
            yield return Frames(3);
            Assert.IsFalse(HandCard("h1").ClassListContains("card--redrawable"));
            Assert.AreEqual(client.Text("ui.board.mulligan-waiting"), root.Q<Label>("prompt-text").text);
            Assert.IsFalse(endMulligan.enabledSelf);
            Assert.AreEqual(client.Text("ui.turn.opponent-mulligan"), root.Q<Label>("turn-label").text);
        }

        [UnityTest]
        public IEnumerator PlayingAUnitAsksForRowAndPosition()
        {
            Show(View(hand: new[] { ("h1", Guard), ("h2", Special) }, mine: new[] { ("b1", Unit, 5, 5) },
                plays: new[] { ("h1", "melee"), ("h1", "ranged"), ("h2", (string)null) }));
            yield return Frames(3);
            Assert.IsEmpty(Slots("my-row-melee"), "no slots before a card is picked");
            Assert.IsTrue(root.Q("prompt").ClassListContains("hidden"));
            Assert.IsTrue(root.Q("my-row-melee").ClassListContains("row--active"), "a row any card may go to is lit");

            // Picking the card: a slot per legal position on each legal row, and the prompt.
            Click(HandCard("h1"));
            yield return Frames(3);
            Assert.IsTrue(HandCard("h1").ClassListContains("card--selected"));
            Assert.AreEqual(2, Slots("my-row-melee").Count, "left of the unit and right of it");
            Assert.AreEqual(1, Slots("my-row-ranged").Count);
            Assert.IsEmpty(Slots("opp-row-melee"));
            Assert.IsTrue(root.Q("my-row-ranged").ClassListContains("row--active"));
            Assert.AreEqual(client.Text("ui.board.choose-place", MatchClient.P("card", "@card.t-u-0002.name")), root.Q<Label>("prompt-text").text);
            Assert.IsEmpty(sent, "nothing is sent until a place is picked");
            yield return Seconds(0.3f);
            yield return Screenshot("11-choose-place");

            // Picking it again unpicks it; picking a slot sends the card, row and position.
            Click(HandCard("h1"));
            yield return Frames(2);
            Assert.IsEmpty(Slots("my-row-melee"));
            Click(HandCard("h1"));
            yield return Frames(2);
            Click(Slots("my-row-melee")[0]);
            Assert.AreEqual(1, sent.Count);
            Assert.AreEqual("play_card", (string)sent[0]["kind"]);
            Assert.AreEqual("h1", (string)sent[0]["card"]);
            Assert.AreEqual("melee", (string)sent[0]["row"]);
            Assert.AreEqual(0, (int)sent[0]["position"]);

            // A special plays at once, without a row.
            Click(HandCard("h2"));
            Assert.AreEqual("play_card", (string)sent[1]["kind"]);
            Assert.AreEqual("h2", (string)sent[1]["card"]);
            Assert.IsNull(sent[1]["row"]);
            Assert.IsNull(sent[1]["position"]);
        }

        [UnityTest]
        public IEnumerator AUnitForTheOtherSideTakesItsPositionThere()
        {
            Show(View(hand: new[] { ("h3", Spy) }, theirs: new[] { ("o1", Guard, 7, 7) }, plays: new[] { ("h3", "melee") }));
            yield return Frames(3);
            Click(HandCard("h3"));
            yield return Frames(3);
            Assert.AreEqual(2, Slots("opp-row-melee").Count, "the positions of the opponent's row-side");
            Assert.IsEmpty(Slots("my-row-melee"));
            Assert.IsTrue(root.Q("opp-row-melee").ClassListContains("row--active"));
            Click(Slots("opp-row-melee")[1]);
            Assert.AreEqual(1, (int)sent[0]["position"]);
            Assert.AreEqual("melee", (string)sent[0]["row"]);
        }

        [UnityTest]
        public IEnumerator TurnButtonsFollowTheLegalIntents()
        {
            var view = View(mine: new[] { ("b1", Unit, 5, 5) });
            view["legal_intents"] = new JArray(new JObject { ["kind"] = "end_turn" });
            Show(view);
            yield return Frames(2);
            Assert.IsTrue(root.Q<Button>("btn-end-turn").enabledSelf);
            Assert.IsFalse(root.Q<Button>("btn-pass").enabledSelf, "a pass the server withholds cannot be sent");
            Click(root.Q<Button>("btn-end-turn"));
            Assert.AreEqual("end_turn", (string)sent[0]["kind"]);

            view["legal_intents"] = new JArray(new JObject { ["kind"] = "pass" });
            Show(view);
            yield return Frames(2);
            Assert.IsFalse(root.Q<Button>("btn-end-turn").enabledSelf);
            Assert.IsTrue(root.Q<Button>("btn-pass").enabledSelf);
            Click(root.Q<Button>("btn-pass"));
            Assert.AreEqual("pass", (string)sent[1]["kind"]);

            view["legal_intents"] = new JArray();
            view["turn"] = "opponent";
            Show(view);
            yield return Frames(2);
            Assert.IsFalse(root.Q<Button>("btn-end-turn").enabledSelf);
            Assert.IsFalse(root.Q<Button>("btn-pass").enabledSelf);
        }

        [UnityTest]
        public IEnumerator MovedCardTravelsAndBanishedCardDrifts()
        {
            Show(View(mine: new[] { ("b1", Unit, 5, 5) }));
            yield return Frames(3);

            // Moved to the other row: the same instance stands elsewhere, so it travels.
            var moved = View();
            ((JArray)moved["me"]["rows"]["ranged"]["cards"]).Add(BoardCard("b1", Unit, 0, power: 5, basePower: 5));
            Show(moved, Event("card_moved", 0, "b1", Unit, ("from_row", "melee"), ("to_row", "ranged")));
            yield return Frames(2);
            Assert.IsNotNull(RowCard("my-row-ranged", "b1"));
            Assert.IsTrue(Ghosts().Single().ClassListContains("card--travel"));
            yield return Seconds(1.2f);
            Assert.IsEmpty(Ghosts());

            // Banished: gone from the row, its ghost drifts away.
            Show(View(), Event("card_banished", 0, "b1", Unit));
            yield return Frames(3);
            Assert.IsNull(RowCard("my-row-ranged", "b1"));
            Assert.IsTrue(Ghosts().Single().ClassListContains("card--banished"));
            yield return Seconds(1.5f);
            Assert.IsEmpty(Ghosts());
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

        /// <summary>A card on a row-side in the shape of match.md §7.</summary>
        private static JObject BoardCard(string instance, string card, int owner, int? power = null, int? basePower = null,
            bool? ready = null, int? charges = null, int cooldown = 0)
        {
            var entry = new JObject { ["instance"] = instance, ["card"] = card, ["owner"] = owner, ["statuses"] = new JArray() };
            if (power.HasValue)
            {
                entry["power"] = power.Value;
                entry["base"] = basePower ?? power.Value;
                entry["aura"] = 0;
                entry["armor"] = 0;
            }
            entry["order"] = ready.HasValue
                ? new JObject { ["ready"] = ready.Value, ["charges"] = charges, ["cooldown"] = cooldown }
                : null;
            return entry;
        }

        /// <summary>Click an element: a button answers to a submit like the one a pointer click
        /// raises through its Clickable; anything else to the click event the board listens for.</summary>
        private static void Click(VisualElement element)
        {
            if (element is Button)
            {
                using (var submit = NavigationSubmitEvent.GetPooled())
                {
                    submit.target = element;
                    element.SendEvent(submit);
                }
                return;
            }
            using (var click = ClickEvent.GetPooled())
            {
                click.target = element;
                element.SendEvent(click);
            }
        }

        private System.Collections.Generic.List<VisualElement> Slots(string row) =>
            root.Q(row).Q("units").Children().Where(c => c.ClassListContains("slot")).ToList();

        private void Hover(VisualElement element)
        {
            using (var enter = PointerEnterEvent.GetPooled(new Event { type = EventType.MouseMove, mousePosition = element.worldBound.center }))
            {
                enter.target = element;
                element.SendEvent(enter);
            }
        }

        private static JObject Destroyed(int seat, string instance, string card)
        {
            var evt = Event("card_destroyed", seat, instance, card, ("row", "melee"));
            evt["banished"] = false;
            evt["source"] = null;
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
            var cards = (hand ?? Array.Empty<(string, string)>()).Select(c => new JObject { ["instance"] = c.instance, ["card"] = c.card }).ToList();
            me["hand"] = new JArray(cards);
            me["hand_count"] = cards.Count;
            var opponent = Side(1, theirs);
            opponent["hand_count"] = 5;
            return new JObject
            {
                ["protocol"] = 2,
                ["match_id"] = "m",
                ["phase"] = "playing",
                ["round"] = 1,
                ["turn"] = turn,
                ["winner"] = null,
                ["me"] = me,
                ["opponent"] = opponent,
                ["legal_intents"] = turn == "me" ? intents : new JArray(),
                ["pending_choice"] = null,
            };
        }

        /// <summary>A side in the shape of match.md §7, with units on its melee row.</summary>
        private static JObject Side(int seat, (string instance, string card, int power, int basePower)[] melee)
        {
            var rows = new JObject();
            foreach (var row in new[] { "melee", "ranged" }) rows[row] = new JObject { ["effect"] = null, ["cards"] = new JArray() };
            foreach (var (instance, card, power, basePower) in melee ?? Array.Empty<(string, string, int, int)>())
            {
                ((JArray)rows["melee"]["cards"]).Add(new JObject
                {
                    ["instance"] = instance, ["card"] = card, ["owner"] = seat, ["power"] = power, ["base"] = basePower,
                    ["aura"] = 0, ["armor"] = 0, ["statuses"] = new JArray(), ["order"] = null,
                });
            }
            return new JObject
            {
                ["seat"] = seat,
                ["faction"] = "test",
                ["score"] = 0,
                ["rounds_won"] = 0,
                ["passed"] = false,
                ["hand_count"] = 0,
                ["deck_count"] = 10,
                ["graveyard"] = new JArray(),
                ["banished"] = new JArray(),
                ["leader"] = null,
                ["mulligan"] = null,
                ["rows"] = rows,
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
