import QtQuick
import QtQuick.Controls
import Quickshell.Io
import qs.Commons as Commons
import qs.Ui as Ui

Rectangle {
  id: root
  property var formats: null
  property var city: ({})
  property bool active: false
  property bool detailsExpanded: false
  property bool radarEnabled: false
  property int zoom: 6
  property bool settingsLoaded: false
  property var radar: ({})
  property int frameIndex: 0
  property bool playing: false
  property string message: ""
  property var pending: null
  signal forecastRequested()
  property string coverageState: "unknown"
  property int imageRevision: 0
  readonly property bool imageReady: frameImageState(false)
  readonly property bool imageError: frameImageState(true)
  readonly property bool projectionUnsupported: radar.status === "unsupported" && radar.reason === "projection_limit"
  readonly property var coverageTiles: Array.isArray(radar.coverage_tiles) ? radar.coverage_tiles : []
  readonly property var frames: Array.isArray(radar.frames) ? radar.frames : []
  readonly property bool busy: worker.running
  readonly property string cityKey: city && isFinite(city.latitude) && isFinite(city.longitude) ? Number(city.latitude).toFixed(5) + "," + Number(city.longitude).toFixed(5) : ""
  readonly property color muted: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.72)
  readonly property color soft: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.075)
  readonly property string scriptPath: decodeURIComponent(Qt.resolvedUrl("radar.py").toString().replace(/^file:\/\//, ""))
  readonly property string frameTime: frames.length > frameIndex ? dateTime(frames[frameIndex]) : "—"
  readonly property string clockLabel: frames.length > frameIndex && validLocal(frames[frameIndex].local_time) ? "City local time · "+(frames[frameIndex].timezone || radar.timezone || "") : "Desktop local time"
  implicitHeight: content.implicitHeight + Commons.Style.space(28)
  height: implicitHeight
  radius: Commons.Style.cornerRadius
  color: soft

  function localSource(value) { return typeof value === "string" && value.length < 4096 && value.indexOf("file:///") === 0 ? value : "" }
  function frameImageState(errors) {
    if(imageRevision<0 || !frameImages || frameIndex>=frames.length || !frames.length || !Array.isArray(frames[frameIndex].tiles) || !frameImages.count) return false
    for(var i=0;i<frameImages.count;i++) {
      var image=frameImages.itemAt(i)
      if(errors && image && image.status===Image.Error)return true
      if(!errors && (!image || image.status!==Image.Ready))return false
    }
    return !errors && frameImages.count===frames[frameIndex].tiles.length
  }
  onImageErrorChanged: if(imageError) Qt.callLater(function(){if(root.imageError){root.playing=false;root.message="Radar image unavailable. Refresh to try again."}})
  function validLocal(value) { return typeof value === "string" && value.length <= 40 && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && isFinite(Date.parse(value)) }
  function dateTime(frame) {
    if(!frame) return "—"
    if(validLocal(frame.local_time) && formats) return formats.dayTime(frame.local_time)
    if(validLocal(frame.local_time)) return frame.local_time.slice(8,10)+"/"+frame.local_time.slice(5,7)+" "+frame.local_time.slice(11,16)
    return typeof frame.time === "number" && isFinite(frame.time) ? (formats ? formats.instant(frame.time) : new Date(frame.time*1000).toLocaleString(Qt.locale("en_GB"),"dd/MM hh:mm")) : "—"
  }
  function prepareCoverage() {
    coverageState="unknown"
    if(!active || !radarEnabled || projectionUnsupported || radar.coverage_status!=="available" || !coverageTiles.length || coverageImages.count!==coverageTiles.length) return false
    for(var i=0;i<coverageTiles.length;i++) {
      var image=coverageImages.itemAt(i), source=localSource(coverageTiles[i].source)
      if(!image || image.status!==Image.Ready || !source) return false
      if(coverageSampler.requested.indexOf(source)<0) {
        coverageSampler.requested=coverageSampler.requested.concat([source])
        coverageSampler.loadImage(source)
      }
      if(!coverageSampler.isImageLoaded(source)) return false
    }
    return true
  }
  function checkCoverage() { if(prepareCoverage())coverageSampler.requestPaint() }
  onRadarChanged: {
    coverageState="unknown"
    if(coverageSampler)coverageSampler.resetSources()
    Qt.callLater(checkCoverage)
  }

  function run(action, arg) {
    if (worker.running) {
      pending = {action: action, arg: arg}
      if (worker.action === "load" && action !== "load") worker.running = false
      return
    }
    pending = null
    worker.action = action
    worker.requestKey = cityKey
    worker.requestZoom = zoom
    worker.command = arg === undefined ? ["python3", "-B", scriptPath, action] : ["python3", "-B", scriptPath, action, JSON.stringify(arg)]
    worker.running = true
  }
  function refresh() {
    if (active && settingsLoaded && radarEnabled && cityKey !== "") run("load", city)
  }
  function configure(change) {
    if (change.enabled !== undefined) radarEnabled = change.enabled
    if (change.zoom !== undefined) { zoom = change.zoom; radar = ({}) }
    playing = false
    message = ""
    run("configure", {enabled: radarEnabled, zoom: zoom})
  }
  function step(delta) {
    playing = false
    if (frames.length) frameIndex = (frameIndex + delta + frames.length) % frames.length
  }
  onCityKeyChanged: {
    radar = ({})
    message = ""
    frameIndex = 0
    playing = false
    refresh()
  }
  onActiveChanged: {
    if (active) { refresh(); Qt.callLater(checkCoverage) }
    else {
      coverageState="unknown"
      playing = false
      if (pending && pending.action === "load") pending = null
      if (worker.running && worker.action === "load") worker.running = false
    }
  }
  Component.onCompleted: run("settings")

  Process {
    id: worker
    property bool timedOut: false
    onRunningChanged: if(running) {timedOut=false;requestDeadline.restart()} else requestDeadline.stop()
    property string action: ""
    property string requestKey: ""
    property int requestZoom: 6
    onExited: {
      if (root.pending) {
        var next = root.pending
        root.pending = null
        if (next.action !== "load" || (root.active && root.radarEnabled))
          Qt.callLater(function() { root.run(next.action, next.arg) })
      }
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if(worker.timedOut)return
        if (!text.trim()) return
        try {
          var parsed = JSON.parse(text)
          if (worker.action !== "load") {
            // A rapid click may have queued a newer complete preference set.
            if (root.pending && root.pending.action === "configure") return
            if (parsed.settings) {
              root.radarEnabled = parsed.settings.enabled === true
              root.zoom = parsed.settings.zoom || 6
              root.settingsLoaded = true
              root.refresh()
            }
          } else if (root.active && root.radarEnabled && worker.requestKey === root.cityKey && worker.requestZoom === root.zoom) {
            root.radar = parsed
            root.frameIndex = Math.max(0, root.frames.length - 1)
            root.message = parsed.error || parsed.message || ""
          }
        } catch (e) { root.message = "Radar data unavailable" }
      }
    }
  }
  Timer {
    id: requestDeadline
    objectName: "radar-request-deadline"
    interval: 50000
    onTriggered: {worker.timedOut=true;root.pending=null;worker.running=false;root.playing=false;root.message="Radar request timed out. Please try again."}
  }
  Timer {
    interval: 600000
    repeat: true
    running: root.active && root.radarEnabled && root.settingsLoaded
    onTriggered: if (!worker.running) root.refresh()
  }
  Timer {
    interval: 800
    repeat: true
    running: root.active && root.radarEnabled && root.playing && root.imageReady && root.frames.length > 1 && Commons.Style.duration(1) > 0
    onTriggered: root.frameIndex = (root.frameIndex + 1) % root.frames.length
  }

  component RadarButton: Ui.Button {
    id: button
    property string label: ""
    property string accessibleLabel: label
    width: Commons.Style.space(38)
    height: Commons.Style.space(36)
    text: label
    fontSize: width > Commons.Style.space(60) ? Commons.Style.font.bodySmall : Commons.Style.font.title
    background: root.soft
    bordered: true
    focusable: true
    opacity: enabled ? 1 : 0.4
    Accessible.role: Accessible.Button
    Accessible.name: accessibleLabel
    Accessible.onPressAction: clicked()
  }

  Column {
    id: content
    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
    anchors.margins: Commons.Style.space(14)
    spacing: Commons.Style.space(10)
    Row {
      width: parent.width; spacing: Commons.Style.space(8)
      PText { width: parent.width - Commons.Style.space(104); anchors.verticalCenter: parent.verticalCenter; text: "Precipitation radar"; font.bold: true; font.pixelSize: Commons.Style.font.body; elide: Text.ElideRight }
      RadarButton { width: Commons.Style.space(96); label: root.radarEnabled ? "Disable" : "Enable"; accessibleLabel: root.radarEnabled ? "Disable radar" : "Enable radar"; onClicked: root.configure({enabled: !root.radarEnabled}) }
    }
    PText {
      width: parent.width
      visible: !root.radarEnabled
      text: "Enable the map to see recent radar images. RainViewer and OpenStreetMap receive the area around this city. Updates every 10 minutes, only while this map is visible."
      wrapMode: Text.WordWrap; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall
    }
    Column {
      width: parent.width; spacing: Commons.Style.space(8); visible: root.radarEnabled
      Item {
        id: viewport
        visible: !root.projectionUnsupported
        width: parent.width; height: width * 240 / 432
        clip: true
        Rectangle { anchors.fill: parent; color: "#dce7e5"; radius: Commons.Style.cornerRadius }
        Item {
          width: 432; height: 240
          scale: viewport.width / 432
          transformOrigin: Item.TopLeft
          Repeater {
            model: root.radar.tiles || []
            delegate: Image {
              required property var modelData
              x: modelData.left; y: modelData.top; width: 256; height: 256
              source: root.localSource(modelData.source); asynchronous: true
              sourceSize.width: 256; sourceSize.height: 256
            }
          }
          Repeater {
            id: frameImages
            model: root.radar.tiles || []
            onCountChanged: root.imageRevision++
            delegate: Image {
              required property var modelData
              required property int index
              x: modelData.left; y: modelData.top; width: 256; height: 256
              source: root.frames.length > root.frameIndex && Array.isArray(root.frames[root.frameIndex].tiles) ? root.localSource(root.frames[root.frameIndex].tiles[index]) : ""
              opacity: 0.8; asynchronous: false
              sourceSize.width: 256; sourceSize.height: 256
              onStatusChanged: root.imageRevision++
            }
          }
          Repeater {
            id: coverageImages
            model: root.coverageTiles
            delegate: Image {
              required property var modelData
              source: root.localSource(modelData.source)
              visible: false; asynchronous: true
              sourceSize.width: 256; sourceSize.height: 256
              onStatusChanged: Qt.callLater(root.checkCoverage)
            }
          }
          Canvas {
            id: coverageSampler
            anchors.fill: parent; opacity: 0.18
            visible: root.active && root.radarEnabled
            property var requested: []
            function resetSources() { for(var i=0;i<requested.length;i++)unloadImage(requested[i]);requested=[];requestPaint() }
            onImageLoaded: Qt.callLater(root.checkCoverage)
            onPaint: {
              var context=getContext("2d");context.reset();context.clearRect(0,0,width,height)
              if(!root.prepareCoverage())return
              try {
                for(var i=0;i<root.coverageTiles.length;i++) {
                  var tile=root.coverageTiles[i]
                  context.drawImage(root.localSource(tile.source),tile.left,tile.top,256,256)
                }
                var alpha=context.getImageData(216,120,1,1).data[3]
                root.coverageState=alpha===0?"covered":alpha===255?"uncovered":"unknown"
              } catch(error) {root.coverageState="unknown"}
            }
          }
          Rectangle {
            anchors.centerIn: parent; width: 12; height: 12; radius: 6
            color: Commons.Color.accent; border.color: "white"; border.width: 2
            visible: root.imageReady
          }
        }
        Rectangle {
          anchors.centerIn: parent; width: Math.min(parent.width - 24, status.implicitWidth + 24); height: status.implicitHeight + 18; radius: Commons.Style.cornerRadius
          color: Commons.Color.background
          visible: root.busy || !root.imageReady
          PText { id: status; anchors.centerIn: parent; text: root.busy ? "Loading radar…" : "No image available"; font.pixelSize: Commons.Style.font.body }
        }
        Rectangle {
          anchors.bottom: parent.bottom; anchors.right: parent.right
          width: credit.implicitWidth + 12; height: 23
          color: "#eeffffff"
          PText { id: credit; anchors.centerIn: parent; text: "© OpenStreetMap contributors ↗"; color: "#203030"; font.pixelSize: Commons.Style.font.bodySmall }
          TapHandler { onTapped: Qt.openUrlExternally("https://www.openstreetmap.org/copyright") }
          Accessible.role: Accessible.Link; Accessible.name: "OpenStreetMap attribution"
          activeFocusOnTab: true
          Keys.onReturnPressed: Qt.openUrlExternally("https://www.openstreetmap.org/copyright")
        }
      }
      Row {
        visible: !root.projectionUnsupported
        width: parent.width; spacing: Commons.Style.space(6)
        RadarButton { label: "‹"; accessibleLabel: "Previous image"; enabled: root.frames.length > 0; onClicked: root.step(-1) }
        RadarButton { label: root.playing ? "Ⅱ" : "▶"; accessibleLabel: root.playing ? "Pause radar animation" : "Play radar animation"; enabled: root.frames.length > 1 && root.imageReady; onClicked: root.playing = !root.playing }
        RadarButton { label: "›"; accessibleLabel: "Next image"; enabled: root.frames.length > 0; onClicked: root.step(1) }
        PText { width: Math.max(0, parent.width - Commons.Style.space(264)); text: root.frameTime; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: Commons.Style.font.bodySmall; elide: Text.ElideRight }
        RadarButton { label: "−"; accessibleLabel: "Zoom out"; enabled: root.zoom > 3; onClicked: root.configure({zoom: root.zoom - 1}) }
        RadarButton { label: "+"; accessibleLabel: "Zoom in"; enabled: root.zoom < 7; onClicked: root.configure({zoom: root.zoom + 1}) }
        RadarButton { label: "↻"; accessibleLabel: "Refresh radar"; enabled: !root.busy; onClicked: root.refresh() }
      }
      Slider {
        id: timeline
        visible: !root.projectionUnsupported
        width: parent.width
        implicitHeight: Commons.Style.space(28)
        from: 0; to: Math.max(1, root.frames.length - 1); stepSize: 1
        value: root.frameIndex; enabled: root.frames.length > 1
        Accessible.name: "Radar timeline"
        onMoved: { root.playing = false; root.frameIndex = Math.round(value) }
        background: Rectangle {
          x: timeline.leftPadding
          y: timeline.topPadding + (timeline.availableHeight - height) / 2
          width: timeline.availableWidth; height: Commons.Style.space(4)
          radius: Commons.Style.cornerRadius > 0 ? height / 2 : 0
          color: Commons.Style.normalFillFor(Commons.Color.foreground, Commons.Color.accent)
          Rectangle {
            x: timeline.mirrored ? parent.width - width : 0
            width: parent.width * timeline.position; height: parent.height; radius: parent.radius
            color: Commons.Color.accent
          }
        }
        handle: Rectangle {
          x: timeline.leftPadding + timeline.visualPosition * (timeline.availableWidth - width)
          y: timeline.topPadding + (timeline.availableHeight - height) / 2
          width: Commons.Style.space(14); height: width
          radius: Commons.Style.cornerRadius > 0 ? width / 2 : 0
          color: timeline.enabled ? Commons.Color.foreground : root.muted
          border.width: timeline.activeFocus ? 2 : 1
          border.color: timeline.activeFocus ? Commons.Color.accent : Commons.Color.background
        }
      }
      Row {
        visible: !root.projectionUnsupported
        width: parent.width; spacing: Commons.Style.space(8)
        PText { width: parent.width / 2 - Commons.Style.space(4); text: root.frames.length ? root.dateTime(root.frames[0]) : "—"; font.pixelSize: Commons.Style.font.bodySmall; color: root.muted }
        PText { width: parent.width / 2 - Commons.Style.space(4); horizontalAlignment: Text.AlignRight; text: root.frames.length ? root.dateTime(root.frames[root.frames.length - 1]) : "—"; font.pixelSize: Commons.Style.font.bodySmall; color: root.muted }
      }
      PText { width: parent.width; visible: !root.projectionUnsupported && root.frames.length>0; text: root.clockLabel; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap }
      PText {
        objectName: "radar-coverage-status"; width: parent.width
        text: root.projectionUnsupported?"This map projection cannot show the selected location. Forecast weather is still available.":root.coverageState==="uncovered"?"No radar coverage at this location. Shaded areas have no radar observations.":root.coverageState==="covered"?"Radar covers this location. Shaded areas are outside coverage.":"Radar coverage is unverified here. A transparent image does not mean dry weather."
        color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap
      }
      RadarButton { objectName: "radar-forecast-cta"; width: parent.width; visible: root.projectionUnsupported || root.coverageState!=="covered"; label: root.projectionUnsupported?"See weather forecast":"See forecast map"; onClicked: root.forecastRequested() }
      PText { width: parent.width; visible: root.message !== ""; text: root.message; color: root.muted; wrapMode: Text.WordWrap; font.pixelSize: Commons.Style.font.bodySmall }
      PText { width: parent.width; visible: root.radar.stale === true; text: "Offline or outdated data · cached images"; color: root.muted; wrapMode: Text.WordWrap; font.pixelSize: Commons.Style.font.bodySmall }
      PText { width: parent.width; text: "Observed images · past 2 hours"; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall }
      RadarButton {
        objectName: "radar-details-toggle"
        width: parent.width
        label: root.detailsExpanded ? "Hide details" : "About this radar"
        Accessible.expandable: true
        Accessible.expanded: root.detailsExpanded
        onClicked: root.detailsExpanded = !root.detailsExpanded
      }
      PText {
        width: parent.width
        visible: root.detailsExpanded
        text: "Blue, yellow, then red indicate increasing intensity. Coverage varies; a transparent area does not guarantee no precipitation. Images update every 10 minutes, only while this map is visible."
        wrapMode: Text.WordWrap; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall
      }
      PText {
        width: parent.width; text: "Radar: RainViewer ↗ · past images · zoom " + root.zoom + "/7"; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall
        TapHandler { onTapped: Qt.openUrlExternally("https://www.rainviewer.com/") }
        activeFocusOnTab: true; Accessible.role: Accessible.Link; Accessible.name: "RainViewer radar data"
        Keys.onReturnPressed: Qt.openUrlExternally("https://www.rainviewer.com/")
        Rectangle { anchors.fill: parent; color: "transparent"; border.width: parent.activeFocus ? 1 : 0; border.color: Commons.Color.accent }
      }
    }
  }
}
