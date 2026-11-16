# Contributing to OWEE

This document covers implementation, development checks and maintenance tasks.
For installation and everyday use, see [README.md](README.md).

## Runtime and architecture

Validated baseline: Omarchy 4.5.0, Quickshell 0.3.2 (Arch build
`0.3.2.r7.g2b4501a`), Qt 6.12 and Python 3.12+ with IANA tzdata.

QML and Qt Quick provide the native Omarchy interface. Small Python workers
handle source requests, normalization, disk storage and notification delivery.
There is no application server or extra persistent Quickshell instance.

Core weather and optional enrichment load separately. Responses are bounded,
malformed data is checked before display, and cached forecasts remain available
with an explicit stale label. Normal refresh is every fifteen minutes; manual
refresh has a sixty-second cooldown, and optional enrichment has a one-hour cache.

Temperature mode, date/number format and automatic refresh live in the native
Omarchy widget entry. Favorites, cards, notification settings and cached data
retain dedicated storage. Existing preferences are preserved during migration.

## Development and validation

The Python runtime uses the standard library. Development checks additionally use
pinned Ruff, mypy and coverage tools. Native UI QA needs QtTest and Pillow.
Keep the virtual environment outside the plugin checkout: the native validator
rejects symlinks inside plugin folders, including ignored development files.

```sh
python3 -m venv /tmp/owee-dev-venv
/tmp/owee-dev-venv/bin/python -m pip install -r requirements-dev.txt
python3 -B qa/qualify.py
python3 -B qa/qualify.py --native --quality-python /tmp/owee-dev-venv/bin/python
```

Live-source checks are separate, bounded probes:

```sh
python3 -B qa/international.py
python3 -B qa/live_maps.py
```

Endurance runs use isolated fixtures, block real API calls and notifications, and
record elapsed time, repeated interactions, CPU, memory and the tested source hash.
Native Wayland loading is checked separately. CI runs deterministic tests on
hosted runners; native checks use the trusted reference desktop.

See [RELEASE.md](RELEASE.md) for the procedure and
[RELEASE_NOTES.md](RELEASE_NOTES.md) for the actual validation history.

## Moving from the original local Pixel Weather plugin

This maintenance task applies only to the original local prototype. Existing OWEE
installations use the normal update command in the README.

From a checkout of this repository, run:

```sh
python3 -B tools/migrate_local.py --apply
```

The migration backs up settings and bar layout, preserves favorites and
notification rules, and provides an explicit rollback tool. Legacy-compatible
state directories keep the name `pixel-weather`. A locked session may require
an Omarchy shell restart after unlocking.
