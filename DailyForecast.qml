import QtQuick
import qs.Commons as Commons
import qs.Ui as Ui
import "WeatherModel.js" as WeatherModel

Column {
  id: root
  property var daily: null
  property var hourly: null
  property string unit: "C"
  property bool stale: false
  property string currentDate: ""
  property bool showAll: false
  readonly property var days: makeDays()
  readonly property var rainByDay: WeatherModel.rainHours(hourly)
  readonly property var detailsByDay: WeatherModel.rainDetails(hourly)
  readonly property color muted: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.72)
  spacing: Commons.Style.space(6)
  function numeric(v) { return typeof v === "number" && isFinite(v) }
  function temperature(v) { return numeric(v) ? Math.round(unit === "F" ? v*9/5+32 : v) : null }
  function makeDays() {
    if (!daily || !daily.time) return []
    var rows=[]
    for (var i=0;i<Math.min(10,daily.time.length);i++) {
      var stamp=String(daily.time[i])
      var low=temperature(daily.temperature_2m_min ? daily.temperature_2m_min[i] : null)
      var high=temperature(daily.temperature_2m_max ? daily.temperature_2m_max[i] : null)
      var probability=daily.precipitation_probability_max ? daily.precipitation_probability_max[i] : null
      rows.push({label:WeatherModel.dayLabel(stamp, currentDate || daily.time[0], stale),
        code:daily.weather_code ? daily.weather_code[i] : null,
        low:low,high:high,probability:numeric(probability)?Math.max(0,Math.min(100,Math.round(probability))):null,
        hours:rainByDay[stamp]||[], details:detailsByDay[stamp]||[]})
    }
    return rows
  }
  PText { text: "Daily forecast"; font.pixelSize: Commons.Style.font.subtitle; font.bold: true }
  PText { width: parent.width; text: "Rain / snow chance by hour · city local time"; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap }
  PText { width: parent.width; text: "Brighter blue = higher chance · grey = 0% · outline = no data"; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap }
  PText { width: parent.width; visible: !root.days.length; text: "Daily forecast unavailable"; color: root.muted; font.pixelSize: Commons.Style.font.body }
  Repeater {
    model: root.showAll ? root.days : root.days.slice(0,5)
    delegate: Rectangle {
      required property var modelData
      required property int index
      width: root.width; height: dayContent.implicitHeight+Commons.Style.space(20)
      color: "transparent"
      Accessible.role: Accessible.StaticText
      Accessible.name: modelData.label + ", " + WeatherModel.description(modelData.code) + ", low " + (modelData.low===null?"unavailable":modelData.low+" degrees "+root.unit) + ", high " + (modelData.high===null?"unavailable":modelData.high+" degrees "+root.unit) + ", " + dayRain.detail
      Column {
        id: dayContent
        x: Commons.Style.space(8); y: Commons.Style.space(10)
        width: parent.width-Commons.Style.space(16); spacing: Commons.Style.space(9)
        Item {
          width: parent.width; height: Commons.Style.space(22)
          WeatherMark { width: 24; height: 24; scale: Commons.Style.space(19)/24; transformOrigin: Item.Left; anchors.verticalCenter: parent.verticalCenter; code: modelData.code }
          PText { x: Commons.Style.space(29); width: parent.width-x; anchors.verticalCenter: parent.verticalCenter; text: modelData.label+" · "+WeatherModel.description(modelData.code); font.pixelSize: Commons.Style.font.body; font.bold: true; elide: Text.ElideRight }
        }
        Item {
          width: parent.width; height: Math.max(lowLabel.implicitHeight, highLabel.implicitHeight)
          PText { id: lowLabel; anchors.left: parent.left; text: "Low "+(modelData.low===null?"—":modelData.low+"°"+root.unit); color: root.muted; font.pixelSize: Commons.Style.font.body }
          PText { id: highLabel; anchors.right: parent.right; text: "High "+(modelData.high===null?"—":modelData.high+"°"+root.unit); font.pixelSize: Commons.Style.font.body; font.bold: true }
        }
        RainTimeline { id: dayRain; objectName: "daily-rain-"+index; width: parent.width; hours: modelData.hours; hourDetails: modelData.details; dailyProbability: modelData.probability }
      }
      Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: root.muted; opacity: 0.12 }
    }
  }
  PText { width: parent.width; visible: root.days.length>0; text: "Hover, click or use arrow keys for an exact hour and its chance of rain / snow."; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap }
  Ui.Button { objectName: "daily-expand"; visible: root.days.length>5; text: root.showAll?"Collapse":"Show " + root.days.length + " days"; focusable: true; fontSize: Commons.Style.font.bodySmall; onClicked: root.showAll=!root.showAll }
}
