import QtQuick
import QtQuick.Shapes
import qs.Commons as Commons
import "WeatherModel.js" as WeatherModel

// Compact weather illustration derived from the local WMO condition.
Item {
  id: sky
  property var code: null
  property bool night: false
  property color ink: Commons.Color.foreground
  property color accent: Commons.Color.accent
  property bool active: false
  property int openingSerial: 0
  // A negative value retains standalone use; panel sections share one clock.
  property real openingProgress: -1
  readonly property bool sharedOpening: isFinite(openingProgress) && openingProgress >= 0
  readonly property string condition: WeatherModel.family(code)
  readonly property bool motionEnabled: Commons.Style.duration(1) > 0
  readonly property bool openingRunning: sharedOpening ? active && motionEnabled && condition !== "unknown" && openingProgress < 1 : introduction.running
  readonly property bool motionRunning: introduction.running || drift.running || precipitation.running || conditionFade.running
  readonly property bool hasCloud: condition !== "clear" && condition !== "unknown"
  readonly property bool hasCelestial: condition === "clear" || condition === "mostlyClear" || condition === "partlyCloudy"
  readonly property bool wet: condition === "rain" || condition === "storm"
  readonly property bool snowy: condition === "snow"
  property real entrance: 1
  property real phase: 0
  property real fallPhase: 0
  property real sceneOpacity: 1
  property int playedSerial: -1
  property bool ready: false
  readonly property real wave: Math.sin(phase * Math.PI * 2)
  readonly property real swell: Math.cos(phase * Math.PI * 2)
  implicitWidth: 160
  implicitHeight: 128

  function reveal(delay) { return Math.max(0, Math.min(1, (entrance - delay) / (1 - delay))) }
  function synchronize() {
    if (!ready) return
    if (!active || !motionEnabled || condition === "unknown") {
      introduction.stop(); drift.stop(); precipitation.stop(); conditionFade.stop()
      entrance = 1; sceneOpacity = 1
      // Preserve a natural, fully populated static illustration when motion is off.
      phase = 0; fallPhase = 0.25
      // Disabled motion consumes this opening; re-enabling does not replay it.
      if (active && !motionEnabled) playedSerial = openingSerial
      return
    }
    if (!drift.running) drift.start()
    if ((wet || snowy) && !precipitation.running) precipitation.start()
    if (!wet && !snowy) precipitation.stop()
    if (sharedOpening) {
      introduction.stop()
      playedSerial = openingSerial
      entrance = Math.max(0, Math.min(1, openingProgress))
    } else if (playedSerial !== openingSerial) {
      playedSerial = openingSerial
      entrance = 0
      introduction.restart()
    }
  }
  function changeCondition() {
    if (!ready) return
    if (active && motionEnabled && playedSerial === openingSerial) {
      sceneOpacity = 0.35
      conditionFade.restart()
    }
    synchronize()
  }
  onActiveChanged: synchronize()
  onOpeningSerialChanged: synchronize()
  onOpeningProgressChanged: synchronize()
  onMotionEnabledChanged: synchronize()
  onConditionChanged: changeCondition()
  onNightChanged: changeCondition()
  Component.onCompleted: { ready = true; synchronize() }
  Component.onDestruction: { introduction.stop(); drift.stop(); precipitation.stop(); conditionFade.stop() }

  NumberAnimation {
    id: introduction
    target: sky; property: "entrance"; from: 0; to: 1
    duration: Commons.Style.duration(220); easing.type: Easing.OutCubic
  }
  NumberAnimation {
    id: drift
    target: sky; property: "phase"; from: 0; to: 1
    duration: Commons.Style.duration(6400); loops: Animation.Infinite; easing.type: Easing.Linear
  }
  NumberAnimation {
    id: precipitation
    target: sky; property: "fallPhase"; from: 0; to: 1
    duration: Commons.Style.duration(sky.snowy ? 3600 : 1500)
    loops: Animation.Infinite; easing.type: Easing.Linear
  }
  NumberAnimation {
    id: conditionFade
    target: sky; property: "sceneOpacity"; to: 1
    duration: Commons.Style.duration(220); easing.type: Easing.OutCubic
  }

  component CloudShape: Shape {
    id: silhouette
    property color fill: sky.ink
    width: 160; height: 110
    preferredRendererType: Shape.CurveRenderer
    ShapePath {
      strokeWidth: 0; fillColor: silhouette.fill
      startX: 57; startY: 79
      PathCubic { x: 51; y: 43; control1X: 31; control1Y: 79; control2X: 31; control2Y: 44 }
      PathCubic { x: 103; y: 45; control1X: 56; control1Y: 19; control2X: 95; control2Y: 21 }
      PathCubic { x: 109; y: 79; control1X: 131; control1Y: 39; control2X: 138; control2Y: 79 }
      PathLine { x: 57; y: 79 }
    }
  }

  Item {
    id: scene
    width: 160; height: 128
    anchors.centerIn: parent
    scale: Math.min(sky.width / width, sky.height / height)
    opacity: sky.sceneOpacity

    // A quiet atmospheric halo gives the moving layers a common centre.
    Rectangle {
      visible: sky.condition !== "unknown"
      x: 25; y: 12; width: 108; height: 108; radius: 54
      color: sky.accent
      opacity: 0.075 * sky.reveal(0)
      scale: 0.94 + 0.035 * sky.swell
    }
    Rectangle {
      visible: sky.hasCelestial
      x: 33; y: 20; width: 92; height: 92; radius: 46
      color: "transparent"; border.width: 1; border.color: sky.accent
      opacity: 0.12 * sky.entrance
      scale: 1 + 0.04 * sky.wave
    }

    Item {
      id: celestial
      visible: sky.hasCelestial
      x: sky.condition === "clear" ? 79 : 102
      y: (sky.condition === "clear" ? 61 : 42) + 3 * sky.wave + 18 * (1 - sky.reveal(0))
      opacity: sky.reveal(0)
      rotation: sky.night ? -18 * (1 - sky.entrance) + 5 * sky.swell : 0
      scale: 0.86 + 0.14 * sky.entrance
      Rectangle {
        visible: !sky.night
        x: -22; y: -22; width: 44; height: 44; radius: 22
        gradient: Gradient {
          GradientStop { position: 0; color: Qt.lighter(sky.accent, 1.22) }
          GradientStop { position: 1; color: sky.accent }
        }
      }
      Item {
        visible: !sky.night
        rotation: sky.phase * 90 - (1 - sky.entrance) * 260
        Repeater {
          model: 8
          Item {
            required property int index
            rotation: index * 45
            Rectangle {
              x: -1.8; y: -37 - 1.5 * sky.wave
              width: 3.6; height: 9; radius: 1.8; color: sky.accent
            }
          }
        }
      }
      // A crescent path leaves a true transparent cutout on every theme.
      Shape {
        preferredRendererType: Shape.CurveRenderer
        visible: sky.night
        x: -26; y: -26; width: 52; height: 52
        scale: 1.1
        ShapePath {
          strokeWidth: 0; fillColor: sky.accent
          startX: 35; startY: 4
          PathCubic { x: 41; y: 42; control1X: 2; control1Y: -3; control2X: -2; control2Y: 43 }
          PathCubic { x: 35; y: 4; control1X: 18; control1Y: 38; control2X: 16; control2Y: 16 }
        }
      }
    }

    Repeater {
      model: 4
      Rectangle {
        required property int index
        readonly property real twinkle: (1 + Math.sin(sky.phase * Math.PI * 4 + index * 1.8)) / 2
        visible: sky.night && sky.hasCelestial
        x: [32, 122, 112, 44][index]
        y: [31, 72, 19, 96][index] - 2 * sky.wave
        width: index % 2 === 0 ? 5 : 3; height: width; radius: 0.8
        rotation: 45
        scale: 0.7 + twinkle * 0.5
        color: sky.accent
        opacity: (0.25 + twinkle * 0.65) * sky.reveal(0.12)
      }
    }

    // Rear cloud drifts in the opposite direction to the foreground cloud.
    CloudShape {
      visible: sky.hasCloud
      x: -13 - 9 * sky.wave - 32 * (1 - sky.reveal(0.08))
      y: -12 + 2 * sky.swell
      scale: sky.condition === "mostlyClear" ? 0.55 : 0.73
      fill: Qt.tint(sky.ink, Qt.rgba(sky.accent.r, sky.accent.g, sky.accent.b, 0.35))
      opacity: 0.52 * sky.reveal(0.08)
    }

    // Precipitation sits behind the front cloud, so particles emerge naturally.
    Item {
      x: 40 + 8 * sky.wave; y: 72; width: 88; height: 49
      clip: true
      visible: sky.wet || sky.snowy
      opacity: sky.reveal(0.25)
      Repeater {
        model: 9
        Rectangle {
          required property int index
          readonly property real travel: (sky.fallPhase + index * 0.137) % 1
          x: 6 + (index % 4) * 20 + (sky.snowy ? 5 * Math.sin(travel * 6.28 + index) : -travel * 9)
          y: travel * 60 - 8
          width: sky.snowy ? 4 : 2.6
          height: sky.snowy ? 4 : 11
          radius: width / 2
          rotation: sky.snowy ? 45 : 18
          color: sky.accent
          opacity: Math.min(1, travel * 6, (1 - travel) * 5) * (index % 3 === 0 ? 0.55 : 0.9)
        }
      }
    }

    CloudShape {
      id: frontCloud
      objectName: "weather-front-cloud"
      visible: sky.hasCloud
      x: 9 + 12 * sky.wave + 44 * (1 - sky.reveal(0.17))
      y: (sky.condition === "mostlyClear" ? 18 : 8) + 4 * sky.swell + 7 * (1 - sky.entrance)
      scale: (sky.condition === "mostlyClear" ? 0.75 : 0.97) * (0.9 + sky.reveal(0.17) * 0.1)
      opacity: sky.reveal(0.17)
      fill: sky.ink
    }

    Repeater {
      model: 3
      Rectangle {
        required property int index
        visible: sky.condition === "fog"
        x: 29 + index * 10 + 10 * Math.sin(sky.phase * 2 * Math.PI + index * 0.8)
        y: 91 + index * 8
        width: 87 - index * 17; height: 3.5; radius: 1.75
        color: sky.accent
        opacity: sky.reveal(0.22) * (0.68 - index * 0.12)
      }
    }

    Shape {
      preferredRendererType: Shape.CurveRenderer
      visible: sky.condition === "storm"
      x: 81 + 8 * sky.wave; y: 78; width: 27; height: 38
      scale: 0.94 + 0.06 * sky.swell
      opacity: sky.reveal(0.28) * (0.5 + 0.4 * Math.pow(Math.max(0, Math.cos(sky.phase * Math.PI * 4)), 4))
      ShapePath {
        fillColor: sky.accent; strokeWidth: 0
        startX: 16; startY: 0
        PathLine { x: 2; y: 21 }
        PathLine { x: 13; y: 21 }
        PathLine { x: 8; y: 36 }
        PathLine { x: 27; y: 13 }
        PathLine { x: 16; y: 13 }
        PathLine { x: 16; y: 0 }
      }
    }

    Rectangle {
      visible: sky.condition === "unknown"
      x: 60; y: 44; width: 40; height: 40; radius: 20
      color: "transparent"; border.width: 2; border.color: sky.ink; opacity: 0.5
      Rectangle { anchors.centerIn: parent; width: 12; height: 2; radius: 1; color: sky.ink }
    }
  }
}
