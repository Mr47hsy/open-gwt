// Orchestrates one player's session: sign in, content, then a match over the socket. Holds the
// latest view and forwards events; decides nothing (ADR 0001).
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using OpenGwt.I18n;
using OpenGwt.Net;
using UnityEngine;

namespace OpenGwt.Match
{
    public sealed class MatchClient : IDisposable
    {
        public ServerApi Api { get; private set; }
        public MatchSocket Socket { get; private set; }
        public MessageRenderer I18n { get; } = new MessageRenderer();
        public string Locale { get; private set; } = MessageRenderer.BaseLocale;
        public string PackHash { get; private set; }
        public Dictionary<string, JObject> Cards { get; } = new Dictionary<string, JObject>(StringComparer.Ordinal);
        public HelloMessage Hello { get; private set; }
        public MatchView View { get; private set; }
        public MatchResult Result { get; private set; }
        public string MatchId { get; private set; }
        public string RoomCode { get; private set; }
        public int Seat => Hello?.Seat ?? -1;
        public bool Prepared => Api != null && Api.Token != null;

        public event Action<MatchView> ViewChanged;
        public event Action<JObject> EventReceived;
        public event Action<ErrorMessage> ErrorReceived;
        public event Action<MatchResult> MatchOver;
        public event Action<string> SocketClosed;

        private string wsUrl;
        private bool closeHandled;

        /// <summary>Guest sign-in, locale negotiation, translation table and content pack.</summary>
        public async Task PrepareAsync(string serverUrl, string displayName, string preferredLocale)
        {
            Api = new ServerApi(serverUrl);
            var token = await Api.GuestAsync(displayName);
            Api.Token = token.Token;
            var locales = await Api.LocalesAsync();
            Locale = I18n.Locales.Count > 0 ? Locale : OpenGwt.I18n.Locale.Negotiate(locales.Locales, preferredLocale, null);
            Api.AcceptLanguage = Locale;
            await Api.UpdateLocaleAsync(Locale);
            I18n.AddTable(Locale, await Api.TableAsync(Locale));
            if (Locale != MessageRenderer.BaseLocale) I18n.AddTable(MessageRenderer.BaseLocale, await Api.TableAsync(MessageRenderer.BaseLocale));
            var pack = await Api.PackAsync();
            PackHash = (string)pack["hash"];
            Cards.Clear();
            foreach (var card in pack["cards"])
            {
                Cards[(string)card["id"]] = (JObject)card;
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
            closeHandled = false;
            Socket?.Dispose();
            Socket = new MatchSocket();
            await Socket.ConnectAsync(wsUrl, Api.Token, Locale);
        }

        /// <summary>Reopen the socket and ask for what was missed (match.md §9).</summary>
        public async Task ReconnectAsync()
        {
            var since = View?.Seq ?? 0;
            Socket?.Dispose();
            Socket = new MatchSocket();
            closeHandled = false;
            await Socket.ConnectAsync(wsUrl, Api.Token, Locale);
            await Socket.SendAsync(new { type = "resync", since_seq = since });
        }

        public Task SendIntentAsync(JObject intent) => Socket.SendAsync(new JObject
        {
            ["type"] = "intent",
            ["intent_id"] = Guid.NewGuid().ToString("N"),
            ["intent"] = intent,
        });

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
                SocketClosed?.Invoke(Socket.CloseReason ?? (Socket.CloseCode?.ToString() ?? "closed"));
            }
        }

        private void Dispatch(string json)
        {
            var message = JObject.Parse(json);
            switch ((string)message["type"])
            {
                case "hello":
                    Hello = Json.Convert<HelloMessage>(message);
                    break;
                case "view":
                    View = Json.Convert<MatchView>(message["view"]);
                    ViewChanged?.Invoke(View);
                    break;
                case "events":
                    foreach (var evt in message["events"])
                    {
                        EventReceived?.Invoke((JObject)evt);
                    }
                    break;
                case "error":
                    ErrorReceived?.Invoke(Json.Convert<ErrorMessage>(message));
                    break;
                case "match_over":
                    Result = Json.Convert<MatchResult>(message["result"]);
                    MatchOver?.Invoke(Result);
                    break;
                case "pong":
                    break;
                default:
                    Debug.LogWarning("unknown message type: " + (string)message["type"]);
                    break;
            }
        }

        public string CardName(string cardId) => I18n.Render(Locale, "card." + cardId + ".name");

        public string CardText(string cardId) => I18n.Render(Locale, "card." + cardId + ".text");

        public string Text(string key, IReadOnlyDictionary<string, object> parameters = null) =>
            I18n.Render(Locale, key, parameters);

        /// <summary>Server-rendered fallback only when the key is unknown here (ADR 0006).</summary>
        public string ErrorText(ErrorMessage error)
        {
            if (error.MessageKey != null && I18n.Lookup(Locale, error.MessageKey) != null)
            {
                return I18n.Render(Locale, error.MessageKey, ToParams(error.Params));
            }
            return error.Message ?? error.Code;
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
