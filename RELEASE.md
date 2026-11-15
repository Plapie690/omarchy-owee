# Release procedure

The candidate is not a promise of a publication date. The marketplace requires
a public GitHub repository, root manifest, README, license and maintainer review:
https://plugins.omarchy.org/publish.html

1. Work on `develop`. Commit a clean candidate with coherent manifest, panel and
   bar versions. Validate on the reference Omarchy 4.5 / Qt 6.12 machine.
2. Run `python3 -B qa/qualify.py --native --report-dir reports/qualification`.
   Run `qa/international.py` and `qa/live_maps.py`; retain their JSON reports.
3. Freeze code, then run `qa/endurance.py --report-dir
   reports/endurance-1.3.0-rc.1`. It requires 43,200 real elapsed seconds and at
   least 1,000 same-process cycles. Reports preserve failure evidence. A source
   change invalidates the run; rerun fast gates and start a new report directory.
4. `python3 -B tools/promote.py` verifies evidence without changing code.
   `--apply` is permitted only after all gates pass: stable metadata changes are
   limited to the three version-bearing runtime files, followed by native
   requalification. The candidate's source hash and stable hash are retained.
5. Connect GitHub with `gh auth login` only when the repository is ready. Create
   a public personal repository `omarchy-owee`, replace README's account
   placeholder, and publish the qualified stable branch as `main`. Add tag
   `v1.3.0`. Do not publish credentials, reports, caches or personal state.
6. Verify a clean Git installation and update, disable/re-enable, removal and
   restoration using the migration backup. Complete the marketplace form in
   `STORE_SUBMISSION.md` with the public URL and the exact qualified commit.

Omarchy updates the default branch by fast-forwarding commits. Never place an
unqualified development commit on `main`, even when a previous stable tag exists.
CI is necessary but does not substitute for native UI and twelve-hour evidence.

## Required gates

Zero unhandled QML errors, crashes, false dry-weather values from missing data,
preference corruption or duplicate notifications. Cache quotas must hold. The
endurance process must spend most of its time closed, keep closed idle CPU at
or below 1% of one core, and finish below warmed RSS plus the larger of 20% or
20 MiB. An outage must retain honest stale/coverage/error state and allow recovery.

The native report, live-source reports and endurance report bind the tested
source digest. Map providers are not hammered by the endurance harness: it uses
local fixtures and simulated faults. Reports do not claim to measure forecast
accuracy against observations; they validate contracts and client behavior.
