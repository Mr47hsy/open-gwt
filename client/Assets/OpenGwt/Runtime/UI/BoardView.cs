// The UI Toolkit controller: three screens (connect, lobby, match). It plays the server's
// event and view batches one step at a time, rendering each view, moving cards between them and
// offering exactly the server's legal intents from the newest; it sends what the player picks and
// shows every string through the message renderer. No rule lives here (ADR 0001, 0005, 0006).
// Speaks match protocol 2 (docs/protocol/match.md).
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
        // Rules.rows of the pack (`cards.md` §4); Board.uxml has one element per row and side.
        private static readonly string[] RowNames = { "melee", "ranged" };
        private static readonly MatchView NoView = new MatchView();

        /// <summary>How long a step whose cards move stays on screen before the next is shown.</summary>
        private const float StepHoldSeconds = 0.55f;

        /// <summary>Steps waiting beyond this are skipped: the newest view is shown without motion.</summary>
        private const int MaxQueuedSteps = 4;

        private sealed class Step
        {
            public readonly List<JObject> Events;
            public readonly MatchView View;

            public Step(List<JObject> events, MatchView view)
            {
                Events = events;
                View = view;
            }
        }

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
        private readonly Button endTurnButton;
        private readonly Button leaderButton;
        private readonly Label statusLabel;
        private readonly Label messageLabel;
        private readonly Label eventLog;
        private readonly Label connectStatus;
        private readonly DropdownField language;
        private readonly DropdownField deck;
        private readonly List<string> log = new List<string>();
        private readonly HashSet<string> flash = new HashSet<string>();
        private readonly Queue<Step> steps = new Queue<Step>();
        private readonly CardPreview preview;
        private readonly BoardMotion motion;
        private List<JObject> batch = new List<JObject>();
        private MatchView shown;
        private float nextStepAt;
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
            endTurnButton = root.Q<Button>("btn-end-turn");
            leaderButton = root.Q<Button>("btn-leader");
            statusLabel = root.Q<Label>("status-label");
            messageLabel = root.Q<Label>("message-label");
            eventLog = root.Q<Label>("event-log");
            connectStatus = root.Q<Label>("connect-status");
            language = root.Q<DropdownField>("language");
            deck = root.Q<DropdownField>("deck");
            root.Q<TextField>("server-url").value = defaultServerUrl;
            preview = new CardPreview(root.Q<VisualElement>("card-preview"), root);
            motion = new BoardMotion(root.Q<VisualElement>("fx-layer"));
            leaderButton.AddManipulator(new CardPreviewManipulator(preview, "leader",
                () => shown?.Me?.Leader == null ? null : Face(shown.Me.Leader.Card)));

            root.Q<Button>("btn-connect").clicked += () => Run(ConnectAsync);
            root.Q<Button>("btn-bot").clicked += () => Run(StartBotAsync);
            root.Q<Button>("btn-create-room").clicked += () => Run(CreateRoomAsync);
            root.Q<Button>("btn-join-room").clicked += () => Run(JoinRoomAsync);
            root.Q<Button>("btn-back").clicked += ShowConnectStep;
            passButton.clicked += () => Send(Intents.Pass());
            endTurnButton.clicked += () => Send(Intents.EndTurn());
            leaderButton.clicked += () =>
            {
                if (shown?.Me?.Leader != null) Send(Intents.UseOrder(shown.Me.Leader.Instance));
            };
            modalCancel.clicked += HideModal;

            FillLanguages();
            language.RegisterValueChangedCallback(evt =>
            {
                if (languageByLabel.TryGetValue(evt.newValue, out var locale)) client.SetLocale(locale);
                ApplyStaticTexts();
                if (shown != null) Render(shown, steps.Count == 0, false);
            });

            client.ViewChanged += OnView;
            client.EventReceived += OnEvent;
            client.ErrorReceived += OnError;
            client.MatchOver += OnMatchOver;
            client.SocketClosed += OnSocketClosed;
            client.ProtocolMismatch += OnProtocolMismatch;
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
            endTurnButton.text = T("ui.board.end-turn");
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
            ClearMatch();
            await client.PlayBotAsync(SelectedDeck());
            EnterMatch();
        }

        private async Task CreateRoomAsync()
        {
            ClearMatch();
            var code = await client.CreateRoomAsync(SelectedDeck());
            EnterMatch();
            if (shown != null) return;
            roomWaitingCode = code;
            statusLabel.text = T("ui.board.room-waiting", "code", code);
        }

        private async Task JoinRoomAsync()
        {
            var code = root.Q<TextField>("room-code-input").value;
            ClearMatch();
            await client.JoinRoomAsync(code, SelectedDeck());
            EnterMatch();
        }

        /// <summary>Empty the board before a match opens: its first view may arrive before the
        /// request that opened it returns, and must not be thrown away.</summary>
        private void ClearMatch()
        {
            log.Clear();
            eventLog.text = "";
            messageLabel.text = "";
            statusLabel.text = "";
            roomWaitingCode = null;
            ResetSteps();
            hand.Clear();
            foreach (var row in RowNames)
            {
                root.Q<VisualElement>("my-row-" + row).Q<VisualElement>("units").Clear();
                root.Q<VisualElement>("opp-row-" + row).Q<VisualElement>("units").Clear();
            }
        }

        private void EnterMatch()
        {
            connectPanel.AddToClassList("hidden");
            match.RemoveFromClassList("hidden");
        }

        private void LeaveMatch()
        {
            HideModal();
            ResetSteps();
            Run(client.LeaveMatchAsync);
            match.AddToClassList("hidden");
            connectPanel.RemoveFromClassList("hidden");
            connectStatus.text = "";
        }

        private void Run(Func<Task> action)
        {
            _ = RunAsync(action);
        }

        private void Send(JObject intent) => Run(() => client.SendIntentAsync(intent));

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

        // --- steps ------------------------------------------------------------------------

        private void OnEvent(JObject evt) => batch.Add(evt);

        private void OnView(MatchView view)
        {
            steps.Enqueue(new Step(batch, view));
            batch = new List<JObject>();
        }

        /// <summary>Show the next queued step when the previous one has had its time; call once per
        /// frame, after <see cref="MatchClient.Pump"/>. One step per frame at most, so the board a
        /// step starts from has always been laid out.</summary>
        public void Tick()
        {
            if (steps.Count == 0 || Time.realtimeSinceStartup < nextStepAt) return;
            var animate = steps.Count <= MaxQueuedSteps;
            Step step;
            if (animate)
            {
                step = steps.Dequeue();
            }
            else
            {
                // Far behind (a resync, a stalled frame): every event line, then the newest view.
                motion.Reset();
                var events = new List<JObject>();
                MatchView last = null;
                while (steps.Count > 0)
                {
                    var next = steps.Dequeue();
                    events.AddRange(next.Events);
                    last = next.View;
                }
                step = new Step(events, last);
            }
            foreach (var evt in step.Events) Describe(evt);
            Render(step.View, steps.Count == 0, animate);
            nextStepAt = Time.realtimeSinceStartup + (motion.Busy ? StepHoldSeconds : 0f);
        }

        private void ResetSteps()
        {
            steps.Clear();
            batch = new List<JObject>();
            shown = null;
            nextStepAt = 0f;
            flash.Clear();
            motion.Reset();
            preview.Hide();
        }

        // --- rendering ----------------------------------------------------------------------

        /// <param name="live">This is the newest view: offer its legal intents and its choices.</param>
        /// <param name="animate">Move the cards from the board shown before.</param>
        private void Render(MatchView view, bool live, bool animate)
        {
            if (view == null) return;
            shown = view;
            var me = view.Me;
            var opp = view.Opponent;
            var seat = client.Seat;
            // Only the newest view offers anything: an older one is a step on the way to it.
            var offers = live ? view : NoView;
            roomWaitingCode = null;

            root.Q<Label>("my-score").text = me.Score.ToString();
            root.Q<Label>("opp-score").text = opp.Score.ToString();
            root.Q<Label>("my-lives").text = Pips(me.RoundsWon);
            root.Q<Label>("opp-lives").text = Pips(opp.RoundsWon);
            root.Q<Label>("deck-count").text = T("ui.board.deck", "count", me.DeckCount);
            root.Q<Label>("opp-hand").text = T("ui.board.opponent-hand", "hand", opp.HandCount, "deck", opp.DeckCount);
            root.Q<Label>("opp-passed").text = opp.Passed ? T("ui.board.passed") : "";
            root.Q<Label>("round-label").text = T("ui.board.round", "round", view.Round);
            root.Q<Label>("turn-label").text = TurnText(view);
            statusLabel.text = StatusText(view);

            if (animate) motion.Capture(BoardCards(), hand.Children().OfType<CardElement>());
            var keep = preview.OwnerKey;
            var board = new Dictionary<string, CardElement>();
            var inHand = new Dictionary<string, CardElement>();
            foreach (var row in RowNames)
            {
                RenderRow(root.Q<VisualElement>("my-row-" + row), me.Rows[row], seat, offers, row, true, board);
                RenderRow(root.Q<VisualElement>("opp-row-" + row), opp.Rows[row], seat, offers, row, false, board);
            }
            RenderHand(view, offers, inHand);
            flash.Clear();
            if (animate)
            {
                motion.Animate(board, inHand, root.Q<Label>("opp-hand").worldBound, root.Q<VisualElement>("middle").worldBound.center,
                    id => new CardElement(null, Face(id), Array.Empty<string>()));
            }
            else
            {
                motion.Settle();
            }
            // A re-render replaces the element under the pointer; keep showing the same card.
            if (keep != null && (board.TryGetValue(keep, out var again) || inHand.TryGetValue(keep, out again)))
            {
                preview.Show(again, keep, (CardFace)again.userData);
            }

            passButton.SetEnabled(offers.Allows("pass"));
            endTurnButton.SetEnabled(offers.Allows("end_turn"));
            leaderButton.SetEnabled(me.Leader != null && offers.CanUseOrder(me.Leader.Instance));
            leaderButton.text = me.Leader == null ? T("ui.board.leader-none") : T("ui.board.leader", "name", client.CardName(me.Leader.Card));

            if (live && view.Phase == "mulligan" && me.Mulligan != null && !me.Mulligan.Done) ShowMulligan(view);
            else if (live && view.PendingChoice != null) ShowChoice(view);
            else if (modalForPhase) HideModal();
        }

        private IEnumerable<CardElement> BoardCards()
        {
            foreach (var row in RowNames)
            {
                foreach (var side in new[] { "my-row-", "opp-row-" })
                {
                    foreach (var card in root.Q<VisualElement>(side + row).Q<VisualElement>("units").Children().OfType<CardElement>())
                    {
                        yield return card;
                    }
                }
            }
        }

        /// <summary>Round wins as pips, one per round needed to win the match (`Rules.rounds_to_win`).</summary>
        private string Pips(int won)
        {
            var needed = Math.Max(client.RoundsToWin, won);
            return new string('●', Math.Max(0, won)) + new string('○', Math.Max(0, needed - won));
        }

        private string TurnText(MatchView view)
        {
            switch (view.Phase)
            {
                case "mulligan":
                    var mine = view.Me.Mulligan != null && !view.Me.Mulligan.Done;
                    return T(mine ? "ui.turn.your-mulligan" : "ui.turn.opponent-mulligan");
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

        private void RenderRow(VisualElement rowElement, RowView row, int seat, MatchView offers, string rowName, bool mine,
            Dictionary<string, CardElement> board)
        {
            var units = rowElement.Q<VisualElement>("units");
            units.Clear();
            var total = 0;
            foreach (var card in row.Cards)
            {
                total += card.Power ?? 0;
                var classes = new List<string>();
                if ((card.Owner != seat) == mine) classes.Add("card--foreign");
                var element = Card(card.Instance, Face(card.Card, card.Power, card.Base), classes);
                if (flash.Contains(card.Instance)) Flash(element);
                units.Add(element);
                board[card.Instance] = element;
            }
            rowElement.Q<Label>("total").text = total.ToString();
            rowElement.Q<Label>("effects").text = row.Effect == null ? "" : EffectText(row.Effect);
            var active = mine && offers.LegalIntents.Any(i => (string)i["kind"] == "play_card" && (string)i["row"] == rowName);
            rowElement.EnableInClassList("row--active", active);
        }

        /// <summary>The name of a row effect and its numbers; the name once the tables have it.</summary>
        private string EffectText(RowEffectView effect)
        {
            var name = Known("row-effect." + effect.Effect.Replace('_', '-') + ".name");
            var numbers = effect.Count.HasValue ? effect.Amount + "×" + effect.Count.Value : effect.Amount.ToString();
            return name.Length == 0 ? numbers : name + " " + numbers;
        }

        private static void Flash(VisualElement element)
        {
            element.AddToClassList("card--flash");
            element.schedule.Execute(() => element.RemoveFromClassList("card--flash")).StartingIn(60);
        }

        private void RenderHand(MatchView view, MatchView offers, Dictionary<string, CardElement> inHand)
        {
            hand.Clear();
            foreach (var card in view.Me.Hand ?? new List<CardRef>())
            {
                var rows = offers.PlayRows(card.Instance);
                var classes = new List<string>();
                if (rows.Count > 0) classes.Add("card--playable");
                var element = Card(card.Instance, Face(card.Card), classes);
                if (flash.Contains(card.Instance)) Flash(element);
                if (rows.Count > 0)
                {
                    var instance = card.Instance;
                    var cardId = card.Card;
                    element.RegisterCallback<ClickEvent>(_ => OnHandCardClicked(instance, cardId, rows));
                }
                hand.Add(element);
                inHand[card.Instance] = element;
            }
        }

        private void OnHandCardClicked(string instance, string cardId, List<string> rows)
        {
            var distinct = rows.Where(r => r != null).Distinct().ToList();
            if (distinct.Count == 0)
            {
                Send(Intents.PlayCard(instance));
                return;
            }
            if (distinct.Count == 1)
            {
                Send(Intents.PlayCard(instance, distinct[0], RightEnd(cardId, distinct[0])));
                return;
            }
            var options = distinct.Select(row => (T("ui.row." + row), (Action)(() =>
            {
                HideModal();
                Send(Intents.PlayCard(instance, row, RightEnd(cardId, row)));
            }))).ToList();
            ShowModal(T("ui.modal.choose-row"), options, false);
        }

        /// <summary>The position at the right end of the row-side a card lands on: the last of the
        /// positions a compressed `play_card` entry stands for (`match.md` §6).</summary>
        private int RightEnd(string cardId, string row) => LandingSide(cardId).Rows[row].Cards.Count;

        /// <summary>The side of the board a card in hand lands on (`cards.md` §3 `side`).</summary>
        private SideView LandingSide(string cardId)
        {
            var def = Def(cardId);
            var opponents = (string)def?["kind"] == "unit" && (string)def?["side"] == "opponent";
            return opponents ? shown.Opponent : shown.Me;
        }

        private JObject Def(string cardId) => client.Cards.TryGetValue(cardId, out var def) ? def : null;

        private static List<string> Words(JObject def, string field) =>
            def?[field] is JArray list ? list.Select(w => (string)w).ToList() : new List<string>();

        /// <summary>The key's text when the tables have it, else empty — for vocabulary names that
        /// arrive with the interface texts of a later phase.</summary>
        private string Known(string key) => client.Knows(key) ? T(key) : "";

        /// <summary>Everything a card shows, rendered in the current language: kind, rows and
        /// statuses from the pack as the server serves it (`opengwt.pack/2`). <paramref name="power"/>
        /// and <paramref name="basePower"/> come from the view for a card on the board; a card
        /// elsewhere shows the printed power.</summary>
        private CardFace Face(string cardId, int? power = null, int? basePower = null)
        {
            var def = Def(cardId);
            var kind = (string)def?["kind"] ?? "";
            var rows = Words(def, "rows");
            var statuses = Words(def, "statuses");
            var face = new CardFace
            {
                Card = cardId,
                Kind = kind,
                Rows = rows,
                Statuses = statuses,
                Power = power ?? (int?)def?["power"],
                BasePower = basePower,
                Name = client.CardName(cardId),
                Text = client.CardText(cardId),
                KindLabel = kind.Length == 0 ? "" : T("ui.kind." + kind),
                RowLabels = rows.Select(r => T("ui.row." + r)).ToList(),
                StatusLabels = statuses.Select(st => Known("status." + st.Replace('_', '-') + ".name")).ToList(),
            };
            if (power.HasValue && basePower.HasValue && power.Value != basePower.Value)
            {
                face.PowerNote = T("ui.preview.base-power", "power", basePower.Value);
            }
            return face;
        }

        /// <summary>A card that opens the preview on hover or long press.</summary>
        private CardElement Card(string instance, CardFace face, IEnumerable<string> classes)
        {
            var element = new CardElement(instance, face, classes) { userData = face };
            element.AddManipulator(new CardPreviewManipulator(preview, instance ?? face.Card, () => face));
            return element;
        }

        // --- modals -------------------------------------------------------------------------

        /// <summary>Redraw one card at a time (`match.md` §6): a click returns that card and its
        /// replacement arrives with the next view; the confirm button ends the mulligan.</summary>
        private void ShowMulligan(MatchView view)
        {
            modalForPhase = true;
            modal.RemoveFromClassList("hidden");
            modalTitle.text = T("ui.modal.mulligan", "count", view.Me.Mulligan.Remaining);
            modalOptions.Clear();
            foreach (var card in view.Me.Hand)
            {
                var redrawable = view.CanRedraw(card.Instance);
                var element = Card(card.Instance, Face(card.Card), redrawable ? new[] { "card--playable" } : Array.Empty<string>());
                if (redrawable)
                {
                    var instance = card.Instance;
                    element.RegisterCallback<ClickEvent>(_ => Send(Intents.Mulligan(instance)));
                }
                modalOptions.Add(element);
            }
            modalConfirm.text = T("ui.board.end-mulligan");
            modalConfirm.SetEnabled(view.Allows("end_mulligan"));
            modalConfirm.style.display = DisplayStyle.Flex;
            modalCancel.style.display = DisplayStyle.None;
            modalConfirm.clickable = new Clickable(() =>
            {
                HideModal();
                Send(Intents.EndMulligan());
            });
        }

        private void ShowChoice(MatchView view)
        {
            var choice = view.PendingChoice;
            var options = new List<(string, Action)>();
            for (var i = 0; i < choice.Options.Count; i++)
            {
                var index = i;
                options.Add((OptionLabel(choice.Options[i]), () =>
                {
                    HideModal();
                    Send(Intents.Choose(index));
                }));
            }
            ShowModal(T(choice.PromptKey, "card", "@card." + (choice.Card?.Card ?? choice.Source?.Card) + ".name"), options, true);
            modalCancel.style.display = choice.Cancellable ? DisplayStyle.Flex : DisplayStyle.None;
            modalCancel.clickable = new Clickable(() =>
            {
                HideModal();
                Send(Intents.CancelChoice());
            });
            // An option that is a card: let the player read it before choosing.
            var buttons = modalOptions.Children().ToList();
            for (var i = 0; i < buttons.Count && i < choice.Options.Count; i++)
            {
                if (choice.Options[i].Card == null) continue;
                var face = Face(choice.Options[i].Card);
                buttons[i].AddManipulator(new CardPreviewManipulator(preview, "choice:" + i, () => face));
            }
        }

        /// <summary>What an option is, in words: the card, or the row-side, or the place on it.</summary>
        private string OptionLabel(ChoiceOption option)
        {
            if (option.Card != null) return client.CardName(option.Card);
            var side = T(option.Side == "me" ? "ui.board.me" : "ui.board.opponent");
            var row = T("ui.row." + option.Row);
            return option.Position.HasValue ? side + " · " + row + " · " + (option.Position.Value + 1) : side + " · " + row;
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
            modalCancel.clickable = new Clickable(HideModal);
        }

        private void HideModal()
        {
            modal.AddToClassList("hidden");
            modalForPhase = false;
        }

        // --- events, errors, end ------------------------------------------------------------

        private string Who(JObject evt) => (int?)evt["seat"] == client.Seat ? "@ui.who.you" : "@ui.who.opponent";

        private static string Name(string cardId) => "@card." + cardId + ".name";

        /// <summary>Apply one event of the step being shown (`match.md` §8): its log line, a flash on
        /// the card it touched, and what the motion needs to know about it. Events with nothing to
        /// show — turns starting and ending, choices made, the board cleared, the match ended — are
        /// ignored: the view carries what they change.</summary>
        private void Describe(JObject evt)
        {
            var type = (string)evt["type"];
            var card = (string)evt["card"];
            var instance = (string)evt["instance"];
            string line = null;
            switch (type)
            {
                case "card_played":
                    motion.NotePlayed(instance, card, (int?)evt["seat"] == client.Seat);
                    line = T("ui.event.card-played", "who", Who(evt), "card", Name(card));
                    break;
                case "card_summoned":
                case "stratagem_placed":
                    line = T("ui.event.unit-summoned", "who", Who(evt), "card", Name(card));
                    break;
                case "card_destroyed":
                    motion.NoteDestroyed(instance);
                    line = T("ui.event.unit-destroyed", "card", Name(card));
                    break;
                case "card_returned":
                    line = T("ui.event.unit-returned", "who", Who(evt), "card", Name(card));
                    break;
                case "order_used":
                    if (instance != null) flash.Add(instance);
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
                case "row_effect_set":
                case "row_effect_cleared":
                    line = T(type == "row_effect_set" ? "ui.event.row-effect-applied" : "ui.event.row-effect-cleared",
                        "who", Who(evt), "row", "@ui.row." + (string)evt["row"], "effect", "@row-effect." + ((string)evt["effect"]).Replace('_', '-') + ".name");
                    break;
                case "unit_damaged":
                case "unit_boosted":
                case "unit_healed":
                case "damage_blocked":
                case "base_power_changed":
                case "armor_changed":
                case "power_changed":
                case "status_added":
                case "status_reduced":
                case "status_removed":
                case "charges_changed":
                    if (instance != null) flash.Add(instance);
                    break;
            }
            if (line == null) return;
            log.Add(line);
            while (log.Count > 3) log.RemoveAt(0);
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

        private void OnProtocolMismatch(int server)
        {
            var text = T("ui.net.protocol-mismatch", "client", MatchClient.Protocol, "server", server);
            ShowMessage(text);
            connectStatus.text = text;
            LeaveMatch();
        }

        public void Dispose()
        {
            client.ViewChanged -= OnView;
            client.EventReceived -= OnEvent;
            client.ErrorReceived -= OnError;
            client.MatchOver -= OnMatchOver;
            client.SocketClosed -= OnSocketClosed;
            client.ProtocolMismatch -= OnProtocolMismatch;
        }
    }
}
