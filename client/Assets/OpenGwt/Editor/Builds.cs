using System;
using UnityEditor;
using UnityEditor.Build.Reporting;

namespace OpenGwt.Editor
{
    /// <summary>Headless builds: `-executeMethod OpenGwt.Editor.Builds.Mac` and friends.</summary>
    public static class Builds
    {
        private static readonly string[] Scenes = { "Assets/OpenGwt/Scenes/Main.unity" };

        public static void Mac() => Build(BuildTarget.StandaloneOSX, "Builds/macOS/open-gwt.app");

        public static void Android() => Build(BuildTarget.Android, "Builds/android/open-gwt.apk");

        public static void IOS() => Build(BuildTarget.iOS, "Builds/ios");

        private static void Build(BuildTarget target, string location)
        {
            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = Scenes,
                locationPathName = location,
                target = target,
                options = BuildOptions.None,
            });
            if (report.summary.result != BuildResult.Succeeded)
            {
                throw new Exception("build failed: " + report.summary.result + " with " + report.summary.totalErrors + " errors");
            }
            Console.WriteLine("open-gwt: built " + location + " (" + report.summary.totalSize / (1024 * 1024) + " MB)");
        }
    }
}
