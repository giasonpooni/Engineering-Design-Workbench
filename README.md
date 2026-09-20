# Streaming Telemetry Feature Extraction

Part of Notation Systems' computational instrumentation and evidence infrastructure.

[Stack map](https://github.com/giasonpooni/Computational-Instrumentation-Workbench/blob/main/docs/STACK.md) · [Contract](docs/CONTRACT.md) · [Stack role](docs/STACK_ROLE.md) · [Validation](docs/IMPLEMENTATION_PLAN.md)

## Implemented scope

`stfe.window-mean.v1` computes one scalar arithmetic mean from **1–32 samples on a declared regular time grid**, retaining source references, causal support, full input covariance and distinct execution/result identities. The executable is a bounded Python reference, with NumPy differential tests.

It is not a live DAQ bus, FFT/STFT engine, C++ implementation, state estimator, sensor-validity check or admission authority. Unknown covariance remains unknown. It does not estimate covariance from sample scatter.

```sh
python -m pip install -e '.[test]'
python -m stfe < examples/window_mean.json
python -m pytest -q
```

```python
from stfe import window_mean
receipt = window_mean(request)
feature = receipt["result_artifact"]["components"][0]
```

The example has synthetic references, a placeholder source digest and an all-zero implementation revision. They demonstrate the interface, not an authenticated source or pinned production execution. A composing adapter must replace these declarations and verify their binding to retained bytes and the actual provider revision.

## Numerical contract

For ordered values `y`, complete sample covariance `R`, and `w_i=1/N`, the operator computes `mean = wᵀy` and `variance = wᵀRw`.

It checks exact symmetry and positive semidefiniteness of the **stored binary64 matrix**, using rational elimination. It accumulates the mean and covariance exactly over those represented inputs, then rounds once to binary64. A nonzero result that would underflow to zero is refused. It never symmetrizes, clamps, adds jitter or silently drops cross-covariance.

This deliberately conservative reference can refuse a nearly PSD matrix that a tolerance-based validator would accept. Such a refusal does not establish that a sensor is invalid; it says this operation cannot honor the supplied numerical claim without repair.

## Causal and evidence boundaries

- Support is `[start, end)` on a named common clock; `end <= received_by <= decision_time`.
- Event times must exactly match the represented grid. Integer-second or exactly representable binary-fraction grids are suitable; jitter is refused, not rounded away.
- Consumed samples must arrive no earlier than their event time, by the cutoff, and within the declared latency bound. Event reordering, receipt reordering, duplicates, missing samples and imputation are refused.
- Out-of-support samples cannot affect the numerical result. Their bytes remain the acquisition subsystem's responsibility.
- Clock/frame mappings are named references, including explicit identity mappings. STFE neither invents them nor proves their applicability.
- Raw values are retained in the companion window; outputs never replace observations.
- `known` covariance requires a full matrix and `declared` or `declared_zero` cross-covariance. `unknown` requires a null matrix and remains unknown downstream.

## Output and interoperability

The receipt contains a telemetry window, nominal-under-declared-grid quality diagnostic, execution declaration, numerical replay-equivalence record and a `notation.instrument.result-artifact.v1` projection. The result hash follows the existing exchange domain-separation convention; the generic result preserves units, feature-space coordinates, calibration references and source bindings.

`numerical_result_id` excludes execution occurrence, creation time and source-batch digest. The result artifact itself binds those occurrence/provenance fields. This separates numerical replay equivalence from evidence identity. No verification artifact is minted by this operator.

Optional adjacent-checkout conformance tests:

```sh
STFE_SET_REPO=/path/to/State-Estimation-Evaluation-Testbed \
STFE_CIW_REPO=/path/to/Computational-Instrumentation-Workbench \
python -m pytest -q
```

The hosted test workflow pins the external SET checker and CIW inspector. CIW owns any composed replay session. An accepted exchange projection alone does not prove source authenticity, numerical execution, physical validity or ESM admission.

## Stack responsibility

| Instrument | Responsibility at this boundary |
| --- | --- |
| PPDA / RCI | Source capture, retained observation bytes, lineage and calibration claims |
| STFE | Declared window mean and propagated feature uncertainty |
| [Geometric State Inference Engine](https://github.com/giasonpooni/Geometric-State-Inference-Engine) | Separate state estimation and fusion |
| GTE / CBSR | Geometry / declared-constraint reconciliation |
| SET | Exchange eligibility and separately implemented evaluation checks |
| CIW / SCR | Replay composition / declared execution records |
| ESM | Governed evidence admission and release |

The three geometry scaffolds are not dependencies. Public code contains reusable operations, contracts and synthetic fixtures; customer data, calibration profiles, deployment policy and internal planning do not belong here.

## Identity and license

Historical repository names were `Telemetric-State-Stream-Filter` and `Stream-State-Telemetry-Filter`; renaming does not mint observation or execution identities. Current material is distributed under [MPL-2.0](LICENSE). Earlier revisions distributed under AGPL-3.0 retain their original terms.
