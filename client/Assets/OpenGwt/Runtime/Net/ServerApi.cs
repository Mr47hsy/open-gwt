// The HTTP side of docs/protocol/match.md §2, over UnityWebRequest so every platform behaves the
// same. Calls must be awaited on the main thread.
using System;
using System.Collections.Generic;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Networking;

namespace OpenGwt.Net
{
    public sealed class ApiException : Exception
    {
        public long Status { get; }
        public string Code { get; }
        public string MessageKey { get; }
        public JObject Params { get; }

        public ApiException(long status, string code, string messageKey, JObject parameters, string message)
            : base(message)
        {
            Status = status;
            Code = code;
            MessageKey = messageKey;
            Params = parameters;
        }
    }

    public sealed class ServerApi
    {
        public string BaseUrl { get; }
        public string Token { get; set; }
        public string AcceptLanguage { get; set; }

        public ServerApi(string baseUrl)
        {
            BaseUrl = baseUrl.TrimEnd('/');
        }

        public async Task<TokenResponse> GuestAsync(string displayName) =>
            Json.Parse<TokenResponse>(await SendAsync("POST", "/auth/guest", Json.Stringify(new { display_name = displayName })));

        public async Task UpdateLocaleAsync(string locale) =>
            await SendAsync("PATCH", "/me", Json.Stringify(new { locale }));

        public async Task<I18nLocales> LocalesAsync() =>
            Json.Parse<I18nLocales>(await SendAsync("GET", "/content/i18n", null));

        public async Task<Dictionary<string, string>> TableAsync(string locale) =>
            Json.Parse<Dictionary<string, string>>(await SendAsync("GET", "/content/i18n/" + locale, null));

        public async Task<JObject> PackAsync() =>
            JObject.Parse(await SendAsync("GET", "/content/pack", null));

        public async Task<MatchCreated> CreateMatchAsync(string mode, string deckId) =>
            Json.Parse<MatchCreated>(await SendAsync("POST", "/matches", Json.Stringify(new { mode, deck_id = deckId })));

        public async Task<MatchCreated> JoinRoomAsync(string roomCode, string deckId) =>
            Json.Parse<MatchCreated>(await SendAsync("POST", "/matches/join", Json.Stringify(new { room_code = roomCode, deck_id = deckId })));

        public async Task<JObject> MatchStatusAsync(string matchId) =>
            JObject.Parse(await SendAsync("GET", "/matches/" + matchId, null));

        private async Task<string> SendAsync(string method, string path, string body)
        {
            using (var request = new UnityWebRequest(BaseUrl + path, method))
            {
                if (body != null)
                {
                    request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
                    request.SetRequestHeader("Content-Type", "application/json");
                }
                request.downloadHandler = new DownloadHandlerBuffer();
                if (!string.IsNullOrEmpty(Token)) request.SetRequestHeader("Authorization", "Bearer " + Token);
                if (!string.IsNullOrEmpty(AcceptLanguage)) request.SetRequestHeader("Accept-Language", AcceptLanguage);

                var operation = request.SendWebRequest();
                while (!operation.isDone) await Awaitable.NextFrameAsync();

                var text = request.downloadHandler.text;
                if (request.result == UnityWebRequest.Result.ConnectionError
                    || request.result == UnityWebRequest.Result.DataProcessingError)
                {
                    throw new ApiException(0, "connection", "error.connection", null, request.error);
                }
                if (request.responseCode >= 400)
                {
                    throw ParseError(request.responseCode, text);
                }
                return text;
            }
        }

        private static ApiException ParseError(long status, string text)
        {
            try
            {
                var error = JObject.Parse(text)["error"] as JObject;
                if (error != null)
                {
                    return new ApiException(
                        status,
                        (string)error["code"],
                        (string)error["message_key"],
                        error["params"] as JObject,
                        (string)error["message"] ?? (string)error["code"]);
                }
            }
            catch (Exception)
            {
                // not the server's error shape; fall through
            }
            return new ApiException(status, "http_" + status, "error.http", null, "HTTP " + status);
        }
    }
}
