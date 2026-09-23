// Renderer for the opengwt.i18n/1 message format (docs/protocol/i18n.md).
// Twin of opengwt.i18n in the server; data/i18n/conformance.json keeps the two equal.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace OpenGwt.I18n
{
    public sealed class MessageRenderer
    {
        public const string BaseLocale = "en";

        private static readonly Regex NamePattern = new Regex("^[a-z][a-z0-9_]*$", RegexOptions.Compiled);
        private static readonly IReadOnlyDictionary<string, object> NoParams = new Dictionary<string, object>();

        private readonly Dictionary<string, Dictionary<string, string>> tables =
            new Dictionary<string, Dictionary<string, string>>(StringComparer.Ordinal);
        private readonly string baseLocale;

        public MessageRenderer(string baseLocale = BaseLocale)
        {
            this.baseLocale = baseLocale;
        }

        public MessageRenderer(IReadOnlyDictionary<string, IReadOnlyDictionary<string, string>> initial, string baseLocale = BaseLocale)
            : this(baseLocale)
        {
            foreach (var pair in initial)
            {
                AddTable(pair.Key, pair.Value);
            }
        }

        public void AddTable(string locale, IReadOnlyDictionary<string, string> table)
        {
            tables[locale] = table.ToDictionary(p => p.Key, p => p.Value, StringComparer.Ordinal);
        }

        public IReadOnlyList<string> Locales => tables.Keys.OrderBy(k => k, StringComparer.Ordinal).ToList();

        public bool Has(string locale) => tables.ContainsKey(locale);

        /// <summary>CLDR plural category of an integer for the supported locales (§5).</summary>
        public static string PluralCategory(string locale, long count)
        {
            var n = Math.Abs(count);
            switch (locale)
            {
                case "en":
                    return n == 1 ? "one" : "other";
                case "zh-CN":
                    return "other";
                case "ru":
                    if (n % 10 == 1 && n % 100 != 11) return "one";
                    if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return "few";
                    return "many";
                default:
                    return "other";
            }
        }

        /// <summary>Locale-major lookup with plural variants (§6); null when the key is missing.</summary>
        public string Lookup(string locale, string key, long? count = null)
        {
            var candidates = count.HasValue
                ? new[] { key + "." + PluralCategory(locale, count.Value), key + ".other", key }
                : new[] { key };
            foreach (var loc in new[] { locale, baseLocale })
            {
                if (loc == null || !tables.TryGetValue(loc, out var table)) continue;
                foreach (var candidate in candidates)
                {
                    if (table.TryGetValue(candidate, out var message)) return message;
                }
            }
            return null;
        }

        public string Render(string locale, string key, IReadOnlyDictionary<string, object> parameters = null)
        {
            var p = parameters ?? NoParams;
            long? count = null;
            foreach (var pair in p)
            {
                Check(pair.Key, pair.Value);
                if (pair.Key == "count") count = ToLong(pair.Value);
            }
            var message = Lookup(locale, key, count);
            return message == null ? key : Format(locale, message, p);
        }

        private static void Check(string name, object value)
        {
            var ok = value is string || (IsInteger(value) && !(value is bool));
            if (!ok) throw new ArgumentException($"parameter '{name}' must be an integer or a string");
            if (name == "count" && !IsInteger(value)) throw new ArgumentException("parameter 'count' must be an integer");
        }

        private static bool IsInteger(object value) =>
            value is int || value is long || value is short || value is byte || value is uint || value is ushort;

        private static long ToLong(object value) => Convert.ToInt64(value, CultureInfo.InvariantCulture);

        private string Format(string locale, string message, IReadOnlyDictionary<string, object> parameters)
        {
            var output = new StringBuilder(message.Length + 16);
            var i = 0;
            while (i < message.Length)
            {
                if (Starts(message, i, "{{")) { output.Append('{'); i += 2; continue; }
                if (Starts(message, i, "}}")) { output.Append('}'); i += 2; continue; }
                if (message[i] == '{')
                {
                    var end = message.IndexOf('}', i);
                    var name = end != -1 ? message.Substring(i + 1, end - i - 1) : "";
                    if (NamePattern.IsMatch(name) && parameters.TryGetValue(name, out var value))
                    {
                        output.Append(Param(locale, value));
                        i = end + 1;
                        continue;
                    }
                }
                output.Append(message[i]);
                i += 1;
            }
            return output.ToString();
        }

        private static bool Starts(string s, int at, string token) =>
            string.CompareOrdinal(s, at, token, 0, token.Length) == 0 && at + token.Length <= s.Length;

        private string Param(string locale, object value)
        {
            if (IsInteger(value)) return ToLong(value).ToString(CultureInfo.InvariantCulture);
            var text = (string)value;
            if (text.StartsWith("@@", StringComparison.Ordinal)) return text.Substring(1);
            if (text.StartsWith("@", StringComparison.Ordinal))
            {
                var reference = text.Substring(1);
                return Lookup(locale, reference) ?? reference;
            }
            return text;
        }
    }

    public static class Locale
    {
        /// <summary>Profile locale, then the best Accept-Language match, then the base (§8).</summary>
        public static string Negotiate(IEnumerable<string> supported, string preferred, string acceptLanguage, string baseLocale = MessageRenderer.BaseLocale)
        {
            var byLower = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (var s in supported) byLower[s.ToLowerInvariant()] = s;
            if (!string.IsNullOrEmpty(preferred) && byLower.TryGetValue(preferred.ToLowerInvariant(), out var exact)) return exact;
            foreach (var tag in AcceptLanguageTags(acceptLanguage))
            {
                if (byLower.TryGetValue(tag, out var match)) return match;
                var prefix = tag.Split('-')[0];
                foreach (var pair in byLower)
                {
                    if (pair.Key.Split('-')[0] == prefix) return pair.Value;
                }
            }
            return baseLocale;
        }

        private static IEnumerable<string> AcceptLanguageTags(string header)
        {
            if (string.IsNullOrEmpty(header)) return Array.Empty<string>();
            var weighted = new List<(double q, int index, string tag)>();
            var index = 0;
            foreach (var part in header.Split(','))
            {
                var piece = part.Trim();
                if (piece.Length == 0) { index++; continue; }
                var semicolon = piece.IndexOf(';');
                var tag = (semicolon == -1 ? piece : piece.Substring(0, semicolon)).Trim().ToLowerInvariant();
                var quality = 1.0;
                if (semicolon != -1)
                {
                    var rest = piece.Substring(semicolon + 1).Trim();
                    if (rest.StartsWith("q=", StringComparison.Ordinal))
                    {
                        quality = double.TryParse(rest.Substring(2), NumberStyles.Float, CultureInfo.InvariantCulture, out var q) ? q : 0.0;
                    }
                }
                if (quality > 0 && tag != "*") weighted.Add((-quality, index, tag));
                index++;
            }
            return weighted.OrderBy(w => w.q).ThenBy(w => w.index).Select(w => w.tag).ToList();
        }
    }
}
