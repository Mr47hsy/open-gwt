using System.Collections.Generic;
using UnityEngine.UIElements;

namespace OpenGwt.UI
{
    /// <summary>A card as a flat box: name, a line of metadata, and the power (ADR 0005).</summary>
    public sealed class CardElement : VisualElement
    {
        public string Instance { get; }
        public string Card { get; }

        private readonly Label power;

        public CardElement(string instance, string card, string name, string meta, int? powerValue, int? basePower, IEnumerable<string> classes)
        {
            Instance = instance;
            Card = card;
            AddToClassList("card");
            foreach (var c in classes) AddToClassList(c);
            var nameLabel = new Label(name);
            nameLabel.AddToClassList("card__name");
            Add(nameLabel);
            var metaLabel = new Label(meta);
            metaLabel.AddToClassList("card__meta");
            Add(metaLabel);
            power = new Label(powerValue.HasValue ? powerValue.Value.ToString() : "");
            power.AddToClassList("card__power");
            if (powerValue.HasValue && basePower.HasValue)
            {
                if (powerValue.Value > basePower.Value) power.AddToClassList("card__power--boosted");
                if (powerValue.Value < basePower.Value) power.AddToClassList("card__power--reduced");
            }
            Add(power);
        }
    }
}
