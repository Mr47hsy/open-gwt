// Shapes of docs/protocol/match.md. Property names are PascalCase here and snake_case on the wire
// (see Json.Settings). Events stay JObject: the set is open-ended and the client only animates
// what it knows.
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

    public sealed class CardRef
    {
        public string Instance { get; set; }
        public string Card { get; set; }
    }

    public sealed class UnitView
    {
        public string Instance { get; set; }
        public string Card { get; set; }
        public int Owner { get; set; }
        public int Power { get; set; }
        public int Base { get; set; }
    }

    public sealed class RowView
    {
        public List<string> Effects { get; set; } = new List<string>();
        public List<UnitView> Units { get; set; } = new List<UnitView>();
    }

    public sealed class LeaderView
    {
        public string Card { get; set; }
        public bool Used { get; set; }
    }

    public sealed class SideView
    {
        public int Seat { get; set; }
        public string Faction { get; set; }
        public int Score { get; set; }
        public int Lives { get; set; }
        public int RoundsWon { get; set; }
        public bool Passed { get; set; }
        public int DeckCount { get; set; }
        public List<CardRef> Discard { get; set; } = new List<CardRef>();
        public LeaderView Leader { get; set; }
        public Dictionary<string, RowView> Rows { get; set; } = new Dictionary<string, RowView>();
        public bool MulliganDone { get; set; }
        public List<CardRef> Hand { get; set; }
        public int? HandCount { get; set; }
    }

    public sealed class MulliganView
    {
        public int? Seat { get; set; }
        public int Max { get; set; }
    }

    public sealed class PendingChoice
    {
        public string PromptKey { get; set; }
        public List<CardRef> Options { get; set; } = new List<CardRef>();
    }

    public sealed class MatchView
    {
        public int Protocol { get; set; }
        public int Seq { get; set; }
        public string Phase { get; set; }
        public int Round { get; set; }
        public string Turn { get; set; }
        public SideView Me { get; set; }
        public SideView Opponent { get; set; }
        public MulliganView Mulligan { get; set; }
        public List<JObject> LegalIntents { get; set; } = new List<JObject>();
        public PendingChoice PendingChoice { get; set; }
        public string Winner { get; set; }
    }

    public sealed class MatchResult
    {
        public int? Winner { get; set; }
        public JArray Rounds { get; set; }
        public string FinalHash { get; set; }
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
    }
}
