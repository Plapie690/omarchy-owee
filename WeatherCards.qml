import QtQuick
import qs.Commons as Commons

Item {
  id: root
  property var order: []
  property var hidden: []
  property bool editing: false
  property bool busy: false
  property bool active: true
  property var scrollView: null
  property var cardInfo: function(id) { return {title: id, value: "—", detail: ""} }
  signal reorderRequested(var allOrder)
  signal toggleRequested(string id)

  readonly property bool dragging: draggingId !== ""
  readonly property bool canEdit: editing && !busy && active
  readonly property bool rightToLeft: LayoutMirroring.enabled
  readonly property real gap: Commons.Style.space(10)
  readonly property real cardWidth: Math.max(1, (width - gap) / 2)
  readonly property real cardHeight: Commons.Style.space(editing ? 220 : 178)
  readonly property real helpHeight: editing ? instructions.implicitHeight + Commons.Style.space(12) : 0
  readonly property var shownOrder: editing ? order : order.filter(function(id) { return hidden.indexOf(id) < 0 })
  readonly property color soft: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.075)
  readonly property color muted: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.72)
  readonly property color accentSoft: Qt.rgba(Commons.Color.accent.r, Commons.Color.accent.g, Commons.Color.accent.b, 0.16)
  implicitHeight: shownOrder.length ? helpHeight + Math.ceil(shownOrder.length / 2) * (cardHeight + gap) - gap : helpHeight
  height: implicitHeight

  property string pressedId: ""
  property string draggingId: ""
  property var dragOrder: []
  property real pressSceneX: 0
  property real pressSceneY: 0
  property real pointerSceneX: 0
  property real pointerSceneY: 0
  property real pointerX: 0
  property real pointerY: 0
  property real dragOffsetX: 0
  property real dragOffsetY: 0
  property int targetIndex: -1

  function title(info, fallback) {
    return String(info.title || fallback || "").replace(/^[☷◉☀◴◌☂✿]\s*/, "")
  }
  function sameOrder(a, b) {
    if (a.length !== b.length) return false
    for (var i = 0; i < a.length; i++) if (a[i] !== b[i]) return false
    return true
  }
  function slotX(index) {
    var column = index % 2
    return (rightToLeft ? 1 - column : column) * (cardWidth + gap)
  }
  function slotY(index) { return helpHeight + Math.floor(index / 2) * (cardHeight + gap) }
  function cancelDrag() {
    pressedId = ""
    draggingId = ""
    targetIndex = -1
    dragOrder = []
  }
  function beginPress(id, sceneX, sceneY) {
    if (!canEdit) return
    cancelDrag()
    pressedId = id
    dragOrder = order.slice()
    pressSceneX = pointerSceneX = sceneX
    pressSceneY = pointerSceneY = sceneY
    var local = mapFromItem(null, sceneX, sceneY)
    var index = order.indexOf(id)
    dragOffsetX = local.x - slotX(index)
    dragOffsetY = local.y - slotY(index)
  }
  function updatePointer(sceneX, sceneY) {
    if (!pressedId || !canEdit) return
    pointerSceneX = sceneX
    pointerSceneY = sceneY
    if (!dragging && Math.abs(sceneX - pressSceneX) + Math.abs(sceneY - pressSceneY) < 8) return
    if (!dragging) { draggingId = pressedId; forceActiveFocus() }
    var local = mapFromItem(null, sceneX, sceneY)
    pointerX = local.x
    pointerY = local.y
    if (scrollView !== null) {
      var viewPoint = scrollView.mapFromItem(null, sceneX, sceneY)
      if (viewPoint.x < 0 || viewPoint.x > scrollView.width || viewPoint.y < 0 || viewPoint.y > scrollView.height) {
        targetIndex = -1
        return
      }
    }
    if (local.x < 0 || local.x > width || local.y < helpHeight || local.y > height) {
      targetIndex = -1
      return
    }
    var column = Math.max(0, Math.min(1, Math.floor((local.x + gap / 2) / (cardWidth + gap))))
    if (rightToLeft) column = 1 - column
    var row = Math.floor((local.y - helpHeight + gap / 2) / (cardHeight + gap))
    targetIndex = Math.min(order.length - 1, row * 2 + column)
  }
  function releasePress(sceneX, sceneY) {
    if (!pressedId) return
    updatePointer(sceneX, sceneY)
    var from = dragOrder.indexOf(draggingId)
    var to = targetIndex
    var next = dragOrder.slice()
    var commit = canEdit && dragging && from >= 0 && to >= 0 && from !== to && sameOrder(order, dragOrder)
    if (commit) next.splice(to, 0, next.splice(from, 1)[0])
    cancelDrag()
    if (commit) reorderRequested(next)
  }
  function moveCard(id, direction) {
    if (!canEdit) return
    cancelDrag()
    var next = order.slice()
    var from = next.indexOf(id)
    var to = from + direction
    if (from < 0 || to < 0 || to >= next.length) return
    next.splice(to, 0, next.splice(from, 1)[0])
    reorderRequested(next)
  }
  function toggleCard(id) {
    if (!canEdit) return
    cancelDrag()
    toggleRequested(id)
  }
  onEditingChanged: if (!editing) cancelDrag()
  onActiveChanged: if (!active) cancelDrag()
  onBusyChanged: if (busy) cancelDrag()
  onVisibleChanged: if (!visible) cancelDrag()
  onOrderChanged: if (pressedId && !sameOrder(order, dragOrder)) cancelDrag()
  Keys.onEscapePressed: function(event) {
    if (pressedId) { cancelDrag(); event.accepted = true }
    else event.accepted = false
  }

  // This timer responds to a held pointer, including with desktop animations off.
  Timer {
    interval: 16
    repeat: true
    running: root.dragging && root.scrollView !== null
    onTriggered: {
      var view = root.scrollView
      var point = view.mapFromItem(null, root.pointerSceneX, root.pointerSceneY)
      if (point.x < 0 || point.x > view.width || point.y < 0 || point.y > view.height) return
      var speed = point.y < 38 ? -7 : point.y > view.height - 38 ? 7 : 0
      if (!speed) return
      view.contentY = Math.max(0, Math.min(Math.max(0, view.contentHeight - view.height), view.contentY + speed))
      root.updatePointer(root.pointerSceneX, root.pointerSceneY)
    }
  }

  component EditButton: Rectangle {
    id: control
    property string label: ""
    property string accessibleLabel: label
    signal clicked()
    width: Commons.Style.space(32); height: Commons.Style.space(30); radius: Commons.Style.cornerRadius
    color: editMouse.containsMouse || activeFocus ? root.accentSoft : root.soft
    opacity: enabled ? 1 : 0.35
    border.width: activeFocus ? 1 : 0
    border.color: Commons.Color.accent
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: accessibleLabel
    Accessible.onPressAction: clicked()
    PText { anchors.centerIn: parent; text: control.label; font.pixelSize: control.width > Commons.Style.space(40) ? Commons.Style.font.bodySmall : Commons.Style.font.title }
    MouseArea { id: editMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { control.forceActiveFocus(); control.clicked() } }
    Keys.onReturnPressed: clicked()
    Keys.onSpacePressed: clicked()
  }

  PText {
    id: instructions
    width: parent.width
    visible: root.editing
    text: "Drag cards by the ⠿ handle or use the arrows. Escape cancels the move."
    color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap
  }

  Repeater {
    model: root.shownOrder
    delegate: Rectangle {
      id: tile
      required property string modelData
      required property int index
      readonly property var info: root.cardInfo(modelData)
      readonly property bool cardHidden: root.hidden.indexOf(modelData) >= 0
      objectName: "card-" + modelData
      x: root.slotX(index); y: root.slotY(index)
      width: root.cardWidth; height: root.cardHeight; radius: Commons.Style.cornerRadius
      color: root.dragging && root.targetIndex === index ? root.accentSoft : root.soft
      border.width: root.dragging && root.targetIndex === index ? 2 : 0
      border.color: Commons.Color.accent
      opacity: root.draggingId === modelData ? 0.25 : 1
      Behavior on opacity { NumberAnimation { duration: Commons.Style.duration(120); easing.type: Easing.OutCubic } }

      Column {
        x: Commons.Style.space(14); y: Commons.Style.space(14)
        width: parent.width - Commons.Style.space(28); spacing: Commons.Style.space(5)
        opacity: tile.cardHidden && root.editing ? 0.55 : 1
        Item {
          id: titleArea
          width: parent.width
          height: Math.max(Commons.Style.space(18), cardTitle.implicitHeight)
          Row {
            anchors.centerIn: parent
            spacing: Commons.Style.space(6)
            MetricIcon {
              width: Commons.Style.space(16); height: width
              anchors.verticalCenter: parent.verticalCenter
              kind: tile.modelData; ink: root.muted
              Accessible.ignored: true
            }
            PText {
              id: cardTitle
              width: Math.max(0, Math.min(implicitWidth, titleArea.width-Commons.Style.space(root.editing ? 86 : 22)))
              anchors.verticalCenter: parent.verticalCenter
              text: root.title(tile.info, tile.modelData); color: root.muted
              font.pixelSize: Commons.Style.font.body; elide: Text.ElideRight
            }
          }
        }
        PText { objectName: "value-" + tile.modelData; width: parent.width; horizontalAlignment: Text.AlignHCenter; text: tile.info.value || "—"; font.pixelSize: tile.modelData === "pollen" || tile.modelData === "sun" ? Commons.Style.font.heading : Commons.Style.font.display; elide: Text.ElideRight }
        PText { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: (tile.cardHidden && root.editing ? "Hidden · " : "") + (tile.info.detail || ""); font.pixelSize: Commons.Style.font.bodySmall; color: root.muted; elide: Text.ElideRight }
        MetricVisual {
          objectName: "visual-" + tile.modelData
          width: parent.width; height: Commons.Style.space(52)
          kind: tile.modelData
          reading: typeof tile.info.reading === "number" ? tile.info.reading : NaN
          direction: typeof tile.info.direction === "number" ? tile.info.direction : NaN
          dayProgress: typeof tile.info.progress === "number" ? tile.info.progress : NaN
          opacity: tile.cardHidden && root.editing ? 0.55 : 1
        }
        Item {
          width: parent.width; height: Commons.Style.font.bodySmall
          visible: tile.modelData === "pressure" || tile.modelData === "uv" || tile.modelData === "humidity"
          PText { anchors.left: parent.left; text: tile.modelData === "pressure" ? "950" : "0"; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall }
          PText { anchors.right: parent.right; text: tile.modelData === "pressure" ? "1050 hPa" : tile.modelData === "uv" ? "11+" : "100 %"; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall }
        }
      }
      Rectangle {
        id: handle
        objectName: "drag-" + tile.modelData
        anchors.top: parent.top; anchors.right: parent.right; anchors.margins: Commons.Style.space(7)
        width: Commons.Style.space(36); height: Commons.Style.space(32); radius: Commons.Style.cornerRadius
        visible: root.editing
        enabled: root.canEdit
        color: root.soft
        border.width: activeFocus ? 1 : 0
        border.color: Commons.Color.accent
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: "Move " + root.title(tile.info, tile.modelData) + ". Use Ctrl and arrow keys to reorder."
        PText { anchors.centerIn: parent; text: "⠿"; font.pixelSize: Commons.Style.font.iconLarge }
        Keys.onPressed: function(event) {
          if (!(event.modifiers & Qt.ControlModifier)) return
          var key = Commons.Util.readingKey(event)
          if (key === Qt.Key_Left || key === Qt.Key_Up) { root.moveCard(tile.modelData, -1); event.accepted = true }
          else if (key === Qt.Key_Right || key === Qt.Key_Down) { root.moveCard(tile.modelData, 1); event.accepted = true }
        }
        MouseArea {
          id: dragArea
          anchors.fill: parent
          preventStealing: true
          cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
          onPressed: function(mouse) { var point = mapToItem(null, mouse.x, mouse.y); root.beginPress(tile.modelData, point.x, point.y) }
          onPositionChanged: function(mouse) { if (pressed) { var point = mapToItem(null, mouse.x, mouse.y); root.updatePointer(point.x, point.y) } }
          onReleased: function(mouse) { var point = mapToItem(null, mouse.x, mouse.y); root.releasePress(point.x, point.y) }
          onCanceled: root.cancelDrag()
        }
      }
      Row {
        anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: Commons.Style.space(12)
        visible: root.editing
        spacing: Commons.Style.space(6)
        EditButton { objectName: "up-" + tile.modelData; label: "↑"; accessibleLabel: "Move up: " + root.title(tile.info, tile.modelData); enabled: root.canEdit && tile.index > 0; onClicked: root.moveCard(tile.modelData, -1) }
        EditButton { objectName: "down-" + tile.modelData; label: "↓"; accessibleLabel: "Move down: " + root.title(tile.info, tile.modelData); enabled: root.canEdit && tile.index < root.order.length - 1; onClicked: root.moveCard(tile.modelData, 1) }
        EditButton { objectName: "toggle-" + tile.modelData; width: Commons.Style.space(68); label: tile.cardHidden ? "Show" : "Hide"; accessibleLabel: label + " " + root.title(tile.info, tile.modelData); enabled: root.canEdit; onClicked: root.toggleCard(tile.modelData) }
      }
    }
  }

  Rectangle {
    id: preview
    readonly property var info: root.draggingId ? root.cardInfo(root.draggingId) : ({})
    visible: root.dragging
    x: root.pointerX - root.dragOffsetX
    y: root.pointerY - root.dragOffsetY
    z: 100
    width: root.cardWidth; height: root.cardHeight; radius: Commons.Style.cornerRadius
    color: Commons.Color.background
    border.width: 2; border.color: Commons.Color.accent
    opacity: 0.94
    Column {
      anchors.fill: parent; anchors.margins: Commons.Style.space(14); spacing: Commons.Style.space(7)
      PText { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: root.title(preview.info, root.draggingId); font.pixelSize: Commons.Style.font.body; elide: Text.ElideRight }
      PText { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: preview.info.value || "—"; font.pixelSize: root.draggingId === "pollen" || root.draggingId === "sun" ? Commons.Style.font.heading : Commons.Style.font.display; elide: Text.ElideRight }
      PText { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: preview.info.detail || ""; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; elide: Text.ElideRight }
      MetricVisual { width: parent.width; height: Commons.Style.space(52); kind: root.draggingId; reading: typeof preview.info.reading === "number" ? preview.info.reading : NaN; direction: typeof preview.info.direction === "number" ? preview.info.direction : NaN; dayProgress: typeof preview.info.progress === "number" ? preview.info.progress : NaN }
      PText { width: parent.width; text: root.targetIndex < 0 ? "Outside the grid · cancel" : "Release to place here"; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap }
    }
  }
}
