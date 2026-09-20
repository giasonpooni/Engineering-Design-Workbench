# Capabilities and limits

FSRT provides fluid measurement reconciliation, static fault geometry, synthetic fault
benchmarks and real-record consistency reports. Numerical claims below refer to the
committed [reports](../results/). [Methods](METHODS.md) explains their assumptions.
No industrial field-validation or general causal-diagnosis claim is established.
The default runtime is NumPy; no CUDA or Rust backend is integrated.

## Reconciliation and measurements

The kernel preserves observations and unprojected estimates, supports hard and soft linear
reconciliation, and reports inconsistency without requiring a correction. It accepts
explicit covariance for uncertain references and relation coefficients. State and covariance
feedback are checked against a full-state Gaussian update.

The [fluid baseline](FLUID_BASELINE.md) maps storage/flow observations and supplied fault
profiles through one interval operator. It carries joint measurement covariance and shared
references, removes declared nuisance effects, and returns ambiguous or insufficient-evidence
outcomes. Boundary measurements support exact interval balances; mean storage requires the
declared within-day flow assumption. The historical reservoir filters retain their separate
daily-mean/reference approximation.

The offset, drift and gain benchmark uses locked magnitudes and disjoint development and
evaluation seeds. Candidate signatures and onset are supplied. Unknown-onset search,
simultaneous faults, operational detection delay and field accuracy are not established.

## Coordinate and camera support

The [invariant layer](INVARIANT_LAYER.md) implements the additive affine Gaussian case,
equivalent to an ordinary Kalman filter. It supports full covariance, missing observations
and fixed affine coordinate charts. Coordinate consistency does not establish physical
conservation, sensor identifiability or nonlinear IEKF support.

The [camera baseline](CAMERA_BASELINE.md) processes synthetic grayscale frames, extracts a
declared horizontal water edge and compensates vertical image translation using a fixed
marker. Shared calibration uncertainty remains correlated across frames. General 3-D pose,
perspective correction, odometry and field validation are not supported. Spectral features
require a complete uniform capture clock and are advisory.

The [recording kit](TANK_RECORDING_PROTOCOL.md) creates blank evidence files and checks
metadata, identities, file presence and supported timestamps. `ready_for_review` does not
validate equipment, calibration or covariance, and the checker does not run real-image
inference. No real tank measurements or field-accuracy results are supplied by the kit.

## Implemented simulation and topology studies

The [two-reach simulation](../results/muskingum_reach.md) evaluates residual-vector diagnosis
with joint covariance on synthetic evidence. With declared routing, all six supplied
instrument faults are identified at the strong tested magnitude across the evaluation
records. A lateral inflow can mimic a gauge fault; adding that physical explanation to the
catalogue produces ambiguity. These results are conditional on the supplied catalogue,
parameters, onset and interval model.

The [second-balance study](../results/second_balance.md) evaluates fault geometry for declared
topologies. The single-closure reservoir has **0 of 4** isolable faults. River continuity
alone reaches **1 of 7**, while the cooling-loop mass/energy pair also reaches **1 of 7**,
leaving fifteen perfectly confounded pairs. Declared routing reaches **5 of 7**; declared
heat-exchanger duty reaches **2 of 7**. The river's one remaining confound is physical:
ungauged lateral inflow versus an inflow-gauge bias. These are design-study results, not
observations of installed equipment.

The [cooling-manifold study](../results/cooling_circuits.md) evaluates metered circuits,
shared thermocouple uncertainty and declared duty. Conservation alone cannot detect the
specified fouling change because it conserves energy. The duty row isolates 18 of 19
declared faults at six circuits. With the header metered, all declared faults are
structurally isolable, but the closest pair still limits separation.

Symmetry produces six tied pairs at six circuits. Increasing the metered circuit count
from one to six moves the hardest-pair amplification by a factor of 1.14; the swept heat-load
prior moves it by 88. At the declared prior that handover falls at four circuits; a
hundredfold looser it falls at three; a hundredfold tighter it never falls in this sweep.
The duty relation and fouling mechanism are declared assumptions; neither is validated on
an installed manifold.

A corrected confound-selection defect had reported a confounded pair as separated at
2.21x. Selecting using the structural label changed confound counts from 6 to 15 and from
1 to 4; the tightest genuinely separated pair is 1.38x. Isolable counts were unchanged.

## Uncertainty in the relation

`ConstraintSet.A_var` supports per-row or full `vec(A)` covariance. The consistency
statistic and projection carry `Cov(E x)`; fault geometry requires an operating point for
an uncertain relation. The [calibration report](../results/errors_in_variables.md) measures
the consequences of treating measured coefficients as exact under its synthetic null.

The [projection report](../results/eiv_projection.md) finds that treating the relation as
exact leaves a nominal 95% region covering 1.5% at the widest tested operating point.
Over-confidence follows `1 + c·scale²` to within 0.10% across a 16x sweep. The declared
version is never worse than leaving the estimate unprojected over that tested range.
The first-order, one-step gain has a measured iteration cost no greater than 0.03 NEES
against a target of 3. Dependence between coefficient error and reference error, or between
coefficient error and state error, is not declared or inferred by this interface.

## Real-record evidence

Committed NOAA and USGS observations are replayable with explicit provenance. Real-record
reports are truth-free. Reservoir declarations support different numbers of inflow gauges
and missing readings; Ridgway and Taylor Park are the two reported sites.

The [diagnosis report](../results/real_diagnosis.md) evaluates declared candidate explanations
on both records. Constant ungauged inflow and an outflow gauge reading low are collinear on
the closure residual. No individual cause is identified. Consumer uncertainty and the
alignment model remain assumptions, and a cause absent from the catalogue cannot be found.

A consistency alarm identifies disagreement among evidence, model and uncertainty. Source
QC flags are corroborating metadata, not verified fault labels. Operational false-alarm
rates, attribution and degradation magnitude require independent validation beyond these
reports.
