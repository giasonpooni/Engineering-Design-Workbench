# Invariant corpus citation: Constraint-Based State Reconciliation

The [invariant corpus](../validation/invariant-corpus-v1.json) retains the canonical
CSE `invariant-corpus-v1` schema and the source citation
`giasonpooni/Construction-State-Estimator-for-BIM`. This is a retained corpus
identity, not an updated dependency location.

In this declaration, **I** denotes the declared global consistency constraints.
Local state estimates are candidates for reconciliation against **I**.
Projection enforces declared constraints; it does not invent them.

The invariant identifier `lattice.constraints` and coordinate identifier
`var.local-estimate` remain unchanged following the repository's rename from
Lattice Calibration Module. Their spelling preserves compatibility with the
retained declaration.

The corpus claim scope is `computational-integrity-only`. It is a declaration,
not execution evidence. The declaration establishes neither physical validity nor
a stability certificate. The separately implemented `cbsr.affine-exact.v1` kernel
and its tests produce scoped numerical receipts; they do not promote this retained
corpus citation into execution evidence. See the [operation contract](AFFINE_EXACT.md)
for implemented uncertainty propagation, correction diagnostics, and limits.
