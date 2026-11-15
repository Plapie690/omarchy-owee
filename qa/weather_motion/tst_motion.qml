import QtQuick
import QtTest
import qs.Commons as Commons
import "WeatherModel.js" as WeatherModel

Item {
  id: scene
  width:400; height:220
  TestCase {
    id: test
    name: "WeatherMotion"
    when: windowShown
    Component { id: skyComponent; Sky { width: 160; height: 110 } }
    Component { id: iconComponent; WeatherIcon { width: 48; height: 48 } }

    function init() { Commons.Style.animationsEnabled = true }

    function test_wmo_data() {
        var groups = {
            clear: [0], mostlyClear: [1], partlyCloudy: [2], cloudy: [3], fog: [45,48],
            rain: [51,53,55,56,57,61,63,65,66,67,80,81,82],
            snow: [71,73,75,77,85,86], storm: [95,96,99]
        }
        var data = []
        for (var family in groups)
            for (var i = 0; i < groups[family].length; i++)
                data.push({tag: String(groups[family][i]), code: groups[family][i], expected: family})
        return data
    }
    function test_wmo(row) { compare(WeatherModel.family(row.code), row.expected) }

    function test_unknown_data() {
        return [
            {tag:"null", value:null}, {tag:"undefined", value:undefined},
            {tag:"string", value:"0"}, {tag:"negative", value:-1},
            {tag:"unlisted", value:4}, {tag:"fraction", value:1.5},
            {tag:"nan", value:NaN}, {tag:"infinity", value:Infinity}
        ]
    }
    function test_unknown(row) { compare(WeatherModel.family(row.value), "unknown") }

    function test_icon_day_night_and_stable_size() {
        var icon = createTemporaryObject(iconComponent, scene, {code:0})
        verify(icon)
        wait(80)
        var day = grabImage(icon)
        icon.night = true
        wait(80)
        var night = grabImage(icon)
        verify(!day.equals(night), "Moon must differ from sun")
        var codes = [null,0,1,2,3,45,61,71,95]
        for (var i=0; i<codes.length; i++) {
            icon.code = codes[i]
            compare(icon.width,48); compare(icon.height,48)
            compare(icon.implicitWidth,24); compare(icon.implicitHeight,24)
        }
    }

    function test_intro_once_and_new_opening() {
        var sky = createTemporaryObject(skyComponent, scene, {code:0, openingSerial:1, active:true})
        verify(sky)
        tryCompare(sky,"openingRunning",true)
        tryCompare(sky,"openingRunning",false,1700)
        verify(sky.motionRunning)
        sky.code = 61
        wait(30)
        compare(sky.openingRunning,false)
        sky.openingSerial = 2
        tryCompare(sky,"openingRunning",true)
        sky.active = false
        compare(sky.motionRunning,false)
        compare(sky.openingRunning,false)
    }

    function test_hidden_pauses_without_intro_replay() {
        var sky = createTemporaryObject(skyComponent,scene,{code:3, openingSerial:3, active:true})
        tryCompare(sky,"openingRunning",true)
        wait(70)
        sky.active = false
        compare(sky.motionRunning,false)
        sky.active = true
        compare(sky.openingRunning,false)
        verify(sky.motionRunning)
        sky.active = false
    }

    function test_disabled_animation_and_live_toggle() {
        Commons.Style.animationsEnabled = false
        var sky = createTemporaryObject(skyComponent,scene,{code:95, openingSerial:4, active:true})
        wait(30)
        compare(sky.motionRunning,false)
        compare(sky.openingRunning,false)
        Commons.Style.animationsEnabled = true
        tryCompare(sky,"motionRunning",true)
        compare(sky.openingRunning,false)
        Commons.Style.animationsEnabled = false
        compare(sky.motionRunning,false)
        compare(sky.openingRunning,false)
    }

    function test_unknown_waits_for_real_condition() {
        var sky = createTemporaryObject(skyComponent,scene,{openingSerial:5,active:true})
        compare(sky.motionRunning,false)
        sky.code = 71
        tryCompare(sky,"openingRunning",true)
        sky.code = null
        compare(sky.motionRunning,false)
    }

    function test_each_weather_has_ambient_motion() {
        var codes = [0,1,2,3,45,61,71,95]
        for (var i=0; i<codes.length; i++) {
            var sky = createTemporaryObject(skyComponent,scene,{code:codes[i],active:true,openingSerial:6})
            verify(sky.motionRunning, "Motion for code " + codes[i])
            sky.active = false
            compare(sky.motionRunning,false)
            sky.destroy()
        }
    }

    function test_ambient_changes_pixels_then_stops_data() {
        return [
            {tag:"sun",code:0,night:false}, {tag:"moon",code:0,night:true},
            {tag:"mostly-clear",code:1,night:false}, {tag:"partly-cloudy",code:2,night:false},
            {tag:"overcast",code:3,night:false}, {tag:"fog",code:45,night:false},
            {tag:"rain",code:61,night:false}, {tag:"snow",code:71,night:false},
            {tag:"storm",code:95,night:false}
        ]
    }

    function changedSamples(first, second) {
        var changed = 0
        for (var y=0; y<first.height; y+=2)
            for (var x=0; x<first.width; x+=2)
                if (Math.abs(first.red(x,y)-second.red(x,y)) > 3
                    || Math.abs(first.green(x,y)-second.green(x,y)) > 3
                    || Math.abs(first.blue(x,y)-second.blue(x,y)) > 3
                    || Math.abs(first.alpha(x,y)-second.alpha(x,y)) > 3) changed++
        return changed
    }

    function test_ambient_changes_pixels_then_stops(row) {
        var sky = createTemporaryObject(skyComponent,scene,{code:row.code,night:row.night,active:true,openingSerial:7})
        tryCompare(sky,"openingRunning",false,1700)
        wait(40)
        var first = grabImage(sky)
        wait(250)
        var second = grabImage(sky)
        wait(500)
        var third = grabImage(sky)
        verify(!first.equals(second), "Ambient motion must remain visible after 250 ms")
        verify(!second.equals(third), "Ambient motion must continue after another 500 ms")
        var changes = changedSamples(first,second) + changedSamples(second,third)
        verify(changes >= (row.code === 3 ? 25 : 8), "Motion must change a meaningful area, samples=" + changes)
        sky.active = false
        wait(50)
        var stopped = grabImage(sky)
        var phase = sky.phase
        wait(500)
        verify(stopped.equals(grabImage(sky)), "Hidden scene must remain static")
        compare(sky.phase, phase, "Animation must not keep ticking after close")
        compare(sky.motionRunning,false)
    }

    function test_closed_condition_changes_do_not_start_motion() {
        var sky = createTemporaryObject(skyComponent,scene,{code:3,active:false,openingSerial:8})
        sky.code = 95
        sky.night = true
        sky.openingSerial = 9
        wait(250)
        compare(sky.motionRunning,false)
        compare(sky.openingRunning,false)
        var first = grabImage(sky)
        wait(250)
        verify(first.equals(grabImage(sky)), "Closed updates must not leave delayed animation callbacks")
    }
}
}
