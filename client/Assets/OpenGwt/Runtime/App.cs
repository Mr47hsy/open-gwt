using OpenGwt.Match;
using OpenGwt.UI;
using UnityEngine;
using UnityEngine.UIElements;

namespace OpenGwt
{
    /// <summary>Scene entry point: owns the client session and the board controller.</summary>
    [RequireComponent(typeof(UIDocument))]
    public sealed class App : MonoBehaviour
    {
        [SerializeField] private string defaultServerUrl = "http://127.0.0.1:8000";

        private MatchClient client;
        private BoardView board;

        private void OnEnable()
        {
            Application.runInBackground = true;
            client = new MatchClient();
            board = new BoardView(GetComponent<UIDocument>().rootVisualElement, client, defaultServerUrl);
        }

        private void Update()
        {
            client?.Pump();
        }

        private void OnDisable()
        {
            board?.Dispose();
            client?.Dispose();
            board = null;
            client = null;
        }
    }
}
