# Curved-surface micro-tools

Use CSR's existing transfer-map mathematics without constructing a full instrument
campaign. This is an additive interface: existing models, transfer records,
calibration contracts, covariance guards and experiment commands are unchanged.
NET remains a consumer, not the owner of this mathematics.

## Array API

```python
from geodesic_testbed.microtools import (
    propagate_pose, propagate_box, propagate_covariance,
)

s = [0.0, 1.0, 2.0]  # arclength in metres, NOT time
pose = propagate_pose(s, 0.0, [0.002, -0.001])
bounds = propagate_box(s, 0.0, [0.002, 0.001])
covariance = propagate_covariance(s, 0.0, [[4e-6, 1e-6], [1e-6, 1e-6]])
assert pose.shape == bounds.shape == (3, 2)
assert covariance.shape == (3, 2, 2)
```

All APIs accept numeric NumPy arrays or sequences, reject booleans/numeric strings,
and return independent arrays. The coordinate order is always lateral displacement
then heading in radians. Curvature must use inverse squared length units consistent
with the supplied arclength and lateral coordinates. Nothing converts units.

`transfer_map` is a validated facade over the existing
`engine.transfer.constant_curvature_transfer`. Pose propagation calls the original
`TransferMap.propagate`. The box operation calls that same signed-pose operator on
four corners; covariance uses the original strict `propagate_covariance`, including
its covariance and lost-variance guards. No solver has been copied into NET.

## Language-neutral operations

`evaluate(operation_id, request)` returns a detached JSON result. Common fields:
`arc_length`, `curvature`, `length_unit` (`m`, `cm`, `mm`), and an explicit `frame`.

| Operation | Additional input | Output |
| --- | --- | --- |
| `csr.pose-propagate.v1` | `initial_error: [lateral, heading]` | Signed sampled errors, shape n x 2 |
| `csr.error-box.v1` | `initial_bounds: [lateral, heading]`, `tolerances: [lateral, heading]` | Worst-case sampled component bounds and declared tolerance PASS/FAIL |
| `csr.covariance-propagate.v1` | Full `covariance`, shape 2 x 2 | Marginal propagated covariance at each sample, shape n x 2 x 2 |

The result keeps the exact JSON request, transfer matrices, basis, units, model,
scope and numerical values. PASS means only that the returned first-order component
bounds do not exceed the supplied limits at the supplied samples. It is not
physical acceptance, a verification occurrence, or authorization to move equipment.

`python -m geodesic_testbed.microtools` reads one bounded JSON request on stdin and
writes one response on stdout. It speaks the existing `ciw.adapter-request.v1` /
`ciw.adapter-response.v1` transport without depending on the `ciw` Python package.
Errors return a refusal with no numerical result. Saved JSON never names code to
import or a command to execute.

```json
{"schema":"ciw.adapter-request.v1","operation_id":"csr.error-box.v1","inputs":{"arc_length":[0,1,2],"curvature":0,"length_unit":"m","frame":"fixture-A/surface","initial_bounds":[0.002,0.001],"tolerances":[0.003,0.001]}}
```

This returns a valid calculation with a failed tolerance check: the last lateral
bound is 0.004 m against a 0.003 m limit. That is not a provider failure.

## Useful bounded applications

An industrial fixture or probe can use the box response to inspect how declared
starting alignment tolerances spread along an idealized surface. A game or
simulation tool can use the identical operator to inspect curved-world movement
or camera-path sensitivity. A scientific notebook can compare the plane, sphere
and hyperbolic response and study the full correlated starting covariance.

These are numerical reference applications, not CAD collision clearance,
mesh navigation, material mechanics, controller stability, or qualified robot
motion. Real measured geometry and calibration still use the original richer
CSR contracts. There is no Blender/Godot/Bevy scene adapter in this increment.

## Numerical and scientific limits

The initial micro-tool profile accepts 1..512 strictly increasing, nonnegative
arclength samples with s <= 1e6. K is zero or 1e-12 <= |K| <= 1e6, and
sqrt(|K|) * max(s) <= 4. All values must be finite; very small nonzero inputs below
1e-100 are refused rather than silently erased. The wire request budget is 64 KiB.
These are declared implementation limits, not inferred physical validity limits.

The outputs solve a FIRST-ORDER constant-curvature transverse model. A numerical
answer does not establish validity for a finite displacement or an arbitrary
measured surface. Box bounds are deterministic, not root-sum-square uncertainties.
Covariance cross terms are preserved; no noise model, confidence level, independent
samples, cross-sample covariance matrix, interpolation or missing-value filling is
invented. The stored transfer matrices permit a downstream specialist to form a
joint model when that model is explicitly declared.

## Qualification

Run `python -m pytest tests/test_microtools.py`. Tests exercise the real original
CSR kernel, independent closed forms, the semigroup identity, correlated and
singular covariance, refusal cases, units, immutability and the actual subprocess.
The dedicated Linux/Windows workflow also runs the installed wheel outside the
source checkout. The original repository verification workflow remains unchanged;
this focused gate does not waive or replace it.
