// Moves cards between two renders of the board. The view decides what changed — a card that was
// in the hand and now stands on a row moved, one that changed row or side moved too, a card that
// was on a row and is gone left — and the events only choose the style: destroyed, banished or
// simply gone, played by the opponent or summoned. Presentation only (ADR 0001): nothing here
// feeds back into what the board shows.
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace OpenGwt.UI
{
    public sealed class BoardMotion
    {
        /// <summary>Longest a ghost may live if its transition never reports an end.</summary>
        private const long GhostTimeoutMs = 2500;

        /// <summary>Longest a ghost may live at all, even if its motion never started.</summary>
        private const long GhostLifetimeMs = 3000;

        /// <summary>Longest to wait for a new element's first layout before animating anyway.</summary>
        private const long LayoutTimeoutMs = 100;

        /// <summary>Classes that describe what a card offers the player, meaningless on a ghost.</summary>
        private static readonly string[] InteractiveClasses =
        {
            "card--playable", "card--selected", "card--flash", "card--pending", "card--instant", "card--enter-from",
        };

        private enum Zone { Board, Hand }

        private readonly struct Seen
        {
            public readonly CardElement Element;
            public readonly Rect Rect;
            public readonly Zone Zone;
            /// <summary>Where exactly: the row element's name on the board, so that a card that
            /// changed row or side travels too.</summary>
            public readonly string Place;

            public Seen(CardElement element, Rect rect, Zone zone, string place)
            {
                Element = element;
                Rect = rect;
                Zone = zone;
                Place = place;
            }
        }

        private readonly VisualElement fx;
        private readonly Dictionary<string, Seen> seen = new Dictionary<string, Seen>();
        private readonly Dictionary<string, string> playedByOpponent = new Dictionary<string, string>();
        private readonly HashSet<string> played = new HashSet<string>();
        private readonly HashSet<string> destroyed = new HashSet<string>();
        private readonly HashSet<string> banished = new HashSet<string>();
        private bool primed;

        /// <summary>True when the last <see cref="Animate"/> started something worth waiting for.</summary>
        public bool Busy { get; private set; }

        public BoardMotion(VisualElement fxLayer)
        {
            fx = fxLayer;
        }

        // --- notes from the event stream ------------------------------------------------------

        public void NotePlayed(string instance, string card, bool mine)
        {
            if (instance == null) return;
            played.Add(instance);
            if (!mine && card != null) playedByOpponent[instance] = card;
        }

        public void NoteDestroyed(string instance)
        {
            if (instance != null) destroyed.Add(instance);
        }

        public void NoteBanished(string instance)
        {
            if (instance != null) banished.Add(instance);
        }

        /// <summary>Forget everything and drop every ghost: a new match, or a jump over many views.</summary>
        public void Reset()
        {
            seen.Clear();
            played.Clear();
            playedByOpponent.Clear();
            destroyed.Clear();
            banished.Clear();
            fx.Clear();
            primed = false;
            Busy = false;
        }

        // --- around one render ----------------------------------------------------------------

        /// <summary>A render without motion (a language switch, a jump over many views): the
        /// next render moves from what it shows.</summary>
        public void Settle()
        {
            seen.Clear();
            played.Clear();
            playedByOpponent.Clear();
            destroyed.Clear();
            banished.Clear();
            primed = true;
            Busy = false;
        }

        /// <summary>Record where every card is, before the board is rebuilt.</summary>
        public void Capture(IEnumerable<CardElement> board, IEnumerable<CardElement> hand)
        {
            seen.Clear();
            Record(board, Zone.Board);
            Record(hand, Zone.Hand);
        }

        private void Record(IEnumerable<CardElement> cards, Zone zone)
        {
            foreach (var card in cards)
            {
                var rect = card.worldBound;
                // Built by a render whose layout never ran: there is nowhere to start from.
                if (card.Instance == null || !Valid(rect)) continue;
                seen[card.Instance] = new Seen(card, rect, zone, PlaceOf(card, zone));
            }
        }

        /// <summary>The hand, or the name of the row element a board card stands in.</summary>
        private static string PlaceOf(VisualElement card, Zone zone) =>
            zone == Zone.Hand ? "hand" : card.parent?.parent?.name ?? "board";

        /// <summary>Start the motion from the captured cards to the rebuilt ones. The first call
        /// after <see cref="Reset"/> only primes: a board shown for the first time does not move.</summary>
        /// <param name="board">New board cards by instance.</param>
        /// <param name="hand">New hand cards by instance.</param>
        /// <param name="opponentOrigin">Where the opponent's cards come from, in panel space.</param>
        /// <param name="centre">The middle of the board, where a played special resolves, in panel space.</param>
        /// <param name="build">Builds a card for a pack id, for cards the client never saw in a hand.</param>
        public void Animate(
            IReadOnlyDictionary<string, CardElement> board,
            IReadOnlyDictionary<string, CardElement> hand,
            Rect opponentOrigin,
            Vector2 centre,
            Func<string, CardElement> build)
        {
            Busy = false;
            if (primed)
            {
                Enter(board, Zone.Board, opponentOrigin, build);
                Enter(hand, Zone.Hand, opponentOrigin, build);
                Leave(board, hand, opponentOrigin, centre, build);
            }
            primed = true;
            seen.Clear();
            played.Clear();
            playedByOpponent.Clear();
            destroyed.Clear();
            banished.Clear();
        }

        private void Enter(IReadOnlyDictionary<string, CardElement> now, Zone zone, Rect opponentOrigin, Func<string, CardElement> build)
        {
            foreach (var pair in now)
            {
                if (seen.TryGetValue(pair.Key, out var before))
                {
                    if (before.Place != PlaceOf(pair.Value, zone)) Travel(Ghost(before.Element, before.Rect), pair.Value, false);
                    continue;
                }
                var card = zone == Zone.Board && playedByOpponent.TryGetValue(pair.Key, out var id) && Valid(opponentOrigin) ? build(id) : null;
                if (card != null) Travel(Ghost(card, Centred(opponentOrigin)), pair.Value, true);
                else Pop(pair.Value);
            }
        }

        private void Leave(
            IReadOnlyDictionary<string, CardElement> board,
            IReadOnlyDictionary<string, CardElement> hand,
            Rect opponentOrigin,
            Vector2 centre,
            Func<string, CardElement> build)
        {
            foreach (var pair in seen)
            {
                if (board.ContainsKey(pair.Key) || hand.ContainsKey(pair.Key)) continue;
                var before = pair.Value;
                var ghost = Ghost(before.Element, before.Rect);
                if (before.Zone == Zone.Hand && played.Contains(pair.Key)) Cast(ghost, centre, false);
                else if (destroyed.Contains(pair.Key)) Exit(ghost, "card--destroyed");
                else if (banished.Contains(pair.Key)) Exit(ghost, "card--banished");
                else Exit(ghost, "card--leaving");
            }
            // The opponent's specials were never on screen: they start at the opponent's hand.
            foreach (var pair in playedByOpponent)
            {
                if (board.ContainsKey(pair.Key) || seen.ContainsKey(pair.Key) || !Valid(opponentOrigin)) continue;
                var card = build(pair.Value);
                if (card != null) Cast(Ghost(card, Centred(opponentOrigin)), centre, true);
            }
        }

        // --- the four motions -----------------------------------------------------------------

        /// <summary>A new card grows in where it stands.</summary>
        private void Pop(CardElement card)
        {
            Busy = true;
            card.AddToClassList("card--enter-from");
            AfterFirstFrame(card, () => card.RemoveFromClassList("card--enter-from"));
        }

        /// <summary>A ghost flies from where the card was to where its new element stands; that
        /// element stays hidden until the ghost lands on it.</summary>
        private void Travel(VisualElement ghost, CardElement target, bool far)
        {
            Busy = true;
            ghost.AddToClassList("card--travel");
            if (far) ghost.AddToClassList("card--enter-far");
            target.AddToClassList("card--instant");
            target.AddToClassList("card--pending");
            var landed = false;
            void Land()
            {
                if (landed) return;
                landed = true;
                ghost.RemoveFromHierarchy();
                target.RemoveFromClassList("card--pending");
                target.schedule.Execute(() => target.RemoveFromClassList("card--instant")).StartingIn(LayoutTimeoutMs);
            }
            AfterFirstFrame(target, () =>
            {
                var from = LocalRect(ghost);
                var to = fx.WorldToLocal(target.worldBound);
                if (!Valid(to) || !Valid(from))
                {
                    Land();
                    return;
                }
                var scale = to.width / from.width;
                var offset = to.center - from.center;
                // Nothing to travel: no transition would run, so none would report its end.
                if (offset.sqrMagnitude < 1f && Mathf.Abs(scale - 1f) < 0.01f)
                {
                    Land();
                    return;
                }
                ghost.style.translate = new Translate(offset.x, offset.y);
                ghost.style.scale = new Scale(new Vector2(scale, scale));
                ghost.RemoveFromClassList("card--enter-far");
                WhenDone(ghost, "translate", Land);
            });
        }

        /// <summary>A card leaves: burned red when destroyed, drifting up when banished, faded otherwise.</summary>
        private void Exit(VisualElement ghost, string style)
        {
            Busy = true;
            AfterFirstFrame(ghost, () =>
            {
                ghost.AddToClassList(style);
                WhenDone(ghost, "opacity", ghost.RemoveFromHierarchy);
            });
        }

        /// <summary>A played special flies to the middle of the board and fades there.</summary>
        private void Cast(VisualElement ghost, Vector2 centre, bool far)
        {
            Busy = true;
            ghost.AddToClassList("card--cast");
            if (far) ghost.AddToClassList("card--enter-far");
            AfterFirstFrame(ghost, () =>
            {
                var from = LocalRect(ghost);
                var to = fx.WorldToLocal(new Rect(centre, Vector2.zero)).position;
                ghost.style.translate = new Translate(to.x - from.center.x, to.y - from.center.y);
                ghost.RemoveFromClassList("card--enter-far");
                ghost.AddToClassList("card--cast-out");
                WhenDone(ghost, "opacity", ghost.RemoveFromHierarchy);
            });
        }

        // --- helpers --------------------------------------------------------------------------

        /// <summary>Move a card into the effects layer at a panel-space rectangle, as a ghost that
        /// looks like it but no longer takes the pointer.</summary>
        private VisualElement Ghost(CardElement card, Rect worldRect)
        {
            card.RemoveFromHierarchy();
            foreach (var c in InteractiveClasses) card.RemoveFromClassList(c);
            card.AddToClassList("card--ghost");
            card.pickingMode = PickingMode.Ignore;
            if (card.OrderButton != null)
            {
                card.OrderButton.pickingMode = PickingMode.Ignore;
                card.OrderButton.SetEnabled(false);
            }
            card.style.translate = StyleKeyword.Null;
            card.style.scale = StyleKeyword.Null;
            var local = fx.WorldToLocal(worldRect);
            card.style.left = local.x;
            card.style.top = local.y;
            card.style.width = local.width;
            card.style.height = local.height;
            fx.Add(card);
            card.schedule.Execute(card.RemoveFromHierarchy).StartingIn(GhostLifetimeMs);
            return card;
        }

        /// <summary>A hand-card-sized rectangle centred on <paramref name="origin"/>.</summary>
        private static Rect Centred(Rect origin)
        {
            var size = new Vector2(84f, 112f);
            return new Rect(origin.center - size * 0.5f, size);
        }

        private static Rect LocalRect(VisualElement ghost) => new Rect(
            ghost.style.left.value.value, ghost.style.top.value.value, ghost.style.width.value.value, ghost.style.height.value.value);

        /// <summary>Run <paramref name="action"/> once the element's current style has been computed
        /// for a frame, so that what the action changes animates from it. The first layout of a new
        /// or moved element marks that moment; a timer covers an element whose rectangle did not change.</summary>
        private static void AfterFirstFrame(VisualElement element, Action action)
        {
            var done = false;
            EventCallback<GeometryChangedEvent> onLayout = null;
            void Run()
            {
                if (done) return;
                done = true;
                element.UnregisterCallback(onLayout);
                action();
            }
            onLayout = _ => Run();
            element.RegisterCallback(onLayout);
            element.schedule.Execute(Run).StartingIn(LayoutTimeoutMs);
        }

        /// <summary>Run <paramref name="action"/> when the named property's transition ends or is
        /// cancelled, or after a timeout if neither is ever reported.</summary>
        private static void WhenDone(VisualElement element, string property, Action action)
        {
            var done = false;
            var name = new StylePropertyName(property);
            void Finish()
            {
                if (done) return;
                done = true;
                action();
            }
            element.RegisterCallback<TransitionEndEvent>(e =>
            {
                if (e.stylePropertyNames.Contains(name)) Finish();
            });
            element.RegisterCallback<TransitionCancelEvent>(e =>
            {
                if (e.stylePropertyNames.Contains(name)) Finish();
            });
            element.schedule.Execute(Finish).StartingIn(GhostTimeoutMs);
        }

        private static bool Valid(Rect rect) =>
            !float.IsNaN(rect.x) && !float.IsNaN(rect.y) && rect.width > 1f && rect.height > 1f;
    }
}
