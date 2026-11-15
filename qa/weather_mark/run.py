#!/usr/bin/env python3
"""Exercise the unmodified vector mark with Qt and render a size/condition sheet.

Only the palette singleton is substituted. No weather process or user state runs.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT


PREVIEW = r'''import QtQuick
Rectangle {
  id: sheet
  width:1040; height:640; color:"#171923"
  property color ink:"#b7bfdf"
  Text { x:28; y:22; text:"Horizon · signature météo / proportions réelles"; color:sheet.ink; font.pixelSize:22; textFormat:Text.PlainText }
  Text { x:28; y:63; text:"12 px dans un emplacement de 21 px · puis 24, 48 et 96 px"; color:sheet.ink; opacity:0.65; font.pixelSize:13; textFormat:Text.PlainText }
  Grid {
    x:28; y:104; columns:4; spacing:12
    Repeater {
      model:[{code:0,night:false,label:"Soleil"},{code:0,night:true,label:"Nuit"},{code:1,night:false,label:"Éclaircies"},{code:2,night:false,label:"Partiellement nuageux"},
        {code:3,night:false,label:"Couvert"},{code:45,night:false,label:"Brume"},{code:61,night:false,label:"Pluie"},{code:71,night:false,label:"Neige"},
        {code:95,night:false,label:"Orage"},{code:85,night:false,label:"Averses de neige"},{code:2,night:true,label:"Nuages nocturnes"},{code:null,night:false,label:"Indisponible"}]
      Rectangle {
        id: tile
        required property var modelData
        width:237; height:163; radius:12; color:"#222737"
        Text { x:12; y:12; text:tile.modelData.label; color:sheet.ink; font.pixelSize:12; textFormat:Text.PlainText }
        Rectangle {
          x:12; y:76; width:21; height:26; color:"#171923"
          WeatherMark { x:4.5; y:7; scale:0.5; transformOrigin:Item.TopLeft; code:tile.modelData.code; night:tile.modelData.night; ink:sheet.ink }
        }
        WeatherMark { x:45; y:75; code:tile.modelData.code; night:tile.modelData.night; ink:sheet.ink }
        WeatherMark { x:78; y:63; scale:2; transformOrigin:Item.TopLeft; code:tile.modelData.code; night:tile.modelData.night; ink:sheet.ink }
        WeatherMark { x:135; y:43; scale:4; transformOrigin:Item.TopLeft; code:tile.modelData.code; night:tile.modelData.night; ink:sheet.ink }
        Text { x:12; y:140; text:"12         24           48                   96"; color:sheet.ink; opacity:0.5; font.pixelSize:9; textFormat:Text.PlainText }
      }
    }
  }
}'''

NATIVE = r'''import QtQuick
import QtQuick.Window
import Quickshell
import qs.Commons as Commons
import qs.Ui as Ui
ShellRoot {
  Window {
    id: window
    visible:true; width:600; height:170; color:Commons.Color.background
    Text { x:20; y:18; text:"Gabarit natif · Horizon · Horizon avec température"; color:Commons.Color.foreground; font.pixelSize:16; textFormat:Text.PlainText }
    Ui.BarIconButton { id: native; x:26; y:70; width:implicitWidth; height:implicitHeight; text:"☁"; slotSize:Commons.Style.bar.statusSlot }
    Ui.BarIconButton {
      id: signature
      x:178; y:70; width:implicitWidth; height:implicitHeight
      slotSize:Commons.Style.bar.statusSlot
      iconComponent: Component { WeatherMark { code:3 } }
    }
    Ui.WidgetButton {
      id: combined
      x:338; y:70; width:implicitWidth; height:implicitHeight
      labelVisible:false; hasVisualContent:true
      fontSize:Commons.Style.bar.iconFont
      implicitWidth:row.implicitWidth + Commons.Style.bar.statusSlot - Commons.Style.bar.iconCanvas
      Row {
        id:row
        anchors.centerIn:parent
        spacing:Commons.Style.space(4)
        Ui.BarIconContent {
          id: normalized
          anchors.verticalCenter:parent.verticalCenter
          width:Commons.Style.bar.iconCanvas; height:width
          sourceComponent:Component { WeatherMark { code:3 } }
        }
        Text { text:"9°"; color:Commons.Color.foreground; font.family:Commons.Style.font.family; font.pixelSize:Commons.Style.bar.iconFont; textFormat:Text.PlainText }
      }
    }
    Text { x:20; y:116; text:"Météo native"; color:Commons.Color.foreground; opacity:0.7; font.pixelSize:11; textFormat:Text.PlainText }
    Text { x:172; y:116; text:"Même emplacement"; color:Commons.Color.foreground; opacity:0.7; font.pixelSize:11; textFormat:Text.PlainText }
    Text { x:332; y:116; text:"Température conservée"; color:Commons.Color.foreground; opacity:0.7; font.pixelSize:11; textFormat:Text.PlainText }
    Timer {
      interval:250; running:true
      onTriggered: {
        if (native.implicitWidth !== Commons.Style.bar.statusSlot || signature.implicitWidth !== native.implicitWidth
            || Math.abs(Math.max(normalized.paintedWidth,normalized.paintedHeight) - Commons.Style.bar.iconSize) > 0.01) {
          console.error("QA_FAIL: native optical size contract"); Qt.exit(1); return
        }
        console.warn("QA_NATIVE_MARK_PASS", "slot",signature.implicitWidth,"painted",normalized.paintedWidth,normalized.paintedHeight,"with temperature",combined.implicitWidth)
        window.contentItem.grabToImage(function(image) {
          if (!image.saveToFile(OUTPUT)) { console.error("QA_FAIL: native capture"); Qt.exit(1); return }
          Qt.quit()
        })
      }
    }
  }
}'''


def prepare(directory, light):
    commons = directory / "qs/Commons"
    commons.mkdir(parents=True)
    (commons / "qmldir").write_text("module qs.Commons\nsingleton Color 1.0 Color.qml\n")
    foreground = "#26354a" if light else "#b7bfdf"
    (commons / "Color.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { property color foreground:"' + foreground + '" }\n')
    for name in ("WeatherMark.qml", "WeatherModel.js"):
        shutil.copy2(SOURCE / name, directory / name)
    shutil.copy2(HERE / "tst_mark.qml", directory / "tst_mark.qml")


def preview(directory, light):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickView
    from PySide6.QtTest import QTest
    app = QGuiApplication.instance() or QGuiApplication([])
    source = PREVIEW
    if light:
        source = source.replace("#171923", "#edf1f8").replace("#222737", "#dbe3f2").replace("#b7bfdf", "#26354a")
    path = directory / "Preview.qml"
    path.write_text(source)
    view = QQuickView()
    view.engine().addImportPath(str(directory))
    view.setSource(QUrl.fromLocalFile(str(path)))
    if view.status() == QQuickView.Status.Error:
        raise RuntimeError("Mark preview failed to load")
    view.show(); QTest.qWait(100)
    image = view.grabWindow()
    if image.isNull():
        raise RuntimeError("Mark preview is empty")
    output = HERE / ("preview-light.png" if light else "preview.png")
    image.save(str(output)); view.close()
    print(output)


def native_preview():
    with tempfile.TemporaryDirectory(prefix="pixel-weather-mark-native-") as temporary:
        directory = Path(temporary)
        for module in ("Commons", "Ui"):
            (directory / module).symlink_to(Path("/usr/share/omarchy/shell") / module, target_is_directory=True)
        for name in ("WeatherMark.qml", "WeatherModel.js"):
            shutil.copy2(SOURCE / name,directory / name)
        output = HERE / "native-comparison.png"
        (directory / "shell.qml").write_text(NATIVE.replace("OUTPUT",json.dumps(str(output))))
        environment = os.environ.copy()
        environment.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", XDG_STATE_HOME=str(directory / "state"))
        result = subprocess.run(["timeout","6s","quickshell","--no-color","-p",str(directory)],env=environment,
                                text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=10)
        (HERE / "native.log").write_text(result.stdout)
        print(result.stdout,end="")
        if result.returncode or "QA_NATIVE_MARK_PASS" not in result.stdout or "QA_FAIL" in result.stdout or "ERROR" in result.stdout:
            raise RuntimeError("Native mark comparison failed")
        print(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--light", action="store_true")
    parser.add_argument("--native", action="store_true", help="Also render real Omarchy controls without starting a weather backend")
    parser.add_argument("--scale", type=float, default=1)
    args = parser.parse_args()
    if not 0.5 <= args.scale <= 3:
        parser.error("--scale must be between 0.5 and 3")
    os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_SCALE_FACTOR=str(args.scale))
    with tempfile.TemporaryDirectory(prefix="pixel-weather-mark-") as temporary:
        directory = Path(temporary)
        prepare(directory, args.light)
        result = subprocess.run(["/usr/lib/qt6/bin/qmltestrunner", "-input", str(directory / "tst_mark.qml"), "-import", str(directory)],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        (HERE / ("test-light.log" if args.light else "test.log")).write_text(result.stdout)
        print(result.stdout, end="")
        if result.returncode:
            raise SystemExit(result.returncode)
        if args.preview:
            preview(directory, args.light)
    if args.native:
        native_preview()


if __name__ == "__main__":
    main()
