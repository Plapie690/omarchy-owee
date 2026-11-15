import QtQuick
import QtQuick.Shapes
import qs.Commons as Commons
import "WeatherModel.js" as WeatherModel

// Horizon: weather first, with asymmetric curves and a bevelled cloud baseline.
// The weather silhouette itself is the mark; there is no enclosing badge.
Item {
  id: mark
  property var code: null
  property bool night: false
  property color ink: Commons.Color.foreground
  readonly property string family: WeatherModel.family(code)
  readonly property bool mixed: family === "mostlyClear" || family === "partlyCloudy"
  readonly property bool compactCloud: ["rain", "snow", "storm", "fog"].indexOf(family) >= 0
  readonly property bool hasCloud: family !== "clear" && family !== "unknown"
  implicitWidth: 24
  implicitHeight: 24
  width: 24; height: 24

  // Clear sky uses the complete sun or crescent, not a small detail in a logo.
  Shape {
    anchors.fill: parent
    preferredRendererType: Shape.CurveRenderer
    visible: mark.family === "clear" && !mark.night
    ShapePath {
      fillColor: mark.ink; strokeColor: "transparent"; strokeWidth: 0
      PathSvg { path: "M16.2 12 A4.2 4.2 0 1 1 7.8 12 A4.2 4.2 0 1 1 16.2 12 Z" }
    }
    ShapePath {
      fillColor: "transparent"; strokeColor: mark.ink; strokeWidth: 1.9
      capStyle: ShapePath.RoundCap
      PathSvg { path: "M12 2 L12 4 M12 20 L12 22 M2 12 L4 12 M20 12 L22 12 M4.7 4.7 L6.3 6.3 M17.7 17.7 L19.3 19.3 M4.7 19.3 L6.3 17.7 M17.7 6.3 L19.3 4.7" }
    }
  }
  Shape {
    anchors.fill: parent
    preferredRendererType: Shape.CurveRenderer
    visible: mark.family === "clear" && mark.night
    ShapePath {
      fillColor: mark.ink; strokeColor: "transparent"; strokeWidth: 0
      PathSvg { path: "M16.5 2.5 C7 -0.2 0.5 10 6.4 17.6 C10.8 23.3 19.4 21 21.5 15.2 C12.5 18.3 8.5 8.2 16.5 2.5 Z" }
    }
    ShapePath {
      fillColor: mark.ink; strokeWidth: 0
      PathSvg { path: "M20 3 L22 5 L20 7 L18 5 Z" }
    }
  }

  // Only the exposed crown is drawn behind the cloud, so no rays cross it.
  Shape {
    anchors.fill: parent
    preferredRendererType: Shape.CurveRenderer
    visible: mark.mixed
    ShapePath {
      fillColor: mark.night ? mark.ink : "transparent"
      strokeColor: mark.ink; strokeWidth: mark.night ? 0 : 1.9
      capStyle: ShapePath.RoundCap
      PathSvg {
        path: mark.night
          ? (mark.family === "mostlyClear"
             ? "M18 2.1 C11.8 0.5 9.3 6.5 12.9 10.5 L16 11.5 L20.7 8.7 C15 9.2 14.6 4.7 18 2.1 Z"
             : "M18 1.5 C14 0.5 11.7 1.8 11.3 4.1 C12.3 4.1 13.3 4.2 14.4 4.9 C14.8 3.6 16.1 2.3 18 1.5 Z")
          : (mark.family === "mostlyClear"
             ? "M20.2 7 A4.2 4.2 0 1 1 11.8 7 A4.2 4.2 0 1 1 20.2 7 M16 0.9 L16 1.6 M21.7 2 L21 2.9 M23 6.5 L22 6.5"
             : "M14.5 3.6 C17 1.6 20.7 3.5 20.7 6.5 L20.7 7.1 M16 0.9 L16 1.6 M21.7 2 L21 2.9 M23 6.5 L22 6.5")
      }
    }
  }
  Shape {
    width: 24; height: 24
    preferredRendererType: Shape.CurveRenderer
    visible: mark.hasCloud
    x: mark.family === "mostlyClear" ? -0.4 : 0
    y: mark.family === "mostlyClear" ? 0.5 : 0
    scale: mark.family === "mostlyClear" ? 0.72 : 1
    transformOrigin: Item.BottomLeft
    transform: Scale { yScale: mark.compactCloud ? 0.72 : 1 }
    ShapePath {
      fillColor: "transparent"; strokeColor: mark.ink; strokeWidth: 2.05
      capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
      // Broad cloud, high asymmetric crown, and a closed diagonal heel.
      PathSvg { path: "M6.2 18.4 C0.6 18.4 0.5 10.3 6.1 9.5 C6.4 2.8 15.1 2 17.8 8.9 C23.6 8.1 25 16.7 19.6 17.4 L18.6 18.4 Z" }
    }
  }
  Shape {
    anchors.fill: parent
    preferredRendererType: Shape.CurveRenderer
    visible: mark.family === "rain"
    ShapePath {
      fillColor: "transparent"; strokeColor: mark.ink; strokeWidth: 1.9
      capStyle: ShapePath.RoundCap
      PathSvg { path: "M7 17.5 L5.5 21.5 M13 17.5 L11.5 21.5 M19 17.5 L17.5 21.5" }
    }
  }
  Shape {
    anchors.fill: parent
    preferredRendererType: Shape.CurveRenderer
    visible: mark.family === "snow"
    ShapePath {
      fillColor: "transparent"; strokeColor: mark.ink; strokeWidth: 1.7
      capStyle: ShapePath.RoundCap
      PathSvg { path: "M12 16 L12 22.7 M9.1 17.7 L14.9 21 M9.1 21 L14.9 17.7" }
    }
  }
  Shape {
    anchors.fill: parent
    preferredRendererType: Shape.CurveRenderer
    visible: mark.family === "storm"
    ShapePath {
      fillColor: mark.ink; strokeColor: "transparent"; strokeWidth: 0
      PathSvg { path: "M13.6 14.7 L8.1 20 L11.8 20 L10 23.5 L17.4 17.8 L13.5 17.8 L15.2 14.7 Z" }
    }
  }
  Shape {
    anchors.fill: parent
    preferredRendererType: Shape.CurveRenderer
    visible: mark.family === "fog"
    ShapePath {
      fillColor: "transparent"; strokeColor: mark.ink; strokeWidth: 1.8
      capStyle: ShapePath.RoundCap
      PathSvg { path: "M3.8 16.7 L20.2 16.7 M6.5 20 L17.5 20 M9 23 L15 23" }
    }
  }
  Shape {
    anchors.fill: parent
    preferredRendererType: Shape.CurveRenderer
    visible: mark.family === "unknown"
    ShapePath {
      fillColor: "transparent"; strokeColor: mark.ink; strokeWidth: 1.9
      capStyle: ShapePath.RoundCap
      PathSvg { path: "M21 12 A9 9 0 1 1 3 12 A9 9 0 1 1 21 12 Z M8.5 12 L15.5 12" }
    }
  }
}
