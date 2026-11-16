import QtQuick
import QtQuick.Controls
import qs.Commons as Commons
import qs.Ui as Ui

Item {
  id: root
  property var cities: []
  property var currentCity: null
  property var primaryCity: null
  property bool busy: false
  signal citySelected(var city)
  readonly property string currentKey: cityKey(currentCity)
  readonly property string primaryKey: cityKey(primaryCity)
  implicitHeight: Commons.Style.space(38)
  height: implicitHeight
  Accessible.role: Accessible.Grouping
  Accessible.name: "Favorite cities"

  function cityKey(city) {
    if (!city || city.latitude == null || city.longitude == null
        || !isFinite(Number(city.latitude)) || !isFinite(Number(city.longitude))) return ""
    return Number(city.latitude).toFixed(5) + "," + Number(city.longitude).toFixed(5)
  }
  function reveal(index) {
    var button = favorites.itemAt(index)
    if (!button) return
    var left = button.x
    var wanted = strip.contentX
    if (left < wanted) wanted = left
    else if (left + button.width > wanted + strip.width) wanted = left + button.width - strip.width
    strip.contentX = Math.max(0, Math.min(Math.max(0, strip.contentWidth - strip.width), wanted))
  }
  function revealCurrent() {
    var items = Array.isArray(cities) ? cities : []
    var index = items.findIndex(function(city) { return root.cityKey(city) === root.currentKey })
    if (index >= 0) reveal(index)
    else strip.contentX = Math.max(0, Math.min(Math.max(0, strip.contentWidth - strip.width), strip.contentX))
  }
  onCurrentKeyChanged: Qt.callLater(revealCurrent)
  onCitiesChanged: Qt.callLater(revealCurrent)
  onWidthChanged: Qt.callLater(revealCurrent)

  Flickable {
    id: strip
    objectName: "favorite-cities-strip"
    anchors.fill: parent
    contentWidth: citiesRow.implicitWidth
    contentHeight: height
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.HorizontalFlick
    onContentWidthChanged: Qt.callLater(root.revealCurrent)
    ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded; height: Commons.Style.space(3) }
    WheelHandler {
      onWheel: function(event) {
        var delta = event.pixelDelta.x || event.pixelDelta.y
        if (!delta) delta = (event.angleDelta.x || event.angleDelta.y) / 120 * Commons.Style.space(96)
        strip.contentX = Math.max(0, Math.min(Math.max(0, strip.contentWidth - strip.width), strip.contentX - delta))
        event.accepted = strip.contentWidth > strip.width
      }
    }
    Row {
      id: citiesRow
      spacing: Commons.Style.space(6)
      Repeater {
        id: favorites
        model: Array.isArray(root.cities) ? root.cities : []
        delegate: Ui.Button {
          id: cityButton
          required property var modelData
          required property int index
          readonly property string key: root.cityKey(modelData)
          readonly property string name: modelData && typeof modelData.name === "string" ? modelData.name : "City"
          readonly property bool primary: root.primaryKey !== "" && key === root.primaryKey
          objectName: "favorite-city-" + index
          text: name
          iconText: primary ? "★" : ""
          iconSize: Commons.Style.font.bodySmall
          height: Commons.Style.space(34)
          width: Math.min(implicitWidth, Commons.Style.space(150), Math.max(Commons.Style.space(64), root.width))
          fontSize: Commons.Style.font.bodySmall
          horizontalPadding: Commons.Style.space(8)
          bordered: true
          focusable: true
          selected: root.currentKey !== "" && key === root.currentKey
          enabled: !root.busy
          Accessible.name: "View " + name + (primary ? ", bar and notification city" : "")
          tooltipText: name + (modelData && modelData.country ? " · " + modelData.country : "") + (primary ? " · Bar & notifications" : "")
          onClicked: root.citySelected(modelData)
          onActiveFocusChanged: if (activeFocus) root.reveal(index)
        }
      }
    }
  }
}
