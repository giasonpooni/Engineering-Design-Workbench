# Pinned CIW subprocess operation

`python -m set_lcm.bridge.ciw` reads one UTF-8 JSON request from standard input
and writes one JSON response to standard output. It requires only FSRT and its
existing NumPy dependency, makes no network requests, and writes no files. CIW
must pin and verify the FSRT revision; this worker does not choose its own pin.

```bash
PYTHONPATH=src python -m set_lcm.bridge.ciw < examples/ciw_tank_request.json
```

The checked-in request is **synthetic**, using the two-tank quickstart's 52/46 kg
case with explicitly correlated measurement errors. It is not a measured tank
record or evidence of field calibration. Existing NOAA/USGS fixtures belong to
different fluid models and are not re-labelled as tank observations.

## Scope and ownership

`fsrt.tank-reconstruct.v1` evaluates **one simultaneous snapshot** of two
reservoir masses in kg. It calls the existing FSRT `KalmanFilter.ingest` and
`consistency_stat`/`reconcile` implementations. No scientific kernel is copied
to CIW, no simulator truth is accepted, and no temporal prediction is performed.

The model declares an independent Gaussian prior (two means, one isotropic
standard deviation) and an independently declared total mass with its variance.
The observation declares its complete 2 by 2 covariance; off-diagonal terms are
retained. All present masses and the declared total must be nonnegative.
Gaussian posterior or reconciled means outside that nonnegative domain are
refused with `physical_model_refusal`; balance consistency alone does not establish
physical admissibility. The wrapper does not clamp negative mass or change the
scientific kernel into a constrained estimator.

Independence of the prior, total and observation is a **model assumption supplied
by using this operation**, not a verified property. If they share calibration or
reference evidence, this operation is unsuitable: it does not model those cross
covariances. A two-channel observation may share a calibration because its full
within-snapshot covariance is explicitly supplied.

Multiple timestamps are refused with `unsupported_temporal_covariance`. Shared
calibration uncertainty across time must not be converted to independent noise
for this operation. A future temporal adapter must represent it or refuse it.

For RCI integration, use separately calibrated mass channels, align their physical
sample times, and supply their calibrated evidence IDs and full joint covariance.
Combining two RCI results diagonally requires an explicit independence declaration
for the two assemblies/calibrations. CIW owns this construction, raw-byte retention,
calibration validity, investigation persistence, and distinct execution/result IDs.
FSRT receives already calibrated observations and does not repeat calibration.

## Wire contract

The complete input shape is `examples/ciw_tank_request.json`. Required top-level
fields are `schema: "ciw.adapter-request.v1"`,
`operation_id: "fsrt.tank-reconstruct.v1"`, and `inputs`. Unknown fields are
refused, including hidden truth or an undeclared covariance representation.
`t` and `arrival_t` are physical sample and availability seconds in the caller's
declared clock; availability must not precede sampling. `source_ids` and
`evidence_ids` preserve the fixed tank ordering and must each have two distinct
nonempty IDs. A missing value is `null` with a Boolean `false` mask; its innovation
remains null, and an estimated state must never be presented as its observation.

Success has `schema: "ciw.adapter-response.v1"`, `status: "ok"`, and `data`:

- `calibrated_observation`: unchanged input observation and its full covariance.
- `unprojected_estimate`: the Gaussian posterior before balance reconciliation.
- `estimate`: the resulting state and its full covariance, explicitly an estimate.
- `residuals`: innovations, innovation variances, balance residuals before/after,
  and any correction. A held correction has no fabricated after-residual.
- `diagnostics`: consistency statistic, declared 0.999 reference threshold,
  reconciliation status, physical-model status and fault-attribution status.
- `observation_evidence_ids` and `assumptions`: provenance and model limits.

Physical-model disagreement returns an `ok` **computation**, with
`physical_model_status: "physical_model_disagreement"`; reconciliation is held
and the unprojected state/covariance remain visible. It does not return a healthy
physical status. A single total-mass residual cannot distinguish sensor bias,
leak, an omitted process or a stale total, so attribution remains
`confounded_or_unidentifiable` when disagreement or missing data is present.
An adequate balance reports `consistent`, which does not certify sensor health.

A refusal has `status: "refused"` and `refusal: {code, message}` with **no `data`**.
Invalid/singular covariance and numerical failures use `numerical_refusal`;
input, model, unit, JSON and absent-data failures have separate codes. JSON never
contains NaN or Infinity, and duplicate input keys are refused. Process exit zero means a valid protocol response was
produced, not that the science was accepted; callers must inspect `status`.
