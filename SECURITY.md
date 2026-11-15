# Security and maintenance

Omarchy plugins run unsandboxed with the user's privileges. Manifest validation
and marketplace listing are not security audits. Review code before installing.

Runtime Python uses standard-library dependencies. HTTPS endpoints and redirects
are allowlisted; network data is never executable code or shell text. Values are
normalized before QML, and text is rendered as plain text. State is atomically
written with bounded caches and recovery copies. Workers have deadlines and
stale-location guards. These measures reduce risk, not eliminate every defect.

Before reporting a vulnerability publicly, provide a private contact through the
repository owner's GitHub profile. Do not post exploit details or personal
coordinates publicly. Non-sensitive bugs may use GitHub Issues with version,
Omarchy/Qt versions, reproduction and redacted logs. There is no automatic upload.

Only the tested runtime baseline is supported. Re-run native GUI and endurance
gates after changes to QML, Python, workflows or release tooling. Provider
contract changes require source-specific tests and documented attribution.
