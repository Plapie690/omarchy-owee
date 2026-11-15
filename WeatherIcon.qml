import QtQuick
import qs.Commons as Commons
import "WeatherModel.js" as WeatherModel

// A fixed square keeps optical size stable when the weather changes.
Canvas {
    id: root
    property var code: null
    property bool night: false
    property color ink: Commons.Color.foreground
    readonly property string family: WeatherModel.family(code)
    implicitWidth: 24
    implicitHeight: 24
    onFamilyChanged: requestPaint()
    onNightChanged: requestPaint()
    onInkChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        var c = getContext("2d")
        c.reset()
        c.scale(width / 24, height / 24)
        c.strokeStyle = ink; c.fillStyle = ink
        c.lineWidth = 1.65; c.lineCap = "round"; c.lineJoin = "round"
        function line(x,y,xx,yy) { c.beginPath(); c.moveTo(x,y); c.lineTo(xx,yy); c.stroke() }
        function circle(x,y,r) { c.beginPath(); c.arc(x,y,r,0,Math.PI*2); c.stroke() }
        function sun(x,y,r) {
            if (night) {
                c.beginPath(); c.moveTo(x+2,y-r)
                c.bezierCurveTo(x-r-5,y-r+1,x-r-3,y+r+5,x+4,y+r-1)
                c.bezierCurveTo(x-2,y+r,x-4,y-r+2,x+2,y-r)
                c.stroke()
            } else {
                circle(x,y,r)
                for (var i=0;i<8;i++) {
                    var a=i*Math.PI/4
                    line(x+(r+2)*Math.cos(a),y+(r+2)*Math.sin(a),x+(r+3.5)*Math.cos(a),y+(r+3.5)*Math.sin(a))
                }
            }
        }
        function cloud() {
            c.beginPath(); c.moveTo(6,16)
            c.bezierCurveTo(0,16,1,8,6,9)
            c.bezierCurveTo(7,2,16,3,17,10)
            c.bezierCurveTo(23,9,24,16,18,16)
            c.closePath(); c.stroke()
        }
        if (family === "unknown") { circle(12,12,7); line(9,12,15,12); return }
        if (family === "clear") { sun(12,12,4); return }
        if (family === "mostlyClear" || family === "partlyCloudy") sun(16,7,2.5)
        // Backing fill makes a cloud legible over the small sun's rays.
        if (family === "mostlyClear" || family === "partlyCloudy") {
            c.clearRect(1,10,22,8)
        }
        cloud()
        if (family === "rain") { line(7,19,6,21); line(12,19,11,21); line(17,19,16,21) }
        if (family === "snow") {
            for (var j=0;j<3;j++) { var x=7+j*5; line(x-1,20,x+1,20); line(x,19,x,21) }
        }
        if (family === "fog") { line(5,19,20,19); line(7,22,17,22) }
        if (family === "storm") {
            c.beginPath(); c.moveTo(13,16); c.lineTo(10,20); c.lineTo(14,20); c.lineTo(12,23); c.stroke()
        }
    }
}
