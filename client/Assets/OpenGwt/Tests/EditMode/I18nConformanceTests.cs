// The C# renderer must agree with the Python one on every case of data/i18n/conformance.json
// (ADR 0006). The JSON is generated from conformance.yaml by `opengwt-data conformance-json`.
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using OpenGwt.I18n;
using UnityEngine;

namespace OpenGwt.Tests
{
    public class I18nConformanceTests
    {
        private static string SuitePath =>
            Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "data", "i18n", "conformance.json"));

        [Test]
        public void ConformanceSuitePasses()
        {
            var suite = JObject.Parse(File.ReadAllText(SuitePath));
            Assert.AreEqual("opengwt.i18n-conformance/1", (string)suite["schema"]);
            var renderer = new MessageRenderer();
            foreach (var pair in (JObject)suite["tables"])
            {
                renderer.AddTable(pair.Key, ((JObject)pair.Value).ToObject<Dictionary<string, string>>());
            }
            var failures = new List<string>();
            var count = 0;
            foreach (var c in (JArray)suite["cases"])
            {
                count++;
                var parameters = new Dictionary<string, object>();
                if (c["params"] is JObject raw)
                {
                    foreach (var p in raw)
                    {
                        parameters[p.Key] = p.Value.Type == JTokenType.Integer ? (object)p.Value.Value<long>() : p.Value.ToString();
                    }
                }
                var got = renderer.Render((string)c["locale"], (string)c["key"], parameters);
                if (got != (string)c["expected"])
                {
                    failures.Add($"{c["locale"]} {c["key"]} {c["params"]}: got '{got}', expected '{c["expected"]}'");
                }
            }
            Assert.Greater(count, 20, "the suite should not be empty");
            Assert.IsEmpty(failures, string.Join("\n", failures));
        }

        [Test]
        public void PluralCategoriesMatchTheProtocol()
        {
            Assert.AreEqual("one", MessageRenderer.PluralCategory("en", 1));
            Assert.AreEqual("one", MessageRenderer.PluralCategory("en", -1));
            Assert.AreEqual("other", MessageRenderer.PluralCategory("en", 0));
            Assert.AreEqual("other", MessageRenderer.PluralCategory("zh-CN", 1));
            Assert.AreEqual("one", MessageRenderer.PluralCategory("ru", 21));
            Assert.AreEqual("few", MessageRenderer.PluralCategory("ru", 22));
            Assert.AreEqual("many", MessageRenderer.PluralCategory("ru", 112));
            Assert.AreEqual("other", MessageRenderer.PluralCategory("xx", 1));
        }

        [Test]
        public void LocaleNegotiationMatchesTheProtocol()
        {
            var supported = new[] { "en", "zh-CN", "ru" };
            Assert.AreEqual("ru", Locale.Negotiate(supported, "ru", "en"));
            Assert.AreEqual("zh-CN", Locale.Negotiate(supported, "ZH-cn", null));
            Assert.AreEqual("ru", Locale.Negotiate(supported, null, "fr;q=0.9, ru;q=0.8, en;q=0.7"));
            Assert.AreEqual("zh-CN", Locale.Negotiate(supported, null, "zh-TW, en;q=0.5"));
            Assert.AreEqual("en", Locale.Negotiate(supported, null, "de, *;q=0.1"));
            Assert.AreEqual("en", Locale.Negotiate(supported, "fr", ""));
            Assert.AreEqual("en", Locale.Negotiate(supported, null, "ru;q=0, en;q=0.2"));
        }
    }
}
