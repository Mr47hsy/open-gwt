using System;
using UnityEngine;
using UnityEngine.UIElements;

namespace OpenGwt.UI
{
    /// <summary>The large card beside the board: shown while the mouse rests on a card, or while a
    /// finger holds one. It never takes the pointer, so it cannot steal the hover it depends on.</summary>
    public sealed class CardPreview
    {
        private readonly VisualElement container;
        private readonly VisualElement cardSlot;
        private readonly Label name;
        private readonly VisualElement tags;
        private readonly Label powerNote;
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
            powerNote = new Label { pickingMode = PickingMode.Ignore };
            powerNote.AddToClassList("preview__chip");
            details.Add(powerNote);
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
            Owner = owner;
            OwnerKey = key;
            heldByTouch = byTouch;
            cardSlot.Clear();
            cardSlot.Add(new CardElement(null, face, new[] { "card--large" }) { pickingMode = PickingMode.Ignore });
            name.text = face.Name;
            tags.Clear();
            AddTag(face.KindLabel, face.Kind == "special" ? "icon--special" : null);
            for (var i = 0; i < face.Rows.Count; i++) AddTag(i < face.RowLabels.Count ? face.RowLabels[i] : face.Rows[i], "icon--" + face.Rows[i]);
            for (var i = 0; i < face.Statuses.Count; i++)
            {
                AddTag(i < face.StatusLabels.Count ? face.StatusLabels[i] : "", CardElement.StatusIcon(face.Statuses[i]));
            }
            powerNote.text = face.PowerNote;
            powerNote.EnableInClassList("hidden", string.IsNullOrEmpty(face.PowerNote));
            text.text = face.Text;

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
        private IVisualElementScheduledItem hold;
        private Vector2 pressedAt;
        private bool swallowClick;

        public CardPreviewManipulator(CardPreview preview, string key, Func<CardFace> face)
        {
            this.preview = preview;
            this.key = key;
            this.face = face;
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

        private void OnEnter(PointerEnterEvent evt)
        {
            if (evt.pointerType != UnityEngine.UIElements.PointerType.mouse) return;
            var shown = face();
            if (shown != null) preview.Show(target, key, shown);
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
                var shown = face();
                if (shown == null) return;
                swallowClick = true;
                preview.Show(target, key, shown, true);
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
