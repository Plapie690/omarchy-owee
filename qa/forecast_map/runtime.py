#!/usr/bin/env python3
"""Check ForecastMap's real Quickshell Process lifecycle with a local backend.

No pointer is injected into the desktop and the test window stays offscreen.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import time

from run import HERE, prepare

QML = '''import QtQuick
import QtQuick.Window
import Quickshell
import "plugin" as Weather
ShellRoot {
  Window {
    id:window
    visible:true; width:460; height:1200
    Loader { id:control; width:432; source:Qt.resolvedUrl("plugin/ForecastMap.qml") }
    property int stage:0
    property int ticks:0
    property int closedAt:0
    Timer {
      interval:40; repeat:true; running:true
      onTriggered: {
        window.ticks++
        if(window.ticks>250) { console.error("QA_FAIL: real Process test timed out",window.stage);Qt.exit(1);return }
        var map=control.item
        if(!map||!map.settingsLoaded)return
        if(window.stage===0) {
          if(map.forecastEnabled||map.frames.length) { console.error("QA_FAIL: disabled map loaded forecast");Qt.exit(1);return }
          map.city={name:"Lyon",latitude:45.75,longitude:4.85};map.active=true
          map.configure({enabled:true});window.stage=1
        } else if(window.stage===1&&!map.busy&&map.imageReady) {
          if(map.frames.length!==4||map.frames.filter(function(f){return f.images.length>0}).length!==1) { console.error("QA_FAIL: preload detected");Qt.exit(1);return }
          map.step(1);window.stage=2
        } else if(window.stage===2&&map.busy) {
          map.configure({layer:"temperature"});map.configure({layer:"clouds"})
          map.city={name:"Paris",latitude:48.85,longitude:2.35};window.stage=3
        } else if(window.stage===3&&!map.busy&&map.imageReady&&map.forecast.city_name==="Paris") {
          if(map.selectedLayer!=="clouds"||map.forecast.settings.layer!=="clouds") { console.error("QA_FAIL: superseded settings response won");Qt.exit(1);return }
          map.selectFrame(1,true,true);map.playing=true;window.stage=4
        } else if(window.stage===4&&map.busy) {
          map.active=false;window.closedAt=window.ticks;window.stage=5
        } else if(window.stage===5&&window.ticks-window.closedAt>15) {
          if(map.busy||map.playing||map.queuedFrame||map.loadRequested) { console.error("QA_FAIL: hidden map is still working");Qt.exit(1);return }
          console.warn("QA_FORECAST_PROCESS_PASS: real Process cancellation, latest city/layer and no preloading")
          Qt.quit()
        }
      }
    }
  }
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix="pixel-weather-forecast-runtime-") as tmp:
        base = Path(tmp)
        prepare(base)
        shell = Path("/usr/share/omarchy/shell")
        for directory in ("Commons", "Ui", "services"):
            (base / directory).symlink_to(shell / directory, target_is_directory=True)
        (base / "shell.qml").write_text(QML)
        runtime = base / "runtime"
        runtime.mkdir(mode=0o700)
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="", QT_QUICK_CONTROLS_STYLE="Basic", QT_QUICK_BACKEND="software",
                   XDG_STATE_HOME=str(base / "state"), XDG_RUNTIME_DIR=str(runtime), XDG_CACHE_HOME=str(base / "cache"),
                   FORECAST_TEST_BASE=str((int(time.time())//3600+1)*3600))
        output_path = HERE / "runtime.log"
        with output_path.open("w") as output:
            result = subprocess.run(["quickshell", "--no-color", "-p", str(base)], env=env, text=True,
                                    stdout=output, stderr=subprocess.STDOUT, timeout=20, start_new_session=True)
        output = output_path.read_text()
        print(output, end="")
        if result.returncode or "QA_FORECAST_PROCESS_PASS" not in output or any(word in output for word in ("QA_FAIL", "ERROR", "WARN scene:")):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
