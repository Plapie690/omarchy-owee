import QtQuick
import qs.Commons as Commons
import qs.Ui as Ui

Rectangle {
  id: root
  property var config: ({})
  property bool busy: false
  property string feedback: ""
  property string primaryCityName: ""
  property bool expanded: false
  property bool embedded: false
  property bool detailsExpanded: false
  signal changed(var patch)
  signal testRequested()
  readonly property bool controlsVisible: expanded || embedded
  readonly property real padding: embedded ? 0 : Commons.Style.space(14)
  readonly property color muted: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.72)
  readonly property color surface: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.075)
  implicitHeight: body.implicitHeight + padding * 2
  radius: Commons.Style.cornerRadius
  color: embedded ? "transparent" : surface

  component ToggleRow: Ui.Toggle {
    signal toggled()
    width: parent.width
    implicitHeight: Commons.Style.space(44)
    titleSize: Commons.Style.font.body
    descriptionSize: Commons.Style.font.bodySmall
    onClicked: toggled()
    Accessible.role: Accessible.CheckBox
    Accessible.name: label
    Accessible.checked: checked
    Accessible.onPressAction: toggled()
  }

  component NumberRow: Item {
    id: number
    required property string label
    required property int currentValue
    property int minimum: 1
    property int maximum: 100
    property int step: 1
    signal edited(int value)
    width: parent.width
    implicitHeight: Math.max(numberLabel.implicitHeight, numberField.implicitHeight) + Commons.Style.space(8)
    PText {
      id: numberLabel
      anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
      width: Math.max(0, parent.width - numberField.width - Commons.Style.space(16))
      text: number.label; wrapMode: Text.WordWrap
      color: root.muted; font.pixelSize: Commons.Style.font.bodySmall
    }
    Ui.NumberField {
      id: numberField
      anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
      fieldWidth: Commons.Style.space(104)
      width: fieldWidth
      from: number.minimum; to: number.maximum; stepSize: number.step; value: number.currentValue
      onModified: function(value) { number.edited(value) }
      Component.onCompleted: field.Accessible.name = number.label
    }
  }

  component TimeRow: Item {
    id: time
    required property string label
    required property string currentValue
    signal edited(string value)
    width: parent.width
    implicitHeight: Math.max(timeLabel.implicitHeight, timeField.implicitHeight) + Commons.Style.space(8)
    PText {
      id: timeLabel
      anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
      width: Math.max(0, parent.width - timeField.width - Commons.Style.space(16))
      text: time.label; wrapMode: Text.WordWrap
      color: root.muted; font.pixelSize: Commons.Style.font.bodySmall
    }
    Ui.TextField {
      id: timeField
      anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
      width: Commons.Style.space(84)
      text: time.currentValue
      inputMask: "99:99"
      validator: RegularExpressionValidator { regularExpression: /^([01]\d|2[0-3]):[0-5]\d$/ }
      horizontalAlignment: TextInput.AlignHCenter
      onEditingFinished: if (acceptableInput && text !== time.currentValue) time.edited(text)
      Accessible.name: time.label
    }
  }

  Column {
    id: body
    x: root.padding; y: root.padding; width: parent.width - root.padding * 2
    spacing: Commons.Style.space(8)
    Item {
      width: parent.width
      height: Math.max(Commons.Style.space(36), headerAction.implicitHeight)
      PText {
        anchors.left: parent.left; anchors.right: headerAction.left
        anchors.rightMargin: Commons.Style.space(12); anchors.verticalCenter: parent.verticalCenter
        text: "Notifications"; font.bold: true; font.pixelSize: Commons.Style.font.title
        elide: Text.ElideRight
      }
      Ui.Button {
        id: headerAction
        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
        visible: !root.embedded
        text: root.expanded ? "Collapse" : "Configure"
        focusable: true
        fontSize: Commons.Style.font.bodySmall
        onClicked: root.expanded = !root.expanded
        Accessible.role: Accessible.Button
        Accessible.name: "Configure weather notifications"
        Accessible.onPressAction: root.expanded = !root.expanded
      }
    }
    PText {
      width: parent.width
      visible: !root.controlsVisible
      text: root.config.enabled ? "Enabled · " + (root.config.daily ? "daily summary and thresholds" : "weather thresholds") : "Disabled"
      color: root.muted; font.pixelSize: Commons.Style.font.bodySmall
    }
    Column {
      width: parent.width; spacing: Commons.Style.space(8); visible: root.controlsVisible
      ToggleRow { label: "Enable notifications"; enabled: !root.busy; checked: root.config.enabled === true; onToggled: root.changed({enabled: !checked}) }
      PText {
        width: parent.width
        text: "Bar & notification city" + (root.primaryCityName ? ": " + root.primaryCityName : "") + ". Open-Meteo forecasts, not official alerts."
        wrapMode: Text.WordWrap; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall
      }
      Column {
        width: parent.width; spacing: Commons.Style.space(4)
        enabled: root.config.enabled === true && !root.busy; opacity: enabled ? 1 : 0.55
        ToggleRow { label: "Upcoming precipitation"; checked: root.config.rain === true; onToggled: root.changed({rain: !checked}) }
        NumberRow { label: "Minimum probability (%)"; currentValue: root.config.rain_probability || 60; minimum: 10; maximum: 100; step: 10; enabled: root.config.rain === true; onEdited: function(value) { root.changed({rain_probability: value}) } }
        NumberRow { label: "Precipitation window (hours)"; currentValue: root.config.rain_hours || 3; minimum: 1; maximum: 6; enabled: root.config.rain === true; onEdited: function(value) { root.changed({rain_hours: value}) } }
        ToggleRow { label: "Strong wind"; checked: root.config.wind === true; onToggled: root.changed({wind: !checked}) }
        NumberRow { label: "Wind threshold (km/h)"; currentValue: root.config.wind_kmh || 50; minimum: 10; maximum: 150; step: 5; enabled: root.config.wind === true; onEdited: function(value) { root.changed({wind_kmh: value}) } }
        ToggleRow { label: "High UV index today"; checked: root.config.uv === true; onToggled: root.changed({uv: !checked}) }
        NumberRow { label: "UV threshold (daily maximum)"; currentValue: root.config.uv_index || 6; minimum: 1; maximum: 15; enabled: root.config.uv === true; onEdited: function(value) { root.changed({uv_index: value}) } }
        ToggleRow { label: "Daily summary"; checked: root.config.daily === true; onToggled: root.changed({daily: !checked}) }
        TimeRow { label: "Summary time (desktop)"; currentValue: root.config.daily_time || "08:00"; enabled: root.config.daily === true; onEdited: function(value) { root.changed({daily_time: value}) } }
        ToggleRow { label: "Quiet hours"; checked: root.config.quiet_enabled !== false; onToggled: root.changed({quiet_enabled: !checked}) }
        TimeRow { label: "Quiet hours start (desktop)"; currentValue: root.config.quiet_start || "22:00"; enabled: root.config.quiet_enabled !== false; onEdited: function(value) { root.changed({quiet_start: value}) } }
        TimeRow { label: "Quiet hours end (desktop)"; currentValue: root.config.quiet_end || "07:00"; enabled: root.config.quiet_enabled !== false; onEdited: function(value) { root.changed({quiet_end: value}) } }
        NumberRow { label: "Repeat interval per alert (min)"; currentValue: root.config.cooldown_minutes || 180; minimum: 30; maximum: 1440; step: 30; onEdited: function(value) { root.changed({cooldown_minutes: value}) } }
      }
      Ui.Button {
        width: parent.width
        text: root.detailsExpanded ? "Hide details" : "Behavior and timing"
        fontSize: Commons.Style.font.bodySmall
        focusable: true
        onClicked: root.detailsExpanded = !root.detailsExpanded
        Accessible.role: Accessible.Button
        Accessible.name: "Notification behavior details"
        Accessible.onPressAction: root.detailsExpanded = !root.detailsExpanded
      }
      PText {
        width: parent.width; visible: root.detailsExpanded
        text: "The summary and quiet hours use this desktop clock. Omarchy Do Not Disturb takes priority. Rules use recent data and pause when automatic refresh is disabled."
        wrapMode: Text.WordWrap; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall
      }
      Ui.Button {
        width: parent.width; enabled: !root.busy
        text: "Send test notification"
        fontSize: Commons.Style.font.bodySmall
        focusable: true
        onClicked: root.testRequested()
        Accessible.role: Accessible.Button
        Accessible.name: "Send a test weather notification"
        Accessible.onPressAction: root.testRequested()
      }
      PText {
        width: parent.width; visible: root.feedback !== ""; text: root.feedback
        wrapMode: Text.WordWrap; font.pixelSize: Commons.Style.font.bodySmall; color: root.muted
      }
    }
  }
}
