# Reconfigurable sensor fusion

The `sensor-fusion` workflow makes a declared state-estimation problem reusable
across sensor arrangements. It composes the existing, pinned Geometric State
Inference Engine (GSIE) through the workbench's source, operation, execution,
inspection and replay contracts. Its operation is `ciw.sensor-fusion.v1`.
The imported inference engines keep their original source, packages and release
identities.

A configuration supplies the state coordinates, geometry, dynamics,
observation maps, covariance and provenance. The adapter validates their
compatibility, invokes the appropriate implemented GSIE geometry and retains
the resulting candidate estimate. Changing a sensor arrangement can reuse the
same operation while preserving the state meaning and uncertainty.

This gives the terminal a shared sensor-fusion interface. Each use case still
supplies a model and supports its assumptions with evidence. Sensor names,
repository membership and numerical agreement do not establish that two
physical inputs measure the same quantity.

## The abstraction ladder

| Layer | Declaration retained by the workflow | Boundary |
| --- | --- | --- |
| Evidence | Observation identity, exact retained record bytes and source references | Retention commits to the supplied bytes; it does not authenticate the acquisition |
| Measurement | Value order, units, frame, nominal time and calibration lineage | Calibration and time applicability remain caller declarations |
| State | Ordered quantities, units, frame, geometry, initial mean and covariance | A posterior is a candidate under the declared model |
| Model | Discrete transition `F`, process covariance `Q`, observation maps `H` and joint measurement covariance `R` | Matrices must describe the declared interval and sensor arrangement |
| Method | Euclidean linear-Gaussian filtering or scalar local-angle filtering | Selection follows supported geometry and model assumptions |
| Composition | Named configurations, active observations and strictly forward batches | Reconfiguration preserves the existing state contract |
| Evaluation | Innovation, covariance and fresh numerical reproduction | Reproduction is scoped, uses the same GSIE implementation and has `independent: false` |
| Domain decision | Physical validation, evidence admission and control permission | These require their own authorities and are not granted by this operation |

The State Estimation Testbed (SET) remains an evaluation instrument. The adapter
does not treat SET as an estimator or use the existence of a SET package as
evidence that a fusion result is consistent. Existing calibrated-observable,
covariance and acquired-window workflows retain their own supported scopes.

## A configuration space, with explicit equivalence

The architectural idea can be expressed as a configuration space whose points
contain a state contract, model, sensor arrangement, uncertainty model, timing
policy and supported filtering geometry. Two points can use the same terminal
interface while describing different scientific experiments.

The implemented reconfiguration changes the active sensor configuration at a
batch boundary. The ordered state coordinates, units, frame, geometry and clock
remain fixed. Prediction carries forward the preceding mean and covariance;
the next observation map conditions that same state. The adapter does not
silently reset uncertainty or initialize a new state when a sensor is absent,
added or replaced.

The retained `configuration_id` and `epoch_index` track the selected sensor
profile together with the fixed state contract and noise policy. They do not
identify the batch's complete stochastic model. Each batch's transition `F`,
process covariance `Q` and `dynamics.model_ref` remain separately bound by the
source and GSIE prediction/state identities. A new interval-specific `F` or `Q`
therefore need not create a new sensor-profile epoch.

A mathematical moduli space requires an equivalence relation, rather than just
a list of interchangeable settings. For estimation, an equivalence claim would
need a declared state map, transformed dynamics and observation models, a
covariance transport rule and a validity domain. For a deterministic invertible
linear coordinate map `x' = T x`, the corresponding mean and covariance are
`m' = T m` and `P' = T P Tᵀ`. Matching dimensions alone does not establish this
equivalence; uncertainty in a physical frame transform also needs its own
joint model.

State transport, coordinate changes, dimension changes and filter-family
changes are future extensions. This operation refuses those changes. Sensor
reconfiguration within a fixed state contract is the implemented first step
toward exploring the larger configuration space.

## Implemented geometries and methods

| Geometry | Supported problem | Current limits |
| --- | --- | --- |
| `euclidean.v1` | Linear state and observation maps, with Gaussian mean/covariance conditioning | Caller-discretized matrices, declared independence and explicit joint measurement covariance |
| `so2_scalar_radians.v1` | One angle in radians, using a wrapped innovation and local tangent covariance | Scalar state, identity transition and identity observation map; one scalar observation per batch |

Euclidean filtering is exact conditioning for the declared linear-Gaussian
problem in exact arithmetic. Binary64 execution still has numerical limits.
GSIE uses linear solves, requires a positive-definite innovation covariance and
uses a guarded Joseph covariance update. It refuses a singular innovation
covariance rather than inventing regularization.

The angle method is a local Gaussian approximation on SO(2). It wraps the
mean and innovation and retains variance in a local tangent coordinate. It
does not represent multimodal circular uncertainty, a three-dimensional
rotation, a pose or a general Lie-group EKF. Alternative angle sensors can be
selected in successive forward batches; correlated simultaneous angular
measurements do not fit this scalar observation contract.

General EKF, UKF, particle, square-root and error-state methods are not
implemented by this adapter. A future capability registry must declare their
required transition and observation functions, derivative or sigma-point
semantics, state geometry, numerical limits and replay profile before they can
be selected. Configuration data must not authorize arbitrary executable code.

## Retained input contract

The source schema is `ciw.sensor-fusion-source.v1`. The two example files are
complete input fixtures, including their retained base64 observation and
calibration artifacts.

| Object | Required content |
| --- | --- |
| Source | `experiment_id`, `configuration`, `prior` and ordered `batches` |
| `configuration.state` | Ordered `quantity_ids` and `units`, one `frame`, supported `geometry` and `clock_id` |
| `configuration.configurations` | Named profiles, each containing its sensor adapters |
| Sensor adapter | `sensor_id`, ordered measurement `quantity_ids` and `units`, measurement `frame`, observation `matrix`, `model_ref` and `calibration` |
| Calibration | Exact `artifact_b64`, half-open `valid_interval` and `claim_scope: caller_declared_not_verified` |
| Prior | Nominal `time`, state `mean` and state `covariance` |
| Batch | Increasing `time`, `configuration_ref`, `dynamics`, `observations` and `measurement_noise` |
| Dynamics | Interval-specific `matrix`, `process_covariance` and `model_ref` |
| Observation | Active `sensor_id` and exact `record_b64` |
| Decoded observation record | Schema `ciw.fusion-observation.v1`, sensor binding, distinct `acquisition_id`, `time`, `clock_id`, ordered quantities/units/frame, `values`, `calibration_ref` and original `raw_evidence_b64` |
| Measurement noise | Exact `channel_order`, full covariance `matrix`, `cross_sensor_policy` and content `evidence_refs`; null for prediction only |

`configuration.noise_policy` requires `declared_zero` for
`prior_measurement_crosscovariance`, `process_measurement_crosscovariance` and
`process_prior_crosscovariance`, together with
`across_batches: declared_independent` and supporting `evidence_refs`. These
noise-policy references and the measurement-noise `evidence_refs` are external
content references: their supporting artifacts are not retained as base64 in
this source. The workflow checks the declarations and reference format; it
cannot authenticate their statistical truth from a reference identifier.

Source data is bounded at 256 KiB. There are at most 16 state quantities,
16 named profiles, 16 sensors per profile, 16 batches and 16 active measurement
channels per batch. Values and matrices must be finite, match the retained
axis order and pass the covariance domain checks. Covariance matrices must be
exactly symmetric; the adapter does not repair an asymmetric input.

Unit and frame fields are exact semantic labels. Their equality is checked
against the selected sensor model. The adapter does not perform dimensional
analysis of matrix coefficients or validate a physical frame transformation.
Those obligations remain with the declared observation model. Reusing the
same retained observation or `acquisition_id` for another assimilation is
refused. Raw-byte digests identify content rather than acquisition occurrences:
different acquisitions may legitimately have identical raw bytes. A new
`acquisition_id` is a caller declaration of a distinct occurrence; changing that
label does not authenticate a new physical acquisition.

## What each batch means

A batch advances to a strictly later nominal time. The caller supplies the
discrete transition `F` and process covariance `Q` for that interval; the
adapter does not infer discretization from a model name or multiply `Q` by an
elapsed time automatically. Prediction is

\[
m^-_k=F_k m^+_{k-1},\qquad
P^-_k=F_k P^+_{k-1}F_k^T+Q_k.
\]

Each active observation supplies a declared sensor model. Its rows are stacked
in retained observation order into `H`, and its values into `y`. Measurement
units can differ by row, for example metres and metres per second. The declared
observation map is responsible for that meaning; the workflow does not infer
unit conversions. All observations in a joint batch must have the same
declared measurement frame and exactly the batch's nominal time.

For Euclidean updates, the retained joint `R` includes every within-batch
cross-covariance. With innovation `ν = y − H m⁻`, the declared calculation is

\[
S=HP^-H^T+R,\qquad
K=P^-H^T S^{-1},\qquad
m^+=m^-+K\nu,
\]

\[
P^+=(I-KH)P^-(I-KH)^T+KRK^T.
\]

The inverse notation defines the mathematics; GSIE performs solves. The
normalized innovation squared, `νᵀ S⁻¹ ν`, is a diagnostic for this assumed
model. It is not an outlier gate, an observability certificate or physical
validation. The adapter does not invoke an OIT observability gate.

The model requires measurement noise to be independent of the prior, process
noise and measurements in other batches. Prediction also assumes that process
noise is independent of the incoming state. Distinct sensor identifiers do not
establish independence. A persistent calibration error shared across times
can be represented by a manually augmented Euclidean state with compatible
`F`, `Q` and `H`. The adapter does not infer the bias state or its dynamics.
The measurement noise remaining after that augmentation must still satisfy the
declared independence policy; arbitrary cross-batch measurement covariance is
not supported.

A batch declaring independent sensors must provide zero off-diagonal
blocks between their measurements. A batch declaring joint correlation
must supply its full matrix; missing or unknown cross-covariance cannot be
replaced with zero. Correlation within one joint batch does not authorize
dependence across batches or between observations and the prior.

An empty observation list explicitly requests prediction only. Its measurement
covariance is null. This carries forward process uncertainty and records the
absence of conditioning; it does not substitute a zero observation or reuse an
old sample.

## Evidence, calibration and time

The source retains exact calibrated-record bytes in base64 together with the
declared calibration profile lineage and applicability interval. Validity is
evaluated at the observation's nominal time. Historical acquisition
applicability is distinct from whether a profile is usable at today's serving
time; see [Covariance provenance](COVARIANCE.md). This workflow checks the
declared nominal-time interval only; it does not generate a current serving-time
calibration assessment.

The adapter checks structural compatibility, the retained commitments and the
declared applicability. It does not independently run calibration, authenticate
the physical sensor, establish a surveyed frame, synchronize clocks or verify
the calibration record against a live device. The caller must support those
claims through the appropriate measurement instruments.

Delayed, out-of-order or differently timed samples are refused. Clock
uncertainty, exposure windows and integration intervals cannot be collapsed
into an exact nominal time without an appropriate declared model. A later
fixed-lag or delayed-measurement method needs a separate capability and retained
state history.

## Run, inspect and replay

Use an exact standalone GSIE checkout at
`5241eee6dab434533bdf0cf0e824bc43b4a79831`. The imported subtree is preserved
source, while the adapter's runtime checks require a standalone repository root
and exact source revision. From the monorepo root, provision a detached
worktree using the retained original history:

```sh
git worktree add --detach /tmp/net-sensor-fusion-gsie 5241eee6dab434533bdf0cf0e824bc43b4a79831
```

Create and inspect the retained tracking experiment:

```sh
python -m ciw sensor-fusion create --input examples/sensor-fusion-tracking.json --gsie-repo /tmp/net-sensor-fusion-gsie --output results/sensor-fusion-tracking.json
python -m ciw sensor-fusion inspect --input results/sensor-fusion-tracking.json
python -m ciw sensor-fusion replay --input results/sensor-fusion-tracking.json --gsie-repo /tmp/net-sensor-fusion-gsie --output results/sensor-fusion-tracking-replay.json
```

The tracking example declares a position/velocity state and different sensor
arrangements. The angle example, `examples/sensor-fusion-angle.json`, exercises
the scalar radians geometry through the same operation. Both are declared
numerical examples; they supply no measured physical performance claim.

The native workbench accepts `source.add` with `kind: sensor-fusion` and executes
`ciw.sensor-fusion.v1`. Its provider binding is
`serve --sensor-fusion-gsie-repo /tmp/net-sensor-fusion-gsie`. One operation
execution contains the declared ordered numerical batches; each batch is not
a separate workbench execution occurrence. Retained bundles use the existing
inspection and replay surfaces. Inspection reads retained evidence and commitments without executing
GSIE. Explicit replay requires an operator-provisioned compatible runtime and
creates fresh execution, result and verification occurrences while comparing
the retained numerical projection.

The source identity, operation identity, execution occurrence, result identity
and verification identity remain separate. The verification records fresh
same-implementation reproduction with `independent: false`. Neither
reproduction nor a positive covariance admits the estimate as canonical state
or grants machine execution permission.

Remove the detached provider worktree when it is no longer needed:

```sh
git worktree remove /tmp/net-sensor-fusion-gsie
```

## References and next acceptance work

The foundational discrete filtering paper is R. E. Kalman (1960),
[A New Approach to Linear Filtering and Prediction Problems](https://doi.org/10.1115/1.3662552).
Simo Särkkä and Lennart Svensson (2023), *Bayesian Filtering and Smoothing*,
second edition, provides the broader filtering and smoothing context; see the
[author's bibliography](https://users.aalto.fi/~ssarkka/#books).
These references describe mathematical methods. Their availability does not
qualify an unimplemented adapter capability.

The acceptance path is analytical Euclidean conditioning, preserved full
within-batch correlation, prediction-only missingness, scalar angle wrapping,
explicit sensor reconfiguration and fresh replay. Refusal checks cover
incompatible dimensions, units, frames, geometry, timestamps, calibration
applicability, undeclared dependence and tampered retained data. Broader
deployment needs measured datasets, domain-specific consistency studies,
qualified frame/clock/calibration chains and independent evaluation before
making a physical sensor-fusion claim.
