# Covariance operation provider

`sensitivity.ciw_adapter` provides the versioned operation
`jspt.covariance-propagate.v1`. This is an operation backend, not an acquisition
instrument. Existing derivative, composition, covariance, and coordinate APIs
remain unchanged. No CIW, RCI, or FSRT imports are required.

The endpoint accepts one JSON request on standard input and writes one JSON
response on standard output. A CIW operator may bind its module to an explicit
clean Git commit, Python executable, and environment. Saved covariance artifacts
contain data and provenance; they cannot select a module, execute a model,
evaluate a symbolic expression, or load arbitrary code.

## Request and ordered bases

The request has exactly these fields:

```json
{
  "schema": "ciw.adapter-request.v1",
  "operation_id": "jspt.covariance-propagate.v1",
  "inputs": {
    "covariance": "a covariance-artifact.v1 object, as specified below",
    "jacobian": [[0.5, 0.5]],
    "output_quantity_ids": ["mean_reading"],
    "output_units": ["m"],
    "output_frame": "measurement-axis",
    "output_reference_values": [10.0],
    "map_kind": "weighted_aggregation"
  }
}
```

The string above is an explanatory placeholder. A complete executable request
is [examples/covariance_request.json](../examples/covariance_request.json).

| Input | Meaning |
| --- | --- |
| `covariance` | Exact input artifact, including its ordered quantities and full square matrix. |
| `jacobian` | Finite real `m × n` matrix. Columns follow input `quantity_ids`; rows follow `output_quantity_ids`. |
| `output_quantity_ids` | Unique ordered output quantities, with one entry per Jacobian row. |
| `output_units` | Declared output units in the same row order. |
| `output_frame` | Declared common output coordinate frame. |
| `output_reference_values` | Caller-supplied output reference point. A Jacobian alone does not determine nonlinear output means. |
| `map_kind` | `linear`, `local_linearization`, `weighted_aggregation`, or `coordinate_change`. |

Input `reference_values` are the declared linearization point. A Jacobian
coefficient has units `output_units[row] / input units[column]`; the provider
does not infer conversions, verify dimensional consistency, or establish that
the named frame matches the physical system. No units or order are silently
changed. Supplying a different basis requires a new declared map and artifact.

For `linear`, `local_linearization`, and `weighted_aggregation`, calculation
delegates to `sensitivity.covariance.first_order_covariance`:

\[
\Sigma_y = J\Sigma_xJ^\mathsf{T}.
\]

Each aggregation row is an explicit weight vector; weights need not be positive
or sum to one. Rectangular and rank-deficient maps are allowed. An invertible
`coordinate_change` instead calls `sensitivity.coordinates.push_covariance`,
retaining its condition-number bound `1e12` and covariance round-trip checks.
This mode refuses singular maps; aggregation does not require invertibility.

## `covariance-artifact.v1`

An artifact has exactly these fields:

| Field | Meaning |
| --- | --- |
| `schema` | `covariance-artifact.v1`. |
| `covariance_id` | `sha256:` plus the digest of every other retained field. |
| `quantity_ids`, `units`, `frame` | Ordered quantities, corresponding units, and one frame identifier. |
| `reference_values` | Finite reference point in the declared quantity order. |
| `matrix` | Full covariance; entry `(i,j)` has units `units[i] * units[j]`. Mixed units are allowed. |
| `method` | Declared derivation method. |
| `basis` | Exactly `kind` and `id`. Kind is `observation`, `calibrated_observation`, `estimated_state`, `parameter`, `coordinate`, or `residual`. |
| `provenance` | Required `provider`, `source_evidence_ids`, `source_covariance_ids`, plus optional JSON-only `metadata`. Each source array contains unique SHA-256 content identities. |
| `assumptions` | Array of nonempty declared assumptions. |

The digest uses UTF-8 bytes of ASCII-escaped JSON with sorted keys, separators
`,` and `:`, and nonfinite numbers forbidden. It includes the order, units,
frame, method, assumptions, and provenance. Received artifacts are validated
without resealing, clipping eigenvalues, dropping off-diagonal terms, or
replacing missing uncertainty with zero.

Wire validation accepts singular covariance and requires nonnegative diagonal
entries; a zero-variance row and column must be exactly zero. Correlation
coordinates must be symmetric with `rtol=0`, `atol=1e-12`. Eigenvalues from both
stored triangles must be at least `-1e-10`. These shared transport tolerances
do not change JSPT's existing scientific kernel checks, which can refuse an
additional numerically marginal case. The kernel's existing tolerated
symmetrization is reported by `checks.input_covariance_symmetrized`; the
received artifact itself remains unchanged.

`sensitivity.make_covariance_artifact` seals a new explicit declaration.
`sensitivity.validate_covariance_artifact` checks a received declaration.
Both dimensions are bounded to 256; requests are bounded to 4 MiB.

## Results and refusals

Success has exactly `schema: ciw.adapter-response.v1`, `status: ok`, and `data`.
The data schema is `jspt.covariance-result.v1` and includes:

- Operation identity, map kind, complete Jacobian, and `jacobian_source: caller_declared`.
- The unchanged input artifact and a new full output covariance artifact.
- Input linearization point and declared output reference values.
- Explicit check flags and scope limitations.

The output links to the input through `source_covariance_ids`, retains its
source evidence identities and assumptions, and preserves upstream metadata
under `provenance.metadata.source_uncertainty_context`. Coverage limits,
omitted uncertainty sources, dependency declarations, and any
`completeness_claimed: false` therefore remain available in a standalone output.
Its coordinate-basis identity commits to the complete supplied map. Repeated
identical input declarations produce identical covariance artifact identities;
CIW separately allocates execution and result identities.

Refusal has exactly `schema: ciw.adapter-response.v1`, `status: refused`, and
`refusal: {code, message}`. It has no data or covariance result.

| Code | Meaning |
| --- | --- |
| `invalid_json` | Malformed or duplicate-key JSON, nonfinite JSON constants, or oversized request. |
| `invalid_input` | Missing/extra fields, artifact identity mismatch, invalid ordering, matrix dimensions, or invalid input covariance. |
| `operation_unavailable` | Unsupported operation identity. |
| `numerical_refusal` | Kernel refusal, singular/ill-conditioned coordinate chart, nonfinite output, or rejected propagated covariance. |

## Validation and scope

The tests exercise full off-diagonal propagation from shared gain and offset
parameters; varying sensitivities that produce less than perfect correlation;
shared-offset averaging and cancellation; singular covariance and rectangular
aggregation; chart conditions; ordering, units and provenance; overflow;
indefinite input refusal; content tampering; and strict JSON transport.

For a fixed affine map, covariance propagation is exact in exact arithmetic.
For a nonlinear model, a supplied Jacobian gives only a local first-order
approximation. This endpoint does not differentiate a model, check the
Jacobian, verify output reference means, run Monte Carlo, establish physical
truth, certify a result, or authorize an action. Existing JSPT model-based
Monte Carlo experiments remain separate APIs.
