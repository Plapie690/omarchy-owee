import QtQuick
import QtTest
import qs.Commons as Commons
import "WeatherModel.js" as Model

Item {
  id: scene
  width: 400; height: 260
  TestCase {
    name: "WeatherMark"
    when: windowShown
    Component {
      id: markComponent
      Item {
        property int logicalSize: 24
        property alias code: mark.code
        property alias night: mark.night
        property alias ink: mark.ink
        property alias family: mark.family
        width: logicalSize; height: logicalSize; clip: true
        WeatherMark { id: mark; scale: parent.logicalSize / 24; transformOrigin: Item.TopLeft }
      }
    }
    Component { id: blankComponent; Item { x:250; width:24; height:24 } }
    function test_wmo_data() {
      var codes = [0,1,2,3,45,48,51,53,55,56,57,61,63,65,66,67,71,73,75,77,80,81,82,85,86,95,96,99]
      return codes.map(function(code) { return {tag:String(code),code:code} })
    }
    function test_wmo(row) {
      var mark = createTemporaryObject(markComponent,scene,{code:row.code})
      verify(mark); compare(mark.family,Model.family(row.code))
      waitForRendering(mark); wait(25)
      var blank = createTemporaryObject(blankComponent,scene)
      verify(!grabImage(mark).equals(grabImage(blank)), "Every weather code must draw a mark")
    }
    function test_unknown_data() {
      return [{tag:"null",code:null},{tag:"invalid",code:4},{tag:"string",code:"0"},{tag:"undefined",code:undefined}]
    }
    function test_unknown(row) {
      var mark = createTemporaryObject(markComponent,scene,{code:row.code})
      compare(mark.family,"unknown")
    }
    function test_day_night_and_palette() {
      var mark = createTemporaryObject(markComponent,scene,{code:0})
      // Capture the whole scene: QtTest crops small-item captures at fractional DPR.
      wait(30); var day = grabImage(scene)
      mark.night = true; wait(30)
      verify(!day.equals(grabImage(scene)),"Night must change the mark")
      var night = grabImage(scene)
      mark.ink = "#df4b71"; wait(30)
      verify(!night.equals(grabImage(scene)),"Palette must update without recreation")
    }
    function test_families_have_distinct_pixels() {
      var mark = createTemporaryObject(markComponent,scene,{code:0})
      var images = []
      var codes = [0,3,45,61,71,95,null]
      for (var i=0;i<codes.length;i++) {
        mark.code = codes[i]; waitForRendering(mark); wait(70)
        var image = grabImage(scene)
        for (var j=0;j<images.length;j++) verify(!image.equals(images[j]),"Distinct family " + codes[i])
        images.push(image)
      }
    }
    function test_sizes_data() {
      return [12,24,48,96].map(function(size){return {tag:String(size),size:size}})
    }
    function test_small_family_distinctions_data() {
      return [12,24].map(function(size) { return {tag:String(size),size:size} })
    }
    function test_small_family_distinctions(row) {
      var mark = createTemporaryObject(markComponent,scene,{code:0,logicalSize:row.size})
      var images = []
      var codes = [0,1,2,3,45,61,71,95,null]
      for (var i=0;i<codes.length;i++) {
        mark.code = codes[i]; waitForRendering(mark); wait(40)
        var image = grabImage(scene)
        for (var j=0;j<images.length;j++) verify(!image.equals(images[j]), "Weather families must remain distinct at " + row.size + " px: " + codes[i])
        images.push(image)
      }
    }
    function test_celestial_day_night_data() {
      return [0,1,2].map(function(code) { return {tag:String(code),code:code} })
    }
    function test_celestial_day_night(row) {
      var mark = createTemporaryObject(markComponent,scene,{code:row.code,logicalSize:12})
      wait(50); var day = grabImage(scene)
      mark.night = true; wait(50)
      verify(!day.equals(grabImage(scene)), "Sun and moon must differ even behind a cloud at 12 px")
    }
    function test_sizes(row) {
      var mark = createTemporaryObject(markComponent,scene,{code:3,logicalSize:row.size})
      var blank = createTemporaryObject(blankComponent,scene,{width:row.size,height:row.size})
      wait(30)
      compare(mark.width,row.size); compare(mark.height,row.size)
      verify(!grabImage(mark).equals(grabImage(blank)),"Nonempty at " + row.size + " px")
    }
  }
}
