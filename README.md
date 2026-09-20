# Constraint-Based State Reconciliation

Part of **Notation Systems' computational instrumentation and evidence infrastructure** for industrial and cyber-physical systems.

[Stack map](https://github.com/giasonpooni/Computational-Instrumentation-Workbench/blob/main/docs/STACK.md) · [Component role and interfaces](docs/STACK_ROLE.md)

**Reconciliation of estimated states against declared constraints, with uncertainty
propagation and correction diagnostics.**

**Current status: one executable bounded reference operation:**
`cbsr.affine-exact.v1`. A standard-library Python kernel reconciles a supplied
estimate and full covariance against explicitly declared exact linear equalities.
It retains the raw candidate and returns a replayable receipt with correction,
pre/post residuals and covariance, feasibility, conditioning, and a declared
normalized-residual hold policy. It is not a general fusion engine or a plant.

## Run

```sh
python -m pip install -e '.[test]'
python -m cbsr < examples/affine_exact.json
python -m pytest -q
```

The fixture reconciles `[62, 41]` kg with covariance `diag(4, 4)` against the
declared law `x_1 + x_2 = 100` kg. The accepted result is `[60.5, 39.5]`, covariance
`[[2, -2], [-2, 2]]`, correction `[-1.5, -1.5]`, and normalized residual `1.125`.
CLI exit codes are `0` accepted, `3` held/refused (receipt on stdout), and `2`
malformed contract (error on stderr). Consumers must inspect status.

```python
from cbsr import reconcile_affine_exact

receipt = reconcile_affine_exact(request)  # request contract: examples/affine_exact.json
if receipt["status"] == "accepted":
    estimate = receipt["reconciled"]["estimate"]
```

See [the operation contract](docs/AFFINE_EXACT.md) for authority, identity,
numeric restrictions, and exact-arithmetic versus encoded-output guarantees.

## Scope and mandate

Within Notation Systems' computational instrumentation stack, this component
reconciles an estimated state with declared physical or structural constraints.
The repository name is method-neutral: covariance weighting is the implemented
first formulation, not the definition of the component.

The retained invariant states:

> projection enforces declared constraints. it does not invent them.

A constraint declaration must remain distinguishable from evidence supporting
that constraint. Satisfying a declared constraint alone does not establish
physical validity, measurement accuracy, or a stability certificate.

Only exact affine declarations are implemented. Uncertain coefficients, uncertain
right-hand sides, inequality constraints, nonlinear reconciliation, automatic
constraint discovery, sensor timing/frame conversion, acquisition, evidence
admission, and stability certification are unsupported. Unknown cross-covariance
is refused; a complete matrix and explicit policy are required.

The implementation uses exact rational arithmetic over strictly typed finite
binary64 inputs, limited to 16 state coordinates and 16 constraint rows. It does
not coerce booleans/strings, symmetrize input covariance, clip eigenvalues, add
jitter, or infer independence. Nonzero uncertainty lost during float output
encoding is refused. Exact nullspaces remain distinct from numerical underflow.

`affine-uncertain-reconciliation` and `nonlinear-local-reconciliation` remain
proposed capability names, not executable operations.

## Relationship to the instrumentation stack

These are responsibility boundaries. A caller can bind an upstream result by
supplying its ID and SHA-256; CBSR retains the claim but does not independently
authenticate a source it has not received. Replay/admission verification belongs
to the calling workbench and evidence system.

| Component | Responsibility |
| --- | --- |
| [Provenance-Preserving Data Acquisition](https://github.com/giasonpooni/Provenance-Preserving-Data-Acquisition) | Acquire source material while retaining source identity, lineage, and explicit missingness. |
| [Evidence and State Management](https://github.com/giasonpooni/Evidence-and-State-Management) | Retain and govern evidence, versioned state, admission, and releases. |
| [Scientific Computation Runtime](https://github.com/giasonpooni/Scientific-Computation-Runtime) | Specify, dispatch, and record scientific computations. |
| Constraint-Based State Reconciliation | Execute bounded exact-affine correction against caller-declared constraints. |
| [Geometric State Inference Engine](https://github.com/giasonpooni/Geometric-State-Inference-Engine) | Estimate state and uncertainty before optional reconciliation. |
| [State Estimation Evaluation Testbed](https://github.com/giasonpooni/State-Estimation-Evaluation-Testbed) | Evaluate state reconstruction and degradation scenarios. |
| [Geospatial State Visualization](https://github.com/giasonpooni/Geospatial-State-Visualization) | Present geographic and temporal state for inspection. |
| [Computational Instrumentation Workbench](https://github.com/giasonpooni/Computational-Instrumentation-Workbench) | Provide the environment for operating, inspecting, and replaying instruments. |

## Identity and compatibility

This repository was previously named **Lattice Calibration Module**
(`Lattice-Calibration-Module`). The descriptive name changes its presentation
and current repository location; it does not redefine retained scientific records.

The `invariant-corpus-v1` schema, `lattice.constraints` invariant,
`var.local-estimate` coordinate, and corpus citation are retained as declared.
Repository naming does not rewrite evidence identities, operation identities,
execution records, verification identities, or historical runtime pins.

## Repository contents

- [Executable operation contract](docs/AFFINE_EXACT.md)
- [Runnable exact-affine fixture](examples/affine_exact.json)
- [Pinned cross-instrument validation sources](validation/cross-instrument-pins.json)
- [Invariant corpus](validation/invariant-corpus-v1.json)
- [Corpus citation and interpretation](docs/invariant-corpus-cite-v1.md)
- [License](LICENSE)

## Cross-instrument validation

The test suite compares live pinned FSRT mass-balance and camera/gauge kernels
with the same caller-declared affine systems. It also compares a declared affine
tangent law with GTE's Jacobian at an on-circle basepoint, and verifies that the
tangent line is **not** promoted to a global circle constraint.

```sh
CBSR_FSRT_REPO=/absolute/path/to/pinned-fsrt \
CBSR_GTE_REPO=/absolute/path/to/pinned-gte \
python -m pytest -q
```

These four comparisons skip when paths are absent. When supplied, a mismatched
revision, tracked modification, or fixture hash fails. Hosted CI explicitly
checks out both pins and runs the comparisons; it does not claim the providers'
full suites are green. Provider implementations are not copied into this package.
