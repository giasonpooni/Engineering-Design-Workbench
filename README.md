# Observability and Identifiability Testbed

[Stack placement and ownership](docs/STACK.md) · [License](LICENSE)

A bounded scientific instrument for **finite-horizon linear observability** and
**local parameter sensitivity diagnostics**. Given a declared model or Jacobian,
it reports numerical rank, conditioning, numerical nullspaces and weak directions.
It does not estimate state, select sensors, admit evidence or actuate equipment.

The implemented foundation is a Python/NumPy library with analytical fixtures,
a runnable replay example and CI for Python 3.11 and 3.12. A full-rank result is
conditional on the supplied model, coordinate scales, horizon and tolerances; it
is not a claim that a physical plant is observable or globally identifiable.

## Install and run

```sh
python -m pip install -e '.[dev]'
python -m pytest
python examples/replay.py
```

For the optional SET exchange adapter and its conformance example:

```sh
python -m pip install -e '.[dev,exchange]'
python examples/exchange.py
python -m pytest
```

This extra pins SET at commit `bd261a765281a95312f7c91a3857233476294c5b`.
The example uses synthetic evidence references and an all-zero revision claim
explicitly marked as unattested. Export conformance is neither independent
verification nor CIW execution/admission.

## Implemented operations

| API | Input | Output |
| --- | --- | --- |
| `lti_observability` | Discrete-time transition `A`, observation `C`, positive integer horizon, ordered state names, optional scales | `O_H = [C; CA; ...; CA^(H-1)]` and rank diagnostics |
| `local_identifiability` | Local sensitivity `J`, SPD measurement covariance `R`, ordered parameter names, optional scales | Whitened sensitivity, `J.T solve(R, J)` and local rank diagnostics |
| `rank_diagnostics` | Nonempty finite real matrix and declared tolerances | Singular values, rank, condition measures, right nullspace and weak retained directions |

```python
from oit import lti_observability, local_identifiability

observability = lti_observability(
    [[1, 1], [0, 1]], [[1, 0]], 2,
    state_names=("position_m", "velocity_m_per_s"),
    state_scales=[1.0, 1.0], rank_rtol=1e-12,
)
assert observability.diagnostics.rank == 2

parameters = local_identifiability(
    [[1, 2]], [[4]], parameter_names=("offset", "gain"), rank_rtol=1e-12,
)
assert parameters.diagnostics.rank == 1
```

Scales declare `x = diag(state_scales) z` or
`theta = diag(parameter_scales) z`. Omitting them is explicitly reported as
**raw model/parameter coordinates and units**. Singular values and conditioning
depend on those choices. Names declare ordering; they do not implement a unit
conversion system. See [the numerical contract](docs/NUMERICS.md).

## Position in the instrument system

GSIE can supply an estimation model for diagnosis. JSPT can supply evaluated
Jacobians. SET can compare diagnostics against controlled analytical fixtures.
EDSPT can consume the resulting observability and information diagnostics when
evaluating experimental candidates. These are integration boundaries, not
implemented model adapters. The optional `oit.exchange.export_result` adapter
exports explicitly mapped diagnostics through SET's existing
`notation.instrument.result-artifact.v1` contract. See [STACK_ROLE.md](STACK_ROLE.md).

Observation evidence, requested operation, individual execution, numerical result
and independent verification retain separate identities. A rank result does not
constitute verification or evidence admission. See [CONTRACT.md](CONTRACT.md).

## Limits

- LTI, discrete-time, finite-horizon observability only; no nonlinear or unknown-input observability claim.
- Identifiability diagnostics are local and depend on the supplied evaluation point.
- The information matrix assumes a parameter-independent covariance and the supplied mean sensitivity; it is not a global identifiability certificate.
- No automatic differentiation, estimator, design optimizer, policy enforcement or operational control is included.
- Replay is deterministic in its declared operation; SVD direction signs and repeated-singular-value bases can differ across numerical libraries.

License: MPL-2.0. See [LICENSE](LICENSE).
