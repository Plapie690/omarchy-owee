import QtQuick
import QtQuick.Controls
import Quickshell.Io
import qs.Commons as Commons
import qs.Ui as Ui

Rectangle {
  id: root
  property var city: ({})
  property bool active: false
  property bool detailsExpanded: false
  property bool forecastEnabled: false
  property int zoom: 6
  property string selectedLayer: "precipitation"
  property bool settingsLoaded: false
  property var forecast: ({})
  property int frameIndex: 0
  property double selectedTime: 0
  property bool playing: false
  property bool legendExpanded: false
  property string message: ""
  property var queuedSettings: null
  property bool loadRequested: false
  property double queuedFrame: 0
  property int settingsRevision: 0
  property int dataRevision: 0
  property double clockEpoch: Date.now() / 1000
  readonly property bool busy: worker.running
  readonly property bool animationAllowed: Commons.Style.duration(1) > 0
  readonly property var frames: Array.isArray(forecast.frames) ? forecast.frames.filter(function(frame) { return typeof frame.time === "number" && isFinite(frame.time) && frame.time > root.clockEpoch }) : []
  readonly property var currentFrame: frames.length > frameIndex ? frames[frameIndex] : null
  readonly property var currentImages: currentFrame && Array.isArray(currentFrame.images) ? currentFrame.images : []
  readonly property bool imageReady: currentImages.length > 0 && currentImages.every(function(item) { return root.localSource(item.source) !== "" })
  readonly property string cityKey: city && city.latitude != null && city.longitude != null && isFinite(city.latitude) && isFinite(city.longitude) ? Number(city.latitude).toFixed(5) + "," + Number(city.longitude).toFixed(5) : ""
  readonly property string frameTime: currentFrame ? dateTime(currentFrame.time) : "—"
  readonly property var layerOptions: Array.isArray(forecast.layers) && forecast.layers.length ? forecast.layers : [
    {id: "precipitation", title: "Precipitation"}, {id: "temperature", title: "Temperature"}, {id: "clouds", title: "Clouds"}
  ]
  readonly property var legend: forecast.legend || ({})
  readonly property bool projectionUnsupported: forecast.status==="unsupported" && forecast.reason==="projection_limit"
  readonly property string frameClockLabel: currentFrame && validLocal(currentFrame.local_time)?"city local time · "+(currentFrame.timezone || forecast.timezone || ""):"desktop local time"
  readonly property string runClockLabel: validLocal(forecast.run_local_time)?"city local time · "+(forecast.timezone || ""):"desktop local time"
  readonly property color muted: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.72)
  readonly property color soft: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.075)
  readonly property color selectedColor: Qt.rgba(Commons.Color.accent.r, Commons.Color.accent.g, Commons.Color.accent.b, 0.2)
  readonly property string scriptPath: decodeURIComponent(Qt.resolvedUrl("forecast_map.py").toString().replace(/^file:\/\//, ""))
  implicitHeight: content.implicitHeight + Commons.Style.space(28)
  height: implicitHeight
  radius: Commons.Style.cornerRadius
  color: soft

  function localSource(value) {
    return typeof value === "string" && value.length < 4096 && value.indexOf("file:///") === 0 ? value : ""
  }
  function dateTime(stamp) {
    if (typeof stamp !== "number" || !isFinite(stamp) || stamp <= 0) return "—"
    var local=""
    if(stamp===forecast.run_time && validLocal(forecast.run_local_time))local=forecast.run_local_time
    else for(var i=0;i<frames.length;i++) if(frames[i].time===stamp && validLocal(frames[i].local_time)){local=frames[i].local_time;break}
    if(local)return local.slice(8,10)+"/"+local.slice(5,7)+" "+local.slice(11,16)
    return new Date(stamp * 1000).toLocaleString(Qt.locale("en_GB"), "dd/MM hh:mm")
  }
  function validLocal(value) { return typeof value === "string" && value.length <= 40 && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && isFinite(Date.parse(value)) }
  function launch(action, arg) {
    worker.action = action
    worker.requestKey = cityKey
    worker.requestZoom = zoom
    worker.requestLayer = selectedLayer
    worker.requestSettingsRevision = settingsRevision
    worker.requestDataRevision = dataRevision
    worker.requestTime = action === "frame" ? arg.time : 0
    worker.receivedOutput = false
    worker.command = arg === undefined ? ["python3", "-B", scriptPath, action] : ["python3", "-B", scriptPath, action, JSON.stringify(arg)]
    worker.running = true
  }
  function schedule() {
    if (worker.running) return
    if (queuedSettings !== null) {
      var config = queuedSettings
      queuedSettings = null
      launch("configure", config)
      return
    }
    if (!active || !forecastEnabled || !settingsLoaded || cityKey === "") return
    if (loadRequested) {
      loadRequested = false
      queuedFrame = 0
      launch("load", city)
    } else if (queuedFrame > 0) {
      var time = queuedFrame
      queuedFrame = 0
      launch("frame", {city: city, time: time})
    }
  }
  function cancelDataRequest() {
    loadRequested = false
    queuedFrame = 0
    if (worker.running && (worker.action === "load" || worker.action === "frame")) worker.running = false
  }
  function refresh() {
    if (!active || !forecastEnabled || !settingsLoaded || cityKey === "") return
    playing = false
    message = ""
    dataRevision++
    cancelDataRequest()
    selectedTime = 0
    loadRequested = true
    Qt.callLater(schedule)
  }
  function configure(change) {
    if (change.enabled !== undefined) forecastEnabled = change.enabled === true
    if (change.zoom !== undefined) zoom = Math.max(3, Math.min(7, Math.round(change.zoom)))
    if (change.layer !== undefined && ["precipitation", "temperature", "clouds"].indexOf(change.layer) >= 0) selectedLayer = change.layer
    settingsRevision++
    dataRevision++
    playing = false
    legendExpanded = false
    message = ""
    cancelDataRequest()
    forecast = ({})
    frameIndex = 0
    selectedTime = 0
    queuedSettings = {enabled: forecastEnabled, zoom: zoom, layer: selectedLayer}
    loadRequested = active && forecastEnabled
    Qt.callLater(schedule)
  }
  function requestSelectedFrame() {
    if (!active || !forecastEnabled || !currentFrame || imageReady) return
    var target = currentFrame.time
    if (worker.running && worker.action === "frame" && worker.requestTime === target && worker.requestDataRevision === dataRevision) return
    queuedFrame = target
    if (worker.running && worker.action === "frame") worker.running = false
    Qt.callLater(schedule)
  }
  function selectFrame(index, fetch, keepPlaying) {
    if (!frames.length) return
    if (!keepPlaying) playing = false
    frameIndex = Math.max(0, Math.min(frames.length - 1, Math.round(index)))
    selectedTime = frames[frameIndex].time
    message = ""
    if (fetch) requestSelectedFrame()
  }
  function step(delta) {
    if (frames.length) selectFrame((frameIndex + delta + frames.length) % frames.length, true, false)
  }
  function togglePlayback() {
    if (frames.length < 2 || !imageReady || !animationAllowed) return
    playing = !playing
  }
  function applyResult(parsed) {
    var wanted = selectedTime || parsed.selected_time || 0
    forecast = parsed
    var index = frames.findIndex(function(frame) { return frame.time === wanted })
    frameIndex = index >= 0 ? index : 0
    selectedTime = frames.length ? frames[frameIndex].time : 0
    message = parsed.error || parsed.message || ""
    if (parsed.error || parsed.stale === true || !imageReady) playing = false
  }
  onFramesChanged: {
    var previous = selectedTime
    var index = frames.findIndex(function(frame) { return frame.time === previous })
    frameIndex = index >= 0 ? index : 0
    selectedTime = frames.length ? frames[frameIndex].time : 0
    if (previous > 0 && previous <= clockEpoch) {
      playing = false
      queuedFrame = 0
      message = frames.length ? "This forecast time has passed. Choose a later time or refresh the map." : "Cached forecast times have passed. Refresh the map."
    }
  }
  onCityKeyChanged: {
    dataRevision++
    cancelDataRequest()
    forecast = ({})
    selectedTime = 0
    frameIndex = 0
    playing = false
    message = ""
    if (active && forecastEnabled && settingsLoaded) { loadRequested = true; Qt.callLater(schedule) }
  }
  onActiveChanged: {
    clockEpoch = Date.now() / 1000
    dataRevision++
    playing = false
    cancelDataRequest()
    if (active && forecastEnabled && settingsLoaded) { loadRequested = true; Qt.callLater(schedule) }
  }
  onAnimationAllowedChanged: if (!animationAllowed) playing = false
  Component.onCompleted: launch("settings")

  Process {
    id: worker
    property string action: ""
    property string requestKey: ""
    property int requestZoom: 6
    property string requestLayer: "precipitation"
    property int requestSettingsRevision: 0
    property int requestDataRevision: 0
    property double requestTime: 0
    property bool receivedOutput: false
    onExited: {
      if (!receivedOutput && root.active && root.forecastEnabled && requestDataRevision === root.dataRevision && root.queuedFrame === 0 && !root.loadRequested && root.queuedSettings === null && (action === "load" || action === "frame")) {
        root.message = "Loading interrupted or forecast unavailable. Please try again."
        root.playing = false
      }
      Qt.callLater(root.schedule)
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (!text.trim()) return
        worker.receivedOutput = true
        try {
          var parsed = JSON.parse(text)
          if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Invalid forecast result")
          if (worker.action === "settings" || worker.action === "configure") {
            if (worker.requestSettingsRevision !== root.settingsRevision || root.queuedSettings !== null) return
            if (!parsed.settings) { root.message = parsed.error || "Map settings unavailable"; return }
            root.forecastEnabled = parsed.settings.enabled === true
            root.zoom = Math.max(3, Math.min(7, parsed.settings.zoom || 6))
            root.selectedLayer = ["precipitation", "temperature", "clouds"].indexOf(parsed.settings.layer) >= 0 ? parsed.settings.layer : "precipitation"
            root.settingsLoaded = true
            root.message = parsed.error || ""
            root.loadRequested = !parsed.error && root.active && root.forecastEnabled && root.cityKey !== ""
            if (parsed.error) { root.queuedFrame = 0; root.playing = false }
          } else if (root.active && root.forecastEnabled && worker.requestKey === root.cityKey && worker.requestZoom === root.zoom && worker.requestLayer === root.selectedLayer && worker.requestDataRevision === root.dataRevision) {
            root.applyResult(parsed)
          }
        } catch (e) {
          root.message = "Map data unavailable"
          root.playing = false
        }
      }
    }
  }
  // One visible image at a time; no forecast sequence is downloaded in advance.
  Timer {
    interval: 3000
    repeat: true
    running: root.active && root.forecastEnabled && root.playing && root.animationAllowed && !root.busy && root.imageReady && root.frames.length > 1
    onTriggered: root.selectFrame((root.frameIndex + 1) % root.frames.length, true, true)
  }
  Timer { interval: 1000; repeat: true; running: root.active && root.forecastEnabled; onTriggered: root.clockEpoch = Date.now() / 1000 }

  component MapButton: Ui.Button {
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
    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: Commons.Style.space(14)
    spacing: Commons.Style.space(10)
    Row {
      width: parent.width; spacing: Commons.Style.space(8)
      PText { width: parent.width - Commons.Style.space(104); anchors.verticalCenter: parent.verticalCenter; text: "Forecast map"; font.bold: true; font.pixelSize: Commons.Style.font.body; elide: Text.ElideRight }
      MapButton { objectName: "forecast-enable"; width: Commons.Style.space(96); label: root.forecastEnabled ? "Disable" : "Enable"; accessibleLabel: root.forecastEnabled ? "Disable forecast map" : "Enable forecast map"; onClicked: root.configure({enabled: !root.forecastEnabled}) }
    }
    PText {
      width: parent.width; visible: !root.forecastEnabled
      text: "Global GDPS model forecasts on a 15 km grid. ECCC GeoMet and OpenStreetMap receive the area around this city. Only the selected time is downloaded, while this map is visible."
      wrapMode: Text.WordWrap; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall
    }
    PText { width: parent.width; visible: !root.forecastEnabled && root.message !== ""; text: root.message; color: root.muted; wrapMode: Text.WordWrap; font.pixelSize: Commons.Style.font.bodySmall }
    Column {
      width: parent.width; spacing: Commons.Style.space(9); visible: root.forecastEnabled
      Row {
        visible: !root.projectionUnsupported
        width: parent.width; spacing: Commons.Style.space(6)
        Repeater {
          model: root.layerOptions
          delegate: MapButton {
            required property var modelData
            objectName: "forecast-layer-" + modelData.id
            width: (content.width - Commons.Style.space(12)) / 3
            label: modelData.id === "precipitation" ? "Precipitation" : modelData.id === "temperature" ? "Temperature" : "Clouds"
            accessibleLabel: modelData.title
            selected: root.selectedLayer === modelData.id
            onClicked: if (root.selectedLayer !== modelData.id) root.configure({layer: modelData.id})
          }
        }
      }
      PText { width: parent.width; text: root.forecast.title || "GDPS model forecast"; font.bold: true; font.pixelSize: Commons.Style.font.body; wrapMode: Text.WordWrap }
      Item {
        id: viewport
        visible: !root.projectionUnsupported
        objectName: "forecast-viewport"
        width: parent.width; height: width * 240 / 432; clip: true
        activeFocusOnTab: true
        Accessible.role: Accessible.Graphic
        Accessible.name: "Forecast map, " + root.frameTime + ", " + (root.forecast.title || root.selectedLayer)
        Keys.onPressed: function(event) {
          var key = Commons.Util.readingKey(event)
          if (key === Qt.Key_Left) { root.step(-1); event.accepted = true }
          else if (key === Qt.Key_Right) { root.step(1); event.accepted = true }
          else if (key === Qt.Key_Space) { root.togglePlayback(); event.accepted = true }
        }
        Rectangle { anchors.fill: parent; color: "#dce7e5"; radius: Commons.Style.cornerRadius; border.width: viewport.activeFocus ? 2 : 0; border.color: Commons.Color.accent }
        Item {
          width: 432; height: 240; scale: viewport.width / 432; transformOrigin: Item.TopLeft
          Repeater {
            model: root.forecast.tiles || []
            delegate: Image {
              required property var modelData
              x: modelData.left; y: modelData.top; width: 256; height: 256
              source: root.localSource(modelData.source); asynchronous: true
              sourceSize.width: 256; sourceSize.height: 256
            }
          }
          Repeater {
            model: root.currentImages
            delegate: Image {
              required property var modelData
              x: modelData.left || 0; y: modelData.top || 0
              width: modelData.width; height: modelData.height
              source: root.localSource(modelData.source); asynchronous: false
              opacity: 0.78
            }
          }
          Rectangle { anchors.centerIn: parent; width: 12; height: 12; radius: 6; color: Commons.Color.accent; border.color: "white"; border.width: 2; visible: root.imageReady }
        }
        Rectangle {
          anchors.centerIn: parent; width: Math.min(parent.width - 24, status.implicitWidth + 24); height: status.implicitHeight + 18; radius: Commons.Style.cornerRadius
          color: Commons.Color.background; visible: !root.imageReady
          PText { id: status; anchors.centerIn: parent; text: root.busy ? "Loading this forecast time…" : "No image available"; font.pixelSize: Commons.Style.font.bodySmall }
        }
        Rectangle {
          anchors.bottom: parent.bottom; anchors.right: parent.right; width: credit.implicitWidth + 12; height: 23; color: "#eeffffff"
          PText { id: credit; anchors.centerIn: parent; text: "© OpenStreetMap contributors ↗"; color: "#203030"; font.pixelSize: Commons.Style.font.bodySmall }
          TapHandler { onTapped: Qt.openUrlExternally("https://www.openstreetmap.org/copyright") }
          activeFocusOnTab: true; Accessible.role: Accessible.Link; Accessible.name: "OpenStreetMap attribution"
          Keys.onReturnPressed: Qt.openUrlExternally("https://www.openstreetmap.org/copyright")
        }
      }
      PText { width: parent.width; visible: !root.projectionUnsupported; text: "Valid at: " + root.frameTime + " · "+root.frameClockLabel; font.bold: true; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap }
      Row {
        visible: !root.projectionUnsupported
        width: parent.width; spacing: Commons.Style.space(6)
        MapButton { objectName: "forecast-previous"; label: "‹"; accessibleLabel: "Previous forecast time"; enabled: root.frames.length > 1; onClicked: root.step(-1) }
        MapButton { objectName: "forecast-play"; label: root.playing ? "Ⅱ" : "▶"; accessibleLabel: root.playing ? "Pause forecast playback" : "Play forecasts, one time step every three seconds"; enabled: root.frames.length > 1 && root.imageReady && root.animationAllowed; onClicked: root.togglePlayback() }
        MapButton { objectName: "forecast-next"; label: "›"; accessibleLabel: "Next forecast time"; enabled: root.frames.length > 1; onClicked: root.step(1) }
        PText { width: Math.max(0, parent.width - Commons.Style.space(264)); text: root.playing ? "Playing" : "Step by step"; color: root.muted; anchors.verticalCenter: parent.verticalCenter; font.pixelSize: Commons.Style.font.bodySmall; elide: Text.ElideRight }
        MapButton { objectName: "forecast-zoom-out"; label: "−"; accessibleLabel: "Zoom out forecast map"; enabled: root.zoom > 3; onClicked: root.configure({zoom: root.zoom - 1}) }
        MapButton { objectName: "forecast-zoom-in"; label: "+"; accessibleLabel: "Zoom in forecast map"; enabled: root.zoom < 7; onClicked: root.configure({zoom: root.zoom + 1}) }
        MapButton { objectName: "forecast-refresh"; label: "↻"; accessibleLabel: "Refresh forecast map"; enabled: !root.busy; onClicked: root.refresh() }
      }
      Slider {
        visible: !root.projectionUnsupported
        id: timeline
        objectName: "forecast-timeline"
        implicitHeight: Commons.Style.space(28)
        width: parent.width; from: 0; to: Math.max(1, root.frames.length - 1); stepSize: 1
        value: root.frameIndex; enabled: root.frames.length > 1
        Accessible.name: "Forecast map time"
        onMoved: root.selectFrame(Math.round(value), !pressed, false)
        onPressedChanged: if (!pressed) root.selectFrame(Math.round(value), true, false)
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
        PText { width: parent.width / 2 - Commons.Style.space(4); text: root.frames.length ? root.dateTime(root.frames[0].time) : "—"; font.pixelSize: Commons.Style.font.bodySmall; color: root.muted }
        PText { width: parent.width / 2 - Commons.Style.space(4); horizontalAlignment: Text.AlignRight; text: root.frames.length ? root.dateTime(root.frames[root.frames.length - 1].time) : "—"; font.pixelSize: Commons.Style.font.bodySmall; color: root.muted }
      }
      PText { width: parent.width; text: root.legend.caption || (root.forecast.unit ? "Unit: " + root.forecast.unit : ""); visible: text !== ""; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap }
      MapButton {
        objectName: "forecast-legend-toggle"
        width: parent.width
        visible: root.localSource(root.legend.source) !== ""
        label: root.legendExpanded ? "Hide legend ⌃" : "Show legend ⌄"
        accessibleLabel: label
        onClicked: root.legendExpanded = !root.legendExpanded
      }
      Column {
        width: parent.width; spacing: Commons.Style.space(5); visible: root.legendExpanded && root.localSource(root.legend.source) !== ""
        Rectangle {
          width: parent.width; height: legendImage.height + 12; radius: Commons.Style.cornerRadius; color: "#f6f6f6"
          Image {
            id: legendImage
            anchors.horizontalCenter: parent.horizontalCenter; y: 6
            width: Math.min(parent.width - 16, root.legend.width || 270)
            height: Math.min(600, (root.legend.height || 64) * width / (root.legend.width || width))
            fillMode: Image.PreserveAspectFit
            source: root.localSource(root.legend.source)
          }
        }
      }
      PText { width: parent.width; visible: root.message !== ""; text: root.message; color: root.muted; wrapMode: Text.WordWrap; font.pixelSize: Commons.Style.font.bodySmall }
      PText { width: parent.width; visible: root.forecast.stale === true; text: "Offline or older model · cached forecasts, dates shown above"; color: root.muted; wrapMode: Text.WordWrap; font.pixelSize: Commons.Style.font.bodySmall }
      PText { width: parent.width; visible: !root.animationAllowed; text: "Animations disabled in Omarchy · arrows and timeline remain available."; color: root.muted; wrapMode: Text.WordWrap; font.pixelSize: Commons.Style.font.bodySmall }
      PText { width: parent.width; visible: !!root.forecast.run_time; text: "Model run: " + root.dateTime(root.forecast.run_time) + " · "+root.runClockLabel; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap }
      PText { width: parent.width; visible: root.projectionUnsupported; text: "The selected location is outside this map projection. Its coordinates have not moved; use the Weather view for numeric forecasts."; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap }
      MapButton {
        objectName: "forecast-details-toggle"
        width: parent.width
        label: root.detailsExpanded ? "Hide details" : "About this forecast"
        Accessible.expandable: true
        Accessible.expanded: root.detailsExpanded
        onClicked: root.detailsExpanded = !root.detailsExpanded
      }
      PText {
        width: parent.width
        visible: root.detailsExpanded
        text: "Model forecast · " + (root.forecast.model || "GDPS") + " · grid spacing " + (root.forecast.resolution || "15 km") + ". Model results may differ from local conditions. Each forecast time is downloaded on demand, with no timeline prefetching."
        color: root.muted; wrapMode: Text.WordWrap; font.pixelSize: Commons.Style.font.bodySmall
      }
      PText { width: parent.width; text: "Data source: Environment and Climate Change Canada"; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap }
      PText {
        width: parent.width; text: "GDPS / GeoMet ↗ · zoom " + root.zoom + "/7"; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall
        TapHandler { onTapped: Qt.openUrlExternally("https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps-geomet_en/") }
        activeFocusOnTab: true; Accessible.role: Accessible.Link; Accessible.name: "GDPS forecast source: Environment and Climate Change Canada"
        Keys.onReturnPressed: Qt.openUrlExternally("https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps-geomet_en/")
        Rectangle { anchors.fill: parent; color: "transparent"; border.width: parent.activeFocus ? 1 : 0; border.color: Commons.Color.accent }
      }
      PText {
        width: parent.width; text: "Environment Canada Open Data Licence ↗"; color: root.muted; font.pixelSize: Commons.Style.font.bodySmall; wrapMode: Text.WordWrap
        TapHandler { onTapped: Qt.openUrlExternally("https://eccc-msc.github.io/open-data/licence/readme_en/") }
        activeFocusOnTab: true; Accessible.role: Accessible.Link; Accessible.name: text
        Keys.onReturnPressed: Qt.openUrlExternally("https://eccc-msc.github.io/open-data/licence/readme_en/")
        Rectangle { anchors.fill: parent; color: "transparent"; border.width: parent.activeFocus ? 1 : 0; border.color: Commons.Color.accent }
      }
    }
  }
}
