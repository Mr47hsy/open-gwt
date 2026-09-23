// Imports every SVG under UI/Art as a UI Toolkit vector image (the built-in Vector Graphics
// module, no package): tessellated with antialiased arc encoding, so it stays sharp at every
// panel scale and USS can tint it. Runs on import, so a fresh clone needs no manual step.
using Unity.VectorGraphics.Editor;
using UnityEditor;

namespace OpenGwt.Editor
{
    internal sealed class SvgImportSettings : AssetPostprocessor
    {
        private const string ArtFolder = "Assets/OpenGwt/UI/Art/";

        public override uint GetVersion() => 1;

        private void OnPreprocessAsset()
        {
            if (!assetPath.StartsWith(ArtFolder) || !assetPath.EndsWith(".svg")) return;
            if (!(assetImporter is SVGImporter svg)) return;
            svg.SvgType = SVGType.VectorImage;
            svg.TessellationMode = TessellationMode.AntialiasedArcEncodings;
        }
    }
}
