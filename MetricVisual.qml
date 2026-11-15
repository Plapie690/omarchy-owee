import QtQuick
import qs.Commons as Commons

Canvas {
  id: visual
  property string kind: ""
  property real reading: NaN
  property real direction: NaN
  property real dayProgress: NaN
  readonly property bool known: isFinite(reading)
  readonly property color ink: Commons.Color.accent
  readonly property color track: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.16)
  readonly property color wash: Qt.rgba(ink.r, ink.g, ink.b, 0.2)
  Accessible.ignored: true
  onKindChanged: requestPaint()
  onReadingChanged: requestPaint()
  onDirectionChanged: requestPaint()
  onDayProgressChanged: requestPaint()
  onInkChanged: requestPaint()
  onTrackChanged: requestPaint()
  onWidthChanged: requestPaint()
  onHeightChanged: requestPaint()
  onVisibleChanged: if (visible) requestPaint()

  onPaint: {
    var ctx = getContext("2d")
    ctx.reset()
    ctx.clearRect(0, 0, width, height)
    ctx.scale(width / 160, height / 52)
    ctx.lineWidth = 2
    ctx.lineCap = "round"
    ctx.lineJoin = "round"
    ctx.strokeStyle = track
    ctx.fillStyle = wash
    function line(x, y, endX, endY, color) {
      ctx.strokeStyle = color; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(endX, endY); ctx.stroke()
    }
    function dot(x, y, radius, color) {
      ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill()
    }
    function arc(start, end, color, weight) {
      ctx.lineWidth = weight; ctx.strokeStyle = color; ctx.beginPath(); ctx.arc(80, 47, 39, start, end); ctx.stroke()
    }
    function drop(x, y, size) {
      ctx.beginPath(); ctx.moveTo(x, y-size)
      ctx.bezierCurveTo(x-size, y, x-size, y+size, x, y+size)
      ctx.bezierCurveTo(x+size, y+size, x+size, y, x, y-size)
      ctx.fillStyle = wash; ctx.fill(); ctx.strokeStyle = ink; ctx.stroke()
    }
    if (kind === "humidity") {
      var level = known ? Math.max(0, Math.min(100, reading)) / 100 : 0
      var top = 44 - level * 33
      for (var i=0; i<4; i++) line(22, 10+i*11, 138, 10+i*11, track)
      if (known) {
        ctx.beginPath(); ctx.moveTo(22, top)
        ctx.bezierCurveTo(42, top-7, 52, top+7, 80, top)
        ctx.bezierCurveTo(105, top-7, 117, top+7, 138, top)
        ctx.lineTo(138, 46); ctx.lineTo(22, 46); ctx.closePath(); ctx.fillStyle=wash; ctx.fill()
        ctx.beginPath(); ctx.moveTo(22, top)
        ctx.bezierCurveTo(42, top-7, 52, top+7, 80, top)
        ctx.bezierCurveTo(105, top-7, 117, top+7, 138, top)
        ctx.strokeStyle=ink; ctx.stroke()
      }
    } else if (kind === "pressure" || kind === "uv") {
      var low = kind === "pressure" ? 950 : 0
      var high = kind === "pressure" ? 1050 : 11
      var progress = Math.max(0, Math.min(1, (reading-low)/(high-low)))
      arc(Math.PI, Math.PI*2, track, 5)
      if (known) {
        arc(Math.PI, Math.PI+Math.PI*progress, ink, 5)
        dot(80+39*Math.cos(Math.PI+Math.PI*progress), 47+39*Math.sin(Math.PI+Math.PI*progress), 4, ink)
      }
      ctx.lineWidth=1
      for (var tick=0; tick<=8; tick++) {
        var angle=Math.PI+Math.PI*tick/8
        line(80+29*Math.cos(angle), 47+29*Math.sin(angle), 80+32*Math.cos(angle), 47+32*Math.sin(angle), track)
      }
    } else if (kind === "sun") {
      ctx.setLineDash([3, 4]); arc(Math.PI, 2*Math.PI, track, 1.5); ctx.setLineDash([])
      line(25, 46, 135, 46, track)
      if (isFinite(dayProgress)) {
        var phase=Math.max(0, Math.min(1, dayProgress)), theta=Math.PI+phase*Math.PI
        arc(Math.PI, theta, ink, 2)
        var sx=80+39*Math.cos(theta), sy=47+39*Math.sin(theta)
        dot(sx, sy, 5, ink)
        for (var ray=0; ray<8; ray++) {
          var a=ray*Math.PI/4
          line(sx+8*Math.cos(a), sy+8*Math.sin(a), sx+10*Math.cos(a), sy+10*Math.sin(a), ink)
        }
      }
      dot(41, 46, 2, ink); dot(119, 46, 2, ink)
    } else if (kind === "wind") {
      ctx.lineWidth=1.5
      ctx.beginPath(); ctx.arc(80, 26, 19, 0, Math.PI*2); ctx.strokeStyle=track; ctx.stroke()
      line(80, 3, 80, 8, track); line(80, 44, 80, 49, track)
      line(57, 26, 62, 26, track); line(98, 26, 103, 26, track)
      line(20, 17, 45, 17, track); line(12, 26, 41, 26, ink); line(22, 35, 45, 35, track)
      line(115, 17, 140, 17, track); line(119, 26, 148, 26, ink); line(115, 35, 138, 35, track)
      if (isFinite(direction)) {
        ctx.save(); ctx.translate(80,26); ctx.rotate(direction*Math.PI/180)
        ctx.beginPath(); ctx.moveTo(0,-15); ctx.lineTo(6,10); ctx.lineTo(0,6); ctx.lineTo(-6,10); ctx.closePath()
        ctx.fillStyle=ink; ctx.fill(); ctx.restore()
      }
    } else if (kind === "visibility") {
      ctx.beginPath(); ctx.moveTo(26,26); ctx.bezierCurveTo(52,-2,108,-2,134,26)
      ctx.bezierCurveTo(108,54,52,54,26,26); ctx.closePath(); ctx.strokeStyle=track; ctx.stroke()
      ctx.beginPath(); ctx.arc(80,26,15,0,2*Math.PI); ctx.fillStyle=wash; ctx.fill(); ctx.strokeStyle=ink; ctx.stroke()
      dot(80,26,5,ink); dot(85,21,2,Commons.Color.background)
    } else if (kind === "precipitation") {
      drop(48,25,8); drop(80,20,11); drop(112,25,8)
      line(37,46,60,46,track); line(70,46,90,46,track); line(100,46,123,46,track)
    } else if (kind === "air") {
      for (var flow=0; flow<3; flow++) {
        var y=13+flow*13
        ctx.beginPath(); ctx.moveTo(24,y); ctx.bezierCurveTo(53,y-10,100,y+10,136,y)
        ctx.strokeStyle=flow===1?ink:track; ctx.stroke()
      }
      dot(45,10,3,ink); dot(111,40,3,ink); dot(126,18,2,track)
    } else if (kind === "pollen") {
      ctx.save(); ctx.translate(80,26)
      for (var petal=0; petal<6; petal++) {
        ctx.rotate(Math.PI/3); ctx.beginPath(); ctx.moveTo(0,-5)
        ctx.bezierCurveTo(-15,-28,15,-28,0,-5); ctx.fillStyle=wash; ctx.fill(); ctx.strokeStyle=ink; ctx.stroke()
      }
      dot(0,0,4,ink); ctx.restore(); dot(40,16,2,track); dot(120,36,2,track)
    }
  }
}
