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
