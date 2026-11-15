#!/usr/bin/env python3
"""Test the unmodified weather drawing components in real Qt, without network.

Only Commons palette/animation settings are substituted. Optional preview uses
the same QML components, rendered in a disposable offscreen PySide6 window.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT


def prepare(directory, light=False):
    commons = directory / "qs/Commons"
    commons.mkdir(parents=True)
    (commons / "qmldir").write_text("module qs.Commons\nsingleton Color 1.0 Color.qml\nsingleton Style 1.0 Style.qml\n")
    palette = ('#26354a', '#edf1f8', '#4667aa') if light else ('#d9dfeb', '#151923', '#91b3fa')
    (commons / "Color.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { property color foreground:"%s"; property color background:"%s"; property color accent:"%s" }\n' % palette)
    (commons / "Style.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { property bool animationsEnabled:true; function duration(value) { return animationsEnabled ? value : 0 } function space(value) { return value } }\n')
    for name in ("Sky.qml", "WeatherIcon.qml", "WeatherModel.js", "MotionCoordinator.qml", "AnimatedSection.qml"):
        shutil.copy2(SOURCE / name, directory / name)
    shutil.copy2(HERE / "tst_motion.qml", directory / "tst_motion.qml")


PREVIEW = r'''import QtQuick
Rectangle {
  width: 1080; height: 520; color: "#151923"
  Text { x:24; y:16; text:"Pixel Weather 0.8 · aperçu contrôlé des conditions"; color:"#d9dfeb"; font.pixelSize:20; textFormat:Text.PlainText }
  Grid {
    x:24; y:64; columns:4; spacing:16
    Repeater {
      model:[{code:0,night:false,label:"Soleil"},{code:0,night:true,label:"Nuit"},{code:1,night:false,label:"Éclaircies"},{code:2,night:true,label:"Éclaircies nocturnes"},
        {code:3,night:false,label:"Couvert"},{code:45,night:false,label:"Brouillard"},{code:61,night:false,label:"Pluie"},{code:71,night:false,label:"Neige"},
        {code:95,night:false,label:"Orage"},{code:2,night:false,label:"Partiellement nuageux"},{code:85,night:false,label:"Averses de neige"},{code:null,night:false,label:"Indisponible"}]
      Rectangle {
        required property var modelData
        width:246; height:132; radius:24; color:"#292f46"
        WeatherIcon { x:16; y:18; width:24; height:24; code:parent.modelData.code; night:parent.modelData.night }
        Text { x:48; y:22; text:parent.modelData.label; color:"#d9dfeb"; font.pixelSize:13; textFormat:Text.PlainText }
        Sky { x:90; y:28; width:138; height:95; code:parent.modelData.code; night:parent.modelData.night; openingSerial:1; active:true }
      }
    }
  }
}'''


def preview(directory, video, light=False):
    from PySide6.QtCore import QElapsedTimer, QUrl
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtQuick import QQuickView
    from PySide6.QtTest import QTest

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 - retain the Qt application lifetime
    path = directory / "Preview.qml"
    source = PREVIEW
    if light:
        source = source.replace('#151923', '#edf1f8').replace('#d9dfeb', '#26354a').replace('#292f46', '#dbe3f2')
    path.write_text(source)
    suffix = 'light-0.8' if light else '0.8'
    view = QQuickView()
    view.engine().addImportPath(str(directory))
    view.setSource(QUrl.fromLocalFile(str(path)))
    if view.status() == QQuickView.Status.Error:
        raise RuntimeError("Weather preview QML failed to load")
    view.show()
    count = 160 if video else 31
    timer = QElapsedTimer()
    timer.start()
    for frame in range(count):
        QTest.qWait(max(0, frame * 50 - timer.elapsed()))
        image = view.grabWindow()
        if image.isNull():
            raise RuntimeError("Weather preview returned an empty frame")
        if frame == 30:
            image.save(str(HERE / f"preview-{suffix}.png"))
        if video:
            image.save(str(directory / f"frame_{frame:04d}.png"))
    view.close()
    if video:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", "20", "-i", str(directory / "frame_%04d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(HERE / f"preview-{suffix}.mp4")], check=True, timeout=30)

    # Capture the same cloudy scene at real elapsed times, rather than manually
    # changing animation properties. This shows the complete opening sequence.
    sequence_source = '''import QtQuick
Rectangle {
  width:240; height:190; color:"#292f46"
  property string stamp:""
  Text { x:16; y:12; text:"Couvert · " + parent.stamp; color:"#d9dfeb"; font.pixelSize:14; textFormat:Text.PlainText }
  Sky { x:34; y:40; width:172; height:137; code:3; openingSerial:1; active:true }
}'''
    if light:
        sequence_source = sequence_source.replace('#d9dfeb', '#26354a').replace('#292f46', '#dbe3f2')
    sequence_path = directory / "Opening.qml"
    sequence_path.write_text(sequence_source)
    sequence_view = QQuickView()
    sequence_view.engine().addImportPath(str(directory))
    sequence_view.setSource(QUrl.fromLocalFile(str(sequence_path)))
    if sequence_view.status() == QQuickView.Status.Error:
        raise RuntimeError("Cloud opening QML failed to load")
    sequence_view.show()
    timer.restart()
    images = []
    for stamp in (100, 400, 900, 1500, 3500):
        QTest.qWait(max(0, stamp - timer.elapsed()))
        sequence_view.rootObject().setProperty("stamp", f"{stamp/1000:g} s")
        QTest.qWait(1)
        images.append(sequence_view.grabWindow())
    sequence_view.close()
    if any(image.isNull() for image in images):
        raise RuntimeError("Cloud opening returned an empty frame")
    sheet = QImage(sum(image.width() for image in images), images[0].height(), QImage.Format.Format_ARGB32)
    sheet.fill(0)
    painter = QPainter(sheet)
    offset = 0
    for image in images:
        # Reset DPR for pixel-accurate compositing at the requested display scale.
        image.setDevicePixelRatio(1)
        painter.drawImage(offset, 0, image)
        offset += image.width()
    painter.end()
    sheet.save(str(HERE / f"opening-{suffix}.png"))


def native_runtime(directory):
    """Load the shared clock with actual Omarchy Commons in an isolated shell."""
    base = directory / "native"
    plugin = base / "plugin"
    plugin.mkdir(parents=True)
    for name in ("Commons", "Ui", "services"):
        (base / name).symlink_to(Path("/usr/share/omarchy/shell") / name, target_is_directory=True)
    for name in ("MotionCoordinator.qml", "AnimatedSection.qml", "Sky.qml", "WeatherModel.js"):
        shutil.copy2(SOURCE / name, plugin / name)
    (base / "shell.qml").write_text('''import QtQuick
import QtQuick.Window
import Quickshell
import "plugin" as Weather
ShellRoot {
  property int stage: 0
  property int ticks: 0
  function check(ok,message) {if(!ok)throw new Error("QA_NATIVE_MOTION_FAIL: "+message)}
  Window {
    visible:true;width:400;height:220
    Weather.MotionCoordinator {id:opening}
    Column {
      width:360;spacing:12
      Weather.AnimatedSection {
        id:hero;width:parent.width;progress:opening.progress
        Rectangle {width:parent.width;height:100;color:"#27344b"}
        Weather.Sky {id:sky;width:130;height:100;code:61;active:opening.active;openingProgress:opening.progress}
      }
      Weather.AnimatedSection {
        id:hourly;width:parent.width;progress:opening.progress;start:0.2
        Rectangle {width:parent.width;height:40;color:"#91b3fa"}
      }
    }
  }
  Timer {
    interval:25;repeat:true;running:true
    onTriggered: {
      try {
        ticks++
        if(ticks>80)throw new Error("QA_NATIVE_MOTION_FAIL: timeout")
        check(hero.height===100&&hourly.y===112,"section geometry remains stable")
        check(opening.duration<=240,"opening stays within the native motion budget")
        if(stage===0) {check(opening.progress===1&&!opening.running,"closed clock is settled");opening.active=true;stage++;return}
        if(stage===1) {
          check(Math.abs(sky.entrance-opening.progress)<0.0001,"illustration shares the section clock")
          if(opening.running)return
          check(opening.progress===1&&hero.opacity===1,"opening finishes fully visible")
          opening.active=false
          check(!sky.motionRunning&&!opening.running&&opening.progress===1,"close stops all motion without hiding exit content")
          stage++;return
        }
        if(stage===2) {
          check(!opening.running&&opening.progress===1&&!sky.motionRunning,"closed state has no animation ticks")
          opening.openingSerial++;opening.active=true
          check(!opening.motionAllowed||opening.progress===0,"reopen starts a fresh shared clock")
          opening.active=false
          check(hero.opacity===1&&!opening.running&&!sky.motionRunning,"mid-opening close leaves native exit visible")
          console.warn("QA_NATIVE_MOTION_PASS: shared clock, native Style, stable geometry, reopen and closed lifecycle")
          Qt.quit()
        }
      } catch(error) {console.error(error.message);Qt.exit(1)}
    }
  }
}
''')
    env = os.environ.copy()
    env.update(XDG_STATE_HOME=str(base / "state"), XDG_CACHE_HOME=str(base / "cache"),
               XDG_CONFIG_HOME=str(base / "config"), XDG_DATA_HOME=str(base / "data"))
    result = subprocess.run(["quickshell", "--no-color", "-p", str(base)], env=env,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=8)
    output = result.stdout
    (HERE / "native.log").write_text(output)
    if result.returncode or "QA_NATIVE_MOTION_PASS" not in output or any(word in output for word in ("ERROR", "WARN scene:", "QA_NATIVE_MOTION_FAIL")):
        raise RuntimeError(output[-6000:])
    print("QA_NATIVE_MOTION_PASS: actual Commons, isolated XDG state, no user preference changes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", "--render", action="store_true", help="Render the condition overview PNG")
    parser.add_argument("--video", action="store_true", help="Also render an eight-second MP4")
    parser.add_argument("--light", action="store_true", help="Use a light Commons palette and preview background")
    parser.add_argument("--scale", type=float, default=1, help="Qt display scale used by tests and preview")
    parser.add_argument("--native", action="store_true", help="Also exercise actual Omarchy Commons with Quickshell")
    args = parser.parse_args()
    if not 0.5 <= args.scale <= 3:
        parser.error("--scale must be between 0.5 and 3")
    os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_SCALE_FACTOR=str(args.scale))
    with tempfile.TemporaryDirectory(prefix="pixel-weather-motion-") as temporary:
        directory = Path(temporary)
        prepare(directory, args.light)
        runner = "/usr/lib/qt6/bin/qmltestrunner"
        result = subprocess.run([runner, "-input", str(directory / "tst_motion.qml"), "-import", str(directory)],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=65)
        (HERE / ("test-light.log" if args.light else "test.log")).write_text(result.stdout)
        print(result.stdout, end="")
        if result.returncode:
            raise SystemExit(result.returncode)
        if args.native:
            native_runtime(directory)
        if args.preview or args.video:
            preview(directory, args.video, args.light)


if __name__ == "__main__":
    main()
