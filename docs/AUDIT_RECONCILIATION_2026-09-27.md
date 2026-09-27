# Runtime audit reconciliation and numeric JSON boundary

This increment reconciles PR #30 with merged PR #29 on main
`4cafa0e1c4193acbc6c8ad62c007c19aba796bc4`. It preserves both source histories;
it does not replace the existing legacy failure-retention behavior.

## Changes and guarantees

- Legacy statistics/spectrum providers receive detached source and parameter
  objects. Retained data and captured selection metadata cannot be changed by
  later provider or caller mutation.
- The existing role and saved-result validators run before legacy publication.
  Invalid output now enters the refusal history introduced by #29. Successful
  responses keep the existing flat legacy format and remain `not_verified`.
- Generic publication retains #30's result-before-execution ordering and
  best-effort cleanup. It is not a multi-file transaction or a power-loss
  durability guarantee; denied cleanup may leave unpublished artifacts.
- Shared JSON parsing rejects floating-point overflow such as `1e309`, including
  nested values, before WebSocket dispatch, CLI connection or remote-result
  acceptance. Duplicate keys and nonstandard nonfinite literals remain refused.
  Finite floats, subnormal values, signed zero and integer representation retain
  their existing behavior. This is not a new arbitrary-precision number policy.

The numerical formulas, tolerances, schemas, provider pins, successful legacy
record shape, process-control exceptions and offline semantic validators are
unchanged. No invalid historical record is repaired to make it acceptable.

## Reproduction and tests

The 20 numeric JSON cases produced **12 failures and 8 passes** against the
unmodified merged-#29 baseline; the patched parser passed all 20. A protocol-valid
exponent previously overflowed Python's float parser without invoking the
`parse_constant` rejection hook. The tests cover file input, inline CLI input,
live loopback WebSockets, the remote-response reader and the watch interface.

The reconciled runtime suite passed **136 tests with zero skips**. It includes
both earlier audit suites, the unchanged #28 CLI tests and #29 failure tests,
updated legacy-isolation tests, publication fault injection, two mutating-failure
cases, and the 20 numeric JSON cases. In particular, rejecting an invalid legacy
result must retain a refusal and must not publish a successful result.

The combined runtime and separately proposed proof-hardening test run passed
**271 tests and skipped five real-SP1 tests**. Those five tests require actual
SCR/prover/guest bindings and are not counted as cryptographic evidence.

Local validation used Linux, Python 3.13.5, NumPy 2.3.5, pytest 9.0.2 and
websockets 16.0. This does not replace the pinned Python 3.11/3.12 and NumPy 2.4.3
CI matrix or the complete native-provider suite.

Source was provisioned from GitHub Actions run `36339548254`, wheel artifact
`10938570758` (merged #29). The ZIP SHA-256 was
`e9e9faac481975bbb37975fa1db3dd870f2090ae08fb801fdb2d383421745e60`.
The original session module matched main's Git blob
`7b60c5716856991221af6e7defefc4b575149e4a`.

## Boundaries still open

Previously observed private-provider authentication failures are not fixed or
bypassed by this increment. Repository permissions, credentials and CI selection
are unchanged. Normal review and relevant CI remain required before merge.
The earlier [session audit](AUDIT_SESSION_INTEGRITY_2026-09-27.md) remains a
historical record of its original baseline, findings and validation.
