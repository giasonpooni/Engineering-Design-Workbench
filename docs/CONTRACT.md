# Operation contract

## Inputs

`rank_candidates(candidates, *, prior=None, criterion="d_opt")` accepts a nonempty finite sequence of `Candidate` records. Supported criteria are `d_opt` and `a_opt`.

Each candidate supplies:

| Field | Contract |
| --- | --- |
| `candidate_id` | Unique nonempty string; stable caller-assigned alternative identity |
| `coordinates` | Nonempty ordered tuple of `ParameterCoordinate(name, scale, unit)` |
| `jacobian` | Finite real matrix `(m, n)` with `m > 0` and one column per coordinate |
| `noise_covariance` | Finite real symmetric numerically positive-definite matrix `(m, m)` |

Coordinate names are unique, units are nonempty strings (`"1"` for dimensionless), and scales are finite and strictly positive. For each coordinate, `physical parameter θ = scale × numerical parameter q`. Jacobian columns are derivatives with respect to `q`. The caller supplies already-scaled Jacobians and precisions; the package performs no rescaling, dimensional analysis, or unit conversion. Covariance rows must correspond to the same measurement ordering and measurement units as the Jacobian rows; this measurement metadata is a caller obligation, not a machine-checked field in v1.

Optional `PriorInformation(coordinates, precision)` must have the same coordinates and a symmetric positive-semidefinite `(n, n)` precision matrix. Zero and rank-deficient priors are allowed. Every candidate and the prior must agree exactly on coordinate names, ordering, scales, and units. Comparisons fail on a mismatch.

Inputs describe a local linear Gaussian measurement model. `R` is parameter-independent within that model. For every candidate considered separately, its measurement noise is independent of information already included in the prior. Nonzero correlations within the candidate's measurement block are represented by `R`. Ranking individual alternatives does not assume that all alternatives will be measured; it does not compute joint information across candidate blocks or resolve cross-block correlations.

## Outputs

`RankingResult` is a frozen record; its `to_dict()` method produces JSON-compatible fields:

| Field | Meaning |
| --- | --- |
| `schema` | `edspt.ranking.v1` |
| `operation` | `finite-candidate-information.v1` |
| `advisory_only` | Always `true` |
| `criterion` | Requested objective |
| `coordinates` | Shared declared parameter coordinates |
| `selected_candidate_id` | Best full-rank alternative, or `null` if none |
| `ranked_candidate_ids` | Full-rank candidates in objective order, then singular candidates by ID |
| `scores` | All candidate records in ascending ID order |
| `assumptions` | Declared model and independence assumptions |

A score record includes the candidate information, total posterior precision, numerical rank, full-rank/singular status, D-opt log determinant, A-opt covariance trace, and eigenvalue/rank-threshold diagnostics. Eigenvalues are those of the precision divided by its maximum absolute entry; the threshold uses that same normalization. Singular scores are `null`, never infinite or a pseudoinverse-derived surrogate.

Candidate IDs identify input alternatives. An advisory selected ID is neither a device command nor proof of physical feasibility or acquisition authorization. The operation name denotes mathematical semantics, not a claim about execution, evidence authenticity, or independent verification. No private operational state is accepted or emitted by the synthetic example.

## Determinism and failure

Input order does not affect output ordering or tie resolution. Exact ties in computed float64 scores use lexicographic candidate ID. Close but unequal scores are not rounded into ties. Numerical results depend on the floating-point environment; cross-platform bitwise equality is not guaranteed.

Inputs are copied and never mutated; output matrices are immutable tuples detached from inputs. Supplied covariance and prior symmetry is exact: neither stored triangle is modified. Validation or unrepresentable finite computations raise `ValueError`. NumPy errors from malformed array conversions can also appear as `ValueError`. There is no partial ranking on invalid input and no automatic input covariance repair.

## SET exchange boundary

`edspt.exchange.export_result` accepts explicit JSON mappings, source/evidence references, an operation ID, an execution reference, a caller-supplied UTC creation instant, and a full Git revision. It binds these values and the numerical result into the existing SET result-artifact contract and validates them using the optional source-pinned dependency. It does not infer a scientific component mapping or recompute supplied results; callers are responsible for mapping the actual operation inputs and result faithfully.

Input content receives a SHA-256 digest. The result digest includes execution identity and the declared metadata. The source revision remains `caller_supplied_unattested`; validation does not prove it describes the running code. Verification references are empty until a separate verifier issues a bound verification artifact. The synthetic example exports finite candidate counts as components, `not_applicable` covariance for those deterministic diagnostics, and the entire ranking under `computation.numerical_result`. Singular objective values remain `null` there.
