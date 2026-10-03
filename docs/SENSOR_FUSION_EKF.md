# Declared nonlinear sensor fusion

`ciw.sensor-fusion-ekf.v1` extends the terminal's estimation interface to a
bounded Euclidean extended Kalman filter (EKF). It composes analytical model
evaluation and Jacobians from the pinned Sensitivity runtime (JSPT) with the
existing Geometric State Inference Engine (GSIE) covariance prediction and
Gaussian conditioning. The original [sensor-fusion operation](SENSOR_FUSION.md)
and its [linear coordinate transport](SENSOR_FUSION_TRANSPORT.md) retain their
own contracts.

The reusable declaration remains a state contract, dynamics, sensor mappings,
uncertainty and timing. This lane replaces caller-supplied linear matrices with
a small allowlist of declared model families. Configuration chooses data and
parameters; it cannot supply Python, executable expressions, arbitrary imports
or callbacks. Its fixed method is
`jspt.analytic-gsie.error-state-ekf.v1`.

The output is a candidate estimate under the declared models. An EKF is a local
Gaussian approximation for a nonlinear problem. Successful replay does not
establish global accuracy, physical model adequacy, calibrated uncertainty,
observability, canonical state admission or permission to operate machinery.

## Model families and domains

Every model has exactly `family`, `parameters` and `evidence_b64`. The retained
evidence contains exact bytes supporting the caller's model declaration; its
presence does not authenticate a device or validate the model experimentally.
The separate `model_ref` identifies the declared model lineage.

| Family | Parameters | Defined map and limit |
| --- | --- | --- |
| `affine.v1` | `matrix`, `offset` | `f(x) = A x + b`; the offset is explicit, including any declared discretized input effect |
| `quadratic.v1` | Symmetric `hessian`, `gradient` | One scalar output `f(x) = 0.5 xᵀ H x + gᵀ x`, with analytical Jacobian `(H x + g)ᵀ` |
| `componentwise-exp.v1` | Empty object | `f(x) = exp(x)` componentwise; coordinates must be dimensionless and finite execution must remain inside the numerical domain |
| `planar-range.v1` | `position_matrix`, `anchor`, `minimum_range` | One true planar range `‖B x − a‖`; `B` selects two distinct state coordinates in metres, the anchor has two metric coordinates, and a positive exclusion radius bounds the singularity |

The planar-range map uses JSPT's Cartesian-to-polar reference map and retains
its range component and analytical derivative. This supplies a Euclidean range
measurement. It does not supply a bearing residual, attitude estimate, pose
geometry or a general manifold filter. At the anchor the derivative is
undefined. Each row of `position_matrix` must contain exactly one coefficient
equal to one and all others zero, with the two rows selecting different state
coordinates whose units are `m`. General projections, scaled selectors and
implicit unit conversions are refused. Range must be at least `minimum_range`
at every evaluated center, including the posterior center used for the nonlinear
residual. A posterior inside the excluded domain refuses the operation even
when the preceding prediction was admissible.

Coordinate order, units and frame labels remain part of each state and sensor
contract. Affine and quadratic coefficients must carry the dimensional meaning
required by their declarations; array dimensions alone cannot establish it.
Exponentiating a temperature in kelvins is not a valid dimensionless response
model. Use an explicitly defined normalized coordinate when such a response is
intended. The range declaration must bind its position projection, anchor and
measurement to one compatible metric frame.

This lane supports Euclidean states and additive declared process/measurement
noise. UKF, particle, square-root, SO(2), attitude, uncertain coordinate maps and
delayed-measurement capabilities require their own implementations and contracts.
The linear transport operation does not automatically transform these nonlinear
models or chain an EKF result as its upstream.

## What is computed

For a declared discrete transition `f`, process covariance `Q`, measurement map
`h` and joint measurement covariance `R`, the analytical linearizations are

\[
m^-_k=f_k(m^+_{k-1}),\qquad
F_k=\left.\frac{\partial f_k}{\partial x}\right|_{m^+_{k-1}},\qquad
P^-_k=F_kP^+_{k-1}F_k^T+Q_k.
\]

\[
\widehat y_k=h_k(m^-_k),\qquad
H_k=\left.\frac{\partial h_k}{\partial x}\right|_{m^-_k},\qquad
\nu_k=y_k-\widehat y_k.
\]

GSIE operates on a zero-mean Euclidean error state with the retained covariance.
It predicts that error covariance with `F` and conditions it with `H` and the
innovation. The resulting correction is added to `m⁻`; GSIE's guarded Joseph
update supplies the posterior covariance. This avoids treating `H m⁻` as the
nonlinear predicted measurement. All active sensor maps are evaluated at the
same predicted state and their rows follow the retained observation order.

For affine maps this calculation reduces to the declared affine-Gaussian
problem. For nonlinear maps, curvature and an uncertain linearization point
can make the local Gaussian approximation inaccurate. A quadratic observation
can be globally ambiguous even when its local derivative is nonzero. A direct
reference channel, a smaller supported domain and an informative prior can help
define a useful experiment; they do not establish general identifiability.

First-order propagation can also collapse at a stationary Jacobian. For example,
`f(x)=x²` has derivative zero at `x=0`, so an EKF prediction can report zero
propagated state variance when `Q=0` even though the nonlinear image of an
uncertain input is uncertain. The retained covariance describes this local
model-conditional approximation. It does not establish exact preservation of
the original nonlinear probability distribution or its moments.

`Q` is already the covariance for the declared discrete interval. The adapter
does not infer a continuous-time stochastic law or scale covariance from a
model name. Constant inputs such as heater power and ambient temperature may
be represented by a declared affine offset for each interval. That offset and
its model evidence must retain the input meaning; an uncertain input cannot
silently become a deterministic offset.

Prediction-only batches carry the predicted mean and covariance forward and
retain that no observation was assimilated. They do not reuse a previous sample
or replace an absent reading with zero. Innovation diagnostics concern the
declared local model; they are not an automatic outlier gate or an empirical
consistency certificate.

## Input, uncertainty and evidence

The source schema is `ciw.sensor-fusion-ekf-source.v1`. Its shape follows the
existing sensor-fusion source:

| Object | EKF declaration |
| --- | --- |
| Source | `schema`, `experiment_id`, `configuration`, `prior`, ordered `batches` |
| Configuration | Existing `state`, named `configurations`, `noise_policy`, plus fixed `method` |
| Sensor | Existing identity, quantities, units, frame, `model_ref` and calibration; `model` replaces `matrix` |
| Dynamics | `model`, interval-specific `process_covariance`, `model_ref` |
| Observation | Unchanged `ciw.fusion-observation.v1` record bytes, distinct acquisition identity, nominal time/clock, values, calibration reference and raw evidence |
| Measurement noise | Exact active `channel_order`, full covariance `matrix`, declared correlation policy and evidence references; null for prediction only |

The existing bounds remain: 256 KiB source data, at most 16 state coordinates,
16 profiles, 16 sensors per profile, 16 ordered batches and 16 active measurement
channels per batch. Exact covariance symmetry, finite numbers, declared axis
order, calibration applicability and strict forward time remain requirements.
Model evaluation also has numerical and domain refusal checks. The operation
does not repair an invalid covariance or invent missing cross-covariances.

The full within-batch `R` includes correlations between different sensors and
different measured quantities. For mixed units, entry `R[i,j]` has the product
of the two channel units. A channel ordering or unit label is not a substitute
for a measured covariance model. Supporting noise-policy and measurement-noise
evidence references remain external content references; reference formatting
does not establish the statistical declaration's truth.

The noise policy still declares zero prior/measurement, process/measurement
and process/prior cross-covariance, with measurement independence across
batches. Shared calibration bias or gain can create dependence across time.
Represent such effects in a declared augmented state with compatible dynamics
and observation maps, or use a future method that explicitly supports that
dependence. Do not repeatedly treat a persistent calibration error as new
independent measurement noise. Remaining noise must satisfy the declared policy
after augmentation.

All measurements in a joint update use exactly the batch's nominal reference
time and declared clock. Receipt time does not replace acquisition time.
Out-of-order observations, exposure windows, uncertain clock alignment and
arbitrary interpolation do not become supported through selecting EKF. The
existing [calibrated-window](CALIBRATED_WINDOW.md) and
[calibrated-observable](CALIBRATED_OBSERVABLE.md) workflows retain their own
clock and calibration uncertainties under stationary-hold scopes. A dynamic
handoff requires an explicit supported time model and preserved uncertainty.

The calibration artifact, validity interval and observation lineage are caller
declarations. The EKF operation does not run physical calibration or a device
driver. Reusing an acquisition or retained observation record for another
assimilation is refused; separate acquisition occurrences may legitimately
contain identical raw reading bytes.

## Three concrete configurations

| Fixture | State and observations | What it demonstrates |
| --- | --- | --- |
| [`sensor-fusion-ekf-metrology.json`](../examples/sensor-fusion-ekf-metrology.json) | Dimensionless normalized temperature `x=(T−300 K)/(100 K)`; direct reference `T=100 K*x+300 K`, synthetic voltage proxy `0.1 V*x²+0.5 V*x` | Explicit affine drift/offset, direct plus nonlinear channels, correlated mixed-unit `R`, dropout and sensor-profile changes |
| [`sensor-fusion-ekf-range.json`](../examples/sensor-fusion-ekf-range.json) | Cartesian `[x,y,vx,vy]`, two synthetic metric anchors and true range observations | Analytical range derivatives, correlated measurements, one-sensor periods and prediction-only tracking |
| [`sensor-fusion-ekf-thermal.json`](../examples/sensor-fusion-ekf-thermal.json) | Core/shell temperatures in kelvins; direct thermometers; discrete two-capacity RC model | Explicit heating/ambient input effect `Bd*u`, correlated uncertainty, thermometer dropout and affine behavior in the EKF lane |

Every observation and calibration artifact in these fixtures is synthetic.
The metrology voltage response is an illustrative instrument hypothesis, not
a measured polymer constitutive law. The range fixture measures true range
under its declared additive noise model; squaring a noisy range reading while
keeping the original Gaussian `R` would describe a different problem.

The thermal fixture was authored with
`ciw.thermal_reference.model_matrices`: capacities `[1000,400] J/K`, internal
and ambient conductances `[8,5] W/K`, and a five-second sample interval. The
model evidence retains the RC declaration, `Bd`, ordered power/ambient inputs
and `offset=Bd*u` for every batch. Parameter uncertainty is explicitly zero for
this synthetic fixture. This composition does not replace the existing thermal
observer's independent reference or qualify those parameters for a mold,
polymer specimen or manufacturing machine.

## Run, inspect and replay

Both providers use the same preserved pins as the existing fusion/transport
lanes:

| Role | Exact revision | Source tree |
| --- | --- | --- |
| Analytical maps and Jacobians, JSPT | `d910f5a1d7f6dd5f2dd87dfca66990f714f97b18` | `5643cc8204b7aa6cbb73df6bf8984abdcec47d3b` |
| Error-state prediction and conditioning, GSIE | `5241eee6dab434533bdf0cf0e824bc43b4a79831` | `375c031c07592d5bcb1d224780f18ceb886df4a1` |

Provision detached standalone provider roots from the retained original history:

```sh
git worktree add --detach /tmp/net-fusion-ekf-jspt d910f5a1d7f6dd5f2dd87dfca66990f714f97b18
git worktree add --detach /tmp/net-fusion-ekf-gsie 5241eee6dab434533bdf0cf0e824bc43b4a79831
```

Create and inspect a retained metrology experiment:

```sh
python -m ciw sensor-fusion-ekf create --input examples/sensor-fusion-ekf-metrology.json --jspt-repo /tmp/net-fusion-ekf-jspt --gsie-repo /tmp/net-fusion-ekf-gsie --output results/sensor-fusion-ekf-metrology.json
python -m ciw sensor-fusion-ekf inspect --input results/sensor-fusion-ekf-metrology.json
python -m ciw sensor-fusion-ekf replay --input results/sensor-fusion-ekf-metrology.json --jspt-repo /tmp/net-fusion-ekf-jspt --gsie-repo /tmp/net-fusion-ekf-gsie --output results/sensor-fusion-ekf-metrology-replay.json
```

Use the range or thermal fixture as `--input` to create those experiments. Output
paths must be new so earlier retained occurrences remain available. Standalone
provider roots must match the exact revisions, source trees and runtime profile;
membership in the monorepo is not itself an executable binding.

The live workbench registers sources with `kind: sensor-fusion-ekf` and executes
`ciw.sensor-fusion-ekf.v1`. Bind both roles explicitly:

```sh
python -m ciw serve --sensor-fusion-ekf-jspt-repo /tmp/net-fusion-ekf-jspt --sensor-fusion-ekf-gsie-repo /tmp/net-fusion-ekf-gsie
```

Inspection and workspace reopening validate retained commitments and bindings
without provider execution. Explicit replay requires both trusted runtime
bindings and creates fresh execution, result and verification occurrences while
comparing the retained numerical projection. Saved source data cannot restore
an executable binding.

The result retains model evaluation centers, values, analytical Jacobians and
the inner GSIE linear subproblems separately from the outer nonlinear state
identities. Diagnostics distinguish `residual`, evaluated as `y−h(m⁺)`, from
`linearized_residual`, computed in the local GSIE correction problem. These can
differ for a nonlinear sensor map.

Numerical refusal guards are conservative. Covered model algebra is compared
with exact binary64-rational references using componentwise relative tolerance
`1e-8`, preserving exact zeros; overflow, underflow and invalid arithmetic are
refused. Adding the GSIE correction to the predicted mean must preserve that
correction when recovered by subtraction, using JSPT's `1e-8` fidelity check
with zero covariance. A large coordinate origin or cancellation can therefore
cause refusal despite finite inputs. Recenter or scale an explicitly redeclared
model when appropriate and verify its equivalence; the operation does not
silently alter coordinates or relax its guards.

Evidence, operation, execution, result and verification identities remain
separate. Fresh same-implementation reproduction has `independent: false`.
Matching numerical reproduction is distinct from independently assessing a
physical process, admitting canonical state or authorizing a machine action.
Remove temporary provider worktrees with `git worktree remove` after use.

## From fixtures to a measured application

A first polymer use case can begin with recorded pressure and temperature
channels, retaining the original bytes, acquisition identities and reference
measurements. Qualify the specific acquisition, frame, clock and applicable
calibration chain before declaring a physical fusion result. Fit and challenge
the observation/dynamics models on separate experimental records; retain the
joint uncertainty and its shared sources instead of deriving confidence from
sensor names.

For cooling or process monitoring, compare against held-out reference
measurements across the declared operating domain, including missing sensors
and changed profiles. Check estimation error, uncertainty coverage and innovation
behavior under supported noise assumptions. A local fit or matching replay does
not establish those properties. Process quality inference and closed-loop
control then require their own validated models, state-admission and device
execution boundaries.
