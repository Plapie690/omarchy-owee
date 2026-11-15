#!/usr/bin/env python3
"""Exercise ForecastMap with actual Qt pointer/keyboard events and a local fake backend.

Every process runs in disposable XDG state; no network or installed plugin is used.
QtTest uses a deterministic Process transport double because Quickshell's Io
types are embedded in its executable. The unmodified component is separately
loaded by the project's real Quickshell runtime and render harnesses.

The button fixture supplies pointer, focus and keyboard transport only. Native
Omarchy button styling is checked separately with unmodified Quickshell controls.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

BACKEND = r'''import json, os, sys, time
from pathlib import Path
state = Path(os.environ['XDG_STATE_HOME'])
state.mkdir(parents=True, exist_ok=True)
cfgpath = state / 'settings.json'
cachepath = state / 'seen.json'
tracepath = state / 'trace.json'
def read(path, fallback):
    try: return json.loads(path.read_text())
    except (OSError, ValueError): return fallback
prefs = read(cfgpath, {'enabled':False,'zoom':6,'layer':'precipitation'})
action = sys.argv[1]
arg = json.loads(sys.argv[2]) if len(sys.argv)>2 else None
trace = read(tracepath, [])
trace.append({'action':action,'arg':arg})
tracepath.write_text(json.dumps(trace))
if action == 'settings':
    print(json.dumps({'settings':prefs})); sys.exit()
if action == 'configure':
    prefs.update(arg)
    cfgpath.write_text(json.dumps(prefs))
    if not prefs['enabled']: cachepath.write_text('{}')
    print(json.dumps({'settings':prefs})); sys.exit()
city = arg['city'] if action == 'frame' else arg
if action == 'frame': time.sleep(0.35)
base = int(os.environ['FORECAST_TEST_BASE'])
times = [base+i*3600 for i in range(4)]
selected = arg['time'] if action == 'frame' else times[0]
key = city['name'] + ':' + prefs['layer'] + ':' + str(prefs['zoom'])
seen = read(cachepath,{})
ready = seen.get(key,[])
if selected not in ready: ready.append(selected)
seen[key] = ready
cachepath.write_text(json.dumps(seen))
asset = Path(__file__).parent / 'map.svg'
overlay = Path(__file__).parent / 'overlay.svg'
legend = Path(__file__).parent / 'legend.svg'
frames = [{'time':stamp,'images':[{'left':0,'top':0,'width':432,'height':240,'source':overlay.as_uri()}] if stamp in ready else []} for stamp in times]
payload = {'settings':prefs,'width':432,'height':240,'provider':'ECCC GeoMet','model':'GDPS','resolution':'15 km',
           'title':{'precipitation':'1-hour precipitation','temperature':'Temperature at 2 m','clouds':'Clouds'}[prefs['layer']],
           'unit':{'precipitation':'mm / 1 h','temperature':'°C','clouds':'%'}[prefs['layer']],
           'layers':[{'id':'precipitation','title':'1-hour precipitation'},{'id':'temperature','title':'Temperature at 2 m'},{'id':'clouds','title':'Clouds'}],
           'tiles':[{'left':0,'top':0,'source':asset.as_uri()},{'left':256,'top':0,'source':asset.as_uri()}],
           'frames':frames,'selected_time':selected,'run_time':base-6*3600,'updated':time.time(),'stale':False,
           'legend':{'source':legend.as_uri(),'width':110,'height':405,'caption':'Valeurs du modèle : '+prefs['layer']},
           'request_trace':trace,'city_name':city['name']}
if city['name']=='Error' and action=='frame':
    payload['error']='Test connection unavailable'; payload['stale']=True
    for frame in payload['frames']:
        if frame['time']==selected: frame['images']=[]
print(json.dumps(payload))
'''


PROCESS = r'''import QtQuick
QtObject {
  id: process
  objectName: "forecast-worker-fixture"
  property var command: []
  property bool running: false
  property QtObject stdout: null
  property bool finishing: false
  property bool failNextConfig: false
  property var preferences: ({enabled:false,zoom:6,layer:"precipitation"})
  property var records: []
  property var cache: ({})
  property var snapshot: []
  property double baseEpoch: (Math.floor(Date.now()/3600000)+1)*3600
  signal exited(int exitCode,int exitStatus)
  onRunningChanged: {
    if (running) {
      snapshot=command.slice()
      var action=snapshot[3]
      var arg=snapshot.length>4?JSON.parse(snapshot[4]):null
      records=records.concat([{action:action,arg:arg}])
      timer.interval=action==="frame"?350:12
      timer.restart()
    } else if (!finishing) {
      timer.stop()
      Qt.callLater(function(){process.exited(-1,15)})
    }
  }
  function deliver() {
    var action=snapshot[3]
    var arg=snapshot.length>4?JSON.parse(snapshot[4]):null
    var response
    if (action==="settings") response={settings:preferences}
    else if (action==="configure") {
      if (failNextConfig) { failNextConfig=false; response={settings:preferences,error:"Enregistrement de test impossible"} }
      else {
        preferences=arg
        if (!arg.enabled) cache=({})
        response={settings:preferences}
      }
    } else {
      var city=action==="frame"?arg.city:arg
      var selected=action==="frame"?arg.time:baseEpoch
      var key=city.name+":"+preferences.layer+":"+preferences.zoom
      var ready=cache[key]||[]
      if (ready.indexOf(selected)<0) ready=ready.concat([selected])
      cache[key]=ready
      var frames=[]
      for(var i=0;i<4;i++) {
        var stamp=baseEpoch+i*3600
        frames.push({time:stamp,images:ready.indexOf(stamp)>=0?[{left:0,top:0,width:432,height:240,source:Qt.resolvedUrl("../plugin/overlay.svg").toString()}]:[]})
      }
      response={settings:preferences,width:432,height:240,provider:"ECCC GeoMet",model:"GDPS",resolution:"15 km",
                title:preferences.layer==="precipitation"?"1-hour precipitation":preferences.layer==="temperature"?"Temperature at 2 m":"Clouds",
                unit:preferences.layer==="precipitation"?"mm / 1 h":preferences.layer==="temperature"?"°C":"%",
                layers:[{id:"precipitation",title:"1-hour precipitation"},{id:"temperature",title:"Temperature at 2 m"},{id:"clouds",title:"Clouds"}],
                tiles:[{left:0,top:0,source:Qt.resolvedUrl("../plugin/map.svg").toString()},{left:256,top:0,source:Qt.resolvedUrl("../plugin/map.svg").toString()}],
                frames:frames,selected_time:selected,run_time:baseEpoch-6*3600,updated:Date.now()/1000,stale:false,
                legend:{source:Qt.resolvedUrl("../plugin/legend.svg").toString(),width:110,height:405,caption:"Valeurs du modèle : "+preferences.layer},
                request_trace:records,city_name:city.name}
      if (city.name==="Error"&&action==="frame") {
        response.error="Test connection unavailable";response.stale=true
        for(var j=0;j<frames.length;j++)if(frames[j].time===selected)frames[j].images=[]
      }
    }
    stdout.text=JSON.stringify(response)
    stdout.streamFinished()
    finishing=true
    running=false
    finishing=false
    exited(0,0)
  }
  property Timer timer: Timer { onTriggered:process.deliver() }
}
'''


BUTTON = r'''import QtQuick
import qs.Commons as Commons
Rectangle {
  id: button
  property string text: ""
  property real fontSize: 12
  property color foreground: Commons.Color.foreground
  property color background: "transparent"
  property bool selected: false
  property bool bordered: false
  property bool focusable: false
  signal clicked()
  implicitWidth: label.implicitWidth + 16
  implicitHeight: 36
  radius: Commons.Style.cornerRadius
  color: selected ? "#35466c" : background
  border.width: bordered || activeFocus ? 1 : 0
  border.color: activeFocus ? Commons.Color.accent : "#66708a"
  activeFocusOnTab: focusable
  Text {
    id: label
    anchors.centerIn: parent
    textFormat: Text.PlainText
    text: button.text
    color: button.foreground
    font.pixelSize: button.fontSize
  }
  MouseArea {
    anchors.fill: parent
    onClicked: { if (button.focusable) button.forceActiveFocus(); button.clicked() }
  }
  Keys.onReturnPressed: if (focusable) clicked()
  Keys.onEnterPressed: if (focusable) clicked()
  Keys.onSpacePressed: if (focusable) clicked()
}
'''


def prepare(base, fake_io=False):
    plugin = base / "plugin"
    plugin.mkdir()
    source = ROOT
    for name in ("ForecastMap.qml", "PText.qml"):
        shutil.copy2(source / name, plugin / name)
    if fake_io:
        qml=plugin / "ForecastMap.qml"
        qml.write_text(qml.read_text().replace('import Quickshell.Io','import "../fakeio" as FakeIo').replace('  Process {','  FakeIo.Process {').replace('stdout: StdioCollector {','stdout: FakeIo.StdioCollector {'))
        io=base / "fakeio"
        io.mkdir()
        (io / "Process.qml").write_text(PROCESS)
        (io / "StdioCollector.qml").write_text('import QtQuick\nQtObject { property string text:""; property bool waitForEnd:false; signal streamFinished() }\n')
    (plugin / "forecast_map.py").write_text(BACKEND)
    (plugin / "map.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#e7eee9"/><path d="M0 180L256 80M60 0L180 256" stroke="white" stroke-width="12"/></svg>')
    (plugin / "overlay.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="432" height="240"><ellipse cx="220" cy="100" rx="90" ry="140" fill="#349be0" opacity=".5"/><ellipse cx="210" cy="110" rx="35" ry="85" fill="#6334d9" opacity=".4"/></svg>')
    (plugin / "legend.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="110" height="405"><rect width="110" height="405" fill="white"/><rect x="12" y="20" width="25" height="360" fill="#349be0"/><text x="48" y="28" font-size="14">100</text><text x="48" y="385" font-size="14">0</text></svg>')
    commons = base / "imports/qs/Commons"
    commons.mkdir(parents=True)
    (commons / "qmldir").write_text("module qs.Commons\nsingleton Color 1.0 Color.qml\nsingleton Style 1.0 Style.qml\nsingleton Util 1.0 Util.qml\nsingleton I18n 1.0 I18n.qml\n")
    (commons / "Color.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { property color foreground:"#dce1f0"; property color background:"#191c27"; property color accent:"#8cabf5" }\n')
    (commons / "Style.qml").write_text('''pragma Singleton
import QtQuick
QtObject {
  property string fontFamily: "Sans"
  property bool animations: true
  property int cornerRadius: 0
  readonly property QtObject font: QtObject {
    readonly property int bodySmall: 11
    readonly property int body: 12
    readonly property int title: 14
  }
  function space(value) { return value }
  function duration(value) { return animations ? value : 0 }
  function normalFillFor(foreground, accent) { return Qt.rgba(foreground.r, foreground.g, foreground.b, 0.075) }
}
''')
    (commons / "Util.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { function readingKey(event) { return event.key } }\n')
    (commons / "I18n.qml").write_text('pragma Singleton\nimport QtQuick\nQtObject { property string formatLocale:"fr-FR" }\n')
    if fake_io:
        ui = base / "imports/qs/Ui"
        ui.mkdir(parents=True)
        (ui / "qmldir").write_text("module qs.Ui\nButton 1.0 Button.qml\n")
        (ui / "Button.qml").write_text(BUTTON)
    return plugin


def main():
    with tempfile.TemporaryDirectory(prefix="pixel-weather-forecast-qa-") as tmp:
        base = Path(tmp)
        prepare(base, fake_io=True)
        shutil.copy2(HERE / "tst_forecast.qml", base / "tst_forecast.qml")
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="", QT_QUICK_CONTROLS_STYLE="Basic", QT_QUICK_BACKEND="software", XDG_STATE_HOME=str(base / "state"),
                   XDG_RUNTIME_DIR=str(base / "runtime"), FORECAST_TEST_BASE=str((int(time.time())//3600+1)*3600))
        Path(env['XDG_RUNTIME_DIR']).mkdir(mode=0o700)
        result = subprocess.run(["/usr/lib/qt6/bin/qmltestrunner", "-input", str(base), "-import", str(base / "imports"), "-o", "-,txt"],
                                env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=55)
        (HERE / "test.log").write_text(result.stdout)
        print(result.stdout, end="")
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
