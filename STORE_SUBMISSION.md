# Marketplace submission draft

Name: Omarchy Weather Enhanced Experience (OWEE)

Plugin ID: `owee.weather`

Repository: `https://github.com/Plapie690/omarchy-owee`

Category: Widgets

Tags: Bar, Quickshell

Optional suggested tag: Weather

Description: Weather for cities and coordinates, hourly rain timelines,
animated past radar, global forecast maps and opt-in notifications. Free public
sources with explicit coverage and stale-data states. No account, key or telemetry.

License: MIT (code); data/API terms and attribution documented in SOURCES.md.

Runtime: Omarchy 4.5, Qt 6.12, Quickshell and Python >=3.12 with IANA tzdata.

Permissions: user-level Python subprocesses, allowlisted HTTPS weather/map
services, user state/cache writes, local opt-in `notify-send`. No sudo/root service.

Release: 1.3.5. The initial stable release was declared by maintainer decision
on 16 November 2026; subsequent changes are recorded in RELEASE_NOTES.md.

Validation: native runtime/UI, 165 Python tests, formatting/motion/preferences,
twelve international locations and seven map cases. Endurance was interrupted
by system power-off after 5 h 05 min / 458 cycles; twelve hours are incomplete.
The maintainer explicitly accepted this limitation for this release.
See RELEASE_NOTES.md; do not claim twelve-hour qualification.

Preview: preview.png at the repository root (promotional artwork generated from
the sample-data interface; no personal state). Actual screenshots remain in
assets/screenshots/. Cover provenance and generation prompt: assets/COVER.md.

Install: `omarchy plugin add <repository>.git --enable`

Update/remove: native `omarchy plugin update/remove owee.weather`.
Removal retains user preferences/cache. Migration includes a byte-preserving
backup and an explicit rollback command. Independent community project.

Submit through:
https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml

Manifest compatibility fix: defaultSection is now center, as required by the marketplace contract.
