using System;
using UnityEngine;
using UnityEngine.UIElements;

namespace OpenGwt.UI
{
    /// <summary>The large card beside the board: shown while the mouse rests on a card, or while a
    /// finger holds one — or, for a row effect, its name and what it does. It never takes the
    /// pointer, so it cannot steal the hover it depends on.</summary>
    public sealed class CardPreview
    {
        private readonly VisualElement container;
        private readonly VisualElement cardSlot;
        private readonly Label name;
        private readonly VisualElement tags;
        private readonly VisualElement notes;
        private readonly VisualElement statuses;
        private readonly Label text;
        private bool heldByTouch;

        /// <summary>The element the preview is showing, or null when hidden.</summary>
        public VisualElement Owner { get; private set; }

        /// <summary>The key (instance id, else card id) of what is showing, so a re-render can keep it.</summary>
        public string OwnerKey { get; private set; }

        public CardPreview(VisualElement container, VisualElement root)
        {
            this.container = container;
            cardSlot = CardElement.Part("preview__card");
            container.Add(cardSlot);
            var details = CardElement.Part("preview__details");
            name = new Label { pickingMode = PickingMode.Ignore };
            name.AddToClassList("preview__name");
            details.Add(name);
            tags = CardElement.Part("preview__line");
            details.Add(tags);
            notes = CardElement.Part("preview__notes");
            details.Add(notes);
            statuses = CardElement.Part("preview__statuses");
            details.Add(statuses);
            text = new Label { pickingMode = PickingMode.Ignore };
            text.AddToClassList("preview__text");
            details.Add(text);
            container.Add(details);
            container.pickingMode = PickingMode.Ignore;

            // A finger lifted anywhere ends a long press, even over an element a re-render replaced.
            root.RegisterCallback<PointerUpEvent>(_ => ReleaseTouch(), TrickleDown.TrickleDown);
            root.RegisterCallback<PointerCancelEvent>(_ => ReleaseTouch(), TrickleDown.TrickleDown);
        }

        public void Show(VisualElement owner, string key, CardFace face, bool byTouch = false)
        {
            Begin(owner, key, byTouch);
            cardSlot.Add(new CardElement(null, face, new[] { "card--large" }) { pickingMode = PickingMode.Ignore });
            name.text = face.Name;
            AddTag(face.KindLabel, CardElement.KindIcon(face.Kind));
            for (var i = 0; i < face.Rows.Count; i++) AddTag(i < face.RowLabels.Count ? face.RowLabels[i] : face.Rows[i], "icon--" + face.Rows[i]);
            foreach (var note in face.Notes) AddNote(note);
            for (var i = 0; i < face.Statuses.Count; i++)
            {
                var label = i < face.StatusLabels.Count ? face.StatusLabels[i] : "";
                var timer = i < face.StatusTimers.Count ? face.StatusTimers[i] : "";
                var about = i < face.StatusTexts.Count ? face.StatusTexts[i] : "";
                AddStatus(CardElement.StatusIcon(face.Statuses[i].Status), label, timer, about);
            }
            text.text = face.Text;
            Place(owner);
        }

        /// <summary>A note instead of a card: a row effect's name and what it does.</summary>
        public void ShowNote(VisualElement owner, string key, string title, string about, bool byTouch = false)
        {
            Begin(owner, key, byTouch);
            name.text = title;
            text.text = about;
            Place(owner);
        }

        private void Begin(VisualElement owner, string key, bool byTouch)
        {
            Owner = owner;
            OwnerKey = key;
            heldByTouch = byTouch;
            cardSlot.Clear();
            tags.Clear();
            notes.Clear();
            statuses.Clear();
            name.text = "";
            text.text = "";
        }

        private void Place(VisualElement owner)
        {
            // Keep clear of the card being inspected: open on the side of the board it is not on.
            // An element a re-render just built has no layout yet; it stands where its
            // predecessor stood, so the side stays.
            var screen = container.parent?.worldBound ?? Rect.zero;
            var at = owner?.worldBound ?? Rect.zero;
            if (!float.IsNaN(at.x) && at.width > 0f) container.EnableInClassList("preview--left", at.center.x > screen.center.x);
            container.AddToClassList("preview--visible");
        }

        public void Hide(VisualElement owner = null)
        {
            if (owner != null && owner != Owner) return;
            Owner = null;
            OwnerKey = null;
            heldByTouch = false;
            container.RemoveFromClassList("preview--visible");
        }

        private void ReleaseTouch()
        {
            if (heldByTouch) Hide();
        }

        /// <summary>An icon, a label, or both, kept together on one line; nothing when there is neither.</summary>
        private void AddTag(string label, string icon)
        {
            var hasLabel = !string.IsNullOrEmpty(label);
            if (icon == null && !hasLabel) return;
            var tag = CardElement.Part("preview__tag");
            if (icon != null) tag.Add(CardElement.Part("preview__icon", icon));
            if (hasLabel)
            {
                var chip = new Label(label) { pickingMode = PickingMode.Ignore };
                chip.AddToClassList("preview__chip");
                tag.Add(chip);
            }
            tags.Add(tag);
        }

        private void AddNote(string note)
        {
            if (string.IsNullOrEmpty(note)) return;
            var label = new Label(note) { pickingMode = PickingMode.Ignore };
            label.AddToClassList("preview__note");
            notes.Add(label);
        }

        /// <summary>A status line: its icon, its name with the timer, and what it does underneath.</summary>
        private void AddStatus(string icon, string label, string timer, string about)
        {
            var line = CardElement.Part("preview__status");
            line.Add(CardElement.Part("preview__icon", icon));
            var column = CardElement.Part("preview__status-body");
            var title = new Label(string.IsNullOrEmpty(timer) ? label : label + " · " + timer) { pickingMode = PickingMode.Ignore };
            title.AddToClassList("preview__status-name");
            column.Add(title);
            if (!string.IsNullOrEmpty(about))
            {
                var body = new Label(about) { pickingMode = PickingMode.Ignore };
                body.AddToClassList("preview__status-text");
                column.Add(body);
            }
            line.Add(column);
            statuses.Add(line);
        }
    }

    /// <summary>Opens the preview for one element: on mouse hover, or after a finger holds it for
    /// <see cref="HoldMs"/>. A long press swallows the click that follows it, so inspecting a card
    /// in the hand never plays it.</summary>
    public sealed class CardPreviewManipulator : PointerManipulator
    {
        public const long HoldMs = 380;
        private const float MoveTolerance = 10f;

        private readonly CardPreview preview;
        private readonly string key;
        private readonly Func<CardFace> face;
        private readonly Action<bool> show;
        private IVisualElementScheduledItem hold;
        private Vector2 pressedAt;
        private bool swallowClick;

        public CardPreviewManipulator(CardPreview preview, string key, Func<CardFace> face)
        {
            this.preview = preview;
            this.key = key;
            this.face = face;
        }

        /// <summary>A manipulator that shows something other than a card face; the callback
        /// receives whether a finger, rather than the mouse, opened it.</summary>
        public CardPreviewManipulator(CardPreview preview, string key, Action<bool> show)
        {
            this.preview = preview;
            this.key = key;
            this.show = show;
        }

        protected override void RegisterCallbacksOnTarget()
        {
            target.RegisterCallback<PointerEnterEvent>(OnEnter);
            target.RegisterCallback<PointerLeaveEvent>(OnLeave);
            target.RegisterCallback<PointerDownEvent>(OnDown);
            target.RegisterCallback<PointerMoveEvent>(OnMove);
            target.RegisterCallback<PointerUpEvent>(OnUp);
            target.RegisterCallback<ClickEvent>(OnClick, TrickleDown.TrickleDown);
            target.RegisterCallback<DetachFromPanelEvent>(OnDetach);
        }

        protected override void UnregisterCallbacksFromTarget()
        {
            target.UnregisterCallback<PointerEnterEvent>(OnEnter);
            target.UnregisterCallback<PointerLeaveEvent>(OnLeave);
            target.UnregisterCallback<PointerDownEvent>(OnDown);
            target.UnregisterCallback<PointerMoveEvent>(OnMove);
            target.UnregisterCallback<PointerUpEvent>(OnUp);
            target.UnregisterCallback<ClickEvent>(OnClick, TrickleDown.TrickleDown);
            target.UnregisterCallback<DetachFromPanelEvent>(OnDetach);
        }

        /// <summary>Open the preview for the target; false when there is nothing to show.</summary>
        private bool Open(bool byTouch)
        {
            if (show != null)
            {
                show(byTouch);
                return true;
            }
            var shown = face();
            if (shown == null) return false;
            preview.Show(target, key, shown, byTouch);
            return true;
        }

        private void OnEnter(PointerEnterEvent evt)
        {
            if (evt.pointerType != UnityEngine.UIElements.PointerType.mouse) return;
            Open(false);
        }

        private void OnLeave(PointerLeaveEvent evt)
        {
            CancelHold();
            if (evt.pointerType == UnityEngine.UIElements.PointerType.mouse) preview.Hide(target);
        }

        private void OnDown(PointerDownEvent evt)
        {
            if (evt.pointerType == UnityEngine.UIElements.PointerType.mouse) return;
            swallowClick = false;
            pressedAt = evt.position;
            CancelHold();
            hold = target.schedule.Execute(() =>
            {
                hold = null;
                if (Open(true)) swallowClick = true;
            }).StartingIn(HoldMs);
        }

        private void OnMove(PointerMoveEvent evt)
        {
            // Dragging the hand to scroll it is not a long press.
            if (hold != null && ((Vector2)evt.position - pressedAt).sqrMagnitude > MoveTolerance * MoveTolerance) CancelHold();
        }

        private void OnUp(PointerUpEvent evt) => CancelHold();

        private void OnClick(ClickEvent evt)
        {
            if (!swallowClick) return;
            swallowClick = false;
            evt.StopImmediatePropagation();
        }

        private void OnDetach(DetachFromPanelEvent evt)
        {
            CancelHold();
            preview.Hide(target);
        }

        private void CancelHold()
        {
            hold?.Pause();
            hold = null;
        }
    }
}
