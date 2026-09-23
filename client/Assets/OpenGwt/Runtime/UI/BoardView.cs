// The UI Toolkit controller: three screens (connect, lobby, match). It renders the latest view,
// offers exactly the server's legal intents, sends what the player picks, and shows every string
// through the message renderer. No rule lives here (ADR 0001, 0005, 0006).
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
        private readonly VisualElement connectStep;
        private readonly VisualElement lobbyStep;
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
        private readonly DropdownField language;
        private readonly DropdownField deck;
        private readonly List<string> log = new List<string>();
        private readonly HashSet<string> mulliganSelection = new HashSet<string>();
        private readonly HashSet<string> flash = new HashSet<string>();
        private readonly HashSet<string> gone = new HashSet<string>();
        private readonly Dictionary<string, string> languageByLabel = new Dictionary<string, string>();
        private readonly Dictionary<string, string> deckByLabel = new Dictionary<string, string>();
        private bool modalForPhase;
        private string roomWaitingCode;

        public BoardView(VisualElement root, MatchClient client, string defaultServerUrl)
        {
            this.root = root;
            this.client = client;
            match = root.Q<VisualElement>("match");
            connectPanel = root.Q<VisualElement>("connect-panel");
            connectStep = root.Q<VisualElement>("connect-step");
            lobbyStep = root.Q<VisualElement>("lobby-step");
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
            language = root.Q<DropdownField>("language");
            deck = root.Q<DropdownField>("deck");
            root.Q<TextField>("server-url").value = defaultServerUrl;

            root.Q<Button>("btn-connect").clicked += () => Run(ConnectAsync);
            root.Q<Button>("btn-bot").clicked += () => Run(StartBotAsync);
            root.Q<Button>("btn-create-room").clicked += () => Run(CreateRoomAsync);
            root.Q<Button>("btn-join-room").clicked += () => Run(JoinRoomAsync);
            root.Q<Button>("btn-back").clicked += ShowConnectStep;
            passButton.clicked += () => Run(() => client.SendIntentAsync(Intent("pass")));
            leaderButton.clicked += () => Run(() => client.SendIntentAsync(Intent("use_leader")));
            modalCancel.clicked += HideModal;

            FillLanguages();
            language.RegisterValueChangedCallback(evt =>
            {
                if (languageByLabel.TryGetValue(evt.newValue, out var locale)) client.SetLocale(locale);
                ApplyStaticTexts();
                if (client.View != null) Render(client.View);
            });

            client.ViewChanged += Render;
            client.EventReceived += OnEvent;
            client.ErrorReceived += OnError;
            client.MatchOver += OnMatchOver;
            client.SocketClosed += OnSocketClosed;
            ApplyStaticTexts();
        }

        // --- static texts -------------------------------------------------------------------

        private string T(string key) => client.Text(key);

        private string T(string key, params object[] pairs) => client.Text(key, MatchClient.P(pairs));

        private void FillLanguages()
        {
            languageByLabel.Clear();
            var labels = new List<string>();
            foreach (var locale in client.I18n.Locales)
            {
                var label = client.I18n.Render(locale, "ui.language.name");
                if (label == "ui.language.name") label = locale;
                languageByLabel[label] = locale;
                labels.Add(label);
            }
            language.choices = labels;
            language.SetValueWithoutNotify(languageByLabel.FirstOrDefault(p => p.Value == client.Locale).Key ?? labels.FirstOrDefault());
        }

        private void ApplyStaticTexts()
        {
            root.Q<Label>("title").text = T("ui.title");
            root.Q<Label>("disclaimer").text = T("ui.disclaimer");
            root.Q<TextField>("server-url").label = T("ui.connect.server");
            root.Q<TextField>("display-name").label = T("ui.connect.name");
            language.label = T("ui.connect.language");
            root.Q<Button>("btn-connect").text = T("ui.connect.connect");
            deck.label = T("ui.lobby.deck");
            root.Q<Button>("btn-bot").text = T("ui.lobby.bot");
            root.Q<Button>("btn-create-room").text = T("ui.lobby.create-room");
            root.Q<TextField>("room-code-input").label = T("ui.lobby.room-code");
            root.Q<Button>("btn-join-room").text = T("ui.lobby.join");
            root.Q<Button>("btn-back").text = T("ui.lobby.back");
            root.Q<Label>("my-name").text = T("ui.board.me");
            root.Q<Label>("opp-name").text = T("ui.board.opponent");
            passButton.text = T("ui.board.pass");
            modalConfirm.text = T("ui.modal.confirm");
            modalCancel.text = T("ui.modal.cancel");
            foreach (var row in RowNames)
            {
                root.Q<VisualElement>("my-row-" + row).Q<Label>("label").text = T("ui.row." + row);
                root.Q<VisualElement>("opp-row-" + row).Q<Label>("label").text = T("ui.row." + row);
            }
            FillDecks();
        }

        private void FillDecks()
        {
            deckByLabel.Clear();
            var labels = new List<string>();
            foreach (var option in client.Decks)
            {
                var label = client.Text("faction." + option.Faction + ".name") + " · " + option.Id;
                deckByLabel[label] = option.Id;
                labels.Add(label);
            }
            deck.choices = labels;
            if (labels.Count > 0 && !labels.Contains(deck.value)) deck.SetValueWithoutNotify(labels[0]);
        }

        private string SelectedDeck() => deckByLabel.TryGetValue(deck.value ?? "", out var id) ? id : client.Decks.FirstOrDefault()?.Id;

        // --- connection and lobby -----------------------------------------------------------

        private async Task ConnectAsync()
        {
            var server = root.Q<TextField>("server-url").value.Trim();
            var name = root.Q<TextField>("display-name").value.Trim();
            if (string.IsNullOrEmpty(name)) name = "Player";
            connectStatus.text = T("ui.connect.connecting", "server", server);
            await client.PrepareAsync(server, name);
            FillLanguages();
            ApplyStaticTexts();
            connectStatus.text = T("ui.connect.signed-in", "name", name);
            connectStep.AddToClassList("hidden");
            lobbyStep.RemoveFromClassList("hidden");
        }

        private void ShowConnectStep()
        {
            lobbyStep.AddToClassList("hidden");
            connectStep.RemoveFromClassList("hidden");
            connectStatus.text = "";
        }

        private async Task StartBotAsync()
        {
            await client.PlayBotAsync(SelectedDeck());
            EnterMatch();
        }

        private async Task CreateRoomAsync()
        {
            var code = await client.CreateRoomAsync(SelectedDeck());
            EnterMatch();
            roomWaitingCode = code;
            statusLabel.text = T("ui.board.room-waiting", "code", code);
        }

        private async Task JoinRoomAsync()
        {
            var code = root.Q<TextField>("room-code-input").value;
            await client.JoinRoomAsync(code, SelectedDeck());
            EnterMatch();
        }

        private void EnterMatch()
        {
            connectPanel.AddToClassList("hidden");
            match.RemoveFromClassList("hidden");
            log.Clear();
            eventLog.text = "";
            messageLabel.text = "";
            statusLabel.text = "";
            roomWaitingCode = null;
            hand.Clear();
            foreach (var row in RowNames)
            {
                root.Q<VisualElement>("my-row-" + row).Q<VisualElement>("units").Clear();
                root.Q<VisualElement>("opp-row-" + row).Q<VisualElement>("units").Clear();
            }
        }

        private void LeaveMatch()
        {
            HideModal();
            Run(client.LeaveMatchAsync);
            match.AddToClassList("hidden");
            connectPanel.RemoveFromClassList("hidden");
            connectStatus.text = "";
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
                var text = client.ErrorText(e);
                ShowMessage(text);
                connectStatus.text = text;
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
            roomWaitingCode = null;

            root.Q<Label>("my-score").text = me.Score.ToString();
            root.Q<Label>("opp-score").text = opp.Score.ToString();
            root.Q<Label>("my-lives").text = Lives(me.Lives);
            root.Q<Label>("opp-lives").text = Lives(opp.Lives);
            root.Q<Label>("deck-count").text = T("ui.board.deck", "count", me.DeckCount);
            root.Q<Label>("opp-hand").text = T("ui.board.opponent-hand", "hand", opp.HandCount ?? 0, "deck", opp.DeckCount);
            root.Q<Label>("opp-passed").text = opp.Passed ? T("ui.board.passed") : "";
            root.Q<Label>("round-label").text = T("ui.board.round", "round", view.Round);
            root.Q<Label>("turn-label").text = TurnText(view);
            statusLabel.text = StatusText(view);

            foreach (var row in RowNames)
            {
                RenderRow(root.Q<VisualElement>("my-row-" + row), me.Rows[row], seat, view, row, true);
                RenderRow(root.Q<VisualElement>("opp-row-" + row), opp.Rows[row], seat, view, row, false);
            }
            RenderHand(view);
            flash.Clear();
            gone.Clear();

            passButton.SetEnabled(HasIntent(view, "pass"));
            leaderButton.SetEnabled(HasIntent(view, "use_leader"));
            leaderButton.text = me.Leader == null
                ? T("ui.board.leader-none")
                : me.Leader.Used ? T("ui.board.leader-used") : T("ui.board.leader", "name", client.CardName(me.Leader.Card));

            if (view.Phase == "mulligan" && view.Mulligan != null && view.Mulligan.Seat == seat) ShowMulligan(view);
            else if (view.Phase == "choosing" && view.PendingChoice != null) ShowChoice(view);
            else if (modalForPhase) HideModal();
        }

        private static string Lives(int lives) => new string('♥', Math.Max(0, lives));

        private string TurnText(MatchView view)
        {
            switch (view.Phase)
            {
                case "mulligan":
                    return T(view.Mulligan != null && view.Mulligan.Seat == client.Seat ? "ui.turn.your-mulligan" : "ui.turn.opponent-mulligan");
                case "choosing":
                    return T(view.PendingChoice != null ? "ui.turn.your-choice" : "ui.turn.opponent-choice");
                case "match_over":
                    return T("ui.turn.over");
                default:
                    return T(view.Turn == "me" ? "ui.turn.yours" : "ui.turn.opponent");
            }
        }

        private string StatusText(MatchView view)
        {
            if (view.Phase == "match_over")
            {
                switch (view.Winner)
                {
                    case "me": return T("ui.result.won");
                    case "opponent": return T("ui.result.lost");
                    default: return T("ui.result.draw");
                }
            }
            return T("ui.board.rounds", "mine", view.Me.RoundsWon, "theirs", view.Opponent.RoundsWon);
        }

        private void RenderRow(VisualElement rowElement, RowView row, int seat, MatchView view, string rowName, bool mine)
        {
            var units = rowElement.Q<VisualElement>("units");
            units.Clear();
            var total = 0;
            foreach (var unit in row.Units)
            {
                total += unit.Power;
                var classes = new List<string>();
                if ((unit.Owner != seat) == mine) classes.Add("card--foreign");
                var def = Def(unit.Card);
                if (IsImmune(def)) classes.Add("card--immune");
                if ((string)def?["kind"] == "special") classes.Add("card--special");
                var element = new CardElement(unit.Instance, unit.Card, client.CardName(unit.Card), Meta(def), unit.Power, unit.Base, classes);
                element.tooltip = client.CardText(unit.Card);
                if (flash.Contains(unit.Instance)) Flash(element);
                units.Add(element);
            }
            rowElement.Q<Label>("total").text = total.ToString();
            rowElement.Q<Label>("effects").text = string.Join("\n", row.Effects.Select(e => T("ui.effect." + e.Replace('_', '-'))));
            rowElement.EnableInClassList("row--active", mine && view.Turn == "me" && LegalRows(view).Contains(rowName));
        }

        private static void Flash(VisualElement element)
        {
            element.AddToClassList("card--flash");
            element.schedule.Execute(() => element.RemoveFromClassList("card--flash")).StartingIn(60);
        }

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
                if (flash.Contains(card.Instance)) Flash(element);
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
            var options = distinct.Select(row => (T("ui.row." + row), (Action)(() =>
            {
                HideModal();
                Run(() => client.SendIntentAsync(new JObject { ["kind"] = "play_card", ["card"] = instance, ["row"] = row }));
            }))).ToList();
            ShowModal(T("ui.modal.choose-row"), options, false);
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
            return rows == null ? "" : string.Join("/", rows.Select(r => T("ui.row." + (string)r)));
        }

        // --- modals -------------------------------------------------------------------------

        private void ShowMulligan(MatchView view)
        {
            mulliganSelection.Clear();
            var max = view.Mulligan.Max;
            modalForPhase = true;
            modal.RemoveFromClassList("hidden");
            modalTitle.text = T("ui.modal.mulligan", "count", max);
            modalOptions.Clear();
            foreach (var card in view.Me.Hand)
            {
                var def = Def(card.Card);
                var element = new CardElement(card.Instance, card.Card, client.CardName(card.Card), Meta(def), (int?)def?["power"], null, new[] { "card--playable" });
                element.tooltip = client.CardText(card.Card);
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
            ShowModal(T(choice.PromptKey), options, true);
            modalCancel.style.display = DisplayStyle.None;
        }

        private void ShowModal(string title, List<(string label, Action onClick)> options, bool forPhase)
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
            modalConfirm.style.display = DisplayStyle.None;
            modalCancel.style.display = DisplayStyle.Flex;
            modalCancel.text = T("ui.modal.cancel");
        }

        private void HideModal()
        {
            modal.AddToClassList("hidden");
            modalForPhase = false;
        }

        // --- events, errors, end ------------------------------------------------------------

        private string Who(JObject evt) => (int?)evt["seat"] == client.Seat ? "@ui.who.you" : "@ui.who.opponent";

        private void OnEvent(JObject evt)
        {
            var type = (string)evt["type"];
            var card = (string)evt["card"];
            var instance = (string)evt["instance"];
            string line = null;
            switch (type)
            {
                case "card_played":
                case "unit_summoned":
                case "card_placed":
                    if (instance != null) flash.Add(instance);
                    line = T(type == "card_played" ? "ui.event.card-played" : "ui.event.unit-summoned", "who", Who(evt), "card", "@card." + card + ".name");
                    break;
                case "unit_destroyed":
                    line = T("ui.event.unit-destroyed", "card", "@card." + card + ".name");
                    break;
                case "unit_returned":
                    if (instance != null) flash.Add(instance);
                    line = T("ui.event.unit-returned", "who", Who(evt), "card", "@card." + card + ".name");
                    break;
                case "leader_used":
                    line = T("ui.event.leader-used", "who", Who(evt));
                    break;
                case "player_passed":
                    line = T("ui.event.player-passed", "who", Who(evt));
                    break;
                case "card_drawn":
                    line = T("ui.event.card-drawn", "who", Who(evt), "count", 1);
                    break;
                case "round_ended":
                    var scores = (JArray)evt["scores"];
                    var mine = client.Seat == 0 ? scores[0] : scores[1];
                    var theirs = client.Seat == 0 ? scores[1] : scores[0];
                    line = T("ui.event.round-ended", "round", (long)evt["round"], "mine", (long)mine, "theirs", (long)theirs);
                    break;
                case "row_effect_applied":
                case "row_effect_cleared":
                    line = T(type == "row_effect_applied" ? "ui.event.row-effect-applied" : "ui.event.row-effect-cleared",
                        "who", Who(evt), "row", "@ui.row." + (string)evt["row"], "effect", "@ui.effect." + ((string)evt["effect"]).Replace('_', '-'));
                    break;
                case "power_changed":
                    if (instance != null) flash.Add(instance);
                    break;
            }
            if (line == null) return;
            log.Add(line);
            while (log.Count > 4) log.RemoveAt(0);
            eventLog.text = string.Join("\n", log);
        }

        private void OnError(ErrorMessage error) => ShowMessage(client.ErrorText(error));

        private void ShowMessage(string text) => messageLabel.text = text;

        private void OnMatchOver(MatchResult result)
        {
            var title = result.Winner == null ? T("ui.result.draw") : result.Winner == client.Seat ? T("ui.result.won") : T("ui.result.lost");
            ShowModal(title, new List<(string, Action)> { (T("ui.modal.back"), LeaveMatch) }, false);
            modalCancel.style.display = DisplayStyle.None;
        }

        private void OnSocketClosed(string reason)
        {
            if (client.Result != null || client.Socket == null) return;
            ShowMessage(T("ui.net.lost", "reason", reason));
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
