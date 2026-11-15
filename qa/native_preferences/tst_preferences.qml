import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import qs.Commons as Commons
import "plugin" as Weather

ShellRoot {
  id: suite
  property var p: null
  property var scope: null
  property int checks: 0
  property int step: 0
  property double since: Date.now()
  property string citiesBefore: ""
  property string cardsBefore: ""
  property string hiddenBefore: ""
  property int writesBeforeReload: 0
  function check(ok, message) {
    if (!ok) throw new Error("QA_FAIL: " + message)
    checks++
    console.warn("QA_NATIVE_PREFERENCES_CHECK", checks, message)
  }
  function advance(next) { step=next; since=Date.now() }
  function settled() { return p && !p.loading && !p.pendingActions.length && Date.now()-since>200 }
  function find(item, name) {
    if (!item) return null
    if (item.objectName === name) return item
    for(var i=0;item.children&&i<item.children.length;i++) {
      var child=find(item.children[i],name)
      if(child)return child
    }
    return null
  }
  function button(item, text) {
    if(!item)return null
    if(item.text===text && typeof item.clicked==="function")return item
    for(var i=0;item.children&&i<item.children.length;i++) {
      var child=button(item.children[i],text)
      if(child)return child
    }
    return null
  }
  function click(item) {
    check(!!item,"native control found")
    var parent=item.parent
    while(parent) { if(typeof parent.forceLayout==="function")parent.forceLayout();parent=parent.parent }
    check(events.mouseClick(item,item.width/2,item.height/2,Qt.LeftButton,Qt.NoModifier,1),"real QtTest click delivered")
  }
  function fits(item) {
    check(!!item,"settings group exists")
    check(item.x>=0&&item.x+item.width<=item.parent.width+0.5,"settings group fits its row width")
    var point=item.mapToItem(stage,0,0)
    check(point.x>=-0.5&&point.x+item.width<=stage.width+0.5,"settings group fits panel viewport")
    for(var i=0;item.children&&i<item.children.length;i++) {
      var child=item.children[i]
      if(typeof child.clicked!=="function")continue
      check(child.x>=-0.5&&child.x+child.width<=item.width+0.5,"native option fits group bounds: "+child.text)
    }
  }
  function preserved() {
    check(JSON.stringify(p.cities)===citiesBefore,"favorite cities preserved")
    check(JSON.stringify(p.cardOrder)===cardsBefore,"card order preserved")
    check(JSON.stringify(p.hiddenCards)===hiddenBefore,"hidden cards preserved")
  }
  QtObject {
    id: nativeShell
    property var saved: ({id:"owee.weather", customOption:"keep", nested:{preserve:17}})
    property int writes: 0
    function updateEntryInline(id, entry) {
      check(id==="owee.weather" && entry.id===id,"native persistence receives correct widget id")
      saved=JSON.parse(JSON.stringify(entry));writes++
    }
  }
  QtObject { id:nativeBar; property QtObject shell:nativeShell; property color barForeground:Commons.Color.foreground }
  QtObject { id:nativeHost; property var settings:({}) }
  Window {
    id: window
    visible:true;width:460;height:760;color:Commons.Color.background
    Rectangle {id:stage;x:14;y:14;width:parent.width-28;height:parent.height-28;color:window.color}
    TestEvent {id:events}
  }
  Loader { id:loader; active:false }
  Component.onCompleted: {
    loader.setSource(Qt.resolvedUrl("plugin/Panel.qml"),{bar:nativeBar,hostWidget:nativeHost,settings:nativeShell.saved})
    loader.active=true
  }
  Timer {
    interval:50;repeat:true;running:true
    onTriggered: {
      try {
        if(step===0) {
          if(!loader.item||!loader.item.result.data||!loader.item.qaScope)return
          p=loader.item;scope=p.qaScope
          scope.parent=stage;scope.width=stage.width;scope.height=stage.height
          citiesBefore=JSON.stringify(p.cities);cardsBefore=JSON.stringify(p.cardOrder);hiddenBefore=JSON.stringify(p.hiddenCards)
          check(p.unit==="F"&&p.temperatureMode==="F","legacy Fahrenheit survives native migration")
          check(p.autoRefresh===false,"legacy automatic refresh off survives migration")
          check(p.formatMode==="english","English formats remain default")
          check(nativeShell.saved.preferencesVersion===1,"legacy preferences seeded once into native entry")
          check(nativeShell.saved.customOption==="keep"&&nativeShell.saved.nested.preserve===17,"native seeding preserves unknown settings")
          check(nativeHost.settings.temperatureMode==="F","bar host receives updated inline settings")
          preserved()
          p.settings=Object.assign({},nativeShell.saved,{temperatureMode:"C",formatMode:"system",autoRefresh:true})
          advance(1);return
        }
        if(step===1) {
          if(!settled()||p.result.unit!=="C"||p.result.auto_refresh!==true)return
          check(p.temperatureMode==="C"&&p.unit==="C","native temperature takes precedence over legacy Fahrenheit")
          check(p.autoRefresh===true,"native automatic refresh takes precedence over legacy off")
          check(p.formatMode==="system","native format mode applied")
          preserved()
          p.setFormatMode("english")
          check(nativeShell.saved.customOption==="keep"&&nativeShell.saved.nested.preserve===17,"preference update merges unknown keys")
          var valid=p.settings
          p.settings={temperatureMode:"invalid",formatMode:"invalid",autoRefresh:"off",preferencesVersion:1}
          check(p.temperatureMode==="C"&&p.formatMode==="english"&&p.autoRefresh===true,"invalid native values fall back safely")
          p.settings=valid
          p.setTemperatureMode("system")
          advance(2);return
        }
        if(step===2) {
          if(!settled()||p.result.unit!=="F")return
          check(p.unit==="F"&&p.temperatureMode==="system","system US measurement resolves Fahrenheit")
          check(p.result.unit==="F","backend unit synchronized for notifications")
          p.systemLocale=Qt.locale("en_GB")
          advance(3);return
        }
        if(step===3) {
          if(!settled()||p.result.unit!=="C")return
          check(p.unit==="C","system UK measurement resolves Celsius")
          check(p.temperatureMode==="system","locale change preserves system preference")
          p.open();p.showPage("settings");window.requestActivate()
          advance(4);return
        }
        if(step===4) {
          if(!settled())return
          fits(find(scope,"unit-selector"))
          fits(find(scope,"format-selector"))
          click(button(find(scope,"unit-selector"),"°F"))
          advance(5);return
        }
        if(step===5) {
          if(!settled()||p.result.unit!=="F")return
          check(p.temperatureMode==="F"&&p.unit==="F","native unit control updates durable preference")
          click(button(find(scope,"format-selector"),"System"))
          check(p.formatMode==="system","native format control updates preference")
          p.setAutoRefresh(false)
          advance(6);return
        }
        if(step===6) {
          if(!settled()||p.result.auto_refresh!==false)return
          check(p.autoRefresh===false,"native automatic refresh synchronized to backend")
          check(nativeShell.saved.temperatureMode==="F"&&nativeShell.saved.formatMode==="system"&&nativeShell.saved.autoRefresh===false,"native entry contains final preferences")
          preserved()
          p.setTemperatureMode("C")
          advance(60);return
        }
        if(step===60) {
          if(!settled()||p.errorText!=="Fixture preference storage failure")return
          check(!!p.result.data&&p.result.unit==="F","failed preference write preserves last valid weather envelope")
          check(p.unit==="C","native preference remains visible while backend failure is reported")
          advance(61);return
        }
        if(step===61) {
          if(Date.now()-since<1000)return
          check(!p.loading&&!p.pendingActions.length,"failed preference write does not keep worker busy retrying")
          check(p.errorText==="Fixture preference storage failure","preference storage error remains visible")
          p.setTemperatureMode("F")
          writesBeforeReload=nativeShell.writes
          p.close();loader.active=false;p=null;scope=null
          advance(7);return
        }
        if(step===7) {
          loader.setSource(Qt.resolvedUrl("plugin/Panel.qml"),{bar:nativeBar,hostWidget:nativeHost,settings:nativeShell.saved})
          loader.active=true;advance(8);return
        }
        if(step===8) {
          if(!loader.item||!loader.item.result.data)return
          p=loader.item
          if(!settled())return
          check(p.temperatureMode==="F"&&p.formatMode==="system"&&p.autoRefresh===false,"panel reload restores all native preferences")
          check(nativeShell.writes===writesBeforeReload,"panel reload does not reseed or reset preferences")
          check(nativeShell.saved.customOption==="keep"&&nativeShell.saved.nested.preserve===17,"unknown native keys survive panel reload")
          preserved()
          console.warn("QA_NATIVE_PREFERENCES_PASS",checks)
          Qt.quit()
        }
      } catch(error) { console.error(String(error));Qt.exit(1) }
    }
  }
}
