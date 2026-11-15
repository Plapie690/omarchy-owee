import QtQuick
import qs.Commons as Commons
import "WeatherModel.js" as WeatherModel

Item {
  id: root
  property var hours: []
  property var hourDetails: []
  property var dailyProbability: null
  property int selectedHour: -1
  readonly property var slots: Array.from({length:24},function(_,i){var p=hours[i];return typeof p==="number"&&isFinite(p)?Math.max(0,Math.min(100,Math.round(p))):null})
  readonly property var peak: findPeak()
  readonly property string detail: describe()
  readonly property color muted: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.72)
  implicitHeight: content.implicitHeight
  activeFocusOnTab: true
  Accessible.role: Accessible.Button
  Accessible.name: "Hourly rain or snow chance. "+detail+". Use Left and Right to explore hours."
  Accessible.onPressAction: { forceActiveFocus(); selectedHour=peak?peak.hour:0 }
  onHoursChanged: selectedHour=-1

  function findPeak() {
    var best=null
    for(var i=0;i<24;i++) if(slots[i]!==null && (best===null || slots[i]>best.chance)) best={hour:i,chance:slots[i]}
    return best
  }
  function describe() {
    if(selectedHour>=0 && selectedHour<24) {
      var entries=hourDetails[selectedHour]||[];
      if(entries.length && entries[0].clock_gap)return WeatherModel.clock(selectedHour)+" · skipped by clock change";
      if(entries.length) return entries.map(function(entry){return String(entry.start_local).slice(11,16)+"–"+String(entry.end_local).slice(11,16)+(entries.length>1 || entry.start_offset!==entry.end_offset?" "+WeatherModel.offsetLabel(entry.start_offset)+" / "+WeatherModel.offsetLabel(entry.end_offset):"")+" · "+(entry.probability===null?"no hourly data":entry.probability+"% chance")}).join("; ");
      var p=slots[selectedHour]
      return WeatherModel.clock(selectedHour)+"–"+WeatherModel.clock(selectedHour+1)+" · "+(p===null?"no hourly data":p+"% chance")
    }
    if(!peak) return typeof dailyProbability==="number"&&isFinite(dailyProbability)?"Day chance: up to "+Math.max(0,Math.min(100,Math.round(dailyProbability)))+"% · hourly detail unavailable":"Hourly rain / snow forecast unavailable"
    if(peak.chance===0) return "Rain / snow chance: 0% in available hours"
    if((hourDetails[peak.hour]||[]).length>1)return "Peak chance: "+peak.chance+"% · "+WeatherModel.clock(peak.hour)+" (repeated clock hour)";
    return "Peak chance: "+peak.chance+"% · "+WeatherModel.clock(peak.hour)+"–"+WeatherModel.clock(peak.hour+1)
  }
  function pick(x) { selectedHour=Math.max(0,Math.min(23,Math.floor(x/Math.max(1,band.width)*24))) }
  function step(delta) { selectedHour=Math.max(0,Math.min(23,(selectedHour<0?(peak?peak.hour:0):selectedHour)+delta)) }
  Keys.onLeftPressed: step(-1)
  Keys.onRightPressed: step(1)
  Keys.onPressed: function(event) {
    if(event.key===Qt.Key_Home) {selectedHour=0;event.accepted=true}
    else if(event.key===Qt.Key_End) {selectedHour=23;event.accepted=true}
  }

  Rectangle { anchors.fill: parent; anchors.margins: -Commons.Style.space(3); color: "transparent"; border.width: root.activeFocus?1:0; border.color: Commons.Color.accent; radius: Commons.Style.cornerRadius }
  Column {
    id: content
    width: parent.width; spacing: Commons.Style.space(5)
    Item {
      id: band
      objectName: "rain-hour-band"
      width: parent.width; height: Commons.Style.space(10)
      Repeater {
        model: root.slots
        delegate: Rectangle {
          required property var modelData
          required property int index
          objectName: "rain-hour-"+index
          x: index*band.width/24; width: Math.max(0,band.width/24-Commons.Style.space(1)); height: band.height
          radius: Commons.Style.space(1)
          color: modelData===null?"transparent":modelData===0?Qt.rgba(root.muted.r,root.muted.g,root.muted.b,0.12):Qt.rgba(Commons.Color.accent.r,Commons.Color.accent.g,Commons.Color.accent.b,0.2+0.8*modelData/100)
          border.width: modelData===null?1:0
          border.color: Qt.rgba(root.muted.r,root.muted.g,root.muted.b,0.32)
          Rectangle { anchors.fill: parent; color: "transparent"; border.width: root.selectedHour===index?1:0; border.color: Commons.Color.foreground; radius: parent.radius }
          Rectangle { anchors.centerIn: parent; width: 1; height: Commons.Style.space(6); rotation:45; color:root.muted; visible:!!root.hourDetails[index]&&!!root.hourDetails[index].length&&root.hourDetails[index][0].clock_gap===true }
        }
      }
      MouseArea {
        anchors.fill: parent; hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onPositionChanged: function(mouse){root.pick(mouse.x)}
        onClicked: function(mouse){root.pick(mouse.x);root.forceActiveFocus()}
        onExited: if(!root.activeFocus)root.selectedHour=-1
      }
    }
    Item {
      width: parent.width; height: Commons.Style.font.bodySmall+Commons.Style.space(3)
      Repeater {
        model: [0,6,12,18,24]
        delegate: PText {
          required property int modelData
          text: WeatherModel.clock(modelData)
          x: Math.max(0,Math.min(parent.width-width,modelData/24*parent.width-width/2))
          color: root.muted; font.pixelSize: Commons.Style.font.bodySmall
        }
      }
    }
    PText { objectName: "rain-hour-detail"; width: parent.width; text: root.detail; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap }
  }
}
