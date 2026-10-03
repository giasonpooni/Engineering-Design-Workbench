# Invariant corpus citation — State Estimation Evaluation Testbed

The [declarative corpus](../validation/invariant-corpus-v1.json) retains the
canonical CSE schema identifier `invariant-corpus-v1` and its historical
citation `giasonpooni/Construction-State-Estimator-for-BIM`. These are retained
schema and provenance identities; the repository rename does not migrate them.

The current repository name is **State Estimation Evaluation Testbed**. Its
evaluation responsibility concerns degraded observations against a declared
plant and measurement model. Noise, missing observations, and latency can
affect reconstruction, but this checkout does not implement those experiments.

The corpus declares `plant.declared` and a state coordinate `var.x` requiring
`declared-H`. Its claim scope is `computational-integrity-only`. The declaration
is not evidence that an estimator ran, that a numerical result was verified,
or that a physical model is valid or stable.

See the [README](../README.md) for current implementation status and component
responsibilities.
