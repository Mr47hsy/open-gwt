// Drives the real board through whole matches against the server-hosted bot with a player that
// picks a random entry of `legal_intents` every time and performs it the way a person would —
// a click on the hand card and on a slot, on the ability button, on a candidate, a row, a slot
// or a face in the dialog, on the pass, end-turn, end-mulligan or cancel button — for several
// seeds, and after every step checks that what the board shows is what the newest view says.
// Needs a running server, named by OPENGWT_TEST_SERVER; ignored otherwise.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using OpenGwt.Match;
using OpenGwt.Net;
using OpenGwt.UI;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace OpenGwt.Tests
{
    public class RandomMatchTests
    {
        private static string Server => Environment.GetEnvironmentVariable("OPENGWT_TEST_SERVER");
        private static int Seeds => int.TryParse(Environment.GetEnvironmentVariable("OPENGWT_TEST_SEEDS"), out var n) ? n : 3;
        private static int FirstSeed => int.TryParse(Environment.GetEnvironmentVariable("OPENGWT_TEST_SEED_FROM"), out var n) ? n : 1;

        private const float MinSecondsBetweenIntents = 0.06f;
        private const float MatchDeadlineSeconds = 300f;

        [UnityTest]
        public IEnumerator TheBoardMatchesTheViewThroughRandomMatches()
        {
            if (string.IsNullOrEmpty(Server)) Assert.Ignore("set OPENGWT_TEST_SERVER to run");
#if UNITY_EDITOR
            var settings = UnityEngine.Object.Instantiate(AssetDatabase.LoadAssetAtPath<PanelSettings>("Assets/OpenGwt/Settings/PanelSettings.asset"));
            var tree = AssetDatabase.LoadAssetAtPath<VisualTreeAsset>("Assets/OpenGwt/UI/Board.uxml");
#else
            PanelSettings settings = null;
            VisualTreeAsset tree = null;
            Assert.Ignore("needs the editor's asset database");
#endif
            var target = new RenderTexture(1600, 900, 24);
            settings.targetTexture = target;
            var host = new GameObject("random-match");
            var document = host.AddComponent<UIDocument>();
            document.panelSettings = settings;
            document.visualTreeAsset = tree;
            yield return null;
            var root = document.rootVisualElement;
            // One client and one board for every match, as in the application: the result
            // dialog's button leaves a match and the next one starts from the lobby.
            using (var client = new MatchClient())
            using (var board = new BoardView(root, client, Server))
            {
                try
                {
                    yield return Await(client, client.PrepareAsync(Server, "random"));
                    for (var seed = FirstSeed; seed < FirstSeed + Seeds; seed++)
                    {
                        yield return PlayOne(root, client, board, seed, seed % 2 == 0 ? "starter-b" : "starter-a");
                    }
                }
                finally
                {
                    UnityEngine.Object.Destroy(host);
                    target.Release();
                }
            }
        }

        private IEnumerator PlayOne(VisualElement root, MatchClient client, BoardView board, int seed, string deckId)
        {
            {
                var rng = new System.Random(seed);
                var checks = 0;
                var moves = 0;
                ErrorMessage lastError = null;
                var sent = new List<JObject>();
                client.ErrorReceived += e => lastError = e;
                client.IntentSent += i => sent.Add(i);
                yield return Await(client, client.PlayBotAsync(deckId));
                root.Q("connect-panel").AddToClassList("hidden");
                root.Q("match").RemoveFromClassList("hidden");

                var lastSeq = -1;
                var lastSentAt = -1f;
                var deadline = Time.realtimeSinceStartup + MatchDeadlineSeconds;
                while (client.Result == null && Time.realtimeSinceStartup < deadline && lastError == null)
                {
                    client.Pump();
                    board.Tick();
                    var view = client.View;
                    if (view != null && client.Hello != null && board.Idle && view.Seq != lastSeq
                        && Time.realtimeSinceStartup - lastSentAt >= MinSecondsBetweenIntents)
                    {
                        yield return null;
                        board.Tick();
                        if (!board.Idle || client.View != view) continue;
                        Check(root, client, view, "seed " + seed + " seq " + view.Seq);
                        checks++;
                        lastSeq = view.Seq;
                        var move = Pick(rng, client, view);
                        if (move != null)
                        {
                            moves++;
                            lastSentAt = Time.realtimeSinceStartup;
                            sent.Clear();
                            yield return Perform(root, board, client, view, move);
                            Assert.AreEqual(1, sent.Count, "seed " + seed + " seq " + view.Seq + ": the board sent " + sent.Count + " intents for " + move);
                            Assert.AreEqual(move.ToString(Newtonsoft.Json.Formatting.None), sent[0].ToString(Newtonsoft.Json.Formatting.None),
                                "seed " + seed + " seq " + view.Seq + ": the board sent something else");
                        }
                    }
                    yield return null;
                }
                Assert.IsNull(lastError, lastError == null ? "" : "seed " + seed + ": " + lastError.Code + " " + lastError.Reason + " " + lastError.Message);
                Assert.IsNotNull(client.Result, "seed " + seed + ": the match did not finish in time after " + moves + " moves");
                Debug.Log("random match seed " + seed + " (" + deckId + "): " + moves + " moves, " + checks + " checks, winner " + client.Result.Winner);

                // The result dialog opens once the last steps have been shown; its button goes back
                // to the lobby, as a player would.
                var dialogBy = Time.realtimeSinceStartup + 5f;
                while (root.Q("modal").ClassListContains("hidden") && Time.realtimeSinceStartup < dialogBy)
                {
                    client.Pump();
                    board.Tick();
                    yield return null;
                }
                Assert.IsFalse(root.Q("modal").ClassListContains("hidden"), "seed " + seed + ": the result dialog");
                var back = root.Q("modal-options").Q<Button>();
                Assert.IsNotNull(back, "seed " + seed + ": the dialog's back button");
                using (var submit = NavigationSubmitEvent.GetPooled())
                {
                    submit.target = back;
                    back.SendEvent(submit);
                }
                yield return null;
                Assert.IsTrue(root.Q("modal").ClassListContains("hidden"), "seed " + seed + ": the dialog closed");
                Assert.IsFalse(root.Q("connect-panel").ClassListContains("hidden"), "seed " + seed + ": back in the lobby");
                var until = Time.realtimeSinceStartup + 5f;
                while (client.Socket != null && Time.realtimeSinceStartup < until)
                {
                    client.Pump();
                    yield return null;
                }
            }
        }

        /// <summary>What the board shows must be what the view says (ADR 0001: every control from
        /// `legal_intents`, every card from the view).</summary>
        private static void Check(VisualElement root, MatchClient client, MatchView view, string at)
        {
            var hand = root.Q<ScrollView>("hand").Children().OfType<CardElement>().Select(c => c.Instance).ToList();
            CollectionAssert.AreEqual(view.Me.Hand.Select(c => c.Instance).ToList(), hand, at + ": the hand");
            foreach (var (side, prefix) in new[] { (view.Me, "my-row-"), (view.Opponent, "opp-row-") })
            {
                foreach (var row in new[] { "melee", "ranged" })
                {
                    var shown = root.Q(prefix + row).Q("units").Children().OfType<CardElement>().ToList();
                    CollectionAssert.AreEqual(side.Rows[row].Cards.Select(c => c.Instance).ToList(), shown.Select(c => c.Instance).ToList(), at + ": " + prefix + row);
                    foreach (var element in shown)
                    {
                        var card = side.Rows[row].Cards.First(c => c.Instance == element.Instance);
                        Assert.AreEqual(card.Order != null, element.OrderButton != null, at + ": ability button of " + element.Instance);
                        if (element.OrderButton != null)
                        {
                            Assert.AreEqual(view.CanUseOrder(card.Instance), element.OrderButton.enabledSelf, at + ": ability of " + element.Instance);
                        }
                        var power = element.Q<Label>(className: "card__power").text;
                        Assert.AreEqual(card.Power.HasValue ? card.Power.Value.ToString() : "", power, at + ": power of " + element.Instance);
                    }
                }
            }
            Assert.AreEqual(view.Allows("pass"), root.Q<Button>("btn-pass").enabledSelf, at + ": pass");
            Assert.AreEqual(view.Allows("end_turn"), root.Q<Button>("btn-end-turn").enabledSelf, at + ": end turn");
            var endMulligan = root.Q<Button>("btn-end-mulligan");
            Assert.AreEqual(view.Allows("end_mulligan"), !endMulligan.ClassListContains("hidden") && endMulligan.enabledSelf, at + ": end mulligan");
            var leader = root.Q("leader-slot").Q<CardElement>();
            Assert.AreEqual(view.Me.Leader != null, leader != null, at + ": leader");
            if (leader?.OrderButton != null) Assert.AreEqual(view.CanUseOrder(view.Me.Leader.Instance), leader.OrderButton.enabledSelf, at + ": leader ability");
            foreach (var card in root.Q<ScrollView>("hand").Children().OfType<CardElement>())
            {
                Assert.AreEqual(view.PlayRows(card.Instance).Count > 0, card.ClassListContains("card--playable"), at + ": playable " + card.Instance);
                Assert.AreEqual(view.CanRedraw(card.Instance), card.ClassListContains("card--redrawable"), at + ": redrawable " + card.Instance);
            }
            var choice = view.PendingChoice;
            var modal = root.Q("modal");
            Assert.AreEqual(choice != null && choice.Kind == "card", !modal.ClassListContains("hidden") && client.Result == null,
                at + ": card dialog (title '" + root.Q<Label>("modal-title").text + "', phase " + view.Phase + ", choice " + (choice?.Kind ?? "none") + ")");
            var prompt = root.Q("prompt");
            Assert.AreEqual(choice != null || (view.Phase == "mulligan" && view.Me.Mulligan != null), !prompt.ClassListContains("hidden"), at + ": prompt");
            var cancel = root.Q<Button>("btn-cancel-choice");
            Assert.AreEqual(choice != null && choice.Cancellable, !cancel.ClassListContains("hidden"), at + ": cancel");
            if (choice != null && choice.Kind == "unit")
            {
                var candidates = root.Q("match").Query<CardElement>(className: "card--candidate").ToList().Select(c => c.Instance).OrderBy(i => i).ToList();
                CollectionAssert.AreEqual(choice.Options.Select(o => o.Instance).OrderBy(i => i).ToList(), candidates, at + ": candidates");
            }
            if (choice != null && choice.Kind == "row")
            {
                var lit = root.Q("match").Query(className: "row--candidate").ToList().Select(r => r.name).OrderBy(n => n).ToList();
                var expected = choice.Options.Select(o => (o.Side == "me" ? "my-row-" : "opp-row-") + o.Row).OrderBy(n => n).ToList();
                CollectionAssert.AreEqual(expected, lit, at + ": row candidates");
            }
            if (choice != null && choice.Kind == "place")
            {
                var slots = root.Q("match").Query(className: "slot").ToList().Count;
                Assert.AreEqual(choice.Options.Count, slots, at + ": place slots");
            }
            if (choice != null && choice.Kind == "card")
            {
                Assert.AreEqual(choice.Options.Count, root.Q("modal-options").Query<CardElement>().ToList().Count, at + ": card options");
            }
        }

        /// <summary>Perform an intent through the board's own controls, as a player would.</summary>
        private static IEnumerator Perform(VisualElement root, BoardView board, MatchClient client, MatchView view, JObject intent)
        {
            var kind = (string)intent["kind"];
            switch (kind)
            {
                case "mulligan":
                    Click(HandCard(root, (string)intent["card"]));
                    break;
                case "end_mulligan":
                    Click(root.Q<Button>("btn-end-mulligan"));
                    break;
                case "end_turn":
                    Click(root.Q<Button>("btn-end-turn"));
                    break;
                case "pass":
                    Click(root.Q<Button>("btn-pass"));
                    break;
                case "use_order":
                    Click(CardOnBoard(root, (string)intent["instance"]).OrderButton);
                    break;
                case "play_card":
                {
                    var card = HandCard(root, (string)intent["card"]);
                    if (intent["row"] == null)
                    {
                        Click(card);
                        break;
                    }
                    if (!card.ClassListContains("card--selected"))
                    {
                        Click(card);
                        yield return null;
                        board.Tick();
                    }
                    var cardId = view.Me.Hand.First(c => c.Instance == (string)intent["card"]).Card;
                    var def = client.Cards[cardId];
                    var mine = !((string)def["kind"] == "unit" && (string)def["side"] == "opponent");
                    Click(Slots(root, (mine ? "my-row-" : "opp-row-") + (string)intent["row"])[(int)intent["position"]]);
                    break;
                }
                case "choose":
                {
                    var choice = view.PendingChoice;
                    var index = (int)intent["option"];
                    var option = choice.Options[index];
                    switch (choice.Kind)
                    {
                        case "unit":
                            Click(CardOnBoard(root, option.Instance));
                            break;
                        case "row":
                            Click(root.Q((option.Side == "me" ? "my-row-" : "opp-row-") + option.Row));
                            break;
                        case "place":
                        {
                            // The slots of that row-side, in position order, are its options in position order.
                            var rowName = (option.Side == "me" ? "my-row-" : "opp-row-") + option.Row;
                            var positions = choice.Options.Where(o => o.Side == option.Side && o.Row == option.Row)
                                .Select(o => o.Position.Value).OrderBy(p => p).ToList();
                            Click(Slots(root, rowName)[positions.IndexOf(option.Position.Value)]);
                            break;
                        }
                        case "card":
                            Click(root.Q("modal-options").Query<CardElement>().ToList()[index]);
                            break;
                        default:
                            Assert.Fail("unknown choice kind " + choice.Kind);
                            break;
                    }
                    break;
                }
                case "cancel_choice":
                    Click(view.PendingChoice?.Kind == "card" ? root.Q<Button>("modal-cancel") : root.Q<Button>("btn-cancel-choice"));
                    break;
                default:
                    Assert.Fail("unknown intent kind " + kind);
                    break;
            }
        }

        private static CardElement HandCard(VisualElement root, string instance)
        {
            var card = root.Q<ScrollView>("hand").Children().OfType<CardElement>().FirstOrDefault(c => c.Instance == instance);
            Assert.IsNotNull(card, "no hand card " + instance);
            return card;
        }

        private static CardElement CardOnBoard(VisualElement root, string instance)
        {
            var card = root.Q("match").Query<CardElement>().ToList().FirstOrDefault(c => c.Instance == instance);
            Assert.IsNotNull(card, "no card " + instance + " on the board");
            return card;
        }

        private static List<VisualElement> Slots(VisualElement root, string row) =>
            root.Q(row).Q("units").Children().Where(c => c.ClassListContains("slot")).ToList();

        /// <summary>Click an element: a button answers to a submit like the one a pointer click
        /// raises through its Clickable; anything else to the click event the board listens for.</summary>
        private static void Click(VisualElement element)
        {
            Assert.IsNotNull(element, "nothing to click");
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

        /// <summary>A random entry of `legal_intents`; a play at a random legal position.</summary>
        private static JObject Pick(System.Random rng, MatchClient client, MatchView view)
        {
            if (view.Phase == "match_over" || view.LegalIntents.Count == 0) return null;
            var intent = view.LegalIntents[rng.Next(view.LegalIntents.Count)];
            if ((string)intent["kind"] != "play_card" || intent["row"] == null) return intent;
            var card = (string)intent["card"];
            var row = (string)intent["row"];
            var cardId = view.Me.Hand.First(c => c.Instance == card).Card;
            var def = client.Cards[cardId];
            var side = (string)def["kind"] == "unit" && (string)def["side"] == "opponent" ? view.Opponent : view.Me;
            return Intents.PlayCard(card, row, rng.Next(side.Rows[row].Cards.Count + 1));
        }

        private static IEnumerator Await(MatchClient client, Task task)
        {
            while (!task.IsCompleted)
            {
                client.Pump();
                yield return null;
            }
            if (task.IsFaulted) throw task.Exception?.InnerException ?? task.Exception;
        }
    }
}
