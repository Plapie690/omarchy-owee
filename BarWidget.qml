import QtQuick
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "owee.weather"
  function inject() {
    if (!loader.item) return
    loader.item.bar = root.bar
    loader.item.settings = root.settings
    loader.item.anchorItem = button
    loader.item.hostWidget = root
  }
  readonly property bool opened: loader.item ? loader.item.opened : false
  readonly property bool popoutSwitchClosing: loader.item ? loader.item.popoutSwitchClosing : false
  function open() { if (loader.item) loader.item.open() }
  function close() { if (loader.item) loader.item.close() }
  function closeForPopoutSwitch() { if (loader.item) loader.item.closeForPopoutSwitch() }
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  onBarChanged: inject()
  onSettingsChanged: inject()
  Loader {
    id: loader
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: { root.inject(); Qt.callLater(root.inject) }
  }
  WidgetButton {
    id: button
    objectName: "weather-bar-button"
    anchors.fill: parent
    bar: root.bar
    labelVisible: false
    hasVisualContent: true
    // The native status slot includes the icon canvas and its side bearings.
    readonly property real nativeBearings: Math.max(0, Style.bar.statusSlot - Style.bar.iconCanvas)
    implicitWidth: vertical ? barSize : weatherContent.implicitWidth + nativeBearings
    implicitHeight: vertical ? weatherContent.implicitHeight + nativeBearings : barSize
    tooltipText: "OWEE 1.3.4 · click to open"
    Accessible.role: Accessible.Button
    Accessible.name: "Weather: " + (loader.item ? loader.item.barTemperature : "—")
    Accessible.onPressAction: if (loader.item) loader.item.toggle()
    Item {
      id: weatherContent
      anchors.centerIn: parent
      readonly property real gap: Style.space(4)
      implicitWidth: button.vertical ? Math.max(optical.width, temperature.implicitWidth) : optical.width + gap + temperature.implicitWidth
      implicitHeight: button.vertical ? optical.height + gap + temperature.implicitHeight : Math.max(optical.height, temperature.implicitHeight)
      width: implicitWidth
      height: implicitHeight
      scale: button.pressScale
      BarIconContent {
        id: optical
        objectName: "weather-bar-optical"
        x: button.vertical ? (parent.width - width) / 2 : 0
        y: button.vertical ? 0 : (parent.height - height) / 2
        width: Style.bar.iconCanvas; height: width
        sourceSize: Style.bar.iconCanvas
        sourceComponent: Component {
          WeatherMark {
            objectName: "weather-bar-icon"
            code: loader.item && loader.item.primaryCurrent ? loader.item.primaryCurrent.weather_code : null
            night: !!loader.item && !!loader.item.primaryCurrent && loader.item.primaryCurrent.is_day === 0
            ink: button.foreground
          }
        }
      }
      PText {
        id: temperature
        objectName: "weather-bar-temperature"
        width: implicitWidth
        height: implicitHeight
        x: button.vertical ? (parent.width - width) / 2 : optical.width + weatherContent.gap
        y: button.vertical ? optical.height + weatherContent.gap : (parent.height - height) / 2
        text: loader.item ? loader.item.barTemperature : "—"
        font.family: button.fontFamily
        font.pixelSize: Style.bar.iconFont
        color: button.foreground
      }
    }
    onPressed: function(b) { if (loader.item) { if (b === Qt.MiddleButton) loader.item.refresh(); else loader.item.toggle() } }
  }
}
