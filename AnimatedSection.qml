import QtQuick
import qs.Commons as Commons

// All section movement is derived from the coordinator, never from a local timer.
Item {
  id: root
  property real progress: 1
  property real start: 0
  property real travel: Commons.Style.space(8)
  readonly property real sectionProgress: Math.max(0, Math.min(1,
    (progress - Math.max(0, Math.min(0.35, start))) / (1 - Math.max(0, Math.min(0.35, start)))))
  readonly property real visualOffset: travel * (1 - sectionProgress)
  implicitHeight: childrenRect.height
  height: implicitHeight
  opacity: 0.35 + 0.65 * sectionProgress
  transform: Translate { y: root.visualOffset }
}
