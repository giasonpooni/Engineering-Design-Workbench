# Budgeted next observation

`budgeted-next-observation.v1` is an additive operation. The existing
`rank_candidates` and `finite-candidate-information.v1` contracts are unchanged.
It selects a single supplied observation block, advisory only.

## Inputs and model binding

```python
rank_budgeted_candidates(
    candidates, *, prior: ModelPrior, available_budget, budget_unit,
    criterion="a_opt",
)
```

`ModelPrior(model_result_id, coordinates, covariance=None, precision=None)`
requires a nonempty model-result reference and exactly one symmetric positive
definite uncertainty representation. Both the supplied matrix and the resulting
precision must pass the existing numerical rank policy in the declared ordered,
scaled coordinates. A rank-deficient prior is refused because it cannot supply
the finite uncertainty baseline this operation requires.

`BudgetedCandidate(candidate, cost, cost_unit, model_result_id,
prior_cross_covariance_policy="unknown")` wraps the existing `Candidate`.
Costs and budget must be finite nonnegative real numbers; booleans and numerical
strings are refused. Zero cost is allowed. All cost units must match the budget
unit exactly; no exchange rates, unit conversion, or rounding is inferred.
Numerical costs or budgets that cannot convert to float64 exactly are refused;
for example, rounding a large integer cannot make an over-budget item affordable.
Every model-result reference must match the prior's reference exactly.

The prior and every candidate use identical parameter names, ordering, scales,
and units. The existing Jacobian and covariance requirements apply even to
unaffordable candidates. Cross-covariance between each candidate's noise and
the prior error must be explicitly `declared_zero`. `unknown`, a missing
declaration, and nonzero policies refuse the entire operation. Within-block
noise correlation is represented by the complete supplied covariance.

Model binding and independence are caller declarations, not authenticated
evidence. CIW is responsible for binding the actual retained model result,
source inputs, and uncertainty propagation. For example, a GSIE state prior
conditional on an SIDT point estimate for A and B describes state uncertainty
under those fitted dynamics. It does not supply missing SIDT parameter
covariance or establish global identification of the physical process.

## Calculation and selection

For each candidate separately, the existing engine calculates

\[
\Lambda_c=\Lambda_0+J_c^T R_c^{-1}J_c.
\]

The retained baseline gives two reductions:

\[
\Delta_A=\operatorname{tr}(P_0)-\operatorname{tr}(\Lambda_c^{-1}),
\qquad
\Delta_D=\log\det\Lambda_c-\log\det\Lambda_0.
\]

`a_opt` maximizes the covariance-trace reduction in the declared scaled
coordinates. `d_opt` maximizes the precision-log-determinant gain, which is
twice the local Gaussian differential-entropy reduction. These are expected
reductions conditional on the supplied model and noise, not observed accuracy
improvements. Scaling and units remain scientifically consequential.

Candidates with `cost <= available_budget` are affordable. The comparison uses
the supplied float64 values without an affordability tolerance. Affordable
candidates whose posterior passes the rank gate are ordered by decreasing
requested reduction, then lexicographic candidate ID for exact numerical ties.
Cost is a feasibility constraint, not a gain-per-cost objective. A zero-gain
candidate remains eligible and can be selected if no better feasible option
exists; the retained zero score makes this explicit. If none is eligible,
the selection is `null`.

No candidates are combined. The operation does not presume independence across
alternatives, solve a knapsack problem, reserve a budget, create an acquisition
command, or approve actuation. An observation block may itself contain multiple
correlated channels with their complete covariance and one declared cost.

## Result and verification boundary

The immutable result serializes to `edspt.budgeted-ranking.v1`. It retains:

| Field | Meaning |
| --- | --- |
| `model_result_id`, `coordinates` | Declared model result and uncertainty coordinates |
| `prior_representation` | Which matrix the caller supplied |
| `prior_covariance`, `prior_precision` | Detached supplied and derived matrices |
| `prior_d_opt_logdet`, `prior_a_opt_trace_covariance` | Actual scoring baseline |
| `available_budget`, `budget_unit` | Declared feasibility limit, never a reservation |
| `scores` | Every candidate in ascending ID order |
| `ranked_candidate_ids` | Eligible candidates only, ordered by reduction |
| `selected_candidate_id` | First ranked candidate or `null` |
| `selection_scope`, `advisory_only` | `one_candidate_block`, `true` |

Each score retains cost, unit, model binding, cross-covariance policy,
affordability, both reductions, the requested reduction, and the existing
`CandidateScore` under `numerical_score`. `eligibility` is `over_budget` if
unaffordable, otherwise `eligible` if scored or `unresolved` if the posterior
failed the numerical rank gate. Unresolved reductions are `null`.

The EDSPT operation describes mathematical content; CIW owns source-pinned
execution and content identities, and ICRH owns conformance and replay checks.
An EDSPT model reference must not substitute for an operation, execution,
evidence, or verification identity. YWIR inference-token admission is a
separate policy decision; sample costs cannot silently become inference tokens.

## Numerical limits

The supplied prior is validated without symmetrization, clipping, or jitter.
A scaled Cholesky solve forms its inverse through a Gram matrix, preserving
computed symmetry. The existing ranking engine calculates the prior baseline
using a zero-sensitivity observation and computes every posterior score with
its unchanged rank/conditioning policy.

Reductions subtract the computed baseline and posterior scores. A negative
reduction within `64 * eps * dimension * max(abs(baseline), abs(posterior))`
is reported as zero; a more negative result refuses the calculation. No
positive floor is invented. Changes below float64 resolution may be reported
as zero. Nonfinite calculations refuse, and extreme directional information
that fails the existing posterior rank policy remains unresolved even though
the prior was mathematically positive definite. No arbitrary-precision or
rigorous error-bound claim is made.

The tests compare against analytic diagonal reductions and an independent
conditional-Gaussian covariance formula with correlated prior and measurement
noise. They also cover model mismatches, unknown cross-covariance, overspending,
zero budgets, exact affordability boundaries, ambiguous units, deterministic
ties, prior rank failure, extreme finite scales, and detached replay content.
