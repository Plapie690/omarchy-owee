# Omarchy Weather Enhanced Experience (OWEE)

A community weather widget for Omarchy Quattro, with a compact bar symbol,
local-time rain timelines, animated past radar, forecast maps and opt-in
notifications. Independent of Google and Omarchy; Pixel Weather inspired the
visual direction. English UI. MIT code, separately licensed data.

**Current build: 1.3.0-rc.1 — release candidate, not yet declared stable.**
A real twelve-hour endurance report is required before stable promotion.

## Requirements

Validated baseline: Omarchy 4.5.0, Quickshell 0.3.2 (Arch build
0.3.2.r7.g2b4501a), Qt 6.12 and Python 3.12 or newer with IANA tzdata.
No third-party Python package is needed at runtime. Native QA also uses QtTest
and Pillow (the latter only compares generated screenshots). No root service,
API key, subscription or extra Quickshell instance is started by the plugin.

## Install and update

After the public repository is created under your GitHub account:

```sh
omarchy plugin add https://github.com/YOUR_GITHUB_ACCOUNT/omarchy-owee.git --enable
omarchy plugin update owee.weather
```

The manifest must be at the repository root. Omarchy updates Git commits on the
repository default branch, not merely version tags. Only qualified releases
belong on that branch. For the existing local Pixel Weather installation, use
`python3 tools/migrate_local.py --apply`; it backs up settings and bar layout
and prints the exact rollback command. State remains in the legacy-compatible
`pixel-weather` folders. Installation does not erase favorites or notification
rules. A locked desktop may require a shell restart after unlocking.

## Reading the weather

- The bar and notifications use the primary city. **Viewing** names the location
  in the panel; **Use in bar** explicitly changes the primary city.
- Search updates while typing. Enter a city or decimal **latitude, longitude**,
  for example `27.7172, 85.3240`. Coordinates bypass the city gazetteer.
- **Now** shows modelled current conditions and feels-like temperature.
- **Hourly** gives temperatures and precipitation probabilities. Probability
  covers the hour ending at the provider timestamp; the peak names its actual
  interval, not an assumed future hour.
- **Daily** keeps Low/High as text. Its 00:00–24:00 stripe shows hourly rain/snow
  chance: brighter blue means higher chance, grey means zero, outline means
  missing data. Hover, click, or use Tab and arrow keys for the precise interval.
  Repeated clock hours retain both UTC periods; a skipped hour is identified.
- Weather, solar events and maps use the selected location's IANA timezone.
  Polar day/night is shown explicitly, rather than fake midnight solar events.
- **Measurements** includes optional air and pollen data. Explanations identify
  units, forecast versus current values, and the European AQI scale. Missing
  pollen is never interpreted as zero. Drag cards in Settings to reorder them.
- **Past rain / Radar** is observed historical precipitation. Coverage masks
  distinguish absent observations from dry conditions. **Upcoming weather** is
  a model forecast; it is not radar or an official warning.
- Maps are opt-in and stop when hidden. Web Mercator cannot show the poles;
  OWEE explains the projection limit without moving the selected location.
- Notifications are opt-in. Quiet hours and the daily summary follow the desktop
  clock; weather intervals follow the primary city's timezone. Cached/stale data
  does not trigger automatic notifications, and Do Not Disturb takes priority.

## Reliability and privacy

Sources are free public services with regional coverage and availability limits.
OWEE does not promise every field everywhere, uninterrupted APIs, or zero bugs.
Core weather and optional enrichment have separate workers. Cache fallback is
labelled, responses and writes are bounded, and malformed optional data does not
remove valid core weather. A sixty-second manual refresh cooldown limits bursts;
normal refresh is fifteen minutes and optional enrichment has a one-hour cache.

See [sources and conditions](SOURCES.md), [privacy](PRIVACY.md),
[release gates](RELEASE.md) and [security reporting](SECURITY.md).

## Validate

```sh
python3 -B qa/qualify.py                         # offline CI gates
python3 -B qa/qualify.py --native                # actual Omarchy runtime/UI gates
python3 -B qa/international.py                  # bounded live global probes
python3 -B qa/live_maps.py                      # bounded live map contracts
python3 -B qa/endurance.py --report-dir reports/endurance-1.3.0-rc.1
python3 -B tools/promote.py                     # checks gates; does not publish
```

The endurance command runs one isolated fixture process for twelve real hours,
at least 1,000 cycles, with CPU/RSS telemetry, real elapsed time and source hash.
A short smoke test cannot qualify as twelve hours. External API calls and real
notifications are blocked in endurance. Native Wayland loading is a separate
required gate; offscreen fixtures are not proof of native GPU behavior.

CI runs deterministic tests on hosted runners for each push/PR. Never run
untrusted PR code on your personal Omarchy session or a privileged self-hosted
runner. Native qualification uses the trusted reference machine and an isolated
XDG state/cache; evidence is excluded from the Git repository.

## Remove

```sh
omarchy plugin remove owee.weather
```

User state and migration backups remain for recovery. See PRIVACY.md for their
locations. Deleting those directories is a separate explicit action.
