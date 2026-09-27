# Session integrity audit - 2026-09-27

## Scope and baseline

This is a targeted continuation of the runtime audit, not a complete security,
scientific, hardware, or deployment qualification of the repository.

Reviewed main: `9d4a77c3d26c86e588169196315024c151c8a5ac`. The earlier failure-retention
fix (#27) and CLI duplicate-JSON fix (#28) are merged into that baseline. This
patch preserves both. It changes `src/ciw/session.py`, adds two regression files,
and records this report. No equations, tolerances, provider pins, schemas,
license grants, repository settings, or equipment permissions are changed.

The targeted invariants are: provider calls cannot mutate retained source or
result records; newly published legacy results satisfy the existing offline
reader; a completed execution is written only after its result dependency; a
failed publication does not alter previously retained in-memory records.

## Reproduced defects and corrections

### 1. Legacy analysis exposed mutable evidence and retained provider-owned data

`analysis.stats` and `analysis.spectrum` called the registered provider with the
live session recording. A provider could change that recording while its saved
file and content-derived identity still referred to the original input. The
result also retained the provider's returned dictionary directly. Subsequent
changes to a reused dictionary or nested PSD array could alter retained history.
The interval list passed to the provider was also reused in the result metadata.

The legacy path now captures the selected recording, selection, and recording
filename; passes detached input and parameter copies to the provider; and copies
returned data before retention. The original flat response format and legacy
workspace version remain unchanged. No generic execution envelope is fabricated
for a legacy command, and legacy error-return semantics are not redesigned here.

### 2. Legacy publication bypassed the existing payload and role checks

Wrong units, wrong sample counts, negative RMS/PSD, missing/extra fields, and
non-object payloads could be returned as successful legacy results. Some saved
workspaces then failed their own offline validation. A provider registered under
an incompatible role could also execute through the legacy entry point.

The legacy path now checks the declared role before calling the provider and
uses `_validate_saved_result` before writing a result. This reuses the existing
read-only validator rather than weakening it or duplicating numerical formulas.
Invalid data is rejected before publication. A subsequent valid request on the
same WebSocket still succeeds. Historical malformed records remain rejected.

### 3. Generic publication could leave a dangling completed execution

The generic path wrote its completed execution before its result. A failure
writing the result left a completion file pointing to a missing dependency,
even though the session returned `storage_error` and retained no in-memory pair.

Publication now writes the result first, then the execution, and only then
updates the in-memory maps. On `OSError`, it attempts to remove only the freshly
allocated files and preserves the original error and prior records. If removal
of the execution file fails, the result dependency is preserved; cleanup must
not create the dangling completion it was intended to prevent. Cleanup failures
are logged on the host. Pending-capacity reservations are still released.

This is NOT a multi-file transaction or a power-loss durability guarantee.
Abrupt process termination can leave unreferenced result files, and denied
cleanup can leave an unpublished pair. Those files are not automatically
admitted into the investigation. The patch does not add a journal, orphan-file
recovery service, directory fsync guarantee, or a multi-process writer lock.

## Validation actually performed

Tests use explicit synthetic/misbehaving providers, temporary directories,
injected storage faults, and actual loopback WebSockets. They do not operate
physical equipment or qualify external scientific providers.

| Test set | Baseline | Patched |
| --- | --- | --- |
| 40 new regression cases | 28 failed, 12 passed | All pass in the combined run |
| New cases + 20 existing runner cases + 30 cases from #27 | Not separately rerun as one baseline suite | 90 passed, no skips |
| Above + 11 unchanged CLI JSON cases from #28 | Not separately rerun as one baseline suite | 101 passed, no skips |
| Python compilation | Not separately rerun | Passed |
| CLI demo, statistics, spectrum, saved-workspace inspection | Not separately rerun | Passed |

The new cases cover provider mutation during and after execution, caller-owned
payload edits, concurrent selection changes, legacy response compatibility,
provider-free reopening, malformed-result refusal before writes, live-socket
recovery, real storage-error classification, retry after failure, publication
order, failures before/after individual writes, cleanup failures, and preservation
of previously retained bytes. Existing runner and JSON tests are unchanged.

Reproduce the focused suite in a normal checkout with the project dependencies:

```sh
python -m pytest -q tests/test_legacy_analysis_boundary.py tests/test_operation_publication.py tests/test_operation_runner.py tests/test_operation_failure_retention.py tests/test_server_json_boundary.py tests/test_cli_json_boundary.py
```

## Local provenance and limitations

Local validation used Linux, Python 3.13.5, NumPy 2.3.5, pytest 9.0.2, and
websockets 16.0. This is not the repository's Python 3.11/3.12 and NumPy 2.4.3
matrix. Full repository, native-provider, Godot, hardware, and cryptographic
qualification were not rerun locally.

The local baseline was reconstructed from the CI-produced wheel for merged #28:
workflow run `36338715553`, artifact `10938446231`, head
`0a7332111e43dbbe9ede98bdd9678afb433d191f`. The downloaded artifact SHA-256 was
verified as `175b06ec9cd6de3c3144a109b50de73c87df84122630dac3c51a6876544421e7`.
The unpacked session source matched current main's Git blob
`e223b8871ba57c5894c1048ca1951e03b423d256` before modification. The retained runner
tests matched `ebb3367c4003c596068f7500fee3b0dc34af743c`; the CLI JSON tests matched
`a93bf98a60a79b9315b0bf616fdef117e85584bd`. This is targeted testing against verified
package contents, not a claim of a complete local source checkout.

The patched session blob is `91f8e45036e98c3f93e94174f436c1581a0650ea`.
The two new test blobs are `4d88d15c274d1b34b9c6b4928925c680cb519211` and
`80bc82d4cf1b06c5e5d697cf12768811cbae6d0f` respectively.

## Outstanding work

Normal review and hosted CI are still required. The preceding audit confirmed
private-provider checkout failures before numerical execution; that access
configuration is not changed or bypassed here. Not every failed native workflow
has been individually diagnosed. Successful local tests do not establish those
providers' availability, physical validity, or cryptographic qualification.

Continue with qualified provider provisioning and broader persistence/recovery
coverage. Preserve strict unavailable/refused outcomes rather than disabling
checks to obtain a green status. In particular, do not describe the ordered
writes and best-effort cleanup in this patch as full transactional storage.
