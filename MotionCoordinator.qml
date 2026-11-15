import QtQuick
import qs.Commons as Commons

// One opening clock for the entire panel; native Omarchy owns the panel exit.
QtObject {
  id: root
  property bool active: false
  property int openingSerial: 0
  readonly property real progress: _progress
  readonly property bool running: opening.running
  readonly property bool motionAllowed: Commons.Style.duration(1) > 0
  readonly property int duration: Math.max(0, Math.min(240, Commons.Style.duration(220)))
  property real _progress: 1
  property bool _ready: false

  function finish() { opening.stop(); _progress = 1 }
  function restart() {
    if (!_ready) return
    opening.stop()
    if (!active || !motionAllowed || duration === 0) { _progress = 1; return }
    _progress = 0
    opening.restart()
  }
  onActiveChanged: if (active) restart(); else finish()
  onOpeningSerialChanged: restart()
  onMotionAllowedChanged: if (!motionAllowed) finish()
  Component.onCompleted: { _ready = true; restart() }
  Component.onDestruction: opening.stop()

  property NumberAnimation _opening: NumberAnimation {
    id: opening
    target: root; property: "_progress"; from: 0; to: 1
    duration: root.duration
    easing.type: Easing.OutCubic
  }
}
