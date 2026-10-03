# Square-tiled rational flow v1

Operation `tsde.square-tiled-flow.v1` computes an exact rational affine trajectory
prefix on the connected square-tiled surface supplied by the caller. It does not
establish ergodicity, physical validity, stability of another solver, or
cryptographic proof of computation.

## Request

```json
{
  "schema": "tsde.square-tiled-flow-request.v1",
  "gluing": {"right": [1, 0, 2], "up": [2, 1, 0]},
  "start": {"tile": 0, "position": ["1/4", "1/3"]},
  "direction": ["1", "1/2"],
  "duration": "3",
  "max_events": 128
}
```

Objects require exactly the shown keys. Both gluing arrays must be permutations
of `0..N-1` of equal length, with `1 <= N <= 32`, generating a connected surface.
Booleans and floats are not indices or budgets. The start tile must exist.

Position, direction and duration use canonical reduced rational strings: `"0"`,
`"2"` or `"-1/3"`, for example. `"1/1"`, `"2/4"`, `"-0"`, exponents,
decimals and JSON numbers are rejected. Numerator magnitude and positive
denominator each have at most 64 bits; input strings have at most 43 characters.
Start coordinates are strictly between zero and one. Direction is nonzero with
component magnitudes at most 1,024. Duration is in `[0,1024]`. `max_events` is an
integer in `[0,1024]`.

`validate_request(request)` returns an independent copy without normalization or
defaults. `run(request)` validates again. Invalid requests or arithmetic values
exceeding the 256-bit numerator/denominator budget raise `ValueError` without a
result. Integer intermediates are exact; the guard bounds resulting positions,
times and retained arithmetic, without truncation or rounding. Inputs and the
maximum 1,025 segments bound intermediate work.

The CLI reads at most 32 KiB of UTF-8 JSON and rejects duplicate keys, nonfinite
constants and malformed input. A valid result is canonical JSON plus a newline,
with exit zero, including partial results. Rejection exits two with a stderr
reason and no stdout result. Callers must inspect `status`.

## Coordinates, topology and gluing

Each tile is an oriented unit square `(x,y)` in `[0,1]^2`. Side length is the
dimensionless coordinate unit; time is a declared flow parameter and direction
is displacement per unit of that parameter. No physical unit, measurement
uncertainty, calibration or observation semantics are added.

| Exit edge | Target tile | Coordinate translation |
| --- | --- | --- |
| right | `right[tile]` | `(-1,0)` |
| left | inverse of `right` at `tile` | `(1,0)` |
| up | `up[tile]` | `(0,-1)` |
| down | inverse of `up` at `tile` | `(0,1)` |

No rotation, reflection or direction change occurs. Segments derive from
`p(t) = p0 + direction * (t-t0)`. Boundary times solve `x=0/1` or `y=0/1`
rationally; the smallest positive time wins. Only exact equality is simultaneous.
Numerical tolerance is zero; no epsilon merges near-corner events.

Corner indices are bottom-left `0`, bottom-right `1`, top-right `2`, top-left `3`.
Edge translations identify corner classes. For `N` faces, `2N` paired edges and
`V` vertices, Euler characteristic is `V-N` and genus is `1-(V-N)/2`. A vertex
with `4k` corners has cone angle `2*pi*k`; `k > 1` is singular. The example has
`N=3`, `V=1`, genus two and one `6*pi` vertex.

The construction and L-shaped example follow documented
[square-tiled surface examples](https://flatsurf.github.io/surface-dynamics/examples/square_tiled_surfaces.html).
[Origami's introduction](https://ag-weitze-schmithusen.github.io/Origami/doc/chap1_mj.html)
provides mathematical background. Neither library is a runtime dependency.

## Stopping policy

A single-edge gluing at the requested duration is applied. Every simultaneous
two-edge hit stops before either gluing, including regular vertices and hits
exactly at the duration. No outgoing sheet is chosen at a singularity.

The event budget counts applied single-edge gluings. Exceeding it stops at the
next boundary before applying its gluing. Vertex status takes precedence if both
conditions occur. A partial result can therefore have `remaining: "0"`. Zero
duration returns the initial state as completed with no segments or events.

| `status` | `final_state.pending_edges` | Meaning |
| --- | --- | --- |
| `completed` | `[]` | Full trajectory under the endpoint policy |
| `stopped_at_vertex` | Two edges | Prefix ends at named glued vertex, without continuation |
| `event_budget_exhausted` | One edge | Prefix ends before an omitted gluing |

Resumption from a boundary is unsupported. A caller must not relabel a prefix as
full or silently choose a vertex continuation.

## Result

| Key | Value |
| --- | --- |
| `schema` | `tsde.square-tiled-flow-result.v1` |
| `operation_id` | `tsde.square-tiled-flow.v1` |
| `request` | Exact validated request copy |
| `request_digest` | Digest of the complete request |
| `claim_scope` | `exact_rational_translation_flow_prefix_on_declared_square_tiled_surface` |
| `arithmetic` | Fixed rational, coordinate, time, bound and stop policies |
| `gluing_validation` | Bijective/connected flags, tile/edge/vertex counts, Euler characteristic, genus, right/left/up/down maps, and vertices |
| `status` | One of the three statuses above |
| `elapsed`, `remaining` | Rational strings |
| `final_state` | `{tile, position, pending_edges, vertex_id}`; vertex ID is null except at a vertex stop |
| `segments` | Ordered `{tile, t_start, t_end, start, end}`; positions are pairs of rational strings |
| `events` | Ordered `{index, time, edge, from_tile, to_tile, from_position, to_position, translation}` |
| `invariants` | Recomputed checks below |
| `artifact_digest` | Digest of all other result keys |

Each vertex record is `{vertex_id, corners, cone_angle_multiple_of_2pi, singular}`;
corners are `[tile, corner_index]` pairs. `arithmetic` records kind
`exact_rational`, coordinate unit `unit_square_side`, time parameter
`declared_flow_parameter`, tolerance `"0"`, derivation
`affine_position_and_rational_boundary_intersection`, input bits `64`, arithmetic
bits `256`, vertex policy `stop_before_any_vertex_continuation`, endpoint policy
`process_single_edge_crossing_at_duration`, and event-budget policy
`stop_at_next_boundary_before_omitted_gluing`.

The implementation recomputes affine motion, continuity via gluing, permutation
maps, closed-square coordinates, strictly increasing event times, unfolded total
displacement after translations, and elapsed duration bounds. Internal failures
raise an error. `requested_duration_completed` is true only for `completed`.
These checks establish internal consistency, not an independent proof.

Canonical encoding is UTF-8 JSON, sorted keys, compact separators, literal
non-ASCII characters and no nonfinite numbers (`ensure_ascii=False`,
`allow_nan=False`). Digests are `sha256:` plus lowercase hexadecimal. Request
digest covers the entire request; artifact digest covers the entire result
except `artifact_digest` itself, including the request, policies and status.
Digests identify content, not invocation or provider revision. Integrating
runtimes must retain their own execution identity and exact provider build.

## Acceptance fixtures

Tests check analytical unfolding on a three-square rectangular torus in all
direction quadrants, a noncommuting genus-two gluing, inverse flow and
noninvolutive inverses, rational near-corner ordering, regular/singular vertex
stops, event budgets, endpoint policy, bounds, malformed inputs, independent
digests and the real CLI. Isolated wheel checks exercise the installed algorithm.
This finite acceptance suite does not extend the profile's mathematical claims.
