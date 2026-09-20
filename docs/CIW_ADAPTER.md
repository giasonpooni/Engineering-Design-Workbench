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
for this operation. Temporal covariance is outside its supported contract.

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

## Additive covariance operation: v2

`fsrt.tank-reconstruct.v2` preserves the v1 estimate, reconciliation gate,
residuals and refusals. It adds ordered, content-addressed covariance artifacts;
`fsrt.tank-reconstruct.v1` and its outputs remain unchanged.

```bash
PYTHONPATH=src python -m set_lcm.bridge.ciw < examples/ciw_tank_request_v2.json
```

The new request is also an explicitly synthetic, correlated two-tank example.
In addition to the existing `model` and `observations`, v2 requires:

- `state_order: ["tank-1.mass", "tank-2.mass"]`. The first observation source
  measures the first model state and the second source the second state; the
  explicit source order must not be inferred from a display label or sorted.
- `observation_covariance`: a complete `covariance-artifact.v1` record described
  below. Its matrix must equal the covariance actually supplied to FSRT.

The input artifact must use `quantity_ids` exactly equal to the observation's
ordered `source_ids`, `units: ["kg", "kg"]`, `frame: "reservoir2.mass"`, and
`basis.kind: "calibrated_observation"`. Its ordered source evidence IDs must
equal the observation's two evidence IDs, now strict `sha256:` content IDs.
Artifact reference values must equal every **present** calibrated observation.
For a masked-out coordinate the reference remains a finite declared reference,
not a substitute observation; the measurement remains `null` and its mask false.

`provenance.metadata` must explicitly declare `shared_dependencies` as a list
(possibly empty), and all three supported independence assumptions as Boolean
true: `prior_independent_of_observations`,
`declared_total_independent_of_observations`, and
`prior_independent_of_declared_total`. False, absent or non-Boolean declarations
are refused with `unsupported_covariance_dependence`. The current operation has
no prior/observation, total/observation or prior/total cross-covariance model.
Full correlation **inside** the observation matrix is supported and affects the
posterior; neither a diagonal matrix nor a missing channel proves independence.

The response adds `state_order` and `covariance_artifacts` to the otherwise
unchanged v1 `data`:

| Key | Ordered quantities | Matrix and reference values | Direct covariance sources |
| --- | --- | --- | --- |
| `observation` | Input source order | Exact incoming artifact | Incoming declared sources |
| `prior` | Fixed state order | `prior_std² I`, declared prior means | None: declared model parameter |
| `declared_total` | `total_mass` | Declared total variance and total mass | None: declared model parameter |
| `innovation` | Present sources only | Full principal submatrix of `P_prior + R`, observed innovations | Observation and prior |
| `posterior` | Fixed state order | Existing Gaussian posterior **before** reconciliation | Observation and prior |
| `reconciled` | Fixed state order | Existing final state/covariance, including held results | Posterior and declared total |

Every generated artifact declares its stage, full source/state orders, observed
mask, reference meaning, independence assumptions and shared dependencies.
`upstream_covariance_metadata` retains the input metadata in full, including any
coverage and exclusion declarations. Such metadata records the provider's stated
uncertainty scope; it is not independent verification of that scope. The complete
input artifact and its assumptions also remain available.

With one missing channel, innovation covariance is an explicitly ordered 1 by 1
artifact; the missing residual stays null in the original residual envelope.
With both channels missing, the existing `insufficient_observations` refusal
remains. An exact total can produce a rank-deficient reconciled covariance; this
is a valid PSD output. Singular observation covariance remains refused by the
existing estimator boundary. Balance disagreement keeps posterior and reconciled
numbers equal while preserving their separate stage identities and held status.

### Covariance artifact wire identity

The required artifact keys are `schema`, `covariance_id`, `quantity_ids`, `units`,
`frame`, `reference_values`, `matrix`, `method`, `basis`, `provenance`, and
`assumptions`. The schema is `covariance-artifact.v1`. Quantities are unique,
ordered nonempty names. Units give each quantity's unit; covariance entry `(i,j)`
has the product of units `i` and `j`. The reference vector and square matrix must
be finite JSON numbers, never booleans. `basis` contains `kind` and `id`;
`provenance` contains `provider`, `source_evidence_ids`, `source_covariance_ids`
and optionally JSON-only `metadata`. Source IDs are unique lowercase
`sha256:` identities. `assumptions` contains declared nonempty strings.

`covariance_id` is `sha256:` followed by the SHA-256 of every other field encoded
as UTF-8 with Python JSON options `sort_keys=True`, `separators=(",", ":")`,
`ensure_ascii=True`, and `allow_nan=False`. Identities include ordering,
references, provenance and assumptions, rather than only the numeric matrix.

PSD checks normalize positive-variance coordinates for unit-scale-independent
validation, require normalized symmetry within absolute `1e-12`, and require
both matrix triangles' normalized eigenvalues at least `-1e-10`. A zero variance
requires an exactly zero row and column. These are numerical validation
tolerances, not uncertainty contributions; no symmetrization, diagonalization or
PSD repair modifies the recorded matrix. FSRT still applies its stricter
positive-definite observation guard before running the estimator.

The v2 path does not add NIS/NEES claims, fault identification, a new consistency
gate, or a physical verification result. Its independent rational reference test
checks the existing Gaussian update under correlated measurement errors; it is
software verification, not a sensor calibration or field validation.
