import QtQuick
import qs.Commons as Commons
import qs.Ui as Ui
import "WeatherModel.js" as WeatherModel

Column {
  id: root
  property var hourly: null
  property var current: null
  property int startIndex: 0
  property string unit: "C"
  property bool stale: false
  property var scrollView: null
  readonly property bool rightToLeft: LayoutMirroring.enabled
  readonly property real cell: Commons.Style.space(56)
  readonly property var samples: makeSamples()
  readonly property string precipitationSummary: summary()
  readonly property color muted: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.72)
  spacing: Commons.Style.space(8)
  function numeric(v) { return typeof v === "number" && isFinite(v) }
  function makeSamples() {
    if (!hourly || !hourly.time) return []
    var rows = []
    for (var i = Math.max(0, startIndex); i < Math.min(hourly.time.length, startIndex + 24); i++) {
      var t = hourly.temperature_2m ? hourly.temperature_2m[i] : null
      var p = hourly.precipitation_probability ? hourly.precipitation_probability[i] : null
      var interval=hourly.rain_intervals && hourly.time_utc ? hourly.rain_intervals.find(function(v){return v.end_utc===hourly.time_utc[i]}) : null
      rows.push({stamp:String(hourly.time[i]), interval:interval, time: String(hourly.time[i]).slice(11,16), code: hourly.weather_code ? hourly.weather_code[i] : null,
        night: !!hourly.is_day && hourly.is_day[i] === 0,
        temperature: numeric(t) ? Math.round(unit === "F" ? t * 9 / 5 + 32 : t) : null,
        probability: numeric(p) ? Math.max(0, Math.min(100, Math.round(p))) : null})
    }
    return rows
  }
  function summary() {
    var peak=null
    for (var i=0;i<samples.length;i++) if (samples[i].probability!==null && (peak===null || samples[i].probability>peak.probability)) peak=samples[i]
    if (peak===null) return "Rain / snow chance unavailable"
    if (peak.probability===0) return "Bars: rain / snow chance · 0% in available hours"
    var reference=current && current.time ? String(current.time).slice(0,10) : samples[0].stamp.slice(0,10)
    var interval=peak.interval?{date:peak.interval.date,label:String(peak.interval.start_local).slice(11,16)+"–"+String(peak.interval.end_local).slice(11,16)}:WeatherModel.rainInterval(peak.stamp)
    var day=interval?interval.date:peak.stamp.slice(0,10), when=interval?interval.label:peak.time
    if(day!==reference || stale) {
      var label=WeatherModel.dayLabel(day,reference,stale)
      when=(label==="Tomorrow"?"tomorrow":label)+" "+when
    }
    return "Bars: rain / snow chance · peak "+peak.probability+"% · "+when
  }
  function center(index) { return (rightToLeft ? samples.length - index - 1 : index) * cell + cell / 2 }
  function move(direction) {
    var delta = direction * cell * 4 * (rightToLeft ? -1 : 1)
    strip.contentX = Math.max(0, Math.min(Math.max(0, strip.contentWidth-strip.width), strip.contentX + delta))
  }
  Item {
    id: title
    width: parent.width; height: Commons.Style.space(34)
    PText { anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; text: "Hourly forecast · °"+root.unit; font.pixelSize: Commons.Style.font.subtitle; font.bold: true }
    Row {
      anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: Commons.Style.space(4)
      Ui.Button { objectName: "hourly-previous"; text: root.rightToLeft ? "›" : "‹"; width: Commons.Style.space(30); height: Commons.Style.space(30); focusable: true; bordered: true; enabled: strip.contentWidth > strip.width && (root.rightToLeft ? strip.contentX < strip.contentWidth-strip.width : strip.contentX > 0); Accessible.name: "Earlier hours"; onClicked: root.move(-1) }
      Ui.Button { objectName: "hourly-next"; text: root.rightToLeft ? "‹" : "›"; width: Commons.Style.space(30); height: Commons.Style.space(30); focusable: true; bordered: true; enabled: strip.contentWidth > strip.width && (root.rightToLeft ? strip.contentX > 0 : strip.contentX < strip.contentWidth-strip.width); Accessible.name: "Later hours"; onClicked: root.move(1) }
    }
  }
  PText { objectName: "hourly-rain-explanation"; width: parent.width; visible: root.samples.length>0; text: root.precipitationSummary; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap }
  PText { id: empty; width: parent.width; visible: !root.samples.length; text: "Hourly forecast unavailable"; color: root.muted; font.pixelSize: Commons.Style.font.body }
  Flickable {
    id: strip
    objectName: "hourly-strip"
    visible: root.samples.length > 0
    width: parent.width; height: Commons.Style.space(148)
    contentWidth: root.samples.length * root.cell; contentHeight: height
    clip: true; boundsBehavior: Flickable.StopAtBounds; flickableDirection: Flickable.HorizontalFlick
    activeFocusOnTab: true
    Keys.onLeftPressed: root.move(root.rightToLeft ? 1 : -1)
    Keys.onRightPressed: root.move(root.rightToLeft ? -1 : 1)
    WheelHandler {
      onWheel: function(event) {
        var delta = event.angleDelta.x
        if (event.modifiers & Qt.ShiftModifier) delta = event.angleDelta.y
        if (!delta) {
          if (root.scrollView) {
            var verticalDelta = event.pixelDelta.y || event.angleDelta.y / 120 * Commons.Style.space(48)
            var view = root.scrollView
            view.contentY = Math.max(0,Math.min(Math.max(0,view.contentHeight-view.height),view.contentY-verticalDelta))
            event.accepted = true
          } else event.accepted = false
          return
        }
        strip.contentX = Math.max(0, Math.min(Math.max(0, strip.contentWidth-strip.width), strip.contentX-delta))
        event.accepted = true
      }
    }
    Repeater {
      model: root.samples
      delegate: Item {
        required property var modelData
        required property int index
        x: root.center(index) - width/2; width: root.cell; height: strip.height
        Accessible.role: Accessible.StaticText
        Accessible.name: modelData.time + ", " + (modelData.temperature === null ? "temperature unavailable" : modelData.temperature + " degrees") + (modelData.probability === null ? "" : ", rain or snow chance " + modelData.probability + " percent during " + (WeatherModel.rainInterval(modelData.stamp)?WeatherModel.rainInterval(modelData.stamp).label:modelData.time))
        PText { anchors.horizontalCenter: parent.horizontalCenter; y: 0; text: modelData.time; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall }
        WeatherMark { anchors.horizontalCenter: parent.horizontalCenter; y: Commons.Style.space(23); scale: Commons.Style.space(20)/24; transformOrigin: Item.Top; code: modelData.code; night: modelData.night }
        PText { objectName: "hourly-temperature-" + index; anchors.horizontalCenter: parent.horizontalCenter; y: Commons.Style.space(51); text: modelData.temperature === null ? "—" : modelData.temperature + "°"; font.pixelSize: Commons.Style.font.body; font.bold: true }
        Item {
          objectName: "hourly-precipitation-" + index
          x: (parent.width-width)/2; y: Commons.Style.space(88)
          width: Commons.Style.space(16); height: Commons.Style.space(28)
          Accessible.ignored: true
          Rectangle {
            objectName: "hourly-precipitation-fill-" + index
            anchors.bottom: parent.bottom
            width: parent.width
            height: parent.height * (modelData.probability === null ? 0 : modelData.probability/100)
            visible: height > 0
            topLeftRadius: Math.min(Commons.Style.space(2), height/2)
            topRightRadius: topLeftRadius
            gradient: Gradient {
              GradientStop { position: 0; color: Qt.rgba(Commons.Color.accent.r, Commons.Color.accent.g, Commons.Color.accent.b, 0.88) }
              GradientStop { position: 1; color: Qt.rgba(Commons.Color.accent.r, Commons.Color.accent.g, Commons.Color.accent.b, 0.64) }
            }
          }
          Rectangle { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; width: Commons.Style.space(12); height: Commons.Style.space(1); color: root.muted; opacity: 0.2 }
        }
        PText { anchors.horizontalCenter: parent.horizontalCenter; y: Commons.Style.space(126); text: modelData.probability === null ? "—" : modelData.probability + " %"; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall }
      }
    }
  }
}
