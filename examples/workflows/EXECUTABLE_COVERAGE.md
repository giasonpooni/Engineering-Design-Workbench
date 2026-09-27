# Executable coverage milestone (frozen 10 profiles)

Generated locally: 2026-09-27T22:46:06Z. Catalog freeze **9074**. No new CIW kinds. ESM **cite_only**.

## Layer histogram (unique-profile representatives)

| Layer | Status histogram |
| --- | --- |
| catalog | pass=10 |
| export | pass=10 |
| executable | blocked=1, not_run=2, pass=6, unavailable=1 |
| numerical | not_run=2, pass=7, unavailable=1 |
| checking | pass=10 |
| replay | not_run=2, pass=7, unavailable=1 |
| ESM | cite_only=10 |

## Per-profile executable path

| Profile | Before exec | After exec / num / replay | Path class |
| --- | --- | --- | --- |
| ENERGY_ACCURACY | not_run | pass / pass / pass | native_offline_analysis (`EnergyAccuracyWorkflow` + `ciw energy replay`) |
| VFE | not_run | pass / pass / pass | provider_free_free_energy_math |
| CSG | not_run | pass / pass / pass | HOST_SYNTHETIC_Jacobi_strip |
| GTE_CIRCLE | not_run | pass / pass / pass | HOST_teaching_radial_residuals |
| RESIDUAL_CUSUM | not_run | pass / pass / pass | HOST_synthetic_CUSUM |
| PLSR | not_run | pass / pass / pass | HOST_ANALOG_identity_certificate (proof NOT_CHECKED) |
| FSRT | blocked | blocked / pass / pass | HOST_hard_reconcile; still no `ciw.fluid-volume.v1` |
| CSE | not_run | not_run | template posteriors only |
| MEASUREMENT_CHAIN | not_run | not_run | schematic stages only |
| PROVED_HEAT | unavailable | unavailable | no SP1 binaries; refuse cases checked; no VERIFIED |

## How to re-run

```bash
python3 examples/workflows/run_executable_coverage.py
```

Prefers `build_coverage_report.py --attempt-execute`; falls back to `_bcr_attempt_shim.py` overlay.

Machine twin: [`executable_coverage_summary.json`](executable_coverage_summary.json). Full report: [`coverage_report.md`](coverage_report.md) (regenerate locally for attempt-execute detail).
