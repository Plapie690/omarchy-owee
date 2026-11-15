#!/usr/bin/env python3
"""Exercise unmodified WeatherCards with real Qt pointer/keyboard events offscreen.

Minimal Commons stubs isolate the interaction from the running desktop; the
project's Quickshell runtime harness separately loads the real Omarchy Commons.
"""
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    with tempfile.TemporaryDirectory(prefix="pixel-weather-cards-test-") as temporary:
        modules = Path(temporary)
        commons = modules / "qs/Commons"
        commons.mkdir(parents=True)
        (commons / "qmldir").write_text("module qs.Commons\nsingleton Color 1.0 Color.qml\nsingleton Style 1.0 Style.qml\nsingleton Util 1.0 Util.qml\n")
        (commons / "Color.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { property color foreground:"#d9dfeb"; property color background:"#151923"; property color accent:"#91b3fa" }\n')
        (commons / "Style.qml").write_text('''pragma Singleton
import QtQuick
QtObject {
  property string fontFamily: "Sans"
  property int cornerRadius: 0
  readonly property QtObject font: QtObject {
    readonly property int bodySmall: 11
    readonly property int body: 12
    readonly property int subtitle: 14
    readonly property int title: 14
    readonly property int heading: 18
    readonly property int display: 24
    readonly property int iconLarge: 18
  }
  function space(value) { return value }
  function duration(value) { return 0 }
}
''')
        (commons / "Util.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { function readingKey(event) { return event.key } }\n')
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="", QT_QUICK_CONTROLS_STYLE="Basic", QT_QUICK_BACKEND="software")
        result = subprocess.run(["/usr/lib/qt6/bin/qmltestrunner", "-input", str(HERE), "-import", str(modules)],
                                env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=40)
        (HERE / "test.log").write_text(result.stdout)
        print(result.stdout, end="")
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
