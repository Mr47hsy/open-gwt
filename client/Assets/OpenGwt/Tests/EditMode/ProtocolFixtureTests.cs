// Every message the rules core emits — generated into Fixtures/ by the server's
// `python -m tests.client_fixtures` from the replay scenarios and the golden match — parses into
// the client's models, and together the fixtures show every event type of match.md §8 and every
// kind of choice of §7. The server's test_client_fixtures.py keeps the files fresh.
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using OpenGwt.Net;
using UnityEngine;

namespace OpenGwt.Tests
{
    public class ProtocolFixtureTests
    {
        // docs/protocol/match.md §8, in the order of its table.
        private static readonly string[] EventTypes =
        {
            "match_started", "stratagem_placed", "round_started", "card_drawn", "draw_skipped", "mulligan_started",
            "card_redrawn", "mulligan_done", "turn_started", "turn_ended", "card_played", "order_used", "card_summoned",
            "card_moved", "card_returned", "control_changed", "card_discarded", "card_destroyed", "card_banished",
            "unit_damaged", "damage_blocked", "unit_boosted", "unit_healed", "base_power_changed", "armor_changed",
            "power_changed", "status_added", "status_reduced", "status_removed", "charges_changed", "row_effect_set",
            "row_effect_cleared", "choice_requested", "choice_made", "choice_cancelled", "player_passed", "round_ended",
            "board_cleared", "match_ended",
        };

        private static readonly string FixtureDir = Path.Combine(Application.dataPath, "OpenGwt", "Tests", "EditMode", "Fixtures");

        private static IEnumerable<(string file, JObject step)> Steps()
        {
            var files = Directory.GetFiles(FixtureDir, "*.json").OrderBy(f => f).ToList();
            Assert.IsNotEmpty(files, "no fixtures: run `python -m tests.client_fixtures` in server/");
            foreach (var file in files)
            {
                var doc = JObject.Parse(File.ReadAllText(file));
                foreach (var step in (JArray)doc["steps"]) yield return (Path.GetFileName(file), (JObject)step);
            }
        }

        [Test]
        public void EveryViewParsesAndHidesTheOpponentsHand()
        {
            var views = 0;
            foreach (var (file, step) in Steps())
            {
                if (!(step["views"] is JObject byseat)) continue;
                foreach (var pair in byseat)
                {
                    views++;
                    var raw = (JObject)pair.Value;
                    var view = Json.Convert<MatchView>(raw);
                    Assert.AreEqual(2, view.Protocol, file);
                    Assert.AreEqual(int.Parse(pair.Key), view.Me.Seat, file);
                    Assert.IsNotNull(view.Me.Hand, file);
                    Assert.IsNull(view.Opponent.Hand, file + ": the opponent's hand must never be in a view");
                    Assert.IsNull(raw["opponent"]["hand"], file);
                    Assert.AreEqual(view.Me.Hand.Count, view.Me.HandCount, file);
                    foreach (var side in new[] { view.Me, view.Opponent })
                    {
                        Assert.IsNotNull(side.Rows["melee"], file);
                        Assert.IsNotNull(side.Rows["ranged"], file);
                        foreach (var row in side.Rows.Values)
                        {
                            foreach (var card in row.Cards)
                            {
                                Assert.IsNotNull(card.Instance, file);
                                Assert.IsNotNull(card.Statuses, file);
                                if (card.Power.HasValue) Assert.IsTrue(card.Base.HasValue && card.Aura.HasValue && card.Armor.HasValue, file);
                            }
                        }
                    }
                    foreach (var intent in view.LegalIntents) Assert.IsNotNull((string)intent["kind"], file);
                    if (view.Phase == "match_over") Assert.IsNotNull(view.Winner, file);
                }
            }
            Assert.Greater(views, 20);
        }

        [Test]
        public void EveryKindOfChoiceHasTheShapeOfItsOptions()
        {
            var kinds = new HashSet<string>();
            var offers = 0;
            foreach (var (file, step) in Steps())
            {
                if (!(step["views"] is JObject byseat)) continue;
                foreach (var pair in byseat)
                {
                    var view = Json.Convert<MatchView>((JObject)pair.Value);
                    var choice = view.PendingChoice;
                    if (choice == null) continue;
                    Assert.AreEqual("choosing", view.Phase, file);
                    Assert.IsTrue(choice.PromptKey.StartsWith("choice."), file);
                    Assert.IsNotNull(choice.Source?.Instance, file);
                    Assert.IsNotEmpty(choice.Options, file);
                    Assert.AreEqual(choice.Options.Count + (choice.Cancellable ? 1 : 0), view.LegalIntents.Count, file);
                    kinds.Add(choice.Kind);
                    foreach (var option in choice.Options)
                    {
                        switch (choice.Kind)
                        {
                            case "unit":
                                Assert.IsTrue(option.Side != null && option.Row != null && option.Position.HasValue && option.Instance != null && option.Card != null, file);
                                var side = option.Side == "me" ? view.Me : view.Opponent;
                                Assert.AreEqual(option.Instance, side.Rows[option.Row].Cards[option.Position.Value].Instance, file + ": a unit option names a card on the board");
                                break;
                            case "row":
                                Assert.IsTrue(option.Side != null && option.Row != null && !option.Position.HasValue && option.Instance == null, file);
                                break;
                            case "place":
                                Assert.IsTrue(option.Side != null && option.Row != null && option.Position.HasValue && option.Instance == null, file);
                                Assert.IsNotNull(choice.Card?.Card, file + ": a place choice names the card being placed");
                                break;
                            case "card":
                                Assert.IsNotNull(option.Card, file);
                                Assert.IsNull(option.Row, file);
                                if (option.Instance == null) offers++;
                                break;
                            default:
                                Assert.Fail(file + ": unknown choice kind " + choice.Kind);
                                break;
                        }
                    }
                }
            }
            CollectionAssert.AreEquivalent(new[] { "unit", "row", "place", "card" }, kinds);
            Assert.Greater(offers, 0, "a `create` offer has no instance");
        }

        [Test]
        public void EveryEventTypeOfTheProtocolAppearsAndParses()
        {
            var seen = new HashSet<string>();
            foreach (var (file, step) in Steps())
            {
                foreach (var pair in (JObject)step["events"])
                {
                    var seat = int.Parse(pair.Key);
                    foreach (var evt in (JArray)pair.Value)
                    {
                        var type = (string)evt["type"];
                        seen.Add(type);
                        Assert.IsNotNull((int?)evt["seq"], file);
                        var owner = (int?)evt["seat"];
                        if ((type == "card_drawn" || type == "card_redrawn") && owner != seat)
                        {
                            Assert.IsNull(evt["card"], file + ": another player's draw shows no card");
                            Assert.IsNull(evt["instance"], file);
                        }
                        if (type == "choice_requested") Assert.IsNull(evt["options"], file + ": options are only in the chooser's view");
                        if (type == "choice_made" && owner != seat) Assert.IsNull(evt["option"], file);
                        if (type == "card_destroyed") Assert.IsNotNull((bool?)evt["banished"], file);
                    }
                }
            }
            CollectionAssert.IsSubsetOf(EventTypes, seen, "event types the fixtures never show");
            CollectionAssert.IsSubsetOf(seen, EventTypes, "event types match.md §8 does not list");
        }

        [Test]
        public void NoFixtureCarriesTheSeedOrADeckOrder()
        {
            foreach (var file in Directory.GetFiles(FixtureDir, "*.json"))
            {
                var text = File.ReadAllText(file);
                Assert.IsFalse(text.Contains("\"seed\""), file);
                Assert.IsFalse(text.Contains("\"deck\":["), file + ": a deck is only ever a count");
            }
        }
    }
}
