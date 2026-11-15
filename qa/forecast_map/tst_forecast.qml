import QtQuick
import QtTest
import qs.Commons as Commons
import "plugin" as Weather

Item {
  width: 500; height: 1400
  Weather.ForecastMap { id: map; x: 14; y: 14; width: 432 }

  TestCase {
    name: "FutureForecastMap"
    when: windowShown
    function settled() { tryVerify(function() { return !map.busy && map.queuedSettings === null && !map.loadRequested && map.queuedFrame === 0 }, 6000) }
    function init() {
      Commons.Style.animations = true
      map.active = false
      map.configure({enabled:false,zoom:6,layer:"precipitation"})
      settled()
      map.city = {name:"Lyon",latitude:45.75,longitude:4.85}
      map.clockEpoch = Date.now()/1000
      map.forecast = ({})
      map.selectedTime = 0
      map.message = ""
    }
    function cleanup() { map.active = false; settled() }
    function activate() {
      map.active = true
      map.configure({enabled:true})
      tryVerify(function() { return map.imageReady && !map.busy }, 7000)
      compare(map.frames.length,4)
    }
    function control(name) { var item = findChild(map,name); verify(item !== null,"Missing control "+name); return item }
    function click(name) { waitForPolish(map); wait(50); var item=control(name); mouseClick(item,item.width/2,item.height/2) }
    function countRequests(action) { return (map.forecast.request_trace || []).filter(function(item) { return item.action===action }).length }
    function test_disabled_card_never_loads_and_activation_only_fetches_first_frame() {
      compare(map.forecastEnabled,false)
      compare(map.frames.length,0)
      map.active = true
      wait(80)
      compare(map.frames.length,0)
      click("forecast-enable")
      tryVerify(function() { return map.imageReady && !map.busy },7000)
      compare(map.frames.filter(function(frame){return frame.images.length>0}).length,1)
      compare(map.frameIndex,0)
      verify(map.frames[0].time>map.clockEpoch)
    }
    function test_pointer_step_fetches_only_selected_time_and_clears_previous_image_immediately() {
      activate()
      var before=countRequests("frame")
      click("forecast-next")
      compare(map.frameIndex,1)
      compare(map.currentImages.length,0)
      tryVerify(function(){return map.imageReady&&!map.busy},6000)
      compare(countRequests("frame"),before+1)
      compare(map.forecast.selected_time,map.currentFrame.time)
      compare(map.frames.filter(function(frame){return frame.images.length>0}).length,2)
    }
    function test_keyboard_navigation_and_pause() {
      activate()
      control("forecast-viewport").forceActiveFocus()
      keyClick(Qt.Key_Right)
      compare(map.frameIndex,1)
      tryVerify(function(){return map.imageReady&&!map.busy},6000)
      keyClick(Qt.Key_Space)
      compare(map.playing,true)
      keyClick(Qt.Key_Space)
      compare(map.playing,false)
    }
    function test_slider_drag_does_not_fetch_intermediate_frames() {
      activate()
      var slider=control("forecast-timeline")
      var before=countRequests("frame")
      mousePress(slider,8,slider.height/2,Qt.LeftButton)
      mouseMove(slider,slider.width/2,slider.height/2,30)
      wait(90)
      compare(countRequests("frame"),before)
      compare(map.busy,false)
      mouseMove(slider,slider.width-8,slider.height/2,30)
      mouseRelease(slider,slider.width-8,slider.height/2,Qt.LeftButton)
      tryVerify(function(){return map.imageReady&&!map.busy},6000)
      compare(map.frameIndex,3)
      compare(countRequests("frame"),before+1)
      compare(map.frames[1].images.length,0)
      compare(map.frames[2].images.length,0)
    }
    function test_explicit_playback_fetches_one_image_after_three_seconds() {
      activate()
      var before=countRequests("frame")
      click("forecast-play")
      compare(map.playing,true)
      wait(180)
      compare(map.frameIndex,0)
      compare(countRequests("frame"),before)
      tryVerify(function(){return map.frameIndex===1&&map.imageReady&&!map.busy},6500)
      compare(countRequests("frame"),before+1)
      map.playing=false
    }
    function test_closing_stops_playback_and_cancels_inflight_frame() {
      activate()
      map.playing=true
      map.step(1)
      tryCompare(map,"busy",true,1000)
      map.active=false
      compare(map.playing,false)
      settled()
      compare(map.queuedFrame,0)
      wait(200)
      compare(map.busy,false)
    }
    function test_latest_layer_and_city_win_over_cancelled_response() {
      activate()
      map.step(1)
      tryCompare(map,"busy",true,1000)
      map.configure({layer:"temperature"})
      map.configure({layer:"clouds"})
      map.city={name:"Paris",latitude:48.85,longitude:2.35}
      tryVerify(function(){return map.imageReady&&!map.busy&&map.forecast.city_name==="Paris"&&map.selectedLayer==="clouds"},8000)
      compare(map.forecast.settings.layer,"clouds")
      compare(map.currentImages.length,1)
      compare(map.forecast.title,"Clouds")
    }
    function test_network_error_stops_playback_and_never_relabels_old_image() {
      map.city={name:"Error",latitude:45.75,longitude:4.85}
      activate()
      map.playing=true
      map.selectFrame(1,true,true)
      tryVerify(function(){return !map.busy&&map.message!==""},6000)
      compare(map.playing,false)
      compare(map.currentImages.length,0)
      verify(map.message.indexOf("Connexion")>=0)
    }
    function test_expired_frames_are_pruned_without_network() {
      activate()
      var first=map.frames[0].time
      map.playing=true
      var before=countRequests("frame")
      map.clockEpoch=first+1
      compare(map.frames.length,3)
      compare(map.playing,false)
      verify(map.currentFrame.time>map.clockEpoch)
      compare(map.currentImages.length,0)
      compare(countRequests("frame"),before)
      map.clockEpoch=map.forecast.frames[3].time+1
      compare(map.frames.length,0)
      compare(map.currentImages.length,0)
    }
    function test_legend_is_collapsed_and_expands_at_readable_native_size() {
      activate()
      compare(map.legendExpanded,false)
      var before=map.implicitHeight
      click("forecast-legend-toggle")
      compare(map.legendExpanded,true)
      tryVerify(function(){return map.implicitHeight>before+350},1000)
      click("forecast-legend-toggle")
      compare(map.legendExpanded,false)
    }
    function test_disabled_desktop_animations_leave_manual_controls() {
      activate()
      Commons.Style.animations=false
      compare(map.animationAllowed,false)
      click("forecast-play")
      compare(map.playing,false)
      click("forecast-next")
      tryVerify(function(){return map.imageReady&&!map.busy},6000)
      compare(map.frameIndex,1)
    }
    function test_failed_settings_save_is_reported_without_loading() {
      var worker=findChild(map,"forecast-worker-fixture")
      verify(worker!==null)
      worker.failNextConfig=true
      map.active=true
      map.configure({enabled:true})
      settled()
      compare(map.forecastEnabled,false)
      verify(map.message.indexOf("Enregistrement")>=0)
      compare(map.frames.length,0)
    }
    function test_dynamic_metadata_stays_plain_text() {
      activate()
      var attack='<img src="https://example.invalid/forecast-probe">'
      var payload=Object.assign({},map.forecast)
      payload.title=attack
      payload.legend=Object.assign({},payload.legend,{caption:attack})
      map.forecast=payload
      wait(20)
      var count=0
      function visit(item) {
        if (item.text===attack) { compare(item.textFormat,Text.PlainText);count++ }
        for(var i=0;item.children&&i<item.children.length;i++)visit(item.children[i])
      }
      visit(map)
      verify(count>=2)
    }
    function test_remote_images_are_never_loaded() {
      compare(map.localSource("https://example.invalid/tracker.png"),"")
      compare(map.localSource("data:image/png;base64,evil"),"")
      compare(map.localSource("file:///tmp/safe.png"),"file:///tmp/safe.png")
      verify(map.dateTime(0)==="—")
    }
  }
}
