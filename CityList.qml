import QtQuick
import qs.Commons as Commons

Column {
  id: root
  property var cities: []
  property var currentCity: null
  property var primaryCity: null
  property bool busy: false
  signal selected(var city)
  signal primaryRequested(string key)
  signal moveRequested(string key, string direction)
  signal removeRequested(string key)
  readonly property color muted: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.72)
  readonly property color surface: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.075)
  spacing: Commons.Style.space(6)

  function cityKey(city) {
    if (!city || city.latitude == null || city.longitude == null) return ""
    return Number(city.latitude).toFixed(5) + "," + Number(city.longitude).toFixed(5)
  }

  component CityButton: Rectangle {
    id: button
    required property string label
    required property string description
    signal clicked()
    width: Commons.Style.space(32); height: Commons.Style.space(36); radius: Commons.Style.cornerRadius
    color: activeFocus || clickArea.containsMouse ? root.surface : "transparent"
    opacity: enabled || label === "★" ? 1 : 0.35
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: description
    Accessible.onPressAction: clicked()
    border.width: activeFocus ? 1 : 0
    border.color: Commons.Color.accent
    PText { anchors.centerIn: parent; text: button.label; font.pixelSize: Commons.Style.font.subtitle; color: button.label === "★" ? Commons.Color.accent : Commons.Color.foreground }
    Keys.onReturnPressed: clicked()
    Keys.onSpacePressed: clicked()
    MouseArea { id: clickArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: button.clicked() }
  }

  PText { width: parent.width; text: "My cities"; font.bold: true; visible: root.cities.length > 0 }
  PText { width: parent.width; text: "★ sets the city used by the bar and notifications."; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap; visible: root.cities.length > 0 }
  Repeater {
    model: root.cities
    delegate: Rectangle {
      id: cityRow
      required property var modelData
      required property int index
      readonly property string key: root.cityKey(modelData)
      readonly property bool primary: key === root.cityKey(root.primaryCity)
      readonly property bool selected: key === root.cityKey(root.currentCity)
      width: root.width; height: Commons.Style.space(54); radius: Commons.Style.cornerRadius
      color: root.surface
      enabled: !root.busy
      Item {
        id: selection
        anchors.left: parent.left; width: Math.max(0, parent.width - Commons.Style.space(144)); height: parent.height
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: "View " + cityRow.modelData.name
        Accessible.onPressAction: root.selected(cityRow.modelData)
        Keys.onReturnPressed: root.selected(cityRow.modelData)
        Keys.onSpacePressed: root.selected(cityRow.modelData)
        Rectangle { anchors.fill: parent; radius: Commons.Style.cornerRadius; color: "transparent"; border.width: selection.activeFocus ? 1 : 0; border.color: Commons.Color.accent }
        Column {
          anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: Commons.Style.space(12); anchors.rightMargin: Commons.Style.space(4); anchors.verticalCenter: parent.verticalCenter; spacing: Commons.Style.space(3)
          PText { width: parent.width; text: (cityRow.selected ? "●  " : "○  ") + cityRow.modelData.name; elide: Text.ElideRight; font.bold: cityRow.selected }
          PText { width: parent.width; text: (cityRow.selected?"Viewing · ":"")+(cityRow.primary ? "Bar & notifications" : (cityRow.modelData.country || "Saved city")); elide: Text.ElideRight; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall }
        }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.selected(cityRow.modelData) }
      }
      Row {
        anchors.right: parent.right; anchors.rightMargin: Commons.Style.space(4); anchors.verticalCenter: parent.verticalCenter; spacing: Commons.Style.space(2)
        CityButton { label: cityRow.primary ? "★" : "☆"; description: cityRow.primary ? cityRow.modelData.name + " is used in the bar and notifications" : "Use " + cityRow.modelData.name + " in the bar and notifications"; enabled: !cityRow.primary; onClicked: root.primaryRequested(cityRow.key) }
        CityButton { label: "↑"; description: "Move up: " + cityRow.modelData.name; enabled: cityRow.index > 0; onClicked: root.moveRequested(cityRow.key, "up") }
        CityButton { label: "↓"; description: "Move down: " + cityRow.modelData.name; enabled: cityRow.index < root.cities.length - 1; onClicked: root.moveRequested(cityRow.key, "down") }
        CityButton { label: "×"; description: "Remove " + cityRow.modelData.name; enabled: root.cities.length > 1; onClicked: root.removeRequested(cityRow.key) }
      }
    }
  }
}
