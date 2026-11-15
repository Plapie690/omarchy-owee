import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import "plugin" as Weather

ShellRoot {
  id: suite
  property var fixtures: @@FIXTURES@@
  property int step: 0
  property int attempts: 0
  property int forecastRequests: 0
  function check(ok, message) { if(!ok)throw new Error("QA_COVERAGE_FAIL: "+message) }
  function find(item, name) {
    if(!item)return null
    if(item.objectName===name)return item
    for(var i=0;item.children&&i<item.children.length;i++) {
      var found=find(item.children[i],name)
      if(found)return found
    }
    return null
  }
  Window {
    id: window
    visible: true; width: 460; height: 1200
    Weather.Radar {
      id: radar; width: 432; active: true
      city: ({latitude:45.75,longitude:4.85,timezone:"Asia/Tokyo"})
      onForecastRequested: suite.forecastRequests++
    }
    Weather.ForecastMap { id: forecast; y: 700; width: 432; active: false }
    TestEvent { id: events }
  }
  Timer {
    interval: 100; repeat: true; running: true
    onTriggered: {
      try {
        attempts++
        if(attempts>150)throw new Error("QA_COVERAGE_FAIL: stage "+step+" timed out; coverage="+radar.coverageState)
        if(step===0) {
          if(radar.busy||radar.coverageState!=="uncovered")return
          check(radar.frames.length===1,"transparent rain tiles preserve observations without implying dry weather")
          check(radar.clockLabel==="City local time · Asia/Tokyo"&&radar.frameTime===fixtures.radarCityClock,"radar uses the city timezone")
          console.warn("QA_COVERAGE_OPAQUE_PASS: opaque mask means outside radar coverage")
          radar.radar=fixtures.clear;step++;return
        }
        if(step===1) {
          if(radar.coverageState!=="covered")return
          console.warn("QA_COVERAGE_TRANSPARENT_PASS: transparent mask means covered")
          radar.radar=fixtures.partial;step++;return
        }
        if(step===2) {
          check(radar.coverageState==="unknown","one missing mask prevents a coverage claim")
          check(radar.frames.length===1,"a missing mask does not suppress valid observations")
          radar.radar=fixtures.unknown;step++;return
        }
        if(step===3) {
          check(radar.coverageState==="unknown","unverified coverage remains unknown despite valid opaque imagery")
          check(radar.localSource("https://example.invalid/mask.png")==="","remote image source is rejected")
          console.warn("QA_COVERAGE_UNKNOWN_PASS: partial and unverified masks remain unknown")
          forecast.forecast=fixtures.forecast;step++;return
        }
        if(step===4) {
          check(forecast.frameTime===fixtures.forecastCityClock,"forecast frame is formatted in Tokyo rather than desktop UTC")
          check(forecast.frameClockLabel==="city local time · Asia/Tokyo","forecast names its city timezone")
          check(forecast.dateTime(fixtures.forecast.run_time)===fixtures.radarCityClock&&forecast.runClockLabel==="city local time · Asia/Tokyo","model run is formatted in the city timezone")
          console.warn("QA_COVERAGE_CITY_TIME_PASS: radar, forecast and model times use Tokyo independently of desktop UTC")
          radar.radar=fixtures.fallback;forecast.forecast=fixtures.forecastFallback;step++;return
        }
        if(step===5) {
          check(radar.frameTime===fixtures.radarDesktopClock&&radar.clockLabel==="Desktop local time","invalid local radar timestamp is explicitly desktop time")
          check(forecast.frameTime===fixtures.forecastDesktopClock&&forecast.frameClockLabel==="desktop local time"&&forecast.runClockLabel==="desktop local time","invalid forecast local timestamps are explicitly desktop time")
          radar.city={latitude:90,longitude:12,timezone:"Etc/GMT"}
          radar.radar=fixtures.polar
          forecast.forecast=fixtures.polar
          step++;return
        }
        if(step===6) {
          if(radar.busy)return
          check(radar.projectionUnsupported&&forecast.projectionUnsupported,"both map projections report unsupported poles")
          check(radar.city.latitude===90&&radar.city.longitude===12&&radar.radar.latitude===90&&radar.radar.longitude===12,"selected polar point was not moved")
          var action=find(radar,"radar-forecast-cta")
          check(!!action&&action.visible&&action.text==="See weather forecast","polar fallback action points to numeric weather")
          check(events.mouseClick(action,action.width/2,action.height/2,Qt.LeftButton,Qt.NoModifier,1),"native fallback button receives a real click")
          check(forecastRequests===1,"fallback signal is emitted exactly once")
          console.warn("QA_COVERAGE_POLAR_PASS: unsupported projection keeps coordinates and emits native fallback action")
          console.warn("QA_COVERAGE_PASS: masks, missing data, projection limits, local clocks and fallback action")
          Qt.quit()
        }
      } catch(error) { console.error(error.message);Qt.exit(1) }
    }
  }
}
