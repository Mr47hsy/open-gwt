using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Newtonsoft.Json.Serialization;

namespace OpenGwt.Net
{
    /// <summary>One serializer configuration: snake_case on the wire, PascalCase in C#.</summary>
    public static class Json
    {
        public static readonly JsonSerializerSettings Settings = new JsonSerializerSettings
        {
            ContractResolver = new DefaultContractResolver { NamingStrategy = new SnakeCaseNamingStrategy() },
            NullValueHandling = NullValueHandling.Ignore,
        };

        public static readonly JsonSerializer Serializer = JsonSerializer.Create(Settings);

        public static T Parse<T>(string json) => JsonConvert.DeserializeObject<T>(json, Settings);

        public static T Convert<T>(JToken token) => token == null ? default : token.ToObject<T>(Serializer);

        public static string Stringify(object value) => JsonConvert.SerializeObject(value, Settings);
    }
}
