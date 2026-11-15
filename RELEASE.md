# Release procedure

The candidate is not a promise of a publication date. The marketplace requires
a public GitHub repository, root manifest, README, license and maintainer review:
https://plugins.omarchy.org/publish.html

1. Work on `develop`. Commit a clean candidate with coherent manifest, panel and
   bar versions. Validate on the reference Omarchy 4.5 / Qt 6.12 machine.
2. Run `python3 -B qa/qualify.py --native --quality-python /path/to/dev-venv/bin/python --report-dir reports/qualification`.
   Run `qa/international.py` and `qa/live_maps.py`; retain their JSON reports.
3. Freeze code, then run `qa/endurance.py --report-dir
   reports/endurance-1.3.0-rc.3`. It requires 43,200 real elapsed seconds and at
   least 1,000 same-process cycles. Reports preserve failure evidence. A source
   change invalidates the run; rerun fast gates and start a new report directory.
4. `python3 -B tools/promote.py` verifies evidence without changing code.
   `--apply` is permitted only after all gates pass: stable metadata changes are
   limited to the three version-bearing runtime files in an isolated worktree,
   followed by native requalification. Main and tag are published atomically;
   the develop checkout stays on the candidate. The candidate's source hash and stable hash are retained.
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

## Production quality checks

Install `requirements-dev.txt` into a separate development virtual environment.
Ruff, mypy and branch coverage are development tools; the installed plugin keeps
its standard-library-only Python runtime. Quality configuration is included in
the source digest used by the release gates.

Notification delivery reserves each event durably before invoking the desktop
service. An uncertain or failed delivery is not retried for the same signature.
A system failure can therefore lose an alert; OWEE does not provide critical
or guaranteed-delivery weather warnings.

Promotion creates qualified `main` and `v1.3.0` refs atomically in a separate
worktree. `develop` remains on the candidate. Never check out `main` while an
automatic promotion is pending. The local finalizer fetches the exact qualified
main commit and fast-forwards the installed plugin, preserving local edits by
refusing dirty or divergent checkouts. It never pushes a remote.
