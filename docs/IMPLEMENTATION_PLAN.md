# Implemented validation surface

This legacy documentation path now describes shipped code and tests, not an unimplemented roadmap. The executable contract is [`stfe.window-mean.v1`](CONTRACT.md).

| Test group | Implemented checks |
| --- | --- |
| Numerical reference | NumPy differential mean and `wᵀRw` for 1, 2, 3, 8 and 32 samples; constant signal, zero-mean cancellation and linear drift |
| Covariance honesty | Full off-diagonal contribution; explicit declared-zero cross-covariance; unknown remains null |
| Numerical refusal | Negative eigen-direction/pivot; zero-pivot coupling; asymmetric claims; nonzero underflow; strict typing |
| Dynamic range | Stable accumulation of means and covariance that overflow naive intermediate sums; cancellation retains positive variance |
| Time | Half-open support; exact regular spacing; duplicate, jitter, missing, event-order and receipt-order refusals |
| Causality | Availability cutoff and latency bound; future append/perturb noninterference |
| Identity | Stable numerical replay identity across new occurrences; separate evidence/window/result/execution identities; source digest changes provenance without changing numerics |
| Exchange | Known and unknown scalar projections accepted by the actual SET checker; optional CIW content-identity/inspection test |
| CLI | JSON roundtrip; duplicate keys, nonfinite constants, invalid records and oversize payload refusals |

Run all local checks with `python -m pytest -q`. Set `STFE_SET_REPO` to an adjacent SET checkout and `STFE_CIW_REPO` to an adjacent CIW checkout to exercise external conformance. Absence of an optional checkout skips that integration test explicitly; it does not claim conformance was executed. Hosted CI fetches immutable provider revisions for these checks and tests Python 3.11, 3.12 and 3.13.

NumPy comparisons use relative tolerance `2e-14` (mean absolute floor `1e-15`) on bounded seeded fixtures. The production reference uses exact rational accumulation over stored binary64 inputs, not an assertion of bitwise equality with NumPy reductions. The covariance PSD test is stricter than tolerance-based exchange eligibility: it refuses a represented indefinite matrix instead of repairing it.

No spectral operation or C++ implementation exists, so there are no claimed spectral-normalization, frequency-axis or cross-language validation results. The operator does not establish physical sensor validity or calibrated detector performance. Those claims require separate evidence and cannot be inferred from these tests.
