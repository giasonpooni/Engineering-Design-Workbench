# Correction-loop validation — 2026-10-03

Baseline: `cbb1db3aa2ad7287c2587b5e542f6a7d90cfb88f`. This increment extends
that merged substrate without changing scientific evidence/result identities,
provider pins, calibration applicability or external operating authority.

## Executed checks

| Gate | Result | Scope |
| --- | --- | --- |
| Final journal/Session/socket focused suite | **94 passed**, no skips | Journal boundaries, source/reference correction, transitive claims, alias withdrawal, storage rollback, atomic checkpoint recovery, v1–4 restore, CLI and native/spatial socket boundaries. |
| Installed-wheel journal/Session/machine suite | **89 passed**, no skips | Tests import the isolated wheel, not the source package. This is overlapping validation, not 89 additional independent scientific claims. |
| Broad source regression | **2,431 passed**, **729 skipped**, **38 subtests passed** | Existing core and optional-provider test collection; skipped provider/platform gates were not executed. Final additional reference-import cases are covered in the focused and installed suites above. |
| Source correction demonstration | **Passed** | Actual registered provider-free encoder operation, local review, fresh identities, exact historical preservation and offline reopen. |
| Installed-wheel correction demonstration | **Passed** | Same fixtures and lifecycle through the packaged implementation, with actual imported module paths checked. |
| Wheel/source comparison | **124 packaged files match** | Every packaged CIW source/resource byte matches this checkout. This is package consistency, not a native source-to-binary attestation. |

The wheel SHA-256 is
`6df87877823fb922d48ed4464512b0196dbbd5820e9ee0046f9b7eae913e1d20`.
Tests ran on Python 3.12.14 with NumPy 2.4.3 and pytest 9.0.2. No Julia, SCR,
SP1, sensor, actuator or private scientific provider was newly qualified.

## Retained synthetic experiment

At 300 decoded counts, the original declared encoder/gearbox/leadscrew model
returns **1.001 m**. The withheld synthetic reference is **0.998 m**. A
**0.5 mm diagnostic threshold** flags the **3 mm residual**. The candidate
homing offset changes from **1.000 m** to **0.997 m**; a fresh invocation then
returns **0.998 m**, with zero residual for this point.

The reference is an explicit data-only retained source, not merely text in a
claim's rationale. The accepted model-source review makes the original source
aliases, execution, result, bundle and dependent claims stale. It leaves the
original evidence bytes and recording unchanged. A later invocation of the old
source remains stale. A separate reference correction test makes only the
reference-dependent claim stale, preserving the unrelated encoder output.

The source demonstration workspace SHA-256 is
`98cc95d04deefb26bba9b6b2c8b677213d3f80450da61a116a87ffd458e3f15c`.
Its exported report binds the original/corrected/reference fixture bytes, source
identities, correction decision, bundles, executions and results. Fresh reruns
have fresh occurrence identities and consequently different workspace digests.

## Reproduce

```bash
python scripts/check_correction_loop.py --output-dir results/correction-demo
python -m pytest tests/test_correction_journal.py tests/test_correction_session.py tests/test_workbench_transport.py tests/test_server_json_boundary.py -q
python -m pytest -q
ciw dependencies results/correction-demo/workspace.json
```

Use the project's declared development dependencies. The demo refuses an
existing output directory. Test counts depend on checkout, optional bindings,
platform and which final cases have been collected; skips are reported separately.

This qualifies a bounded local correction workflow. The algebraic threshold is
not a probabilistic confidence interval. Physical calibration performance,
authenticated review, ESM/canonical-state admission, actuator authorization,
comprehensive certificate premises and regulator acceptance remain open.
See [the operation contract](CORRECTION_LOOP.md) and
[the concerns audit](CONCERNS_AUDIT_2026-10-03.md).
