// The view of docs/protocol/match.md §7 must map onto the C# models without loss.
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using OpenGwt.Net;

namespace OpenGwt.Tests
{
    public class MessageModelTests
    {
        private const string ViewJson = @"{
          ""protocol"": 1, ""seq"": 42, ""phase"": ""playing"", ""round"": 1, ""turn"": ""me"",
          ""me"": { ""seat"": 0, ""faction"": ""placeholder-a"", ""score"": 17, ""lives"": 2, ""rounds_won"": 0, ""passed"": false,
                    ""hand"": [ { ""instance"": ""c17"", ""card"": ""a-u-0001"" } ], ""deck_count"": 12,
                    ""discard"": [], ""leader"": { ""card"": ""a-l-0001"", ""used"": false }, ""mulligan_done"": true,
                    ""rows"": { ""melee"": { ""effects"": [], ""units"": [ { ""instance"": ""c09"", ""card"": ""a-u-0001"", ""owner"": 0, ""power"": 5, ""base"": 5 } ] },
                                ""ranged"": { ""effects"": [""power_to_one""], ""units"": [] } } },
          ""opponent"": { ""seat"": 1, ""faction"": ""placeholder-b"", ""score"": 12, ""lives"": 2, ""rounds_won"": 0, ""passed"": true,
                    ""hand_count"": 8, ""deck_count"": 13, ""discard"": [], ""leader"": null, ""mulligan_done"": true,
                    ""rows"": { ""melee"": { ""effects"": [], ""units"": [] }, ""ranged"": { ""effects"": [], ""units"": [] } } },
          ""mulligan"": null,
          ""legal_intents"": [ { ""kind"": ""pass"" }, { ""kind"": ""play_card"", ""card"": ""c17"", ""row"": ""melee"" } ],
          ""pending_choice"": null, ""winner"": null }";

        [Test]
        public void ViewRoundTripsThroughTheModels()
        {
            var view = Json.Parse<MatchView>(ViewJson);
            Assert.AreEqual(42, view.Seq);
            Assert.AreEqual("playing", view.Phase);
            Assert.AreEqual(1, view.Me.Hand.Count);
            Assert.IsNull(view.Opponent.Hand);
            Assert.AreEqual(8, view.Opponent.HandCount);
            Assert.AreEqual(5, view.Me.Rows["melee"].Units[0].Base);
            Assert.AreEqual("power_to_one", view.Me.Rows["ranged"].Effects[0]);
            Assert.IsNull(view.Opponent.Leader);
            Assert.AreEqual("play_card", (string)view.LegalIntents[1]["kind"]);
            Assert.IsTrue(view.Opponent.Passed);
        }

        [Test]
        public void ErrorsAndHelloParse()
        {
            var error = Json.Parse<ErrorMessage>(@"{""type"":""error"",""code"":""not_your_turn"",""message_key"":""error.not-your-turn"",""params"":{},""message"":""It is not your turn."",""intent_id"":""x1""}");
            Assert.AreEqual("not_your_turn", error.Code);
            Assert.AreEqual("x1", error.IntentId);
            var hello = Json.Parse<HelloMessage>(@"{""type"":""hello"",""protocol"":1,""pack_hash"":""sha256:abc"",""match_id"":""m"",""player_id"":""p"",""seat"":1,""locale"":""zh-CN""}");
            Assert.AreEqual(1, hello.Seat);
            Assert.AreEqual("sha256:abc", hello.PackHash);
            var intent = Json.Stringify(new { kind = "play_card", card = "c1", row = "melee" });
            Assert.AreEqual("play_card", (string)JObject.Parse(intent)["kind"]);
        }
    }
}
