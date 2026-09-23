using System;
using System.Collections.Generic;
using UnityEngine.UIElements;

namespace OpenGwt.UI
{
    /// <summary>What a card shows, already rendered to text: built by the board from the view, the
    /// pack and the translation tables, and read by <see cref="CardElement"/> and the preview.</summary>
    public sealed class CardFace
    {
        public string Card;
        public string Kind = "";
        public IReadOnlyList<string> Rows = Array.Empty<string>();
        public int? Power;
        public int? BasePower;
        public bool Immune;

        public string Name = "";
        public string Text = "";
        public string KindLabel = "";
        public IReadOnlyList<string> RowLabels = Array.Empty<string>();
        public string ImmuneLabel = "";
        public string PowerNote = "";
    }

    /// <summary>A card on the vector frame: power badge, row / kind / status icons, a watermark in the
    /// art window and the name (ADR 0005). Layout and look are Board.uss; the children never take
    /// the pointer, so the card itself receives hover, press and click.</summary>
    public sealed class CardElement : VisualElement
    {
        public string Instance { get; }
        public string Card { get; }

        public CardElement(string instance, CardFace face, IEnumerable<string> classes)
        {
            Instance = instance;
            Card = face.Card;
            AddToClassList("card");
            if (face.Kind == "special") AddToClassList("card--special");
            if (face.Kind == "leader") AddToClassList("card--leader");
            if (face.Immune) AddToClassList("card--immune");
            foreach (var c in classes) AddToClassList(c);

            var art = Part("card__art");
            var watermark = WatermarkIcon(face);
            if (watermark != null) art.Add(Part("card__watermark", watermark));
            Add(art);

            var power = new Label(face.Power.HasValue ? face.Power.Value.ToString() : "");
            power.AddToClassList("card__power");
            if (!face.Power.HasValue) power.AddToClassList("card__power--none");
            else if (face.BasePower.HasValue && face.Power.Value > face.BasePower.Value) power.AddToClassList("card__power--boosted");
            else if (face.BasePower.HasValue && face.Power.Value < face.BasePower.Value) power.AddToClassList("card__power--reduced");
            Add(power);

            var icons = Part("card__icons");
            foreach (var icon in Icons(face)) icons.Add(Part("card__icon", icon));
            Add(icons);

            var name = new Label(face.Name);
            name.AddToClassList("card__name");
            Add(name);

            foreach (var child in Children()) child.pickingMode = PickingMode.Ignore;
        }

        /// <summary>The icon classes shown in a card's header: a special's spark, a unit's rows, then statuses.</summary>
        public static IEnumerable<string> Icons(CardFace face)
        {
            if (face.Kind == "special") yield return "icon--special";
            foreach (var row in face.Rows) yield return "icon--" + row;
            if (face.Immune) yield return "icon--immune";
        }

        private static string WatermarkIcon(CardFace face)
        {
            if (face.Kind == "special") return "icon--special";
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
