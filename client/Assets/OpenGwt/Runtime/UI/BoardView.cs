// The UI Toolkit controller: renders the latest view, offers exactly the server's legal intents,
// and sends what the player picks. No rule lives here (ADR 0001, 0005).
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using OpenGwt.Match;
using OpenGwt.Net;
using UnityEngine;
using UnityEngine.UIElements;

namespace OpenGwt.UI
{
    public sealed class BoardView : IDisposable
    {
        private static readonly string[] RowNames = { "melee", "ranged", "siege" };

        private readonly VisualElement root;
        private readonly MatchClient client;
        private readonly VisualElement match;
        private readonly VisualElement connectPanel;
        private readonly VisualElement modal;
        private readonly Label modalTitle;
        private readonly VisualElement modalOptions;
        private readonly Button modalConfirm;
        private readonly Button modalCancel;
        private readonly ScrollView hand;
        private readonly Button passButton;
        private readonly Button leaderButton;
        private readonly Label statusLabel;
        private readonly Label messageLabel;
        private readonly Label eventLog;
        private readonly Label connectStatus;
        private readonly List<string> log = new List<string>();
        private readonly HashSet<string> mulliganSelection = new HashSet<string>();
        private bool modalForPhase;

        public BoardView(VisualElement root, MatchClient client, string defaultServerUrl)
        {
            this.root = root;
            this.client = client;
            match = root.Q<VisualElement>("match");
            connectPanel = root.Q<VisualElement>("connect-panel");
            modal = root.Q<VisualElement>("modal");
            modalTitle = root.Q<Label>("modal-title");
            modalOptions = root.Q<VisualElement>("modal-options");
            modalConfirm = root.Q<Button>("modal-confirm");
            modalCancel = root.Q<Button>("modal-cancel");
            hand = root.Q<ScrollView>("hand");
            passButton = root.Q<Button>("btn-pass");
            leaderButton = root.Q<Button>("btn-leader");
            statusLabel = root.Q<Label>("status-label");
            messageLabel = root.Q<Label>("message-label");
            eventLog = root.Q<Label>("event-log");
            connectStatus = root.Q<Label>("connect-status");
            root.Q<TextField>("server-url").value = defaultServerUrl;

            root.Q<Button>("btn-bot").clicked += () => Run(StartBotAsync);
            root.Q<Button>("btn-create-room").clicked += () => Run(CreateRoomAsync);
            root.Q<Button>("btn-join-room").clicked += () => Run(JoinRoomAsync);
            passButton.clicked += () => Run(() => client.SendIntentAsync(Intent("pass")));
            leaderButton.clicked += () => Run(() => client.SendIntentAsync(Intent("use_leader")));
            modalCancel.clicked += HideModal;

            client.ViewChanged += Render;
            client.EventReceived += OnEvent;
            client.ErrorReceived += OnError;
            client.MatchOver += OnMatchOver;
            client.SocketClosed += OnSocketClosed;
        }

        // --- connection ---------------------------------------------------------------------

        private async Task PrepareAsync()
        {
            if (client.Prepared) return;
            var server = root.Q<TextField>("server-url").value;
            var name = root.Q<TextField>("display-name").value;
            connectStatus.text = "Connecting to " + server + " …";
            await client.PrepareAsync(server, name, PreferredLocale());
            connectStatus.text = "Signed in; locale " + client.Locale;
        }

        private static string PreferredLocale()
        {
            var saved = PlayerPrefs.GetString("locale", "");
            if (!string.IsNullOrEmpty(saved)) return saved;
            switch (Application.systemLanguage)
            {
                case SystemLanguage.ChineseSimplified:
                case SystemLanguage.Chinese:
                    return "zh-CN";
                case SystemLanguage.Russian:
                    return "ru";
                default:
                    return "en";
            }
        }

        private async Task StartBotAsync()
        {
            await PrepareAsync();
            await client.PlayBotAsync("starter-a");
            EnterMatch();
        }

        private async Task CreateRoomAsync()
        {
            await PrepareAsync();
            var code = await client.CreateRoomAsync("starter-a");
            EnterMatch();
            statusLabel.text = "Room code: " + code + " — waiting for the other player";
        }

        private async Task JoinRoomAsync()
        {
            await PrepareAsync();
            var code = root.Q<TextField>("room-code-input").value;
            await client.JoinRoomAsync(code, "starter-b");
            EnterMatch();
        }

        private void EnterMatch()
        {
            connectPanel.AddToClassList("hidden");
            match.RemoveFromClassList("hidden");
            log.Clear();
            eventLog.text = "";
            messageLabel.text = "";
        }

        private void Run(Func<Task> action)
        {
            _ = RunAsync(action);
        }

        private async Task RunAsync(Func<Task> action)
        {
            try
            {
                await action();
            }
            catch (ApiException e)
            {
                ShowMessage(e.Message);
                connectStatus.text = e.Message;
            }
            catch (Exception e)
            {
                Debug.LogException(e);
                ShowMessage(e.Message);
                connectStatus.text = e.Message;
            }
        }

        // --- rendering ----------------------------------------------------------------------

        private static JObject Intent(string kind) => new JObject { ["kind"] = kind };

        public void Render(MatchView view)
        {
            if (view == null) return;
            var me = view.Me;
            var opp = view.Opponent;
            var seat = client.Seat;

            root.Q<Label>("my-score").text = me.Score.ToString();
            root.Q<Label>("opp-score").text = opp.Score.ToString();
            root.Q<Label>("my-lives").text = Lives(me.Lives);
            root.Q<Label>("opp-lives").text = Lives(opp.Lives);
            root.Q<Label>("deck-count").text = "deck " + me.DeckCount;
            root.Q<Label>("opp-hand").text = "hand " + (opp.HandCount ?? 0) + " · deck " + opp.DeckCount;
            root.Q<Label>("opp-passed").text = opp.Passed ? "PASSED" : "";
            root.Q<Label>("round-label").text = "round " + view.Round;
            root.Q<Label>("turn-label").text = TurnText(view);
            statusLabel.text = StatusText(view);

            foreach (var row in RowNames)
            {
                RenderRow(root.Q<VisualElement>("my-row-" + row), me.Rows[row], seat, view, row, true);
                RenderRow(root.Q<VisualElement>("opp-row-" + row), opp.Rows[row], seat, view, row, false);
            }

            RenderHand(view);
            passButton.SetEnabled(HasIntent(view, "pass"));
            leaderButton.SetEnabled(HasIntent(view, "use_leader"));
            leaderButton.text = me.Leader == null ? "No leader" : (me.Leader.Used ? "Leader used" : "Leader: " + client.CardName(me.Leader.Card));

            if (view.Phase == "mulligan" && view.Mulligan != null && view.Mulligan.Seat == seat) ShowMulligan(view);
            else if (view.Phase == "choosing" && view.PendingChoice != null) ShowChoice(view);
            else if (modalForPhase) HideModal();
        }

        private static string Lives(int lives) => new string('♥', Math.Max(0, lives));

        private string TurnText(MatchView view)
        {
            switch (view.Phase)
            {
                case "mulligan": return view.Mulligan != null && view.Mulligan.Seat == client.Seat ? "your mulligan" : "opponent's mulligan";
                case "choosing": return view.PendingChoice != null ? "your choice" : "opponent chooses";
                case "match_over": return "match over";
                default: return view.Turn == "me" ? "YOUR TURN" : "opponent's turn";
            }
        }

        private string StatusText(MatchView view)
        {
            if (view.Phase == "match_over")
            {
                switch (view.Winner)
                {
                    case "me": return "You won the match";
                    case "opponent": return "You lost the match";
                    default: return "The match is a draw";
                }
            }
            var mine = view.Me.RoundsWon;
            var theirs = view.Opponent.RoundsWon;
            return "rounds " + mine + " : " + theirs;
        }

        private void RenderRow(VisualElement rowElement, RowView row, int seat, MatchView view, string rowName, bool mine)
        {
            var units = rowElement.Q<VisualElement>(className: "row__units");
            units.Clear();
            var total = 0;
            foreach (var unit in row.Units)
            {
                total += unit.Power;
                var classes = new List<string>();
                if (unit.Owner != seat && mine || unit.Owner == seat && !mine) classes.Add("card--foreign");
                var def = Def(unit.Card);
                if (IsImmune(def)) classes.Add("card--immune");
                if ((string)def?["kind"] == "special") classes.Add("card--special");
                units.Add(new CardElement(unit.Instance, unit.Card, client.CardName(unit.Card), Meta(def), unit.Power, unit.Base, classes));
            }
            rowElement.Q<Label>(className: "row__total").text = total.ToString();
            rowElement.Q<Label>(className: "row__effects").text = string.Join("\n", row.Effects.Select(EffectTag));
            rowElement.EnableInClassList("row--active", mine && view.Turn == "me" && LegalRows(view).Contains(rowName));
        }

        private static string EffectTag(string effect) => effect == "power_to_one" ? "power → 1" : effect == "double_power" ? "×2" : effect;

        private void RenderHand(MatchView view)
        {
            hand.Clear();
            var plays = view.LegalIntents.Where(i => (string)i["kind"] == "play_card").ToList();
            foreach (var card in view.Me.Hand ?? new List<CardRef>())
            {
                var def = Def(card.Card);
                var rows = plays.Where(i => (string)i["card"] == card.Instance).Select(i => (string)i["row"]).ToList();
                var classes = new List<string>();
                if (rows.Count > 0) classes.Add("card--playable");
                if ((string)def?["kind"] == "special") classes.Add("card--special");
                if (IsImmune(def)) classes.Add("card--immune");
                var element = new CardElement(card.Instance, card.Card, client.CardName(card.Card), Meta(def), (int?)def?["power"], null, classes);
                element.tooltip = client.CardText(card.Card);
                if (rows.Count > 0)
                {
                    var instance = card.Instance;
                    var options = rows;
                    element.RegisterCallback<ClickEvent>(_ => OnHandCardClicked(instance, options));
                }
                hand.Add(element);
            }
        }

        private void OnHandCardClicked(string instance, List<string> rows)
        {
            var distinct = rows.Where(r => r != null).Distinct().ToList();
            if (distinct.Count <= 1)
            {
                var intent = new JObject { ["kind"] = "play_card", ["card"] = instance };
                if (distinct.Count == 1) intent["row"] = distinct[0];
                Run(() => client.SendIntentAsync(intent));
                return;
            }
            var options = distinct.Select(row => (client.Text("ui.row." + row), (Action)(() =>
            {
                HideModal();
                Run(() => client.SendIntentAsync(new JObject { ["kind"] = "play_card", ["card"] = instance, ["row"] = row }));
            }))).ToList();
            ShowModal("Choose a row", options, null, false);
        }

        private HashSet<string> LegalRows(MatchView view) =>
            new HashSet<string>(view.LegalIntents.Where(i => (string)i["kind"] == "play_card").Select(i => (string)i["row"]).Where(r => r != null));

        private static bool HasIntent(MatchView view, string kind) => view.LegalIntents.Any(i => (string)i["kind"] == kind);

        private JObject Def(string cardId) => client.Cards.TryGetValue(cardId, out var def) ? def : null;

        private static bool IsImmune(JObject def) => def?["traits"] is JArray traits && traits.Any(t => (string)t == "immune");

        private string Meta(JObject def)
        {
            if (def == null) return "";
            var kind = (string)def["kind"];
            if (kind != "unit") return kind;
            var rows = def["rows"] as JArray;
            return rows == null ? "" : string.Join("/", rows.Select(r => client.Text("ui.row." + (string)r)));
        }

        // --- modals -------------------------------------------------------------------------

        private void ShowMulligan(MatchView view)
        {
            mulliganSelection.Clear();
            var max = view.Mulligan.Max;
            var options = new List<(string, Action)>();
            modalForPhase = true;
            modal.RemoveFromClassList("hidden");
            modalTitle.text = "Mulligan: pick up to " + max + " cards to redraw";
            modalOptions.Clear();
            foreach (var card in view.Me.Hand)
            {
                var def = Def(card.Card);
                var element = new CardElement(card.Instance, card.Card, client.CardName(card.Card), Meta(def), (int?)def?["power"], null, new[] { "card--playable" });
                var instance = card.Instance;
                element.RegisterCallback<ClickEvent>(_ =>
                {
                    if (mulliganSelection.Contains(instance)) mulliganSelection.Remove(instance);
                    else if (mulliganSelection.Count < max) mulliganSelection.Add(instance);
                    element.EnableInClassList("card--selected", mulliganSelection.Contains(instance));
                });
                modalOptions.Add(element);
            }
            modalConfirm.style.display = DisplayStyle.Flex;
            modalConfirm.text = "Confirm";
            modalCancel.style.display = DisplayStyle.None;
            modalConfirm.clickable = new Clickable(() =>
            {
                var intent = new JObject { ["kind"] = "mulligan", ["cards"] = new JArray(mulliganSelection.ToArray()) };
                HideModal();
                Run(() => client.SendIntentAsync(intent));
            });
        }

        private void ShowChoice(MatchView view)
        {
            var choice = view.PendingChoice;
            var options = new List<(string, Action)>();
            for (var i = 0; i < choice.Options.Count; i++)
            {
                var index = i;
                var option = choice.Options[i];
                options.Add((client.CardName(option.Card), () =>
                {
                    HideModal();
                    Run(() => client.SendIntentAsync(new JObject { ["kind"] = "choose", ["option"] = index }));
                }));
            }
            ShowModal(client.Text(choice.PromptKey), options, null, true);
            modalCancel.style.display = DisplayStyle.None;
        }

        private void ShowModal(string title, List<(string label, Action onClick)> options, Action onConfirm, bool forPhase)
        {
            modalForPhase = forPhase;
            modal.RemoveFromClassList("hidden");
            modalTitle.text = title;
            modalOptions.Clear();
            foreach (var (label, onClick) in options)
            {
                var button = new Button(onClick) { text = label };
                button.AddToClassList("button");
                modalOptions.Add(button);
            }
            modalConfirm.style.display = onConfirm == null ? DisplayStyle.None : DisplayStyle.Flex;
            modalCancel.style.display = DisplayStyle.Flex;
            if (onConfirm != null) modalConfirm.clickable = new Clickable(onConfirm);
        }

        private void HideModal()
        {
            modal.AddToClassList("hidden");
            modalForPhase = false;
        }

        // --- events, errors, end ------------------------------------------------------------

        private void OnEvent(JObject evt)
        {
            var type = (string)evt["type"];
            var card = (string)evt["card"];
            var line = type;
            if (card != null) line += " " + client.CardName(card);
            if (evt["seat"] != null) line = ((int)evt["seat"] == client.Seat ? "you: " : "opp: ") + line;
            if (type == "power_changed") line += " " + evt["from"] + "→" + evt["to"];
            if (type == "round_ended") line += " " + string.Join(":", ((JArray)evt["scores"]).Select(s => s.ToString())) + " winner " + evt["winner"];
            log.Add(line);
            while (log.Count > 4) log.RemoveAt(0);
            eventLog.text = string.Join("\n", log);
        }

        private void OnError(ErrorMessage error) => ShowMessage(client.ErrorText(error));

        private void ShowMessage(string text)
        {
            messageLabel.text = text;
        }

        private void OnMatchOver(MatchResult result)
        {
            var title = result.Winner == null ? "Draw" : result.Winner == client.Seat ? "You won" : "You lost";
            ShowModal(title, new List<(string, Action)>
            {
                ("Back to menu", () =>
                {
                    HideModal();
                    match.AddToClassList("hidden");
                    connectPanel.RemoveFromClassList("hidden");
                }),
            }, null, false);
            modalCancel.style.display = DisplayStyle.None;
        }

        private void OnSocketClosed(string reason)
        {
            if (client.Result != null) return;
            ShowMessage("Connection lost (" + reason + "), reconnecting …");
            Run(async () =>
            {
                await Task.Delay(1000);
                await client.ReconnectAsync();
                ShowMessage("");
            });
        }

        public void Dispose()
        {
            client.ViewChanged -= Render;
            client.EventReceived -= OnEvent;
            client.ErrorReceived -= OnError;
            client.MatchOver -= OnMatchOver;
            client.SocketClosed -= OnSocketClosed;
        }
    }
}
