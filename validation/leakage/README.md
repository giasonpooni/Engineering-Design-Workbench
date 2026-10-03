# Fluid and material balance qualification

The shipped workload passed 497 targeted regression tests with no skips, using
the actual operator-bound FlowState checkout at
`09a756dd9cdd3a9bb6cb14b5cd498f6259937ac2`. Its exact source tree is
`c79c44f90d5ff3920e58a53e9c277104e7e07bd3`.

`targeted-regression.json` records the tested source hashes and test accounting.
The combined run passed 489 tests; eight existing fluid tests encountered a full
temporary filesystem. After removing this task's reproducible temporary outputs,
all eight passed individually on the same frozen source. No numerical or contract
failure remained. Native leakage, offline verification, polymer coupling, CLI,
typed agents, and existing Session/dependency behavior were exercised.

`qualification.json` records 19 passing checks for both volume and mass workflows,
native calculation, independent audit, exact covariance retention, read-only
verification, export, typed agent graphs, retries and fresh replay.

`installed-package-check.json` records 37 passing checks on an isolated wheel
installation, including actual polymer occurrence coupling, nested CLI entrypoints
and complete MCP stdio execution/retry/replay for both bases. The native runtime
used Python 3.12.14 and NumPy 2.4.3; SciPy was absent and was not required by these
native conservation APIs. The wheel SHA256 is recorded in that receipt.

These are finite software and numerical checks. They do not establish sensor
calibration traceability, physical validation, leak cause/location, learned-model
performance or hardware-control authority. The original raw declarations and full
joint covariance remain available in each generated workspace.
