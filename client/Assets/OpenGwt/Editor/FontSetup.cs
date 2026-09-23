// Turns the TTFs in Assets/OpenGwt/Fonts into dynamic SDF font assets with the fallback chain of
// Fonts/README.md, and points the panel's text settings at them. Idempotent; headless-friendly.
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using UnityEngine.TextCore.LowLevel;
using UnityEngine.TextCore.Text;
using UnityEngine.UIElements;

namespace OpenGwt.Editor
{
    public static class FontSetup
    {
        private const string Fonts = "Assets/OpenGwt/Fonts";
        private const string PanelPath = "Assets/OpenGwt/Settings/PanelSettings.asset";
        private const string TextSettingsPath = "Assets/OpenGwt/Settings/PanelTextSettings.asset";

        [MenuItem("OpenGwt/Set Up Fonts")]
        public static void Run()
        {
            var sans = Create("NotoSans-Regular", 72, 1024);
            var sansBold = Create("NotoSans-Bold", 72, 1024);
            var sansSC = Create("NotoSansSC-Regular", 72, 2048);
            var serif = Create("NotoSerif-Regular", 72, 1024);
            var serifBold = Create("NotoSerif-Bold", 72, 1024);
            var serifSC = Create("NotoSerifSC-Regular", 72, 2048);

            SetFallbacks(sans, sansSC);
            SetFallbacks(sansBold, sansSC);
            SetFallbacks(serif, serifSC, sans, sansSC);
            SetFallbacks(serifBold, serifSC, sansBold, sansSC);
            SetBold(sans, sansBold);
            SetBold(serif, serifBold);

            var textSettings = AssetDatabase.LoadAssetAtPath<PanelTextSettings>(TextSettingsPath);
            if (textSettings == null)
            {
                textSettings = ScriptableObject.CreateInstance<PanelTextSettings>();
                AssetDatabase.CreateAsset(textSettings, TextSettingsPath);
            }
            textSettings.fallbackFontAssets = new List<FontAsset> { sans, sansSC };
            EditorUtility.SetDirty(textSettings);

            var panel = AssetDatabase.LoadAssetAtPath<PanelSettings>(PanelPath);
            if (panel != null)
            {
                panel.textSettings = textSettings;
                EditorUtility.SetDirty(panel);
            }
            AssetDatabase.SaveAssets();
            Debug.Log("open-gwt: font assets and fallback chain set up");
        }

        private static void SetFallbacks(FontAsset asset, params FontAsset[] fallbacks)
        {
            asset.fallbackFontAssetTable = new List<FontAsset>(fallbacks);
            EditorUtility.SetDirty(asset);
        }

        private static void SetBold(FontAsset regular, FontAsset bold)
        {
            // the getter hands out the live array; index 7 is weight 700 (bold)
            regular.fontWeightTable[7].regularTypeface = bold;
            EditorUtility.SetDirty(regular);
        }

        private static FontAsset Create(string name, int samplingPointSize, int atlasSize)
        {
            var path = Fonts + "/" + name + "-SDF.asset";
            var existing = AssetDatabase.LoadAssetAtPath<FontAsset>(path);
            if (existing != null) return existing;
            var font = AssetDatabase.LoadAssetAtPath<Font>(Fonts + "/" + name + ".ttf");
            if (font == null) throw new System.IO.FileNotFoundException(Fonts + "/" + name + ".ttf");
            var asset = FontAsset.CreateFontAsset(
                font, samplingPointSize, 9, GlyphRenderMode.SDFAA, atlasSize, atlasSize,
                AtlasPopulationMode.Dynamic, true);
            asset.name = name + "-SDF";
            AssetDatabase.CreateAsset(asset, path);
            asset.atlasTextures[0].name = name + " Atlas";
            AssetDatabase.AddObjectToAsset(asset.atlasTextures[0], asset);
            asset.material.name = name + " Material";
            AssetDatabase.AddObjectToAsset(asset.material, asset);
            EditorUtility.SetDirty(asset);
            return asset;
        }
    }
}
