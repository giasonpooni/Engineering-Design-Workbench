# Sensor-fusion coordinate transport

`ciw.sensor-fusion-transport.v1` continues an existing fusion experiment in a
declared linear state basis. It selects the exact final posterior from a
retained `ciw.sensor-fusion.v1` bundle, transports the state and future models
through the pinned Sensitivity runtime (JSPT), and runs the transformed
continuation through the existing GSIE sensor-fusion workflow. The original
sensor-fusion operation and its implementation remain unchanged.

This extends sensor reconfiguration to deterministic invertible Euclidean
coordinate changes. A caller can declare a permutation, unit scaling,
orientation change or mixed basis while retaining the full covariance and the
same measurement evidence. The map declaration supplies the coordinate
relation; numerical execution does not establish a physical frame calibration
or the dimensional meaning of a matrix coefficient.

## The declared relation

For the homogeneous map `x' = T x`, with the same state dimension and clock,
the implemented laws are

\[
m'=Tm,\qquad P'=TPT^T,
\]

\[
F'=TFT^{-1},\qquad Q'=TQT^T,\qquad H'=HT^{-1}.
\]

`F`, `Q` and `H` in the source describe the future experiment in the original
state basis. JSPT derives their target-basis versions. Measurement coordinates
remain fixed: observation record bytes, measurement units and frame,
calibration artifacts, values and joint covariance `R` remain unchanged. All
sensor profiles are transported, including profiles that are inactive in a
particular batch. Model references in the generated source bind the original
model reference to the retained map declaration.

In exact arithmetic, prediction and linear-Gaussian conditioning commute with
this coordinate relation. Binary64 execution is guarded and has a bounded
numerical domain. A successful transport reports a computation under the
declared relation; it does not prove that the relation describes a real device
or a surveyed frame.

For example, changing a two-dimensional position state from metres to
millimetres uses `T = diag(1000, 1000)`. The mean scales by 1000 and covariance
by 1,000,000. A sensor that still supplies metres keeps its observations and
`R`; its observation matrix becomes `H / 1000`. A mixed basis such as
`T = [[1, 1], [0, 1]]` changes both diagonal and cross-covariance entries. Keeping
only marginal variances would lose the declared relation.

This is a concrete part of the larger configuration-space architecture. A
mathematical moduli space requires an explicit equivalence relation: here the
relation is an invertible linear state map with the corresponding model and
covariance laws. The implementation evaluates declared instances of that
relation. Its finite numerical acceptance tolerance does not itself define a
quotient, a universal physical equivalence or a transport on arbitrary
manifolds.

## Retained source and posterior selection

The source schema is `ciw.sensor-fusion-transport-source.v1`. Input data is
bounded at 256 KiB. The continuation inherits the existing sensor-fusion
limits and its measurement, calibration, timing and noise contract; see
[Reconfigurable sensor fusion](SENSOR_FUSION.md#retained-input-contract).

| Field | Required content |
| --- | --- |
| `experiment_id` | The new declared experiment identity |
| `configuration` | Exact fixed transport policy shown below |
| `selection` | Exact upstream bundle, result, execution, numerical result, final state and batch identities |
| `transport.matrix` | A finite invertible `n × n` matrix `T`, with `1 ≤ n ≤ 16` |
| `transport.target_state` | Ordered distinct `quantity_ids`, ordered `units`, `frame`, `geometry: euclidean.v1` and unchanged `clock_id` |
| `transport.map_evidence_b64` | Exact retained bytes of the caller's coordinate-relation evidence or declaration |
| `continuation.configuration` | An existing sensor-fusion configuration in the selected upstream state basis |
| `continuation.batches` | Nonempty strictly forward batches, expressed in that original basis |

The `selection` object has exactly these fields:

```json
{
  "upstream_bundle_id": "sha256:<exact upstream bundle digest>",
  "upstream_result_id": "sha256:<exact primary result identity>",
  "upstream_execution_id": "execution-<exact primary execution occurrence>",
  "upstream_numerical_result_id": "sha256:<exact primary numerical result identity>",
  "state_id": "sha256:<exact final estimate identity>",
  "batch_index": 0
}
```

The placeholders above illustrate field roles; they are not valid input
identities. `batch_index` must identify the last estimate in the actual
upstream bundle. Selection binds both content and its execution occurrence.
A numerically identical replay bundle is a different upstream occurrence and
cannot satisfy a selector for the original bundle.

The fixed policy is

```json
{
  "map_semantics": "deterministic_invertible_linear_euclidean",
  "model_reconfiguration": "provider_transformed_f_q_h",
  "observation_coordinates": "unchanged",
  "clock": "unchanged",
  "map_uncertainty": "declared_zero",
  "cross_history_noise": "declared_independent",
  "state_admission": "not_performed"
}
```

The caller cannot supply a replacement prior. The workflow validates the
upstream bundle and takes the selected final mean, covariance and time
directly from it. `continuation.configuration.state` must exactly match that
upstream state contract. Only the target state declaration changes basis;
state dimension and clock remain fixed. Subsequent batches must be strictly
later than the selected posterior time.

The incoming posterior is a candidate estimate, not an admitted physical
state. Its use as a prior does not change that authority. As in the original
workflow, independence from that incoming state, process noise and earlier
measurements is a caller declaration requiring supporting evidence. The
adapter does not infer independence from a fresh experiment identifier.

Continuation refuses observation record or `acquisition_id` reuse from the
upstream source. Distinct acquisitions may legitimately have identical raw
reading bytes; content identity alone is not an acquisition identity. A new
label still does not authenticate a new physical acquisition.

## Providers and numerical guards

| Role | Fixed implementation | Source identity |
| --- | --- | --- |
| State and model transport | JSPT `sensitivity.affine` and its coordinate kernels | Revision `d910f5a1d7f6dd5f2dd87dfca66990f714f97b18`; source tree `5643cc8204b7aa6cbb73df6bf8984abdcec47d3b` |
| Continuation filtering | GSIE through unchanged `ciw.sensor-fusion.v1` | Revision `5241eee6dab434533bdf0cf0e824bc43b4a79831`; source tree `375c031c07592d5bcb1d224780f18ceb886df4a1` |

Both bindings require standalone repository roots at the exact revision and
source tree, with retained interpreter and dependency identities. The source
chooses data, not an executable module or arbitrary callback. The transport
wrapper uses a fixed program to invoke JSPT's existing kernels; GSIE remains
the filtering provider.

The chart requires condition number at most `1e12`, as well as JSPT's
invertibility and round-trip checks. State mean fidelity uses the provider's
`1e-8` componentwise tolerance, scaled by the original mean magnitude or
standard deviation. Covariance fidelity uses its `1e-8` normalized
round-trip tolerance and preserves exact zero-uncertainty directions.
Transported state and process covariances must satisfy the provider's
positive-semidefinite domain checks.

For transition and observation matrices, floating-point overflow, underflow,
invalid arithmetic and division errors are refused during forward and reverse
transport. The wrapper checks each recovered original matrix column through
JSPT's `check_mean_fidelity` with zero covariance: nonzero coefficients use
relative tolerance `1e-8`, and original zero coefficients must recover
exactly. A finite, nominally invertible map can therefore still be refused if
it erases a coefficient or introduces excessive cancellation.

Offsets, dimension changes, uncertain maps, clock changes, SO(2) transport,
nonlinear manifold transport and changes of filter family require further
declared capabilities. This operation accepts only a retained `sensor-fusion`
upstream; it does not automatically chain another transport wrapper.

## Lineage, inspection and fresh reproduction

The retained transport result contains the selected source state identity,
target state contract, map identity, mapped prior and its initial-state
identity. It also retains the exact canonical generated
`ciw.sensor-fusion-source.v1` bytes and their byte digest. The child GSIE
workflow must consume precisely those bytes and the mapped initial state.
Parent lineage binds the selected upstream posterior to that new child prior;
the child keeps its normal v1 predecessor-state sequence.

One top-level transport operation contains the JSPT computation and a fresh
GSIE child bundle. The child retains its primary execution and its own fresh
numerical reproduction. Top-level reproduction repeats the whole composition,
including fresh child sessions and executions; it cannot reuse the first
child as a reproduced result. The upstream bundle remains an immutable input.

Evidence identities, operation identities, execution occurrences, result
identities and verification identities remain distinct. The numerical
projection retains the complete selection, map result, generated source
commitment and child numerical result. It excludes the known child session,
execution and verification occurrence wrappers so an explicit replay can
compare scientific content while minting fresh occurrences.

Verification reports same-implementation fresh reproduction with
`independent: false`. It does not authenticate map evidence, perform physical
validation, admit state or grant machine execution authority. Inspection
validates retained commitments, source and child bindings without rerunning
provider arithmetic. The workbench view exposes the selected upstream state,
mapped prior and continuation estimates with their full covariance matrices,
state contracts and lineage.

## Run, inspect and replay

Provision exact detached provider worktrees from the preserved source history:

```sh
git worktree add --detach /tmp/net-fusion-transport-jspt d910f5a1d7f6dd5f2dd87dfca66990f714f97b18
git worktree add --detach /tmp/net-fusion-transport-gsie 5241eee6dab434533bdf0cf0e824bc43b4a79831
```

The executable example creates its upstream experiment, derives the exact
selector and continues in millimetres with `T = diag(1000, 1000)`:

```sh
python examples/sensor_fusion_transport.py --jspt-repo /tmp/net-fusion-transport-jspt --gsie-repo /tmp/net-fusion-transport-gsie --output-dir results/sensor-fusion-transport-example
```

The output directory must not already exist. It contains `upstream.json`,
`transport-source.json`, `transport.json`, `replay.json`, `baseline.json` and
`report.json`. The report compares the mapped continuation with an
original-basis continuation transformed into the target units. This is a
declared numerical example, with no measured physical performance claim.

`create` takes a declaration and its exact upstream bundle. The selector must
be populated from that bundle; a portable fixture cannot predict newly minted
upstream execution identities.

```sh
python -m ciw sensor-fusion-transport create --input transport-source.json --upstream upstream-fusion.json --jspt-repo /tmp/net-fusion-transport-jspt --gsie-repo /tmp/net-fusion-transport-gsie --output transport-bundle.json
python -m ciw sensor-fusion-transport inspect --input transport-bundle.json
python -m ciw sensor-fusion-transport replay --input transport-bundle.json --jspt-repo /tmp/net-fusion-transport-jspt --gsie-repo /tmp/net-fusion-transport-gsie --output transport-replay.json
```

Output paths must be new paths so previous retained occurrences remain
available. Replay reads the upstream retained inside the input bundle and
requires both providers. Inspection requires no provider binding.

The native workbench accepts `source.add` with
`kind: sensor-fusion-transport` and executes
`ciw.sensor-fusion-transport.v1` against a selected registered `sensor-fusion`
bundle. To create the upstream and transport it in the same live workbench,
bind the original fusion operation as well as both transport providers:

```sh
python -m ciw serve --sensor-fusion-gsie-repo /tmp/net-fusion-transport-gsie --sensor-fusion-transport-jspt-repo /tmp/net-fusion-transport-jspt --sensor-fusion-transport-gsie-repo /tmp/net-fusion-transport-gsie
```

The paired transport flags bind only the new operation. Alternatively, restore
a workspace containing the retained upstream bundle with
`serve --workspace <workspace.json>` and the two transport bindings;
recreating the upstream is unnecessary. Remove detached worktrees after use
with `git worktree remove`.

## Acceptance scope

The executable acceptance cases compare filtering in the original basis with
filtering after transport. They cover unit scaling, permutations, orientation,
identity and a correlated mixed basis, including full process covariance,
within-batch measurement correlation and prediction-only continuation.
They compare means, full covariances and invariant innovation diagnostics.

Refusal cases cover singular and ill-conditioned maps, numerical overflow,
underflow and cancellation, wrong source or occurrence selection, historical
posterior substitution, acquisition reuse, incompatible state contracts,
tampered generated sources and child bindings, and occurrence reuse.
Passing these cases establishes the tested declared numerical behavior.
Measured use cases still require independently supported model, calibration,
frame, timing and statistical assumptions.
