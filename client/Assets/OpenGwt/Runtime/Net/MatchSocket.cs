// One WebSocket per match (docs/protocol/match.md §3). Receives on a background task and hands
// complete text frames to the main thread through a queue; sends are serialised.
using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace OpenGwt.Net
{
    public sealed class MatchSocket : IDisposable
    {
        private readonly ConcurrentQueue<string> inbox = new ConcurrentQueue<string>();
        private readonly SemaphoreSlim sendLock = new SemaphoreSlim(1, 1);
        private ClientWebSocket socket;
        private CancellationTokenSource cancel;

        public volatile bool Closed;
        public string CloseReason { get; private set; }
        public int? CloseCode { get; private set; }

        public bool IsOpen => socket != null && socket.State == WebSocketState.Open && !Closed;

        public async Task ConnectAsync(string url, string token, string acceptLanguage)
        {
            socket = new ClientWebSocket();
            socket.Options.SetRequestHeader("Authorization", "Bearer " + token);
            if (!string.IsNullOrEmpty(acceptLanguage)) socket.Options.SetRequestHeader("Accept-Language", acceptLanguage);
            cancel = new CancellationTokenSource();
            await socket.ConnectAsync(new Uri(url), cancel.Token);
            _ = Task.Run(ReceiveLoopAsync);
        }

        private async Task ReceiveLoopAsync()
        {
            var buffer = new byte[64 * 1024];
            var frame = new MemoryStream();
            try
            {
                while (socket.State == WebSocketState.Open && !cancel.IsCancellationRequested)
                {
                    var result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), cancel.Token);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        CloseCode = (int?)socket.CloseStatus;
                        CloseReason = socket.CloseStatusDescription;
                        break;
                    }
                    frame.Write(buffer, 0, result.Count);
                    if (result.EndOfMessage)
                    {
                        inbox.Enqueue(Encoding.UTF8.GetString(frame.ToArray()));
                        frame.SetLength(0);
                    }
                }
            }
            catch (OperationCanceledException)
            {
            }
            catch (Exception e)
            {
                CloseReason = e.Message;
            }
            finally
            {
                Closed = true;
            }
        }

        public bool TryDequeue(out string json) => inbox.TryDequeue(out json);

        public async Task SendAsync(object message)
        {
            if (!IsOpen) return;
            var bytes = Encoding.UTF8.GetBytes(Json.Stringify(message));
            await sendLock.WaitAsync();
            try
            {
                await socket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, cancel.Token);
            }
            finally
            {
                sendLock.Release();
            }
        }

        public async Task CloseAsync()
        {
            try
            {
                if (socket != null && socket.State == WebSocketState.Open)
                {
                    await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", CancellationToken.None);
                }
            }
            catch (Exception)
            {
                // closing a half-dead socket is best effort
            }
            cancel?.Cancel();
        }

        public void Dispose()
        {
            cancel?.Cancel();
            socket?.Dispose();
            sendLock.Dispose();
        }
    }
}
