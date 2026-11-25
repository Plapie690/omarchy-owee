# OWEE 1.3.5

## Marketplace review fixes

Addresses the two low-severity findings reported by HANCORE-linux in the
[marketplace review](https://github.com/omacom/omarchy-plugin-marketplace/issues/15159#issuecomment-7013791022).

- **Backup integrity:** rollback refuses files missing from the backup inventory.
  It restores the legacy plugin from explicit manifest entries, stages state and
  configuration sources, and checks copied bytes against their recorded hashes.
  Backup contents and metadata are rechecked before publication. Additional or
  altered files abort restoration before live targets are changed.
- **Notification policy:** all four automatic alerts and the test message now
  use fixed notification text and validated weather values. Provider city names
  are kept out of both notification sinks, preventing them from being classified
  as verification codes that bypass Do Not Disturb. Alerts still refer to the
  primary bar city, whose name remains available in the panel.

Regression tests cover malicious backups, changes during staging, successful
byte/mode-preserving restoration, and hostile/international city names. A native
qualification gate tests actual OWEE payloads against the installed Omarchy
classifier and DND delivery policy without sending any desktop notifications.

The incomplete endurance qualification documented for 1.3.0 remains incomplete;
this update does not claim a new twelve-hour run or marketplace approval.

---

# OWEE 1.3.4

## Refresh beside Settings

A manual refresh icon now sits beside Settings in the fixed panel header.
It is accessible from Weather, Maps, Settings and the city picker, including
when the content is scrolled. The same action is available through keyboard
focus. It uses the existing weather worker and one-minute request limit, and
is disabled while that worker is busy.

The former Settings-only refresh button has moved to the header. Weather
sources, preferences and the selected primary city are unchanged.

The incomplete endurance qualification documented for 1.3.0 remains incomplete;
this update does not claim a new twelve-hour run.

---

# OWEE 1.3.3

## Favorite cities in the navigation

Saved cities are available directly beside Weather and Maps. One click changes
the viewed city, with the current city highlighted and the bar city marked by a
star. Switching cities on Maps keeps the map page open. Choosing the current
city does not trigger another request.

The favorites strip scrolls when needed and reveals focused cities during
keyboard navigation. Long names remain bounded and their full label is available
in the tooltip. Cities still manages search, favorites, order and removal.

The separate Use in bar action sits beside the bar-city label. Viewing a favorite
keeps the bar and notification city unchanged until that action is chosen.

---

# OWEE 1.3.2

## Softer forecast panels

Hourly and daily forecasts now sit on a shared, quiet surface derived from the
active Omarchy theme. A subtle vertical tint, fine border and interior spacing
separate the forecasts from the main background and soften their contrast.

---

# OWEE 1.3.1

## Marketplace compatibility

The marketplace accepts `left`, `center` or `right` for
`barWidget.defaultSection`. Version 1.3.0 used `centerBegin`, which the local
shell accepted but the marketplace rejected. The manifest now uses `center`;
the native installer routes that choice beside the clock. Existing widget
placement is preserved.

A regression test now checks that the manifest uses the portable marketplace
contract. Validation includes the marketplace's own manifest validator and the
native runtime/UI gates. This patch changes the manifest and version labels,
without changing weather data, preferences or application behavior.

The incomplete endurance qualification documented for 1.3.0 below remains
incomplete; this metadata patch does not claim a new twelve-hour run.

---

# OWEE 1.3.0

Released as stable by maintainer decision on 16 November 2026.

## Features

- A compact weather symbol and temperature in the Omarchy bar.
- Separate primary and viewed cities, favorites and coordinate search.
- Hourly forecasts and daily local-time precipitation timelines.
- Animated historical radar, coverage masks and on-demand forecast maps.
- Configurable measurement cards and opt-in notifications with quiet hours.
- Coordinated opening motion, native widget preferences and optional system formats.

## Validation and explicit release exception

The candidate passed 164 Python tests, native QML/runtime/UI checks, formatting,
motion and preference migration tests at 100% and 150% scaling, and bounded live
checks for twelve international locations and seven map cases. Stable metadata
is revalidated before the stable commit and tag are created.

The twelve-hour endurance run on candidate 1.3.0-rc.3 completed 458 cycles over
5 h 05 min before the desktop session closed during system power-off at 01:38
Europe/Paris on 16 November 2026. Average closed-panel CPU was about 0.005% of one
core; the final sampled memory remained below the configured allowance.
The report is failed/incomplete, not a passed twelve-hour qualification.

The maintainer explicitly requested stable promotion and publication without
repeating that run. This release records that exception; it does not change the
automatic release gate or fabricate additional runtime evidence. Other release
checks remain mandatory. No zero-bug or forecast-accuracy guarantee is made.

## Known limits

Data availability depends on public providers and regional coverage. Air/pollen
may be unavailable. Web Mercator maps cannot display the poles. Optional maps
and notifications are disabled until enabled. An uncertain notification delivery
is not retried for the same signature, so a system failure can lose an alert.
