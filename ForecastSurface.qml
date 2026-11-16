import QtQuick
import qs.Commons as Commons

// A quiet, theme-derived surface shared by both forecast sections.
Rectangle {
  id: root
  default property alias contentData: body.data
  property alias spacing: body.spacing
  readonly property alias contentItem: body
  readonly property real contentInset: Commons.Style.space(12)
  readonly property color surfaceColor: Qt.tint(Commons.Color.background,
    Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.065))
  implicitHeight: body.implicitHeight + contentInset * 2
  height: implicitHeight
  radius: Commons.Style.cornerRadius
  color: surfaceColor
  border.width: 1
  border.color: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.055)
  gradient: Gradient {
    GradientStop {
      position: 0
      color: Qt.tint(root.surfaceColor,
        Qt.rgba(Commons.Color.accent.r, Commons.Color.accent.g, Commons.Color.accent.b, 0.035))
    }
    GradientStop { position: 1; color: root.surfaceColor }
  }

  property Column _body: Column {
    id: body
    parent: root
    x: root.contentInset
    y: root.contentInset
    width: Math.max(0, root.width - root.contentInset * 2)
  }
}
