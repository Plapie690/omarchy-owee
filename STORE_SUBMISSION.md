# Marketplace submission draft

Name: Omarchy Weather Enhanced Experience (OWEE)

Plugin ID: `owee.weather`

Repository: `https://github.com/YOUR_GITHUB_ACCOUNT/omarchy-owee`

Category/tags: weather, bar-widget, forecasts, radar, notifications

Description: Weather for cities and coordinates, hourly rain timelines,
animated past radar, global forecast maps and opt-in notifications. Free public
sources with explicit coverage and stale-data states. No account, key or telemetry.

License: MIT (code); data/API terms and attribution documented in SOURCES.md.

Runtime: Omarchy 4.5, Qt 6.12, Quickshell and Python >=3.12 with IANA tzdata.

Permissions: user-level Python subprocesses, allowlisted HTTPS weather/map
services, user state/cache writes, local opt-in `notify-send`. No sudo/root service.

Qualification evidence: add the exact commit and passing release-gate report
identifiers after the real twelve-hour run. Do not claim qualification while it
is pending, failed, source-mismatched, or merely a short smoke test.

Install: `omarchy plugin add <repository>.git --enable`

Update/remove: native `omarchy plugin update/remove owee.weather`.
Removal retains user preferences/cache. Migration includes a byte-preserving
backup and an explicit rollback command. Independent community project.

Submit through:
https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml
