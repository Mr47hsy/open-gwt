// Plays a whole match against the server-hosted bot through MatchClient: the client's networking,
// message models and flow against the real server, with no UI. Needs a running server, named by
// OPENGWT_TEST_SERVER (for example http://127.0.0.1:8765); ignored otherwise.
using System;
using System.Collections;
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

        [UnityTest]
        public IEnumerator PlaysAFullMatchAgainstTheBot()
        {
            if (string.IsNullOrEmpty(Server)) Assert.Ignore("set OPENGWT_TEST_SERVER to run");
            using (var client = new MatchClient())
            {
                var leakedHands = 0;
                var views = 0;
                var events = 0;
                ErrorMessage lastError = null;
                client.ErrorReceived += e => lastError = e;
                client.EventReceived += _ => events++;
                client.ViewChanged += v =>
                {
                    views++;
                    if (v.Opponent.Hand != null) leakedHands++;
                };

                yield return Await(client, client.PrepareAsync(Server, "playmode", "zh-CN"));
                Assert.AreEqual("zh-CN", client.Locale);
                Assert.GreaterOrEqual(client.Cards.Count, 30);
                Assert.AreEqual("占位 A 单位 1", client.CardName("a-u-0001"));
                Assert.AreEqual("Placeholder A unit 1", client.I18n.Render("en", "card.a-u-0001.name"));

                yield return Await(client, client.PlayBotAsync("starter-a"));
                var moves = 0;
                var lastSeq = -1;
                var deadline = Time.realtimeSinceStartup + 120f;
                while (client.Result == null && Time.realtimeSinceStartup < deadline && lastError == null)
                {
                    client.Pump();
                    var view = client.View;
                    if (view != null && client.Hello != null && view.Seq != lastSeq)
                    {
                        lastSeq = view.Seq;
                        var move = ScriptedMove(view, client.Seat);
                        if (move != null)
                        {
                            moves++;
                            yield return Await(client, client.SendIntentAsync(move));
                        }
                    }
                    yield return null;
                }

                Assert.IsNull(lastError, lastError == null ? "" : lastError.Code + ": " + lastError.Message);
                Assert.IsNotNull(client.Result, "the match did not finish in time after " + moves + " moves");
                Assert.AreEqual(0, leakedHands, "the opponent's hand must never be in a view");
                Assert.Greater(views, 5);
                Assert.Greater(events, 10);
                Assert.IsTrue(client.Result.Winner == null || client.Result.Winner == 0 || client.Result.Winner == 1);
                Debug.Log("client e2e: " + moves + " moves, " + views + " views, " + events + " events, winner " + client.Result.Winner);
            }
        }

        /// <summary>The same policy as the server's scripted test client: first legal card, else pass.</summary>
        private static JObject ScriptedMove(MatchView view, int seat)
        {
            if (view.Phase == "match_over" || view.LegalIntents.Count == 0) return null;
            if (view.Phase == "mulligan")
            {
                var first = view.Me.Hand.Take(1).Select(c => c.Instance).ToArray();
                return new JObject { ["kind"] = "mulligan", ["cards"] = new JArray(first) };
            }
            if (view.Phase == "choosing") return view.LegalIntents[0];
            var play = view.LegalIntents.FirstOrDefault(i => (string)i["kind"] == "play_card");
            return play ?? new JObject { ["kind"] = "pass" };
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
