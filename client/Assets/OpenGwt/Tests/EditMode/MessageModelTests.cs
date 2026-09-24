// The view, errors and result of docs/protocol/match.md (protocol 2) must map onto the C# models
// without loss, and the intent builders must produce the shapes of §6.
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using OpenGwt.Net;

namespace OpenGwt.Tests
{
    public class MessageModelTests
    {
        // The example of match.md §7, with a pending choice added.
        private const string ViewJson = @"{
          ""protocol"": 2, ""match_id"": ""m1"", ""seq"": 42, ""phase"": ""choosing"", ""round"": 2, ""turn"": ""me"", ""winner"": null,
          ""me"": { ""seat"": 0, ""faction"": ""placeholder-a"", ""score"": 17, ""rounds_won"": 1, ""passed"": false,
                    ""hand"": [ { ""instance"": ""c17"", ""card"": ""u-0002"" } ], ""hand_count"": 1, ""deck_count"": 12,
                    ""graveyard"": [ { ""instance"": ""c03"", ""card"": ""s-0001"" } ], ""banished"": [],
                    ""leader"": { ""instance"": ""c29"", ""card"": ""l-0001"", ""order"": { ""ready"": true, ""charges"": 1, ""cooldown"": 0 } },
                    ""mulligan"": null,
                    ""rows"": { ""melee"": { ""effect"": null, ""cards"": [
                                  { ""instance"": ""c09"", ""card"": ""u-0003"", ""owner"": 0, ""power"": 6, ""base"": 4, ""aura"": 1, ""armor"": 2,
                                    ""statuses"": [ { ""status"": ""bleeding"", ""turns"": 2 }, { ""status"": ""shielded"" } ], ""order"": null },
                                  { ""instance"": ""c11"", ""card"": ""a-0001"", ""owner"": 0, ""statuses"": [],
                                    ""order"": { ""ready"": false, ""charges"": null, ""cooldown"": 1 } } ] },
                                ""ranged"": { ""effect"": { ""effect"": ""damage_weakest"", ""amount"": 2 }, ""cards"": [] } } },
          ""opponent"": { ""seat"": 1, ""faction"": ""placeholder-b"", ""score"": 12, ""rounds_won"": 1, ""passed"": false,
                    ""hand_count"": 8, ""deck_count"": 13, ""graveyard"": [], ""banished"": [], ""leader"": null,
                    ""mulligan"": { ""remaining"": 2, ""done"": false },
                    ""rows"": { ""melee"": { ""effect"": null, ""cards"": [] }, ""ranged"": { ""effect"": null, ""cards"": [] } } },
          ""legal_intents"": [ { ""kind"": ""choose"", ""option"": 0 }, { ""kind"": ""choose"", ""option"": 1 }, { ""kind"": ""cancel_choice"" } ],
          ""pending_choice"": { ""kind"": ""unit"", ""prompt_key"": ""choice.damage"", ""source"": { ""instance"": ""c21"", ""card"": ""u-0002"" },
                                ""cancellable"": true,
                                ""options"": [ { ""side"": ""opponent"", ""row"": ""melee"", ""position"": 0, ""instance"": ""c40"", ""card"": ""u-0101"" },
                                               { ""side"": ""opponent"", ""row"": ""ranged"", ""position"": 2, ""instance"": ""c44"", ""card"": ""u-0010"" } ] } }";

        [Test]
        public void ViewRoundTripsThroughTheModels()
        {
            var view = Json.Parse<MatchView>(ViewJson);
            Assert.AreEqual(2, view.Protocol);
            Assert.AreEqual("m1", view.MatchId);
            Assert.AreEqual(42, view.Seq);
            Assert.AreEqual("choosing", view.Phase);
            Assert.IsNull(view.Winner);
            Assert.AreEqual(1, view.Me.Hand.Count);
            Assert.AreEqual(1, view.Me.HandCount);
            Assert.IsNull(view.Opponent.Hand, "the opponent's side never has a hand");
            Assert.AreEqual(8, view.Opponent.HandCount);
            Assert.AreEqual(1, view.Me.Graveyard.Count);
            Assert.AreEqual("c29", view.Me.Leader.Instance);
            Assert.IsTrue(view.Me.Leader.Order.Ready);
            Assert.AreEqual(1, view.Me.Leader.Order.Charges);
            Assert.IsNull(view.Opponent.Leader);
            Assert.AreEqual(2, view.Opponent.Mulligan.Remaining);
            Assert.IsFalse(view.Opponent.Mulligan.Done);

            var unit = view.Me.Rows["melee"].Cards[0];
            Assert.AreEqual(6, unit.Power);
            Assert.AreEqual(4, unit.Base);
            Assert.AreEqual(1, unit.Aura);
            Assert.AreEqual(5, unit.OwnPower, "current power without the aura");
            Assert.AreEqual(2, unit.Armor);
            Assert.AreEqual(2, unit.Statuses[0].Turns);
            Assert.IsTrue(unit.Has("shielded"));
            Assert.IsNull(unit.Statuses[1].Turns);
            Assert.IsNull(unit.Order);
            var artifact = view.Me.Rows["melee"].Cards[1];
            Assert.IsNull(artifact.Power, "an artifact has no power");
            Assert.IsNull(artifact.Order.Charges, "unlimited charges are null");
            Assert.AreEqual(1, artifact.Order.Cooldown);
            Assert.AreEqual("damage_weakest", view.Me.Rows["ranged"].Effect.Effect);
            Assert.AreEqual(2, view.Me.Rows["ranged"].Effect.Amount);
            Assert.IsNull(view.Me.Rows["ranged"].Effect.Count);
            Assert.IsNull(view.Me.Rows["melee"].Effect);

            var choice = view.PendingChoice;
            Assert.AreEqual("unit", choice.Kind);
            Assert.AreEqual("choice.damage", choice.PromptKey);
            Assert.AreEqual("c21", choice.Source.Instance);
            Assert.IsTrue(choice.Cancellable);
            Assert.AreEqual(2, choice.Options.Count);
            Assert.AreEqual("opponent", choice.Options[1].Side);
            Assert.AreEqual(2, choice.Options[1].Position);
            Assert.AreEqual("c44", choice.Options[1].Instance);
            Assert.IsNull(choice.Card, "only a place choice names the card being placed");

            Assert.IsTrue(view.Allows("cancel_choice"));
            Assert.IsFalse(view.Allows("pass"));
        }

        [Test]
        public void LegalIntentsDriveTheHelpers()
        {
            var view = Json.Parse<MatchView>(@"{""legal_intents"": [
                { ""kind"": ""pass"" }, { ""kind"": ""play_card"", ""card"": ""c17"", ""row"": ""melee"" },
                { ""kind"": ""play_card"", ""card"": ""c17"", ""row"": ""ranged"" }, { ""kind"": ""play_card"", ""card"": ""c18"" },
                { ""kind"": ""use_order"", ""instance"": ""c29"" }, { ""kind"": ""mulligan"", ""card"": ""c17"" } ]}");
            CollectionAssert.AreEqual(new[] { "melee", "ranged" }, view.PlayRows("c17"));
            CollectionAssert.AreEqual(new string[] { null }, view.PlayRows("c18"), "a special is playable without a row");
            Assert.IsEmpty(view.PlayRows("c19"));
            Assert.IsTrue(view.CanUseOrder("c29"));
            Assert.IsFalse(view.CanUseOrder("c17"));
            Assert.IsTrue(view.CanRedraw("c17"));
            Assert.IsTrue(view.Allows("pass"));
            Assert.IsFalse(view.Allows("end_turn"));
        }

        [Test]
        public void IntentsHaveTheWireShape()
        {
            Assert.AreEqual("{\"kind\":\"mulligan\",\"card\":\"c1\"}", Intents.Mulligan("c1").ToString(Newtonsoft.Json.Formatting.None));
            Assert.AreEqual("{\"kind\":\"end_mulligan\"}", Intents.EndMulligan().ToString(Newtonsoft.Json.Formatting.None));
            Assert.AreEqual("{\"kind\":\"play_card\",\"card\":\"c1\",\"row\":\"melee\",\"position\":3}",
                Intents.PlayCard("c1", "melee", 3).ToString(Newtonsoft.Json.Formatting.None));
            Assert.AreEqual("{\"kind\":\"play_card\",\"card\":\"c2\"}", Intents.PlayCard("c2").ToString(Newtonsoft.Json.Formatting.None));
            Assert.AreEqual("{\"kind\":\"use_order\",\"instance\":\"c9\"}", Intents.UseOrder("c9").ToString(Newtonsoft.Json.Formatting.None));
            Assert.AreEqual("{\"kind\":\"end_turn\"}", Intents.EndTurn().ToString(Newtonsoft.Json.Formatting.None));
            Assert.AreEqual("{\"kind\":\"pass\"}", Intents.Pass().ToString(Newtonsoft.Json.Formatting.None));
            Assert.AreEqual("{\"kind\":\"choose\",\"option\":2}", Intents.Choose(2).ToString(Newtonsoft.Json.Formatting.None));
            Assert.AreEqual("{\"kind\":\"cancel_choice\"}", Intents.CancelChoice().ToString(Newtonsoft.Json.Formatting.None));
        }

        [Test]
        public void ErrorsHelloAndResultParse()
        {
            var error = Json.Parse<ErrorMessage>(@"{""type"":""error"",""code"":""illegal_intent"",""message_key"":""error.illegal-intent"",""params"":{},""message"":""No."",""intent_id"":""x1"",""details"":{""reason"":""error.play.row-full""}}");
            Assert.AreEqual("illegal_intent", error.Code);
            Assert.AreEqual("x1", error.IntentId);
            Assert.AreEqual("error.play.row-full", error.Reason);
            Assert.IsNull(Json.Parse<ErrorMessage>(@"{""type"":""error"",""code"":""not_your_turn""}").Reason);

            var hello = Json.Parse<HelloMessage>(@"{""type"":""hello"",""protocol"":2,""pack_hash"":""sha256:abc"",""match_id"":""m"",""player_id"":""p"",""seat"":1,""locale"":""zh-CN""}");
            Assert.AreEqual(2, hello.Protocol);
            Assert.AreEqual(1, hello.Seat);

            var result = Json.Parse<MatchResult>(@"{""winner"":null,""rounds"":[{""round"":1,""winners"":[0,1],""scores"":[10,10]},{""round"":2,""winners"":[1],""scores"":[3,9]}]}");
            Assert.IsNull(result.Winner);
            Assert.AreEqual(2, result.Rounds.Count);
            CollectionAssert.AreEqual(new[] { 0, 1 }, result.Rounds[0].Winners, "a tie has two winners");
            Assert.AreEqual(9, result.Rounds[1].Scores[1]);

            // On connect to a finished match the server sends match_over with a null seq (§4).
            var over = JObject.Parse(@"{""type"":""match_over"",""seq"":null,""result"":{""winner"":1,""rounds"":[]}}");
            Assert.AreEqual(JTokenType.Null, over["seq"].Type);
            Assert.AreEqual(1, Json.Convert<MatchResult>(over["result"]).Winner);
            Assert.IsNull(Json.Convert<MatchResult>(JValue.CreateNull()), "a null result parses to null, which the client replaces");
        }
    }
}
