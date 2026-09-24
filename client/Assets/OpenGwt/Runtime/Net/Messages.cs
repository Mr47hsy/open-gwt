// Shapes of docs/protocol/match.md (protocol 2). Property names are PascalCase here and
// snake_case on the wire (see Json.Settings). Events stay JObject: the set is open-ended and the
// client only animates what it knows.
using System.Collections.Generic;
using Newtonsoft.Json.Linq;

namespace OpenGwt.Net
{
    public sealed class TokenResponse
    {
        public string Token { get; set; }
        public string PlayerId { get; set; }
    }

    public sealed class I18nLocales
    {
        public List<string> Locales { get; set; }
        public string PackHash { get; set; }
    }

    public sealed class MatchCreated
    {
        public string MatchId { get; set; }
        public string RoomCode { get; set; }
        public string WsUrl { get; set; }
    }

    public sealed class HelloMessage
    {
        public string Type { get; set; }
        public int Protocol { get; set; }
        public string PackHash { get; set; }
        public string MatchId { get; set; }
        public string PlayerId { get; set; }
        public int Seat { get; set; }
        public string Locale { get; set; }
    }

    /// <summary>A card by instance and card id: a hand or zone entry, a choice's source, the card a
    /// placement puts down.</summary>
    public sealed class CardRef
    {
        public string Instance { get; set; }
        public string Card { get; set; }
    }

    /// <summary>The activated ability of a card on the board or of the leader (§7): `Charges` is null
    /// when unlimited; `Ready` is only ever true for this player's cards on their turn.</summary>
    public sealed class OrderView
    {
        public bool Ready { get; set; }
        public int? Charges { get; set; }
        public int Cooldown { get; set; }
    }

    /// <summary>A status on a card, with its timer when it has one (`cards.md` §9).</summary>
    public sealed class StatusView
    {
        public string Status { get; set; }
        public int? Turns { get; set; }
    }

    /// <summary>A card on a row-side (§7). Power fields are only present for units: `Power` is the
    /// current power plus `Aura`; the unit is boosted when `Power - Aura` is above `Base`, damaged
    /// when below. `Order` is null for a card without an activated ability.</summary>
    public sealed class BoardCardView
    {
        public string Instance { get; set; }
        public string Card { get; set; }
        public int Owner { get; set; }
        public int? Power { get; set; }
        public int? Base { get; set; }
        public int? Aura { get; set; }
        public int? Armor { get; set; }
        public List<StatusView> Statuses { get; set; } = new List<StatusView>();
        public OrderView Order { get; set; }

        /// <summary>The current power without the aura, for the boosted / damaged comparison.</summary>
        public int? OwnPower => Power.HasValue ? Power.Value - (Aura ?? 0) : (int?)null;

        public bool Has(string status)
        {
            foreach (var s in Statuses)
            {
                if (s.Status == status) return true;
            }
            return false;
        }
    }

    /// <summary>The row effect of a row-side (`cards.md` §10), or null.</summary>
    public sealed class RowEffectView
    {
        public string Effect { get; set; }
        public int Amount { get; set; }
        public int? Count { get; set; }
    }

    public sealed class RowView
    {
        public RowEffectView Effect { get; set; }
        public List<BoardCardView> Cards { get; set; } = new List<BoardCardView>();
    }

    public sealed class LeaderView
    {
        public string Instance { get; set; }
        public string Card { get; set; }
        public OrderView Order { get; set; }
    }

    /// <summary>During the mulligan, a player's redraws left and whether they are done (§7).</summary>
    public sealed class MulliganView
    {
        public int Remaining { get; set; }
        public bool Done { get; set; }
    }

    public sealed class SideView
    {
        public int Seat { get; set; }
        public string Faction { get; set; }
        public int Score { get; set; }
        public int RoundsWon { get; set; }
        public bool Passed { get; set; }
        /// <summary>Own hand only; the opponent's side never has it (§7, §11).</summary>
        public List<CardRef> Hand { get; set; }
        public int HandCount { get; set; }
        public int DeckCount { get; set; }
        public List<CardRef> Graveyard { get; set; } = new List<CardRef>();
        public List<CardRef> Banished { get; set; } = new List<CardRef>();
        public LeaderView Leader { get; set; }
        public MulliganView Mulligan { get; set; }
        public Dictionary<string, RowView> Rows { get; set; } = new Dictionary<string, RowView>();
    }

    /// <summary>One option of a pending choice (§7). Which fields are present depends on the kind:
    /// `unit` has side, row, position, instance and card; `row` side and row; `place` side, row and
    /// position; `card` instance and card — or card alone for what `create` offers.</summary>
    public sealed class ChoiceOption
    {
        public string Side { get; set; }
        public string Row { get; set; }
        public int? Position { get; set; }
        public string Instance { get; set; }
        public string Card { get; set; }
    }

    public sealed class PendingChoice
    {
        public string Kind { get; set; }
        public string PromptKey { get; set; }
        public CardRef Source { get; set; }
        public bool Cancellable { get; set; }
        public List<ChoiceOption> Options { get; set; } = new List<ChoiceOption>();
        /// <summary>For a `place` choice, the card being placed.</summary>
        public CardRef Card { get; set; }
    }

    public sealed class MatchView
    {
        public int Protocol { get; set; }
        public string MatchId { get; set; }
        public int Seq { get; set; }
        public string Phase { get; set; }
        public int Round { get; set; }
        public string Turn { get; set; }
        public string Winner { get; set; }
        public SideView Me { get; set; }
        public SideView Opponent { get; set; }
        public List<JObject> LegalIntents { get; set; } = new List<JObject>();
        public PendingChoice PendingChoice { get; set; }

        // --- what the server allows right now (§6): the only source of enabled controls ---------

        public bool Allows(string kind)
        {
            foreach (var intent in LegalIntents)
            {
                if ((string)intent["kind"] == kind) return true;
            }
            return false;
        }

        /// <summary>The rows a card in hand may be played to; empty when it cannot be played. A
        /// special, which has no row, is listed once with a null row.</summary>
        public List<string> PlayRows(string instance)
        {
            var rows = new List<string>();
            foreach (var intent in LegalIntents)
            {
                if ((string)intent["kind"] == "play_card" && (string)intent["card"] == instance) rows.Add((string)intent["row"]);
            }
            return rows;
        }

        public bool CanUseOrder(string instance)
        {
            foreach (var intent in LegalIntents)
            {
                if ((string)intent["kind"] == "use_order" && (string)intent["instance"] == instance) return true;
            }
            return false;
        }

        public bool CanRedraw(string instance)
        {
            foreach (var intent in LegalIntents)
            {
                if ((string)intent["kind"] == "mulligan" && (string)intent["card"] == instance) return true;
            }
            return false;
        }
    }

    public sealed class RoundResult
    {
        public int Round { get; set; }
        public List<int> Winners { get; set; } = new List<int>();
        public List<int> Scores { get; set; } = new List<int>();
    }

    public sealed class MatchResult
    {
        public int? Winner { get; set; }
        public List<RoundResult> Rounds { get; set; } = new List<RoundResult>();
    }

    public sealed class ErrorMessage
    {
        public string Type { get; set; }
        public string Code { get; set; }
        public string MessageKey { get; set; }
        public JObject Params { get; set; }
        public string Message { get; set; }
        public string IntentId { get; set; }
        public JToken Details { get; set; }

        /// <summary>The reason key of an `illegal_intent` (§10), or null.</summary>
        public string Reason => Details is JObject d && d["reason"] is JValue v && v.Type == JTokenType.String ? (string)v : null;
    }

    /// <summary>The intents of §6, in their wire shape. The board builds them only from entries of
    /// `legal_intents`; nothing here decides whether one is legal.</summary>
    public static class Intents
    {
        public static JObject Mulligan(string card) => new JObject { ["kind"] = "mulligan", ["card"] = card };

        public static JObject EndMulligan() => new JObject { ["kind"] = "end_mulligan" };

        public static JObject PlayCard(string card, string row = null, int? position = null)
        {
            var intent = new JObject { ["kind"] = "play_card", ["card"] = card };
            if (row != null) intent["row"] = row;
            if (position.HasValue) intent["position"] = position.Value;
            return intent;
        }

        public static JObject UseOrder(string instance) => new JObject { ["kind"] = "use_order", ["instance"] = instance };

        public static JObject EndTurn() => new JObject { ["kind"] = "end_turn" };

        public static JObject Pass() => new JObject { ["kind"] = "pass" };

        public static JObject Choose(int option) => new JObject { ["kind"] = "choose", ["option"] = option };

        public static JObject CancelChoice() => new JObject { ["kind"] = "cancel_choice" };
    }
}
