# Methods

Yield of a settled burst is a declared structure increment over
tokens spent:

```text
structure = rank_delta{>0} + 1{glued} + 1{new morphism} - similarity
            - 1{eta falling and confidence rising}
eta_obs   = structure / max(tokens_spent, 1)
eta_hat   <- (1 - a) eta_hat + a eta_obs
```

with `a = ETA_BLEND = 0.4` frozen in `ywir.constitution`.

This is not expected free energy in the full Friston form. It is the
v0 oracle for "did this burst raise rank, glue, or emit a reusable
map?" Dual prices and an MPC horizon are compatible extensions —
not implied capabilities.

Classify before spend. Priority is fail-closed:

1. close / already closed
2. plant refuse or explicit evidence request
3. compose candidates present in the store
4. eta falling and confidence rising
5. gauge department, or high similarity with no rank and no morphism
6. rank-flat on a non-exploration department
7. eta_hat below threshold on a non-exploration department
8. department empty or starved
9. else ADMIT

Settlement that does not glue is refused and does not debit. No
nearest-repair of an unglued burst.

An advisory ADMIT is followed by explicit `reserve`, which rechecks the
decision and holds its token cap under the host lock. Department availability
is unspent budget minus pending reservations. `settle` requires that exact
host/loop/base/proposal-bound pending capability and consumes it once; actual
spend cannot exceed the cap. `cancel` releases an unused hold. Close/reindex
refuse while holds remain. Invalid settlement or store conflict leaves budget,
yield, composition store and pending authorization unchanged.

This transaction scope is one live `HostState` process. It does not cover
external execution/billing, persistence, distributed workers or direct state
mutation. See the [0.2 migration example](../README.md#reservation-api-02).
