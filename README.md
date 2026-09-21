# Metrological Calibration and Uncertainty Runtime

[Stack placement and ownership](docs/STACK.md) · [License](LICENSE)

MCUR is a bounded scientific instrument for applying a declared affine measurement calibration and propagating its joint uncertainty. It keeps the raw observation, indicated value, corrected value, calibration evidence references, applicability checks, and uncertainty budget distinct.

The implemented operation is `mcur.affine-first-order.v1`:

\[
y=gx+b,\qquad J=[g,\;x,\;1],\qquad u_y^2=J\Sigma_{[x,g,b]}J^T.
\]

The complete ordered covariance includes correlation between the indication, gain, and offset. Calibration coefficient covariance is pinned in the profile and must equal the corresponding block in the supplied joint covariance.

## Status and scope

This repository contains an executable Python foundation, synthetic replay, analytical and adversarial tests, and optional export into the existing State Estimation Evaluation Testbed (SET) result contract. It does not contain a physical sensor integration, calibration fitting service, calibration certificate issuer, or operational admission controller.

Current behavior:

- Check sensor, quantity, input unit, acquisition-time validity, indicated-value range, and declared environmental applicability.
- Preserve raw and indicated values while returning a separate corrected value and first-order uncertainty budget.
- Accept correlations, negative covariance contributions, and exactly positive-semidefinite singular matrices.
- Reject nonfinite, asymmetric, or indefinite covariance, including very small numerical scales; never clip eigenvalues or silently symmetrize inputs.
- Retain optional reported serving status separately from validity at acquisition time.
- Export a caller-mapped result with distinct operation, execution, input, result, and verification identities through SET's existing `notation.instrument.result-artifact.v1` contract.

The calibration is affine in `x` for fixed coefficients, but `g*x` is jointly nonlinear when both are uncertain. The reported uncertainty is a first-order approximation. Supplied reference IDs are evidence pointers; their presence does not establish certified metrological traceability.

## Run

Requires Python 3.11 or later.

```bash
python -m pip install -e '.[test]'
python -m pytest -q
python examples/replay.py
```

The synthetic replay has `raw=300`, `indicated=3 kPa`, `g=2`, and `b=1 kPa`. It returns `corrected=7 kPa` and variance `22.35 kPa²`, including all covariance terms.

For the pinned SET conformance example:

```bash
python -m pip install -e '.[test,exchange]'
python -m pytest -q
python examples/exchange.py
```

The optional dependency is pinned to SET commit `bd261a765281a95312f7c91a3857233476294c5b`. Base installations skip exchange tests when SET is absent; CI installs both extras. The example's all-zero source revision is explicitly synthetic and unattested. A real caller must supply its actual source commit and execution reference. Contract conformance neither attests that commit nor verifies physical calibration.

## Public API

```python
from mcur import CalibrationProfile, JointCovariance, Observation, calibrate

result = calibrate(observation, profile, joint_covariance)
```

`Observation`, `CalibrationProfile`, `JointCovariance`, and `CalibrationResult` are immutable typed records. `Interval`, `EnvironmentReading`, and `EnvironmentRequirement` express applicability. `ServingStatus` carries a caller-reported `ServingState` independently of acquisition-time validity. Invalid scientific inputs raise `CalibrationError`.

The complete examples demonstrate concrete record construction. The optional `mcur.exchange.export_result` helper deliberately requires an explicit scientific-to-contract mapping.

## System boundary

| Neighbor | Relationship |
| --- | --- |
| Provenance-Preserving Data Acquisition (PPDA) | Retains source bytes and extraction lineage. MCUR consumes a referenced observation and never rewrites that evidence. |
| RCI measurement adapter | Retains its acquisition and measurement boundary. MCUR provides reusable calibration profile and propagation math; no RCI replacement or native adapter is implemented here. |
| Jacobian Sensitivity Propagation Testbed (JSPT) | Generalized sensitivity and uncertainty propagation remain separate from this measurement-specific calibration operation. |
| Geometric State Inference Engine (GSIE) | May consume the corrected measurement and candidate uncertainty through an explicit mapping. MCUR does not infer plant state or certify estimator adequacy. |
| SET | Owns the existing exchange contract and external conformance validation. |
| CIW / ESM | Bind evidence, executions, results, verification, and admission under their own authority. This repository has no native CIW adapter and grants no admission or actuation authority. |

See [the contract](docs/CONTRACT.md), [numerical semantics](docs/NUMERICS.md), and [stack role](docs/STACK_ROLE.md).

## License

Mozilla Public License 2.0. See [LICENSE](LICENSE).
