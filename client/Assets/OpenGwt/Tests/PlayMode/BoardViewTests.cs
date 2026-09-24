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
                ["choice.damage"] = "Test: choose what to damage",
                ["choice.set-row-effect"] = "Test: choose a row",
                ["choice.place"] = "Test: put {card}",
                ["choice.create"] = "Test: choose a card to create",
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
            Click(HandCard("h2"));
            Assert.AreEqual(1, sent.Count, "nothing else is sent until the server answers");
            Show(view);
            yield return Frames(2);
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

            // A special plays at once, without a row — once the server has answered the last intent.
            Show(View(hand: new[] { ("h1", Guard), ("h2", Special) }, mine: new[] { ("b1", Unit, 5, 5) },
                plays: new[] { ("h1", "melee"), ("h1", "ranged"), ("h2", (string)null) }));
            yield return Frames(2);
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
        public IEnumerator LobbyShowsWhatEachDeckBrings()
        {
            // The lobby is filled from the pack when the board is built: a client with a pack first.
            board.Dispose();
            client.LoadPack(JObject.Parse(@"{""hash"":""h"",""rules"":{""rounds_to_win"":2},""cards"":[],""decks"":[
                {""id"":""deck-a"",""faction"":""test"",""leader"":""t-l-0001"",""stratagem"":""t-g-0001"",""cards"":[],
                 ""provisions"":{""used"":163,""budget"":165},""problems"":[]},
                {""id"":""deck-b"",""faction"":""test"",""leader"":""t-l-0001"",""stratagem"":""t-g-0001"",""cards"":[],
                 ""provisions"":{""used"":170,""budget"":165},
                 ""problems"":[{""key"":""error.deck.over-budget"",""params"":{""used"":170,""budget"":165}},
                               {""key"":""error.deck.too-many-copies"",""card"":""t-u-0001"",""params"":{""card"":""@card.t-u-0001.name"",""count"":3,""limit"":2}}]}]}"));
            client.I18n.MergeTable("en", new System.Collections.Generic.Dictionary<string, string> { ["faction.test.name"] = "Test faction" });
            board = new BoardView(root, client, "http://127.0.0.1:1");
            root.Q("connect-step").AddToClassList("hidden");
            root.Q("lobby-step").RemoveFromClassList("hidden");
            root.Q("connect-panel").RemoveFromClassList("hidden");
            yield return Frames(3);

            var lines = root.Q("deck-summary").Query<Label>().ToList().Select(l => l.text).ToList();
            CollectionAssert.Contains(lines, client.Text("ui.lobby.leader", MatchClient.P("name", "@card.t-l-0001.name")));
            CollectionAssert.Contains(lines, client.Text("ui.lobby.stratagem", MatchClient.P("name", "@card.t-g-0001.name")));
            CollectionAssert.Contains(lines, client.Text("ui.lobby.provisions", MatchClient.P("used", 163, "budget", 165)));
            Assert.IsFalse(lines.Any(l => l == client.Text("ui.lobby.problems")), "a legal deck lists no problems");
            Assert.IsTrue(lines.Any(l => l.Contains("Test leader")), "names are rendered through the tables");

            var dropdown = root.Q<DropdownField>("deck");
            dropdown.value = dropdown.choices[1];
            yield return Frames(2);
            lines = root.Q("deck-summary").Query<Label>().ToList().Select(l => l.text).ToList();
            CollectionAssert.Contains(lines, client.Text("ui.lobby.provisions", MatchClient.P("used", 170, "budget", 165)));
            CollectionAssert.Contains(lines, client.Text("ui.lobby.problems"));
            CollectionAssert.Contains(lines, client.Text("error.deck.over-budget", MatchClient.P("used", 170, "budget", 165)));
            CollectionAssert.Contains(lines, client.Text("error.deck.too-many-copies", MatchClient.P("card", "@card.t-u-0001.name", "count", 3, "limit", 2)));
            yield return Seconds(0.3f);
            yield return Screenshot("16-lobby");
            root.Q("connect-panel").AddToClassList("hidden");
        }

        [UnityTest]
        public IEnumerator EveryEventOfTheProtocolHasALogLineOrIsIgnored()
        {
            // The log keeps the last three lines; each event type either writes one or is ignored on purpose.
            var ignored = new[] { "turn_started", "turn_ended", "power_changed", "choice_made", "board_cleared", "match_ended" };
            var events = new[]
            {
                new JObject { ["type"] = "match_started", ["starter"] = 1 },
                new JObject { ["type"] = "stratagem_placed", ["seat"] = 1, ["instance"] = "g1", ["card"] = Stratagem, ["row"] = "melee", ["position"] = 0 },
                new JObject { ["type"] = "round_started", ["round"] = 1, ["starter"] = 1 },
                new JObject { ["type"] = "card_drawn", ["seat"] = 0, ["instance"] = "h1", ["card"] = Unit },
                new JObject { ["type"] = "draw_skipped", ["seat"] = 1, ["reason"] = "hand_full", ["count"] = 2 },
                new JObject { ["type"] = "mulligan_started", ["round"] = 1, ["redraws"] = new JArray(2, 3) },
                new JObject { ["type"] = "card_redrawn", ["seat"] = 0, ["instance"] = "h1", ["card"] = Unit },
                new JObject { ["type"] = "mulligan_done", ["seat"] = 0, ["count"] = 1 },
                new JObject { ["type"] = "turn_started", ["seat"] = 1 },
                new JObject { ["type"] = "card_played", ["seat"] = 1, ["instance"] = "o1", ["card"] = Guard, ["from"] = "hand", ["row"] = "melee", ["position"] = 0, ["side"] = "self" },
                new JObject { ["type"] = "order_used", ["seat"] = 1, ["instance"] = "g1", ["card"] = Stratagem, ["charges"] = 0, ["cooldown"] = 0 },
                new JObject { ["type"] = "card_summoned", ["seat"] = 1, ["instance"] = "o2", ["card"] = Unit, ["from"] = "deck", ["row"] = "ranged", ["position"] = 0, ["side"] = "self" },
                new JObject { ["type"] = "card_moved", ["seat"] = 1, ["instance"] = "o2", ["card"] = Unit, ["from_row"] = "ranged", ["to_row"] = "melee", ["position"] = 1 },
                new JObject { ["type"] = "card_returned", ["seat"] = 0, ["instance"] = "b1", ["card"] = Unit },
                new JObject { ["type"] = "control_changed", ["seat"] = 1, ["instance"] = "b2", ["card"] = Unit, ["from_seat"] = 0, ["row"] = "melee", ["position"] = 2, ["source"] = "o1" },
                new JObject { ["type"] = "card_discarded", ["seat"] = 0, ["instance"] = "h2", ["card"] = Special },
                new JObject { ["type"] = "card_destroyed", ["seat"] = 1, ["instance"] = "o2", ["card"] = Unit, ["row"] = "melee", ["banished"] = false, ["source"] = null },
                new JObject { ["type"] = "card_banished", ["seat"] = 1, ["instance"] = "o3", ["card"] = Unit },
                new JObject { ["type"] = "unit_damaged", ["seat"] = 1, ["instance"] = "o1", ["card"] = Guard, ["amount"] = 2, ["power"] = 5, ["reason"] = "damage", ["source"] = "s1" },
                new JObject { ["type"] = "damage_blocked", ["seat"] = 1, ["instance"] = "o1", ["card"] = Guard, ["amount"] = 2, ["reason"] = "damage", ["source"] = "s1" },
                new JObject { ["type"] = "unit_boosted", ["seat"] = 1, ["instance"] = "o1", ["card"] = Guard, ["amount"] = 3, ["power"] = 8, ["reason"] = "boost", ["source"] = "s1" },
                new JObject { ["type"] = "unit_healed", ["seat"] = 1, ["instance"] = "o1", ["card"] = Guard, ["amount"] = 1, ["power"] = 7, ["source"] = "s1" },
                new JObject { ["type"] = "base_power_changed", ["seat"] = 1, ["instance"] = "o1", ["card"] = Guard, ["from"] = 7, ["to"] = 9, ["power"] = 9, ["source"] = "s1" },
                new JObject { ["type"] = "armor_changed", ["seat"] = 1, ["instance"] = "o1", ["card"] = Guard, ["from"] = 0, ["to"] = 2, ["reason"] = "add_armor", ["source"] = "s1" },
                new JObject { ["type"] = "power_changed", ["seat"] = 1, ["instance"] = "o1", ["card"] = Guard, ["from"] = 9, ["to"] = 10, ["reason"] = "aura", ["source"] = null },
                new JObject { ["type"] = "status_added", ["seat"] = 1, ["instance"] = "o1", ["card"] = Guard, ["status"] = "bleeding", ["turns"] = 2, ["reason"] = "add_status", ["source"] = "s1" },
                new JObject { ["type"] = "status_added", ["seat"] = 1, ["instance"] = "o1", ["card"] = Guard, ["status"] = "shielded", ["reason"] = "add_status", ["source"] = "s1" },
                new JObject { ["type"] = "status_reduced", ["seat"] = 1, ["instance"] = "o1", ["card"] = Guard, ["status"] = "bleeding", ["turns"] = 1, ["reason"] = "cancelled", ["source"] = "s2" },
                new JObject { ["type"] = "status_removed", ["seat"] = 1, ["instance"] = "o1", ["card"] = Guard, ["status"] = "shielded", ["reason"] = "blocked", ["source"] = "s1" },
                new JObject { ["type"] = "charges_changed", ["seat"] = 1, ["instance"] = "g1", ["card"] = Stratagem, ["from"] = 0, ["to"] = 1, ["source"] = "s1" },
                new JObject { ["type"] = "row_effect_set", ["seat"] = 0, ["row"] = "melee", ["effect"] = "damage_weakest", ["amount"] = 2, ["source"] = "s1" },
                new JObject { ["type"] = "row_effect_cleared", ["seat"] = 0, ["row"] = "melee", ["effect"] = "damage_weakest", ["source"] = "s2" },
                new JObject { ["type"] = "choice_requested", ["seat"] = 1, ["kind"] = "unit", ["prompt_key"] = "choice.damage", ["option_count"] = 2, ["source"] = "o1", ["cancellable"] = false },
                new JObject { ["type"] = "choice_made", ["seat"] = 1 },
                new JObject { ["type"] = "choice_cancelled", ["seat"] = 1 },
                new JObject { ["type"] = "player_passed", ["seat"] = 1, ["auto"] = true },
                new JObject { ["type"] = "turn_ended", ["seat"] = 1 },
                new JObject { ["type"] = "round_ended", ["round"] = 1, ["winners"] = new JArray(0, 1), ["scores"] = new JArray(5, 5) },
                new JObject { ["type"] = "board_cleared", ["round"] = 1, ["kept"] = new JArray() },
                new JObject { ["type"] = "match_ended", ["winner"] = null, ["rounds"] = new JArray() },
            };
            var view = View();
            foreach (var evt in events)
            {
                var before = root.Q<Label>("event-log").text;
                Show(view, evt);
                // A step after one whose cards moved waits its hold; give each up to a second to show.
                var until = Time.realtimeSinceStartup + 0.9f;
                while (Time.realtimeSinceStartup < until && root.Q<Label>("event-log").text == before)
                {
                    board.Tick();
                    yield return null;
                }
                var after = root.Q<Label>("event-log").text;
                var type = (string)evt["type"];
                if (ignored.Contains(type)) Assert.AreEqual(before, after, type + " is ignored on purpose");
                else Assert.AreNotEqual(before, after, type + " should add a line");
                Assert.IsFalse(after.Contains("ui.event."), type + ": a raw key in the log: " + after);
                Assert.IsFalse(after.Contains("{"), type + ": a placeholder left in the log: " + after);
            }
            yield return Screenshot("17-event-log");
        }

        // --- the four kinds of choice (match.md §7) -------------------------------------------

        private JObject Choosing(string kind, string promptKey, bool cancellable, params JObject[] options)
        {
            var view = View(hand: new[] { ("h1", Special) }, mine: new[] { ("b1", Unit, 5, 5) }, theirs: new[] { ("o1", Guard, 7, 7) });
            ((JArray)view["opponent"]["rows"]["ranged"]["cards"]).Add(BoardCard("o2", Unit, 1, power: 3, basePower: 5));
            view["phase"] = "choosing";
            var legal = new JArray();
            for (var i = 0; i < options.Length; i++) legal.Add(new JObject { ["kind"] = "choose", ["option"] = i });
            if (cancellable) legal.Add(new JObject { ["kind"] = "cancel_choice" });
            view["legal_intents"] = legal;
            view["pending_choice"] = new JObject
            {
                ["kind"] = kind, ["prompt_key"] = promptKey, ["source"] = new JObject { ["instance"] = "s1", ["card"] = Special },
                ["cancellable"] = cancellable, ["options"] = new JArray(options.Cast<object>().ToArray()),
            };
            return view;
        }

        private static JObject Option(string side, string row, int? position = null, string instance = null, string card = null)
        {
            var option = new JObject();
            if (side != null) option["side"] = side;
            if (row != null) option["row"] = row;
            if (position.HasValue) option["position"] = position.Value;
            if (instance != null) option["instance"] = instance;
            if (card != null) option["card"] = card;
            return option;
        }

        [UnityTest]
        public IEnumerator AUnitChoiceHighlightsItsCandidatesOnTheBoard()
        {
            Show(Choosing("unit", "choice.damage", true,
                Option("opponent", "melee", 0, "o1", Guard), Option("opponent", "ranged", 0, "o2", Unit)));
            yield return Frames(3);

            Assert.IsTrue(root.Q("modal").ClassListContains("hidden"), "a unit is chosen on the board, not in a dialog");
            Assert.IsTrue(RowCard("opp-row-melee", "o1").ClassListContains("card--candidate"));
            Assert.IsTrue(RowCard("opp-row-ranged", "o2").ClassListContains("card--candidate"));
            Assert.IsTrue(RowCard("my-row-melee", "b1").ClassListContains("card--dimmed"), "not a candidate");
            Assert.IsFalse(HandCard("h1").ClassListContains("card--playable"), "no play while a choice is pending");
            Assert.AreEqual("Test: choose what to damage", root.Q<Label>("prompt-text").text);
            Assert.AreEqual("Test special", root.Q<Label>("prompt-source").text, "the card whose ability asks");
            var cancel = root.Q<Button>("btn-cancel-choice");
            Assert.IsFalse(cancel.ClassListContains("hidden"));
            Assert.IsTrue(cancel.enabledSelf);
            Assert.AreEqual(client.Text("ui.turn.your-choice"), root.Q<Label>("turn-label").text);
            yield return Seconds(0.3f);
            yield return Screenshot("12-choice-unit");

            Click(RowCard("opp-row-ranged", "o2"));
            Assert.AreEqual("choose", (string)sent[0]["kind"]);
            Assert.AreEqual(1, (int)sent[0]["option"]);
            Click(RowCard("my-row-melee", "b1"));
            Assert.AreEqual(1, sent.Count, "a card that is not a candidate does nothing");
            Click(RowCard("opp-row-melee", "o1"));
            Assert.AreEqual(1, sent.Count, "a second candidate is not sent while the first answer is on its way");
            // The server refused it: the same choice is offered again and can be cancelled.
            client.Receive("{\"type\":\"error\",\"code\":\"illegal_intent\",\"message_key\":\"error.illegal-intent\",\"params\":{},\"message\":\"No.\",\"details\":{\"reason\":\"error.choice.out-of-range\"}}");
            yield return Frames(2);
            Assert.AreEqual(client.Text("error.choice.out-of-range"), root.Q<Label>("message-label").text, "the reason is shown when the tables know it");
            Click(cancel);
            Assert.AreEqual("cancel_choice", (string)sent[1]["kind"]);

            // Not cancellable: no cancel button.
            Show(Choosing("unit", "choice.damage", false, Option("opponent", "melee", 0, "o1", Guard)));
            yield return Frames(2);
            Assert.IsTrue(cancel.ClassListContains("hidden"));
        }

        [UnityTest]
        public IEnumerator ARowChoiceLightsTheRowSides()
        {
            Show(Choosing("row", "choice.set-row-effect", false, Option("opponent", "melee"), Option("me", "ranged")));
            yield return Frames(3);

            Assert.IsTrue(root.Q("opp-row-melee").ClassListContains("row--candidate"));
            Assert.IsTrue(root.Q("my-row-ranged").ClassListContains("row--candidate"));
            Assert.IsFalse(root.Q("my-row-melee").ClassListContains("row--candidate"));
            Assert.IsFalse(RowCard("opp-row-melee", "o1").ClassListContains("card--candidate"), "the row is the option, not its cards");
            Assert.AreEqual("Test: choose a row", root.Q<Label>("prompt-text").text);
            yield return Seconds(0.3f);
            yield return Screenshot("13-choice-row");

            Click(root.Q("my-row-ranged"));
            Assert.AreEqual(1, (int)sent[0]["option"]);
            Click(root.Q("my-row-melee"));
            Assert.AreEqual(1, sent.Count, "a row-side that is not offered does nothing");

            // Once the choice is made the rows go back to normal.
            Show(View(mine: new[] { ("b1", Unit, 5, 5) }));
            yield return Frames(2);
            Assert.IsFalse(root.Q("my-row-ranged").ClassListContains("row--candidate"));
            Click(root.Q("my-row-ranged"));
            Assert.AreEqual(1, sent.Count);
        }

        [UnityTest]
        public IEnumerator APlaceChoiceOffersSlotsForTheCardBeingPlaced()
        {
            var view = Choosing("place", "choice.place", false,
                Option("me", "melee", 0), Option("me", "melee", 1), Option("me", "ranged", 0));
            view["pending_choice"]["card"] = new JObject { ["instance"] = "p1", ["card"] = Guard };
            Show(view);
            yield return Frames(3);

            Assert.AreEqual(2, Slots("my-row-melee").Count);
            Assert.AreEqual(1, Slots("my-row-ranged").Count);
            Assert.IsEmpty(Slots("opp-row-melee"));
            Assert.AreEqual("Test: put Test guard", root.Q<Label>("prompt-text").text, "the view names the card being placed");
            Assert.AreEqual(Guard, root.Q("prompt-card").Q<CardElement>().Card, "and it is shown");
            yield return Seconds(0.3f);
            yield return Screenshot("14-choice-place");

            Click(Slots("my-row-ranged")[0]);
            Assert.AreEqual("choose", (string)sent[0]["kind"]);
            Assert.AreEqual(2, (int)sent[0]["option"]);
        }

        [UnityTest]
        public IEnumerator ACardChoiceListsTheOffer()
        {
            // A `create` offer: cards without an instance yet, next to one from a zone.
            Show(Choosing("card", "choice.create", false, Option(null, null, instance: "z1", card: Unit), Option(null, null, card: Special)));
            yield return Frames(3);

            Assert.IsFalse(root.Q("modal").ClassListContains("hidden"));
            Assert.AreEqual("Test: choose a card to create", root.Q<Label>("modal-title").text);
            var faces = root.Q("modal-options").Query<CardElement>().ToList();
            Assert.AreEqual(2, faces.Count);
            Assert.AreEqual(Unit, faces[0].Card);
            Assert.AreEqual(Special, faces[1].Card);
            Assert.AreEqual(DisplayStyle.None, root.Q<Button>("modal-cancel").resolvedStyle.display, "not cancellable");
            yield return Seconds(0.3f);
            yield return Screenshot("15-choice-card");

            Click(faces[1]);
            Assert.AreEqual("choose", (string)sent[0]["kind"]);
            Assert.AreEqual(1, (int)sent[0]["option"]);
            Assert.IsTrue(root.Q("modal").ClassListContains("hidden"));

            // A cancellable one — a graveyard without an offer — shows the cancel button.
            Show(Choosing("card", "choice.play-from-graveyard", true, Option(null, null, instance: "z1", card: Unit)));
            yield return Frames(3);
            Assert.AreEqual(DisplayStyle.Flex, root.Q<Button>("modal-cancel").resolvedStyle.display);
            Click(root.Q<Button>("modal-cancel"));
            Assert.AreEqual("cancel_choice", (string)sent[1]["kind"]);
        }

        [UnityTest]
        public IEnumerator ARefusedCardChoiceCanBeAnsweredAgainAndAZoneStillCloses()
        {
            // A card choice that cannot be cancelled: the dialog's cancel button is disabled.
            Show(Choosing("card", "choice.create", false, Option(null, null, card: Unit), Option(null, null, card: Special)));
            yield return Frames(3);
            var faces = root.Q("modal-options").Query<CardElement>().ToList();
            Click(faces[0]);
            Assert.AreEqual("choose", (string)sent[0]["kind"]);
            Assert.IsTrue(root.Q("modal").ClassListContains("hidden"));

            // Refused: the dialog comes back with its options.
            client.Receive("{\"type\":\"error\",\"code\":\"choice_pending\",\"message_key\":\"error.choice-pending\",\"params\":{},\"message\":\"Choose first.\"}");
            yield return Frames(2);
            Assert.IsFalse(root.Q("modal").ClassListContains("hidden"), "the choice is offered again");
            Assert.AreEqual(2, root.Q("modal-options").Query<CardElement>().ToList().Count);
            Click(root.Q("modal-options").Query<CardElement>().ToList()[1]);
            Assert.AreEqual(1, (int)sent[1]["option"]);

            // The choice made, a zone list opens and its close button works.
            var after = View(mine: new[] { ("b1", Unit, 5, 5) });
            after["me"]["graveyard"] = new JArray(new JObject { ["instance"] = "d1", ["card"] = Special });
            Show(after);
            yield return Frames(2);
            Click(root.Q<Label>("my-graveyard"));
            yield return Frames(1);
            Assert.IsFalse(root.Q("modal").ClassListContains("hidden"));
            var close = root.Q<Button>("modal-cancel");
            Assert.IsTrue(close.enabledSelf, "the close button is usable after a non-cancellable choice");
            Click(close);
            Assert.IsTrue(root.Q("modal").ClassListContains("hidden"));
        }

        [UnityTest]
        public IEnumerator TheResultWaitsForTheLastStepsAndTheOpponentsLeaderShows()
        {
            var view = View(mine: new[] { ("b1", Unit, 5, 5) });
            view["opponent"]["leader"] = new JObject
            {
                ["instance"] = "l2", ["card"] = Leader,
                ["order"] = new JObject { ["ready"] = false, ["charges"] = 1, ["cooldown"] = 0 },
            };
            view["phase"] = "mulligan";
            view["turn"] = null;
            view["me"]["mulligan"] = new JObject { ["remaining"] = 0, ["done"] = true };
            view["opponent"]["mulligan"] = new JObject { ["remaining"] = 2, ["done"] = false };
            view["legal_intents"] = new JArray();
            Show(view);
            yield return Frames(3);
            var theirs = root.Q("opp-leader-slot").Q<CardElement>();
            Assert.IsNotNull(theirs, "the opponent's leader is public");
            Assert.IsFalse(theirs.OrderButton.enabledSelf, "and never usable by this player");
            Assert.AreEqual(client.Text("ui.board.opponent-redraws", MatchClient.P("count", 2)), root.Q<Label>("opp-mulligan").text);

            // Two steps arrive with the match over: the first moves a card, so the second waits
            // its hold, and the dialog waits for the second.
            var first = View(mine: new[] { ("b1", Unit, 5, 5), ("x1", Unit, 5, 5) });
            var last = View();
            last["phase"] = "match_over";
            last["winner"] = "me";
            last["turn"] = null;
            Show(first, Event("card_played", 0, "x1", Unit, ("from", "hand"), ("row", "melee")));
            Show(last, Destroyed(0, "b1", Unit));
            client.Receive("{\"type\":\"match_over\",\"seq\":9,\"result\":{\"winner\":0,\"rounds\":[]}}");
            yield return Frames(2);
            Assert.IsTrue(root.Q("modal").ClassListContains("hidden"), "not while a step is still waiting");
            yield return Seconds(1.0f);
            Assert.IsFalse(root.Q("modal").ClassListContains("hidden"));
            Assert.AreEqual(client.Text("ui.result.won"), root.Q<Label>("modal-title").text);
        }

        [UnityTest]
        public IEnumerator AServerOnAnotherProtocolIsRefused()
        {
            var mismatches = new System.Collections.Generic.List<int>();
            client.ProtocolMismatch += v => mismatches.Add(v);
            client.Receive("{\"type\":\"hello\",\"protocol\":3,\"pack_hash\":\"test\",\"match_id\":\"m\",\"player_id\":\"p\",\"seat\":0,\"locale\":\"en\"}");
            Show(View(mine: new[] { ("b1", Unit, 5, 5) }));
            yield return Frames(3);
            CollectionAssert.AreEqual(new[] { 3 }, mismatches);
            Assert.IsNull(client.Hello);
            Assert.IsNull(client.View, "nothing after the mismatched hello is handled");
            Assert.IsNull(RowCard("my-row-melee", "b1"));
            var expected = client.Text("ui.net.protocol-mismatch", MatchClient.P("client", MatchClient.Protocol, "server", 3));
            Assert.AreEqual(expected, root.Q<Label>("connect-status").text);
            Assert.IsFalse(root.Q("connect-panel").ClassListContains("hidden"), "back at the connect screen");
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
