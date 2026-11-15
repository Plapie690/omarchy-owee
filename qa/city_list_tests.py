#!/usr/bin/env python3
"""Exercise the unchanged CityList with real pointer/key events in an isolated Qt view.

Commons colors/fonts are fixtures; full Omarchy imports are separately checked by
runtime_qml.py. No backend, network, user-state write or visible desktop window.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from runtime_qml import ROOT


QML = '''import QtQuick
import QtTest
import "plugin" as Weather

Item {
  width: 460; height: 350
  readonly property var lyon: ({name:"Lyon",latitude:45.75,longitude:4.85})
  readonly property var paris: ({name:"Paris",latitude:48.85,longitude:2.35})
  readonly property var nice: ({name:"Nice",latitude:43.7,longitude:7.25})
  Weather.CityList { id: cities; x: 10; y: 10; width: 440 }
  SignalSpy { id: selected; target: cities; signalName: "selected" }
  SignalSpy { id: primary; target: cities; signalName: "primaryRequested" }
  SignalSpy { id: moved; target: cities; signalName: "moveRequested" }
  SignalSpy { id: removed; target: cities; signalName: "removeRequested" }
  TestCase {
    name: "PrimaryCityChooser"
    when: windowShown
    function init() {
      cities.cities = [lyon,paris,nice]
      cities.currentCity = paris
      cities.primaryCity = lyon
      cities.busy = false
      wait(20)
      selected.clear(); primary.clear(); moved.clear(); removed.clear()
    }
    function row(name) {
      for (var i=0;i<cities.children.length;i++) {
        var item = cities.children[i]
        if (item.modelData && item.modelData.name === name) return item
      }
      fail("No city row: " + name)
    }
    function button(item,label) {
      if (item.label === label) return item
      for (var i=0;item.children && i<item.children.length;i++) {
        var found = button(item.children[i],label)
        if (found) return found
      }
      return null
    }
    function click(item) { verify(item !== null); mouseClick(item,item.width/2,item.height/2) }
    function test_consult_city_preserves_primary_selection() {
      var target = row("Nice")
      mouseClick(target,24,target.height/2)
      compare(selected.count,1)
      compare(selected.signalArguments[0][0].name,"Nice")
      compare(primary.count,0)
      compare(cities.primaryCity.name,"Lyon")
    }
    function test_star_only_changes_primary_and_uses_correct_coordinates() {
      click(button(row("Paris"),"☆"))
      compare(primary.count,1)
      compare(primary.signalArguments[0][0],"48.85000,2.35000")
      compare(selected.count,0)
      compare(removed.count,0)
      click(button(row("Lyon"),"★"))
      compare(primary.count,1)
    }
    function test_keyboard_star_and_row_selection() {
      var star = button(row("Paris"),"☆")
      star.forceActiveFocus()
      keyClick(Qt.Key_Space)
      compare(primary.count,1)
      compare(primary.signalArguments[0][0],"48.85000,2.35000")
      var selection = row("Nice").children[0]
      selection.forceActiveFocus()
      keyClick(Qt.Key_Return)
      compare(selected.count,1)
      compare(selected.signalArguments[0][0].name,"Nice")
    }
    function test_move_bounds_and_remove_signal() {
      click(button(row("Lyon"),"↑"))
      click(button(row("Nice"),"↓"))
      compare(moved.count,0)
      click(button(row("Paris"),"↑"))
      compare(moved.count,1)
      compare(moved.signalArguments[0][0],"48.85000,2.35000")
      compare(moved.signalArguments[0][1],"up")
      click(button(row("Nice"),"×"))
      compare(removed.count,1)
      compare(removed.signalArguments[0][0],"43.70000,7.25000")
      compare(selected.count,0)
    }
    function test_busy_disables_pointer_actions() {
      cities.busy = true
      var target = row("Paris")
      mouseClick(target,20,target.height/2)
      click(button(target,"☆")); click(button(target,"↑")); click(button(target,"×"))
      compare(selected.count,0); compare(primary.count,0); compare(moved.count,0); compare(removed.count,0)
    }
    function test_last_city_cannot_be_removed() {
      cities.cities = [lyon]
      wait(20)
      click(button(row("Lyon"),"×"))
      compare(removed.count,0)
    }
  }
}
'''


def main():
    runner = Path("/usr/lib/qt6/bin/qmltestrunner")
    if not runner.exists():
        raise SystemExit("Qt6 qmltestrunner is required")
    with tempfile.TemporaryDirectory(prefix="pixel-weather-city-qa-") as tmp:
        base = Path(tmp)
        plugin = base / "plugin"
        plugin.mkdir()
        for name in ("CityList.qml", "PText.qml"):
            shutil.copy2(ROOT / name, plugin / name)
        commons = base / "imports/qs/Commons"
        commons.mkdir(parents=True)
        (commons / "qmldir").write_text("module qs.Commons\nsingleton Color 1.0 Color.qml\nsingleton Style 1.0 Style.qml\n")
        (commons / "Color.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { property color foreground: "#eeeeee"; property color background: "#181a20"; property color accent: "#88aaff" }\n')
        (commons / "Style.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { property string fontFamily: "sans-serif"; property int cornerRadius:0; property QtObject font: QtObject { property int body:12; property int bodySmall:11; property int subtitle:14 }; function space(n) { return n } }\n')
        (base / "tst_citylist.qml").write_text(QML)
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", XDG_STATE_HOME=str(base / "state"))
        result = subprocess.run([str(runner), "-input", str(base), "-import", str(base / "imports"), "-o", "-,txt"], env=env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        (ROOT / "qa/city-list-tests.log").write_text(result.stdout)
        print(result.stdout, end="")
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
