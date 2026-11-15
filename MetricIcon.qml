import QtQuick
import QtQuick.Shapes
import qs.Commons as Commons

// One optical grid and stroke weight for measurements and panel actions.
Item {
  id: icon
  property string kind: ""
  property color ink: Commons.Color.foreground
  implicitWidth: 20
  implicitHeight: 20
  readonly property var paths: ({
    wind: "M3 7 H15 C20 7 20 2 16 2 M3 12 H20 C24 12 24 17 20 17 M3 17 H11 C16 17 16 22 12 22",
    humidity: "M12 2 C10 6 5 11 5 15 A7 7 0 0 0 19 15 C19 11 14 6 12 2 Z M8 15 Q8 19 12 19",
    uv: "M16 12 A4 4 0 1 1 8 12 A4 4 0 1 1 16 12 M12 2 V4 M12 20 V22 M2 12 H4 M20 12 H22 M5 5 L7 7 M17 17 L19 19 M5 19 L7 17 M17 7 L19 5",
    sun: "M5 16 A7 7 0 0 1 19 16 M2 19 H22 M12 2 V5 M3 7 L5 9 M21 7 L19 9 M2 14 H4 M20 14 H22",
    pressure: "M4 19 A10 10 0 1 1 20 19 M7 8 L8 9 M12 5 V7 M17 8 L16 9 M12 15 L17 10 M14 15 A2 2 0 1 1 10 15 A2 2 0 1 1 14 15",
    visibility: "M2 12 C7 3 17 3 22 12 C17 21 7 21 2 12 Z M15 12 A3 3 0 1 1 9 12 A3 3 0 1 1 15 12",
    precipitation: "M8 3 C6 7 3 10 3 13 A5 5 0 0 0 13 13 C13 10 10 7 8 3 Z M18 8 C16 11 14 14 14 17 A4 4 0 0 0 22 17 C22 14 20 11 18 8 Z",
    air: "M2 6 H15 M5 11 H22 M2 16 H18 M7 21 H22",
    pollen: "M12 8 C4 -1 0 9 8 12 C-1 20 10 25 12 16 C18 25 25 15 16 12 C25 4 15 -1 12 8 Z M14 12 A2 2 0 1 1 10 12 A2 2 0 1 1 14 12",
    settings: "M9 2 H15 L16 6 L20 7 L22 11 L19 14 L19 18 L15 21 L12 19 L8 21 L4 18 L5 14 L2 11 L4 7 L8 6 Z M16 12 A4 4 0 1 1 8 12 A4 4 0 1 1 16 12",
    refresh: "M20 8 A9 9 0 1 0 21 16 M20 2 V8 H14",
    location: "M12 22 C8 17 4 13 4 9 A8 8 0 1 1 20 9 C20 13 16 17 12 22 Z M15 9 A3 3 0 1 1 9 9 A3 3 0 1 1 15 9"
  })
  Shape {
    width: 24; height: 24
    scale: Math.min(icon.width, icon.height) / 24
    transformOrigin: Item.TopLeft
    preferredRendererType: Shape.CurveRenderer
    ShapePath {
      fillColor: "transparent"; strokeColor: icon.ink; strokeWidth: 1.7
      capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
      PathSvg { path: icon.paths[icon.kind] || "M5 12 H19" }
    }
  }
}
