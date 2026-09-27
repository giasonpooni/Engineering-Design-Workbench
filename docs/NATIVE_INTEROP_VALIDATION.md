# Native interoperability validation

This report records the bounded native increment on 2026-09-26. It is a
partial integration report: numerical execution and exact integer checking
are distinct from the still-unavailable SP1 proof gate.

## Source and runtime identities

- Workbench repository ID: `1377790873`, resolved as
  `giasonpooni/Parametric-Design-Testbed`; base main
  `b3951c83c43ec735e2b515b0a08909b9b025cfa3`. Concurrent default-branch
  main advanced to `a073cda9c59718ff480f60e63faddf6e4a8e6ef6` with a
  README-only change; that change was not merged into this isolated increment.
- SCR base/default branch: `claude/deterministic-state-architecture-q9kl5c`,
  `a59aba283b0304faeeb3e5d305087e7709e171ca`.
- Both increments use `codex/native-interop-v1`. This increment changes
  neither default branch. The pre-existing design-study, linear-response, exact-response and
  scalar JuMP work is preserved in the Workbench branch.
- Final reviewed SCR source: `fd61efb3e0e5868d0f95ba27706b64a9afca595f`.
  Tested Windows host SHA256:
  `8f6c8957b527084546ba6f0270409591145372b6612db3762320cbb925590ca6`.
- The authoritative current native source and Julia closure pins are in
  [native-interop-runtimes.json](../src/ciw/native-interop-runtimes.json).
  Historical provider manifests remain unchanged.
- Actual Windows toolchains: Python 3.12.14, Rust 1.96.0, MSVC 19.44.35228,
  CXX 1.0.202, Julia 1.10.12. Julia package versions are listed in the
  [operator guide](NATIVE_INTEROP.md) and generated manifests.

The checked-in native worker uses canonical LF bytes, SHA256
`076935fb2828cf460afb72e20d17e434a465fe1a95700df397a636bc5a18c2fd`.
The earlier source/installed gate 3 reports used the preceding CRLF artifact,
`e598eafae6dba8e9afddc74e16ee498123b7982d2d5b2858bc8f6b9f4fb61d16`.
Their numerical code is unchanged, but their artifact identities are distinct.
The registry retains the preceding **whole** four-file Julia closure in
`historical_julia_files`. All four hashes must match one registered closure;
individual hashes cannot be mixed across versions. Historical inspection
preserves the original byte bindings, and explicit historical replay requires
its original runtime closure. Line-ending normalization does not reinterpret
or rewrite retained evidence.

Publication through the GitHub Git-data API creates commit metadata distinct
from local commits. Every published tree is compared to the tested local tree;
the runtime binds the published commit from a clean checkout. This is source
identity checking, not cryptographic source-to-binary attestation.

## Executable checks

| Boundary | Source / build | Genuine run | Checked scope | Evidence |
| --- | --- | --- | --- | --- |
| Python ↔ Rust | PASS: compiled SCR host and installed CIW wheel | PASS on Windows | Bounded transport, identity bindings, refusals and independent values | Source and installed gates: each 16 PASS / 5 NOT_RUN |
| Rust ↔ Julia | PASS: generated manifests and instantiated Julia 1.10.12 environments | PASS on Windows | Framing, analytic reference, exact affine arithmetic, A/B/A and restart | 29 genuine worker tests plus the nested-path regression; shared gates |
| Rust ↔ C++ | PASS: Windows MSVC and Linux native builds | PASS on both platforms | Affine layout, exact bounds, force/energy values and malformed inputs | Shared Windows gates; final Linux host CI |
| JuliaControl | PASS: ControlSystemsBase 1.22.0 | PASS | Zero-force state response versus analytic reference and separately executed Tsit5 | Both shared gates; maximum Tsit5 discrepancy `7.828182546631979e-12` |
| JuMP + HiGHS | PASS: JuMP 1.31.2, HiGHS wrapper 1.25.4 / library v1.15.1 | PASS | Actual coupled/interior and active-bound solves; independent objective, feasibility and projected-gradient checks | Both shared gates; genuine worker cases also exercise changed targets, rectangular models and iteration refusal |
| Native exact affine checker | PASS: compiled independent Rust checker | PASS | Retained Julia candidate accepted; one changed integer numerator rejected; commitments agree with Python reference | `exact-julia-check-canonical/report.json`; 744-byte canonical statement |
| SP1 heat / new affine proof | Source present; build BLOCKED by unavailable SP1 fork/toolchain checkout | NOT_RUN | No genuine proof generation or fresh cryptographic verification | Readiness failure retained; no guest ELF identity, registry entry or proof fabricated |
| Save / reopen / replay | PASS: shared session and installed wheel | PASS on Windows | Offline inspection, new replay occurrences, linked Julia trajectory → C++ force calculation | Canonical shared gates; final installed-wheel reopening of all 11 bundles in each historical gate 3 workspace |

Additional test results:

- General Python regression: **1664 passed, 603 optional external-provider
  skips, 38 subtests passed**. These skips do not count toward required native
  conformance.
- Final focused contracts/retention suite: **52 passed** in 2.90 seconds,
  including two regressions for rejecting boolean time-vector values and two
  whole-closure history checks.
  Tests using transport doubles remain distinct from genuine native runs.
- Genuine Julia suite: **29 passed**; the subsequent normalized-path
  regression passed separately (**1 passed, 22 deselected**).
- Windows AddressSanitizer: **7 instrumented host tests passed** before the
  later JSON parser feature repair; that repair did not change the C++ kernel.
- Final Linux [native CI run 36265059988](https://github.com/giasonpooni/Scientific-Computation-Runtime/actions/runs/36265059988),
  job `108468054390`, succeeded at the final SCR pin: **8 Rust tests passed,
  15 Python tests passed with 2 deselected, and 8 ASan/UBSan tests passed**.
  The deselected checks are genuine Julia and Windows child cleanup; this
  Linux run does not establish Linux Julia or installed-CIW interoperability.
  The earlier sanitizer link failure was fixed with explicit C++ runtime
  linkage and the corrected sanitizer gate executed successfully.

The final canonical source and installed-wheel gate 4 reports each contain
**16 PASS and 5 NOT_RUN**, with `native_subset_passed: true` and
`full_completion: false`. Both bind the LF worker hash `076935fb…` above.
The preceding gate 3 reports have the same outcomes and remain historical
evidence bound to their CRLF worker hash `e598eafa…`.
Their unrun rows are native exact checking, SP1, UBSan, separate legacy-worker
protocol testing and physical validation. The first, third and fourth have
separate successful evidence above; the reports are not rewritten to imply
those checks ran inside the shared command. SP1 remains blocked, and physical
validation remains unperformed. Cross-provider binary64 and exact-affine
comparisons both had zero discrepancy.

The final boolean time-vector and whole-closure history validation fixes were
followed by a rebuilt and reinstalled wheel. Isolated installed Python, running
outside the source
checkout, reopened and inspected all **11 bundles in each** historical gate 3
source/installed replayed workspace while provider invocation, runtime access and independent
numerical checking were patched to fail if called. Both checks passed. This
is a final offline compatibility check, not another numerical execution.

Operator-retained evidence locations, relative to the development workspace:

- Canonical source gate: `work/pdt-native-interop-v1/results/native-gate-source-4/report.json`.
- Canonical installed-wheel gate: `work/pdt-ig4/report.json`.
- Historical source gate: `work/pdt-native-interop-v1/results/native-gate-source-3/report.json`.
- Historical installed-wheel gate: `work/pdt-ig3/report.json`.
- Final installed reopening: `work/pdt-native-interop-v1/results/native-installed-historical-closure-reopen.json`.
- Canonical Julia exact-candidate check: `work/scr-native-probes/exact-julia-check-canonical/report.json`.
- Historical exact-candidate check: `work/scr-native-probes/exact-julia-check/report.json`.

The final native checker consumed canonical source gate 4 `bundle-04.json`,
bundle identity
`sha256:fd3c8c50a8a048136c930a0f398aaf71fb0fc0d2b2afe600bda3ca9c71692e33`.
Its executable SHA256 was
`b2cd9869e3269f8d50df6bfbeeaa319d5c8ce27899ddd5c160438c1f3a663e35`.
Incrementing `model_output[0]` by one integer numerator changed the outcome
from exit 0 / accepted to exit 2 / refused. This establishes the bounded
native check, not an SP1 proof or a physical claim.

The first general regression attempt had a Windows temporary-directory cleanup
error after the expected output-budget refusal. A focused rerun also exceeded
Windows' path-length limit. With shorter test paths the subprocess file passed
38 tests, followed by the full regression result above. No refusal check was
removed or weakened.

Genuine integration additionally exposed two transport defects before success:
Julia's unresolved `native-interop/../julia-oscillator` path exceeded Windows'
path limit, and the default Rust JSON parser changed selected binary64 values
by one ULP. The worker normalizes file paths. The Rust parser enables exact
binary64 round trips and tests captured failing bit patterns. CIW retains strict
raw-child/outer-result bindings; it does not hide the discrepancy in the
scientific comparison tolerance.

## Separate broader CI status

The successful SCR native-owner job does not cover all Workbench workflows.
Prototype/Godot, installed-package, Windows-deployment and container checks
passed. Other provider-integration and PLSR jobs remain **BLOCKED** at private
repository clone authentication. A separate base Linux pytest failure exposed
an existing empty-directory fixture that expected a wrong-revision error.
The test-only repair now creates a genuine wrong-revision Git checkout and
passed outside any Git ancestor; that file reported **3 passed, 3 optional
SET-provider skips**. The earlier Ubuntu Python 3.11 CI job still records its
pre-repair failure. Other Python matrix jobs were cancelled by CI fail-fast,
not passed; a completed rerun of that matrix is not claimed here. These
outcomes are not counted as native numerical failures or as completed provider
integrations.

## Reproduce

Provision the pinned owner source, compiled host and Julia environments first.
Use the [operator binding](NATIVE_INTEROP.md#runtime-binding-and-execution).
Neither command installs packages or compiles a runtime:

```text
python scripts/check_native_interop.py --probe --binding /operator/native-binding.json
python scripts/check_native_interop.py --run --binding /operator/native-binding.json --output /new/run-directory
```

For the installed-wheel gate, invoke the same script with the isolated installed
Python from a directory outside the source checkout and pass `--fixtures` with
the explicit fixture file. The script does not modify `sys.path`. Existing
output directories are refused. `--require-all` exits nonzero while mandatory
proof/platform gates are incomplete, even when the native subset passes.

The fixed fixture set is
[reference_fixtures.json](../examples/native-interop/reference_fixtures.json).
It contains non-square arrays, negative values, nonzero offsets, exact D256
values, oscillator inputs for independent analytic checks and exact QP goldens.

```text
python -m pytest -q
python -m pytest tests/test_native_interop.py tests/test_native_interop_contract.py -q
```

Set `CIW_TEST_JULIA` and `CIW_TEST_JULIA_DEPOT` for the genuine Julia tests:

```text
python -m pytest tests/test_julia_oscillator.py tests/test_julia_worker_native.py -q
```

The owner SCR README gives compiled-host and ASan/UBSan commands. Its separate
native checker is built with
`cargo build --locked --manifest-path zk/affine-check/Cargo.toml`; point
`CARGO_TARGET_DIR` outside the source checkout. Run `ste-affine-check` with
`--statement-file` pointing to exact canonical statement bytes. It does not
invoke a cryptographic verifier.

The manually dispatched
[native integration workflow](../.github/workflows/native-interop.yml) requires
an operator-provisioned `SCR_READ_TOKEN` for the private owner repository. Its
default full gate refuses incomplete proof/sanitizer evidence. A workflow
configuration is not evidence of a completed run.

## Costs and remaining limits

The canonical gate 4 persistent A/B/A probes measured the following on the
Windows workstation. Package caches already existed, and the source and
installed runs overlapped on that workstation. These are individual runs,
not a speedup study or a statistical latency guarantee. Historical gate 3
measurements remain in their original reports and are not reassigned to the
canonical worker.

| Measurement | Source gate 4 | Installed-wheel gate 4 |
| --- | ---: | ---: |
| Persistent process lifetime (s) | 17.108823 | 17.222081 |
| First dispatch, excluding handshake startup (s) | 1.0456216 | 1.0375479 |
| Two subsequent dispatches (s) | 0.0188950 / 0.0246125 | 0.0195734 / 0.0186976 |
| Combined startup / response-write / teardown overhead (s) | 16.019694 | 16.146262 |
| Request serialization and framing (s) | 0.000233400 | 0.000289100 |
| Three independent affine checks (microseconds) | 90.20 / 176.70 / 105.90 | 117.00 / 90.50 / 81.40 |
| Retained persistent transport (bytes) | 37,167 | 37,168 |
| Nine initial retained bundles (bytes) | 413,510 | 413,491 |

The QP library's reported solve times, initial run / fresh reproduction, were
0.000074863 / 0.000115156 seconds for the source interior case and
0.000254869 / 0.000329971 seconds for its active-bound case. Installed-wheel
values were 0.000079870 / 0.000072956 and 0.000231981 / 0.000281096 seconds,
respectively. These solver-reported intervals exclude host startup and do not
measure the entire Julia calculation. Full reports also retain each execution's
process, dispatch, independent-check, request and response measurements.

The canonical exact checker took **0.0188719 seconds** for the accepted
statement and **0.0149537 seconds** for the altered-candidate refusal. These
are process-launch-through-exit wall times, not isolated checker-kernel times.

Fresh shared reproduction starts another process and is not labelled a warm
benchmark. Peak memory, isolated build/precompilation, isolated Julia/native
calculation and checker-kernel time, genuine proof generation and
fresh cryptographic verification costs remain unmeasured in these reports.
The separate Linux sanitizer result does not turn either shared report into
a full integration pass. No physical accuracy, privacy, actuation authority
or complete cross-platform integration is claimed.
