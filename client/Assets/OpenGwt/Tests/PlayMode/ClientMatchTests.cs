// Plays whole matches against the server-hosted bot through MatchClient: the client's networking,
// message models and flow against the real server on protocol 2, with no UI. The policy takes
// every move from `legal_intents` alone — it never derives legality — and covers every intent
// kind: one redraw per round and `end_mulligan`, activated abilities, a card at a random legal
// row and position, `end_turn`, a pass now and then while one is offered (the server passes for
// an empty hand by itself), and every choice, with one `cancel_choice` on the first cancellable
// one. Needs a running server, named by
// OPENGWT_TEST_SERVER (for example http://127.0.0.1:8765); ignored otherwise.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using OpenGwt.Match;
using OpenGwt.Net;
using UnityEngine;
using UnityEngine.TestTools;

namespace OpenGwt.Tests
{
    public class ClientMatchTests
    {
        private static string Server => Environment.GetEnvironmentVariable("OPENGWT_TEST_SERVER");

        /// <summary>The server closes a socket that sends more than twenty intents a second
        /// (match.md §3); a scripted client stays well below that.</summary>
        private const float MinSecondsBetweenIntents = 0.06f;

        private const float MatchDeadlineSeconds = 240f;

        [UnityTest]
        public IEnumerator PlaysAFullMatchAgainstTheBotWithStarterA() => PlayMatch("starter-a", 1);

        [UnityTest]
        public IEnumerator PlaysAFullMatchAgainstTheBotWithStarterB() => PlayMatch("starter-b", 2);

        private IEnumerator PlayMatch(string deckId, int seed)
        {
            if (string.IsNullOrEmpty(Server)) Assert.Ignore("set OPENGWT_TEST_SERVER to run");
            using (var client = new MatchClient())
            {
                var leaks = new List<string>();
                var views = 0;
                var events = 0;
                ErrorMessage lastError = null;
                client.ErrorReceived += e => lastError = e;
                client.EventReceived += e =>
                {
                    events++;
                    var type = (string)e["type"];
                    if ((type == "card_drawn" || type == "card_redrawn") && (int?)e["seat"] != client.Seat && e["card"] != null)
                    {
                        leaks.Add("the opponent's draw named its card: " + e);
                    }
                    if (type == "choice_requested" && e["options"] != null) leaks.Add("choice options in an event: " + e);
                };
                client.ViewChanged += v =>
                {
                    views++;
                    if (v.Opponent.Hand != null) leaks.Add("the opponent's hand was in a view");
                    Assert.AreEqual(2, v.Protocol);
                };
                client.MessageReceived += json =>
                {
                    if (json.Contains("\"seed\"")) leaks.Add("a message carried a seed");
                    if (json.Contains("\"deck\":[")) leaks.Add("a message carried a deck's order");
                };

                client.SetLocale("zh-CN");
                yield return Await(client, client.PrepareAsync(Server, "playmode"));
                Assert.AreEqual("zh-CN", client.Locale);
                Assert.AreEqual("和机器人对战", client.Text("ui.lobby.bot"));
                Assert.AreEqual("你：打出 占位 A 单位 1", client.Text("ui.event.card-played", MatchClient.P("who", "@ui.who.you", "card", "@card.u-1001.name")));
                Assert.GreaterOrEqual(client.Cards.Count, 30);
                Assert.AreEqual("占位 A 单位 1", client.CardName("u-1001"));
                Assert.AreEqual("Placeholder A unit 1", client.I18n.Render("en", "card.u-1001.name"));
                var deck = client.Decks.Single(d => d.Id == deckId);
                Assert.IsNotNull(deck.Leader);
                Assert.IsNotNull(deck.Stratagem);
                Assert.Greater(deck.ProvisionsBudget, 0);
                Assert.LessOrEqual(deck.ProvisionsUsed, deck.ProvisionsBudget);
                Assert.IsEmpty(deck.Problems);

                yield return Await(client, client.PlayBotAsync(deckId));
                var policy = new Policy(client, seed);
                var lastSeq = -1;
                var lastSentAt = -1f;
                var deadline = Time.realtimeSinceStartup + MatchDeadlineSeconds;
                while (client.Result == null && Time.realtimeSinceStartup < deadline && lastError == null)
                {
                    client.Pump();
                    var view = client.View;
                    if (view != null && client.Hello != null && view.Seq != lastSeq && Time.realtimeSinceStartup - lastSentAt >= MinSecondsBetweenIntents)
                    {
                        var move = policy.Next(view);
                        if (move != null)
                        {
                            lastSeq = view.Seq;
                            lastSentAt = Time.realtimeSinceStartup;
                            yield return Await(client, client.SendIntentAsync(move));
                        }
                    }
                    yield return null;
                }

                Assert.IsNull(lastError, lastError == null ? "" : lastError.Code + ": " + lastError.Message + " " + lastError.Details);
                Assert.IsNotNull(client.Result, "the match did not finish in time after " + policy.Sent + " moves");
                Assert.IsEmpty(leaks);
                Assert.Greater(views, 5);
                Assert.Greater(events, 10);
                Assert.IsTrue(client.Result.Winner == null || client.Result.Winner == 0 || client.Result.Winner == 1);
                Assert.IsNotEmpty(client.Result.Rounds);
                foreach (var kind in new[] { "mulligan", "end_mulligan", "play_card", "use_order", "end_turn", "pass", "choose" })
                {
                    Assert.IsTrue(policy.Used.Contains(kind), "the match never called for " + kind + "; used " + string.Join(", ", policy.Used));
                }
                Assert.IsTrue(policy.ChoiceKinds.Contains("unit"), "no unit choice; kinds " + string.Join(", ", policy.ChoiceKinds));
                Debug.Log("client e2e " + deckId + ": " + policy.Sent + " moves, " + views + " views, " + events + " events, winner "
                    + client.Result.Winner + ", intents " + string.Join(", ", policy.Used) + ", choices " + string.Join(", ", policy.ChoiceKinds)
                    + (policy.Cancelled ? ", one cancelled" : ""));
            }
        }

        /// <summary>Picks every move from the view's `legal_intents`; positions are drawn from the
        /// range a compressed `play_card` entry stands for (match.md §6).</summary>
        private sealed class Policy
        {
            private readonly MatchClient client;
            private readonly System.Random rng;
            private int redrewInRound;

            public readonly HashSet<string> Used = new HashSet<string>();
            public readonly HashSet<string> ChoiceKinds = new HashSet<string>();
            public bool Cancelled;
            public int Sent;

            public Policy(MatchClient client, int seed)
            {
                this.client = client;
                rng = new System.Random(seed);
            }

            public JObject Next(MatchView view)
            {
                var move = Pick(view);
                if (move == null) return null;
                Sent++;
                Used.Add((string)move["kind"]);
                return move;
            }

            private JObject Pick(MatchView view)
            {
                if (view.Phase == "match_over" || view.LegalIntents.Count == 0) return null;
                var legal = view.LegalIntents;
                if (view.Phase == "mulligan")
                {
                    var redraws = legal.Where(i => (string)i["kind"] == "mulligan").ToList();
                    if (redraws.Count > 0 && redrewInRound != view.Round)
                    {
                        redrewInRound = view.Round;
                        return redraws[rng.Next(redraws.Count)];
                    }
                    return view.Allows("end_mulligan") ? Intents.EndMulligan() : null;
                }
                if (view.Phase == "choosing")
                {
                    if (view.PendingChoice == null) return null;
                    ChoiceKinds.Add(view.PendingChoice.Kind);
                    if (!Cancelled && view.Allows("cancel_choice"))
                    {
                        Cancelled = true;
                        return Intents.CancelChoice();
                    }
                    var choices = legal.Where(i => (string)i["kind"] == "choose").ToList();
                    return choices[rng.Next(choices.Count)];
                }
                var orders = legal.Where(i => (string)i["kind"] == "use_order").ToList();
                if (orders.Count > 0) return orders[0];
                // A deliberate pass one time in six, so the intent is exercised and not only the
                // automatic pass of an empty hand.
                if (view.Allows("pass") && rng.Next(6) == 0) return Intents.Pass();
                var plays = legal.Where(i => (string)i["kind"] == "play_card").ToList();
                if (plays.Count > 0)
                {
                    var play = plays[rng.Next(plays.Count)];
                    var card = (string)play["card"];
                    var row = (string)play["row"];
                    if (row == null) return Intents.PlayCard(card);
                    var cardId = view.Me.Hand.First(c => c.Instance == card).Card;
                    var def = client.Cards[cardId];
                    var side = (string)def["kind"] == "unit" && (string)def["side"] == "opponent" ? view.Opponent : view.Me;
                    return Intents.PlayCard(card, row, rng.Next(side.Rows[row].Cards.Count + 1));
                }
                if (view.Allows("end_turn")) return Intents.EndTurn();
                if (view.Allows("pass")) return Intents.Pass();
                return null;
            }
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
