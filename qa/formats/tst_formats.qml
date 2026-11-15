import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import "plugin" as Weather

ShellRoot {
  Weather.WeatherFormats { id: english }
  Weather.WeatherFormats { id: us; mode: "system"; systemLocaleName: "en_US" }
  Weather.WeatherFormats { id: french; mode: "system"; systemLocaleName: "fr_FR" }
  Window {
    visible: true; width: 200; height: 100
    TestCase {
      name: "WeatherFormats"
      when: true
      function equal(actual, expected) {
        if(actual!==expected)console.error("QA_FORMATS_MISMATCH: "+actual+" expected "+expected)
        compare(actual, expected)
      }
      function nativeUsClock(hour, minute) {
        return new Date(2000,0,15,hour,minute).toLocaleTimeString(Qt.locale("en_US"), Locale.ShortFormat)
      }
      function test_numbers() {
        equal(english.number(1234.5, 1), "1,234.5")
        equal(us.number(1234.5, 1), "1,234.5")
        verify(french.number(1234.5, 1).endsWith("234,5"))
        equal(english.number(null), "—")
        equal(english.number(NaN), "—")
      }
      function test_city_wall_clock_never_shifts() {
        equal(english.cityTime("2026-03-08T02:30:00+05:45"), "02:30")
        equal(us.cityTime("2026-03-08T02:30:00+05:45"), nativeUsClock(2,30))
        equal(french.cityTime("2026-03-08T02:30:00+05:45"), "02:30")
        equal(english.cityTime("2026-11-01T01:30:00-04:00"), "01:30")
        equal(english.cityTime("2026-11-01T01:30:00-05:00"), "01:30")
        equal(us.cityTime("2026-11-01T13:05:00-05:00"), nativeUsClock(13,5))
        equal(us.cityTime("2026-11-01T00:00:00-05:00"), nativeUsClock(0,0))
        equal(us.cityTime("2026-11-01T12:00:00-05:00"), nativeUsClock(12,0))
      }
      function test_days_and_missing() {
        equal(english.day("2026-11-15"), "Sun 15 Nov")
        equal(us.day("2026-11-15"), "11/15/26")
        equal(french.day("2026-11-15"), "15/11/2026")
        equal(english.day("2026-02-30"), "—")
        equal(english.cityTime("2026-11-15T24:00"), "—")
        equal(english.cityTime("2026-11-15T12:99"), "—")
        equal(english.cityTime("2026-11-15T12:30:99"), "—")
        equal(english.cityTime("bad data"), "—")
        equal(english.instant(null), "—")
        equal(english.instant(Infinity), "—")
        equal(us.clockHour(24), "24:00")
        equal(english.clockHour(0), "00:00")
      }
      function test_city_calendar_and_metadata_clock() {
        equal(english.dayTime("2026-11-15T08:10:00+05:45"), "15/11 08:10")
        equal(us.dayTime("2026-11-15T08:10:00+05:45"), "11/15/26 "+nativeUsClock(8,10))
        equal(french.dayTime("2026-11-15T08:10:00+05:45"), "15/11/2026 08:10")
        var stamp = Date.UTC(2026, 10, 15, 8, 10) / 1000
        equal(english.instant(stamp), new Date(stamp * 1000).toLocaleString(Qt.locale("en_GB"), "dd/MM hh:mm"))
      }
      function test_live_mode_switch() {
        english.systemLocaleName="fr_FR"
        english.mode="system"
        equal(english.number(1.5,1),"1,5")
        equal(english.day("2026-11-15"),"15/11/2026")
        english.mode="english"
        equal(english.number(1.5,1),"1.5")
      }
      function cleanupTestCase() {
        if(qtest_results.failCount > 0) { console.error("QA_FORMATS_FAIL: "+qtest_results.failCount+" failures"); Qt.exit(1); return }
        console.warn("QA_FORMATS_PASS: "+qtest_results.passCount+" tests"); Qt.quit()
      }
    }
  }
}
