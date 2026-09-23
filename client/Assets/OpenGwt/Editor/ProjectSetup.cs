// Creates the assets that cannot be plain text: the panel settings, the scene and the player
// settings. Idempotent; run from the menu or headless with -executeMethod.
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UIElements;

namespace OpenGwt.Editor
{
    public static class ProjectSetup
    {
        private const string Root = "Assets/OpenGwt";
        private const string ScenePath = Root + "/Scenes/Main.unity";
        private const string PanelPath = Root + "/Settings/PanelSettings.asset";

        [MenuItem("OpenGwt/Set Up Project")]
        public static void Run()
        {
            Directory.CreateDirectory(Root + "/Settings");
            Directory.CreateDirectory(Root + "/Scenes");

            var theme = AssetDatabase.LoadAssetAtPath<ThemeStyleSheet>(Root + "/UI/OpenGwtTheme.tss");
            var board = AssetDatabase.LoadAssetAtPath<VisualTreeAsset>(Root + "/UI/Board.uxml");
            if (theme == null || board == null)
            {
                throw new FileNotFoundException("OpenGwtTheme.tss or Board.uxml did not import");
            }

            var panel = AssetDatabase.LoadAssetAtPath<PanelSettings>(PanelPath);
            if (panel == null)
            {
                panel = ScriptableObject.CreateInstance<PanelSettings>();
                AssetDatabase.CreateAsset(panel, PanelPath);
            }
            panel.themeStyleSheet = theme;
            panel.scaleMode = PanelScaleMode.ScaleWithScreenSize;
            panel.referenceResolution = new Vector2Int(1600, 900);
            panel.screenMatchMode = PanelScreenMatchMode.MatchWidthOrHeight;
            panel.match = 0.5f;
            EditorUtility.SetDirty(panel);

            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var camera = new GameObject("Main Camera").AddComponent<Camera>();
            camera.tag = "MainCamera";
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color(0.09f, 0.11f, 0.13f);
            camera.orthographic = true;
            var app = new GameObject("App");
            var document = app.AddComponent<UIDocument>();
            document.panelSettings = panel;
            document.visualTreeAsset = board;
            app.AddComponent<App>();
            EditorSceneManager.SaveScene(scene, ScenePath);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };

            PlayerSettings.companyName = "open-gwt contributors";
            PlayerSettings.productName = "open-gwt";
            PlayerSettings.SetApiCompatibilityLevel(NamedBuildTarget.Standalone, ApiCompatibilityLevel.NET_Standard);
            PlayerSettings.SetApiCompatibilityLevel(NamedBuildTarget.iOS, ApiCompatibilityLevel.NET_Standard);
            PlayerSettings.SetApiCompatibilityLevel(NamedBuildTarget.Android, ApiCompatibilityLevel.NET_Standard);
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.defaultScreenWidth = 1600;
            PlayerSettings.defaultScreenHeight = 900;
            PlayerSettings.resizableWindow = true;
            PlayerSettings.runInBackground = true;
            PlayerSettings.defaultInterfaceOrientation = UIOrientation.LandscapeLeft;
            PlayerSettings.allowedAutorotateToPortrait = false;
            PlayerSettings.allowedAutorotateToPortraitUpsideDown = false;
            PlayerSettings.allowedAutorotateToLandscapeLeft = true;
            PlayerSettings.allowedAutorotateToLandscapeRight = true;

            AssetDatabase.SaveAssets();
            Debug.Log("open-gwt: project set up (scene, panel settings, player settings)");
        }
    }
}
