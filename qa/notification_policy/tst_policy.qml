import QtQuick
import Quickshell
import "native/Detect.js" as Detect
import "native/Delivery.js" as Delivery

ShellRoot {
  readonly property var payloads: @@CASES@@
  property int checks: 0
  function check(ok, message) {
    if (!ok) throw new Error("QA_FAIL: " + message)
    checks++
  }
  function run() {
    try {
      // Prove this is the classifier that admits the reviewed attack. No
      // notification is delivered; these are the shell's pure policy functions.
      var control = Detect.scan("Precipitation in Your verification code is 482913", "Chance 80 %")
      check(control.code === "482913", "reviewed provider-name attack is detected as an OTP")
      check(Delivery.quietReason({app: "OWEE", urgency: 1, code: control.code}, true) === "", "reviewed OTP classification bypasses DND")
      for (var i = 0; i < payloads.length; i++) {
        var row = payloads[i]
        var found = Detect.scan(row.summary, row.body)
        check(found.code === "", "payload " + i + " is never classified as an OTP")
        row.code = found.code
        check(Delivery.quietReason(row, true) === "silenced", "DND suppresses payload " + i)
        check(Delivery.quietReason(row, false) === "", "normal mode allows payload " + i)
      }
      console.warn("QA_NOTIFICATION_POLICY_PASS: " + checks + " checks; " + payloads.length + " real payloads; no desktop notifications")
      Qt.callLater(function() { Qt.quit() })
    } catch (error) {
      console.error(error.message)
      Qt.callLater(function() { Qt.exit(1) })
    }
  }
  Component.onCompleted: Qt.callLater(run)
}
