using System;
using System.Collections.Generic;
using OpenGwt.Net;
using UnityEngine.UIElements;

namespace OpenGwt.UI
{
    /// <summary>What a card shows, already rendered to text: built by the board from the view, the
    /// pack and the translation tables, and read by <see cref="CardElement"/> and the preview.
    /// Kinds, rows and statuses are the card protocol's words (`cards.md` §3, §9); the numbers
    /// come from the view for a card on the board (`match.md` §7) and from the pack elsewhere.</summary>
    public sealed class CardFace
    {
        public string Card;
        public string Kind = "";
        public IReadOnlyList<string> Rows = Array.Empty<string>();
        public IReadOnlyList<StatusView> Statuses = Array.Empty<StatusView>();
        /// <summary>Current power plus aura on the board; printed power elsewhere.</summary>
        public int? Power;
        public int? BasePower;
        public int? Aura;
        public int? Armor;
        /// <summary>The activated ability, or null for a card without one.</summary>
        public OrderView Order;
        /// <summary>`use_order` for this card is among the legal intents right now.</summary>
        public bool OrderUsable;

        public string Name = "";
        public string Text = "";
        public string KindLabel = "";
        public IReadOnlyList<string> RowLabels = Array.Empty<string>();
        /// <summary>Per status, its name, or empty while the tables have none.</summary>
        public IReadOnlyList<string> StatusLabels = Array.Empty<string>();
        /// <summary>Per status, what it does, or empty while the tables have none.</summary>
        public IReadOnlyList<string> StatusTexts = Array.Empty<string>();
        /// <summary>Per status, its timer in words, or empty for one without.</summary>
        public IReadOnlyList<string> StatusTimers = Array.Empty<string>();
        /// <summary>Short lines under the name: base power, boosted or damaged by, aura, armour,
        /// the ability's charges and cooldown, provisions and colour.</summary>
        public IReadOnlyList<string> Notes = Array.Empty<string>();

        /// <summary>Current power without the aura: what boosts raise and damage lowers.</summary>
        public int? OwnPower => Power.HasValue ? Power.Value - (Aura ?? 0) : (int?)null;

        public bool Has(string status)
        {
            foreach (var s in Statuses)
            {
                if (s.Status == status) return true;
            }
            return false;
        }
    }

    /// <summary>A card on the vector frame: power and armour badges, row / kind / status icons with
    /// timers, a watermark in the art window, the name and, for a card with an activated ability,
    /// its button (ADR 0005). Layout and look are Board.uss; every child but the order button
    /// ignores the pointer, so the card itself receives hover, press and click.</summary>
    public sealed class CardElement : VisualElement
    {
        public string Instance { get; }
        public string Card { get; }

        /// <summary>The activated ability's button, or null for a card without one. The board
        /// wires its click; it is enabled only when the face says the order is usable.</summary>
        public Button OrderButton { get; }

        public CardElement(string instance, CardFace face, IEnumerable<string> classes)
        {
            Instance = instance;
            Card = face.Card;
            AddToClassList("card");
            if (face.Kind.Length > 0) AddToClassList("card--" + face.Kind);
            if (face.Has("immune")) AddToClassList("card--immune");
            if (face.Order != null) AddToClassList("card--ordered");
            foreach (var c in classes) AddToClassList(c);

            var art = Part("card__art");
            var watermark = WatermarkIcon(face);
            if (watermark != null) art.Add(Part("card__watermark", watermark));
            Add(art);

            var power = new Label(face.Power.HasValue ? face.Power.Value.ToString() : "");
            power.AddToClassList("card__power");
            if (!face.Power.HasValue) power.AddToClassList("card__power--none");
            else if (face.BasePower.HasValue && face.OwnPower.Value > face.BasePower.Value) power.AddToClassList("card__power--boosted");
            else if (face.BasePower.HasValue && face.OwnPower.Value < face.BasePower.Value) power.AddToClassList("card__power--reduced");
            Add(power);

            if (face.Armor.HasValue && face.Armor.Value > 0)
            {
                var armor = new Label(face.Armor.Value.ToString());
                armor.AddToClassList("card__armor");
                Add(armor);
            }

            var icons = Part("card__icons");
            foreach (var icon in Icons(face)) icons.Add(Part("card__icon", icon));
            foreach (var status in face.Statuses)
            {
                icons.Add(Part("card__icon", StatusIcon(status.Status)));
                if (status.Turns.HasValue)
                {
                    var timer = new Label(status.Turns.Value.ToString());
                    timer.AddToClassList("card__icon-timer");
                    icons.Add(timer);
                }
            }
            Add(icons);

            var name = new Label(face.Name);
            name.AddToClassList("card__name");
            Add(name);

            foreach (var child in Children()) child.pickingMode = PickingMode.Ignore;

            if (face.Order != null)
            {
                OrderButton = new Button();
                OrderButton.AddToClassList("card__order");
                OrderButton.EnableInClassList("card__order--ready", face.OrderUsable);
                OrderButton.Add(Part("card__order-icon", "icon--order"));
                var charges = new Label(face.Order.Charges.HasValue ? face.Order.Charges.Value.ToString() : "∞") { pickingMode = PickingMode.Ignore };
                charges.AddToClassList("card__order-charges");
                OrderButton.Add(charges);
                if (face.Order.Cooldown > 0)
                {
                    var cooldown = new Label("·" + face.Order.Cooldown) { pickingMode = PickingMode.Ignore };
                    cooldown.AddToClassList("card__order-cooldown");
                    OrderButton.Add(cooldown);
                }
                OrderButton.SetEnabled(face.OrderUsable);
                Add(OrderButton);
            }
        }

        /// <summary>The icon class of a status (`cards.md` §9): one SVG per status in UI/Art.</summary>
        public static string StatusIcon(string status) => "icon--" + status.Replace('_', '-');

        /// <summary>The icon class of a kind other than a unit, or null.</summary>
        public static string KindIcon(string kind) =>
            kind == "special" || kind == "artifact" || kind == "leader" || kind == "stratagem" ? "icon--" + kind : null;

        /// <summary>The icon classes shown in a card's header before the statuses: the kind's icon
        /// for a card that is not a unit, then its rows.</summary>
        public static IEnumerable<string> Icons(CardFace face)
        {
            var kind = KindIcon(face.Kind);
            if (kind != null) yield return kind;
            foreach (var row in face.Rows) yield return "icon--" + row;
        }

        private static string WatermarkIcon(CardFace face)
        {
            var kind = KindIcon(face.Kind);
            if (kind != null) return kind;
            return face.Rows.Count > 0 ? "icon--" + face.Rows[0] : null;
        }

        internal static VisualElement Part(params string[] classes)
        {
            var element = new VisualElement { pickingMode = PickingMode.Ignore };
            foreach (var c in classes) element.AddToClassList(c);
            return element;
        }
    }
}
