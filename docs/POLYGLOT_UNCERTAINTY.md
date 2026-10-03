# Correlated uncertainty through the existing native architecture

This extends the mean-response integration without changing its v1 semantics.
Python retains orchestration and scientific records; SCR/Rust supervises the
existing C++ or Julia affine implementation. Domain repositories still own
models, Jacobians, evidence interpretation and calibration. GSC reads results.

## Computation and limits

For the supplied fixed Jacobian J and full input covariance C, compute
C_y = J C J^T. The input covariance belongs to the case's delta coordinates,
centred at its declared delta. Translation from an original state mean changes
that reference, not covariance. J is treated as exact: no coefficient, model,
observation or calibration uncertainty is silently added. No Gaussian law or
confidence interval is inferred from covariance alone.

With the existing normalization A=Sy^-1 J Sx and Cn=Sx^-1 C Sx^-1, evaluate
L=A Cn column by column, then Y=L A^T column by column, and C_y=Sy Y Sy.
Every column uses the unchanged affine-binary64.v1 operation. No new native
kernel, provider pin, worker closure or second estimator is introduced.

For n inputs and m outputs, this requires 1+n+m native sessions including the
mean response. Each session retains its existing fresh reproduction. Dimensions
remain 1 through 8 and every intermediate request respects the original native
bounds. This is a bounded, inspectable integration path, not a high-throughput
batched implementation. Startup overhead can dominate; persistent batching is
not claimed. Predictable first-stage input violations refuse before execution.
A later-stage refusal cannot produce a successful composite artifact.

The existing covariance-artifact.v1 validator checks the complete input/output
matrix, ordered quantities, units, frame and references. No diagonalization,
eigenvalue clipping, jitter or automatic symmetrization is added. Both positive
semidefinite singular matrices and exact common-mode cancellation are covered.
The full matrix, not a list of marginal sigmas, crosses the interface.

## Independent check and identity

Explicit execution also evaluates J C J^T independently with Python Fraction
arithmetic over the supplied binary64 values. For each entry, the declared
comparison budget is 1e-10 times the absolute exact result plus 256*2^-52 times
the sum of absolute triple-product terms. This is a numerical comparison policy,
not a proved error bound for arbitrary computations. It has no dimensionful
absolute floor. Erasing a nonzero exact covariance entry to zero is refused.

Each check binds the full problem, output matrix, policy and all native bundle
digests. The composite calculation, covariance artifact, checker and individual
native execution occurrences retain separate identities. All stages must use
the same bound runtime and distinct execution/reproduction occurrences.

Inspection validates retained native bindings, case order and covariance shape,
reassembles retained columns and checks the saved check record. It launches no
provider and does not repeat the rational reference. Existing numerical
covariance validation still runs. Inspection is not fresh verification or
source authentication; a digest is not a signature. Replay explicitly requires
the original runtime and creates new execution and verification occurrences.
Its receipt states numerical-policy agreement, never cross-platform bit identity.

## API and commands

```python
from ciw import polyglot_uncertainty as uncertainty

problem = uncertainty.from_domain(domain_export)
run = uncertainty.execute(problem, provider="julia", bindings={"runtime": binding_file})
covariance = uncertainty.inspect(run)  # no runtime binding required
view = uncertainty.export_view(run)
replayed = uncertainty.replay(run, bindings={"runtime": binding_file})
new_view = uncertainty.export_view(replayed["run"])
```

For a saved notation.linear-uncertainty.v1 problem:

```sh
python -m ciw.polyglot_uncertainty run problem.json --provider cpp --binding runtime.json --output run.json
python -m ciw.polyglot_uncertainty view run.json --output view.json
python -m ciw.polyglot_uncertainty replay run.json --binding runtime.json --output replay.json
```

Replay writes a wrapper containing run and receipt. Pass its run member to the
view API. Outputs must be new files; the CLI does not overwrite retained data.
Use the existing [native provisioning guide](NATIVE_INTEROP.md). No saved case
can request package installation, arbitrary code or executable paths.

## Domain extensions

The data-only notation.domain-uncertainty-inputs.v1 export supplies case,
covariance_matrix, source_evidence_ids, source_covariance_ids and assumptions.
The Terminal binds and validates it without importing a domain provider.

- BIM exports its entire raw belief covariance for supported small worlds,
  with selected output rows of the existing Jacobian. Larger worlds refuse
  rather than silently losing correlations through marginal selection.
- Curved surfaces export one shared heading uncertainty across several samples.
  A deterministic perturbation validity bound does not bound a distribution's
  entire support; lateral and surface uncertainty remain outside this adapter.
- FSRT exports the original unprojected residual A x-b, with joint coordinates
  (x,b), Jacobian [A,-I] and an explicitly supplied state/RHS cross block.
  Uncertain A is refused by that adapter; held corrections stay visible.

GSC receives a separately versioned covariance-view envelope containing the
unchanged mean-only envelope. The old mean schema still says not_propagated;
the new outer schema owns the explicit propagated covariance. GSC's /numerics
page reads a local file against a separately supplied retained-artifact digest,
shows full cross-covariance and makes no execution or state-admission request.

## Run the gates

```sh
python -m unittest discover -s tests -p 'test_polyglot*.py' -v
python scripts/check_polyglot_uncertainty_native.py --binding runtime.json --output-dir native-uncertainty-evidence
```

Unit tests use explicitly labelled protocol doubles for orchestration. The real
native reader rejects those records. The second command requires actual C++ AND
Julia execution, fresh reproduction/replay and exact synthetic correlated and
common-mode cases. Missing providers fail; this is not replaced by unit tests.
Private SCR PR #7 provides an own-repository qualification workflow without a
new cross-repository secret. Its completed run, not its existence, establishes
native execution evidence. No physical validation, SP1 proof, equipment action,
canonical state admission or public deployment is introduced here.
