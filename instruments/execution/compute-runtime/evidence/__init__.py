"""Evidence pool: the first real implementation of the pool architecture
investigated (research-only, no code) in
`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md`.

This package holds uncertain, conflicting, machine- or human-extracted
evidence -- it is explicitly NOT `core.canonical` and never becomes it
automatically. See `docs/SCOUT_ARCHITECTURE.md` for the full boundary
rationale and `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §O for the single
crossing rule this package deliberately does not yet implement (only a
`Derived value`, reviewed, may seed a `CandidateDelta` -- this package
stops one stage short of that, per this phase's own scope).
"""
