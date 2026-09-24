// Orchestrates one player's session: sign in, content, then a match over the socket. Holds the
// latest view and forwards events; decides nothing (ADR 0001). Speaks match protocol 2.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using OpenGwt.I18n;
using OpenGwt.Net;
using UnityEngine;

namespace OpenGwt.Match
{
    /// <summary>A deck of the content pack as the lobby offers it (`match.md` §2, `cards.md` §14).</summary>
    public sealed class DeckOption
    {
        public string Id;
        public string Faction;
        public string Leader;
        public string Stratagem;
        public int ProvisionsUsed;
        public int ProvisionsBudget;
        /// <summary>Deck-building rules the deck breaks, each `{key, card?, params}` (§10); empty for a legal deck.</summary>
        public List<JObject> Problems = new List<JObject>();
    }

    public sealed class MatchClient : IDisposable
    {
        /// <summary>The match protocol this client speaks (`match.md` §1).</summary>
        public const int Protocol = 2;

        private const string LocalePref = "opengwt.locale";

        public ServerApi Api { get; private set; }
        public MatchSocket Socket { get; private set; }
        public MessageRenderer I18n { get; } = new MessageRenderer();
        public string Locale { get; private set; } = MessageRenderer.BaseLocale;
        public string PackHash { get; private set; }
        public string PlayerName { get; private set; }
        public Dictionary<string, JObject> Cards { get; } = new Dictionary<string, JObject>(StringComparer.Ordinal);
        public List<DeckOption> Decks { get; } = new List<DeckOption>();
        /// <summary>The `Rules` the server plays with, from the pack (`cards.md` §4, §14): read for display only.</summary>
        public JObject Rules { get; private set; } = new JObject();
        public HelloMessage Hello { get; private set; }
        public MatchView View { get; private set; }
        public MatchResult Result { get; private set; }
        public string MatchId { get; private set; }
        public string RoomCode { get; private set; }
        public int Seat => Hello?.Seat ?? -1;
        public bool Prepared => Api != null && Api.Token != null;
        public int RoundsToWin => (int?)Rules["rounds_to_win"] ?? 2;
        /// <summary>The close code of the last socket that closed, or null (`match.md` §3).</summary>
        public int? LastCloseCode { get; private set; }
        /// <summary>A reconnect makes sense: a match is open, its server speaks our protocol and the
        /// player has not left it.</summary>
        public bool CanReconnect => wsUrl != null && !mismatched && !leaving && Result == null;

        public event Action<MatchView> ViewChanged;
        public event Action<JObject> EventReceived;
        public event Action<ErrorMessage> ErrorReceived;
        public event Action<MatchResult> MatchOver;
        public event Action<string> SocketClosed;
        /// <summary>The server speaks another protocol version: the player has to update (§1).</summary>
        public event Action<int> ProtocolMismatch;
        /// <summary>Every message as it arrived, before parsing: for tests that check the wire.</summary>
        public event Action<string> MessageReceived;
        /// <summary>Every intent the board sends, as sent: for tests that drive the board without a server.</summary>
        public event Action<JObject> IntentSent;
        /// <summary>The cards, decks, rules or tables were reloaded because the server's pack changed (§1).</summary>
        public event Action ContentChanged;

        private string wsUrl;
        private bool closeHandled;
        private bool mismatched;
        private bool leaving;

        public MatchClient()
        {
            // The strings the first screen needs, before any server is known (ADR 0006).
            foreach (var asset in Resources.LoadAll<TextAsset>("i18n"))
            {
                var table = JsonConvert.DeserializeObject<Dictionary<string, string>>(asset.text);
                if (table != null) I18n.MergeTable(asset.name, table);
            }
            Locale = DefaultLocale();
        }

        private string DefaultLocale()
        {
            var saved = PlayerPrefs.GetString(LocalePref, "");
            if (!string.IsNullOrEmpty(saved) && I18n.Has(saved)) return saved;
            string system;
            switch (Application.systemLanguage)
            {
                case SystemLanguage.ChineseSimplified:
                case SystemLanguage.Chinese:
                    system = "zh-CN";
                    break;
                case SystemLanguage.Russian:
                    system = "ru";
                    break;
                default:
                    system = "en";
                    break;
            }
            return I18n.Has(system) ? system : MessageRenderer.BaseLocale;
        }

        /// <summary>Switch the interface language; remembered across runs.</summary>
        public void SetLocale(string locale)
        {
            if (!I18n.Has(locale)) return;
            Locale = locale;
            PlayerPrefs.SetString(LocalePref, locale);
            PlayerPrefs.Save();
            if (Api != null) Api.AcceptLanguage = locale;
        }

        /// <summary>Guest sign-in, locale on the profile, translation tables and the content pack.</summary>
        public async Task PrepareAsync(string serverUrl, string displayName)
        {
            Api = new ServerApi(serverUrl) { AcceptLanguage = Locale };
            PlayerName = displayName;
            var token = await Api.GuestAsync(displayName);
            Api.Token = token.Token;
            var locales = await Api.LocalesAsync();
            if (!locales.Locales.Contains(Locale)) Locale = OpenGwt.I18n.Locale.Negotiate(locales.Locales, Locale, null);
            await Api.UpdateLocaleAsync(Locale);
            I18n.MergeTable(Locale, await Api.TableAsync(Locale));
            if (Locale != MessageRenderer.BaseLocale)
            {
                I18n.MergeTable(MessageRenderer.BaseLocale, await Api.TableAsync(MessageRenderer.BaseLocale));
            }
            LoadPack(await Api.PackAsync());
        }

        /// <summary>Take the cards, decks and rules of a content pack (`opengwt.pack/2`).</summary>
        internal void LoadPack(JObject pack)
        {
            PackHash = (string)pack["hash"];
            Rules = pack["rules"] as JObject ?? new JObject();
            Cards.Clear();
            foreach (var card in pack["cards"] ?? new JArray()) Cards[(string)card["id"]] = (JObject)card;
            Decks.Clear();
            foreach (var deck in pack["decks"] ?? new JArray())
            {
                var provisions = deck["provisions"] as JObject;
                Decks.Add(new DeckOption
                {
                    Id = (string)deck["id"],
                    Faction = (string)deck["faction"],
                    Leader = (string)deck["leader"],
                    Stratagem = (string)deck["stratagem"],
                    ProvisionsUsed = (int?)provisions?["used"] ?? 0,
                    ProvisionsBudget = (int?)provisions?["budget"] ?? 0,
                    Problems = (deck["problems"] as JArray)?.OfType<JObject>().ToList() ?? new List<JObject>(),
                });
            }
        }

        public async Task PlayBotAsync(string deckId) => await OpenAsync(await Api.CreateMatchAsync("bot", deckId));

        public async Task<string> CreateRoomAsync(string deckId)
        {
            var created = await Api.CreateMatchAsync("room", deckId);
            RoomCode = created.RoomCode;
            await OpenAsync(created);
            return RoomCode;
        }

        public async Task JoinRoomAsync(string roomCode, string deckId) =>
            await OpenAsync(await Api.JoinRoomAsync(roomCode.Trim().ToUpperInvariant(), deckId));

        private async Task OpenAsync(MatchCreated created)
        {
            MatchId = created.MatchId;
            wsUrl = created.WsUrl;
            View = null;
            Result = null;
            Hello = null;
            closeHandled = false;
            mismatched = false;
            leaving = false;
            LastCloseCode = null;
            Socket?.Dispose();
            Socket = new MatchSocket();
            await Socket.ConnectAsync(wsUrl, Api.Token, Locale);
        }

        /// <summary>Reopen the socket and ask for what was missed (match.md §9): the server sends
        /// `hello` and a full view, then the events after `since_seq` and one more view.</summary>
        public async Task ReconnectAsync()
        {
            if (!CanReconnect) return;
            var since = View?.Seq ?? 0;
            Socket?.Dispose();
            Socket = new MatchSocket();
            closeHandled = false;
            await Socket.ConnectAsync(wsUrl, Api.Token, Locale);
            await Socket.SendAsync(new { type = "resync", since_seq = since });
        }

        public async Task LeaveMatchAsync()
        {
            leaving = true;
            wsUrl = null;
            if (Socket != null) await Socket.CloseAsync();
            Socket?.Dispose();
            Socket = null;
            View = null;
            Result = null;
            Hello = null;
            MatchId = null;
            RoomCode = null;
        }

        public Task SendIntentAsync(JObject intent)
        {
            IntentSent?.Invoke(intent);
            if (Socket == null) return Task.CompletedTask;
            return Socket.SendAsync(new JObject
            {
                ["type"] = "intent",
                ["intent_id"] = Guid.NewGuid().ToString("N"),
                ["intent"] = intent,
            });
        }

        /// <summary>Drain the socket on the main thread; call once per frame.</summary>
        public void Pump()
        {
            if (Socket == null) return;
            while (Socket.TryDequeue(out var json))
            {
                try
                {
                    Dispatch(json);
                }
                catch (Exception e)
                {
                    Debug.LogException(e);
                }
            }
            if (Socket.Closed && !closeHandled)
            {
                closeHandled = true;
                LastCloseCode = Socket.CloseCode;
                SocketClosed?.Invoke(Socket.CloseReason ?? (Socket.CloseCode?.ToString() ?? "closed"));
            }
        }

        /// <summary>Handle one server message as if it had come over the socket: the seam the
        /// board's PlayMode tests drive the client through without a server.</summary>
        internal void Receive(string json) => Dispatch(json);

        private void Dispatch(string json)
        {
            MessageReceived?.Invoke(json);
            // Nothing from a server that speaks another protocol, or after leaving, is handled.
            if (mismatched || leaving) return;
            var message = JObject.Parse(json);
            switch ((string)message["type"])
            {
                case "hello":
                    Hello = Json.Convert<HelloMessage>(message);
                    if (Hello.Protocol != Protocol)
                    {
                        var spoken = Hello.Protocol;
                        Hello = null;
                        mismatched = true;
                        ProtocolMismatch?.Invoke(spoken);
                        _ = Socket?.CloseAsync();
                        break;
                    }
                    if (PackHash != null && Hello.PackHash != null && Hello.PackHash != PackHash) _ = RefreshContentAsync();
                    break;
                case "view":
                    View = Json.Convert<MatchView>(message["view"]);
                    ViewChanged?.Invoke(View);
                    break;
                case "events":
                    foreach (var evt in message["events"]) EventReceived?.Invoke((JObject)evt);
                    break;
                case "error":
                    ErrorReceived?.Invoke(Json.Convert<ErrorMessage>(message));
                    break;
                case "match_over":
                    Result = Json.Convert<MatchResult>(message["result"]) ?? new MatchResult();
                    MatchOver?.Invoke(Result);
                    break;
                case "pong":
                    break;
                default:
                    Debug.LogWarning("unknown message type: " + (string)message["type"]);
                    break;
            }
        }

        /// <summary>The server's content pack changed under us (`match.md` §1): fetch the tables
        /// and the pack again, then tell the board to render from them.</summary>
        private async Task RefreshContentAsync()
        {
            try
            {
                I18n.MergeTable(Locale, await Api.TableAsync(Locale));
                if (Locale != MessageRenderer.BaseLocale)
                {
                    I18n.MergeTable(MessageRenderer.BaseLocale, await Api.TableAsync(MessageRenderer.BaseLocale));
                }
                LoadPack(await Api.PackAsync());
                ContentChanged?.Invoke();
            }
            catch (Exception e)
            {
                Debug.LogException(e);
            }
        }

        public string CardName(string cardId) => I18n.Render(Locale, "card." + cardId + ".name");

        public string CardText(string cardId) => I18n.Render(Locale, "card." + cardId + ".text");

        public string Text(string key) => I18n.Render(Locale, key);

        public string Text(string key, IReadOnlyDictionary<string, object> parameters) => I18n.Render(Locale, key, parameters);

        /// <summary>True when the tables have the key in the current locale or the base one.</summary>
        public bool Knows(string key) => I18n.Lookup(Locale, key) != null;

        public static Dictionary<string, object> P(params object[] pairs)
        {
            var result = new Dictionary<string, object>();
            for (var i = 0; i + 1 < pairs.Length; i += 2) result[(string)pairs[i]] = pairs[i + 1];
            return result;
        }

        /// <summary>The reason of an illegal intent when the tables know it, else the error's key,
        /// else the server-rendered fallback (ADR 0006, `match.md` §10).</summary>
        public string ErrorText(ErrorMessage error)
        {
            if (error.Reason != null && Knows(error.Reason)) return I18n.Render(Locale, error.Reason);
            if (error.MessageKey != null && Knows(error.MessageKey))
            {
                return I18n.Render(Locale, error.MessageKey, ToParams(error.Params));
            }
            return error.Message ?? error.Code;
        }

        public string ErrorText(ApiException error)
        {
            if (error.MessageKey != null && Knows(error.MessageKey))
            {
                return I18n.Render(Locale, error.MessageKey, ToParams(error.Params));
            }
            return error.Message;
        }

        public static Dictionary<string, object> ToParams(JObject raw)
        {
            var result = new Dictionary<string, object>();
            if (raw == null) return result;
            foreach (var pair in raw)
            {
                if (pair.Value.Type == JTokenType.Integer) result[pair.Key] = pair.Value.Value<long>();
                else result[pair.Key] = pair.Value.ToString();
            }
            return result;
        }

        public void Dispose()
        {
            Socket?.Dispose();
        }
    }
}
