# Stack role

The Observability and Identifiability Testbed (OIT) diagnoses what a declared
model and experiment can distinguish. It is a bounded analysis instrument.

| Neighbor | Relationship | Authority retained by that neighbor |
| --- | --- | --- |
| GSIE | Supplies model matrices or uses model-bound diagnostic results | State estimation, posterior propagation and estimation-result identity |
| JSPT | Can supply local Jacobian/sensitivity matrices with evaluation context | Derivative computation and its own numerical verification |
| SET | Evaluates OIT results against declared analytical/reference cases | Evaluation claims and their independent verification identity |
| EDSPT | Can consume information, nullspace and weak-direction diagnostics for candidate experiments | Experiment design criteria, candidate ranking and execution decisions |
| CIW / ESM | May bind results to evidence and a governed session | Canonical state, admission, policy and operational authorization |

These relationships describe compatible contracts. The numerical core does not
import or require neighboring repositories. The optional `oit.exchange` export
adapter calls the validator from SET at pinned commit
`c4d39c755187796ce2c72552a90454871c516c8f`, reusing the existing
`notation.instrument.result-artifact.v1` format. Cross-instrument model adapters
must preserve evaluation point, column ordering, units/scales, model version,
numerical tolerances and input lineage. No CIW execution or ESM admission is
implemented by exporting a conforming result.

OIT owns construction of finite-horizon LTI observability matrices, explicit
coordinate scaling, SPD covariance whitening and local numerical rank diagnostics.
It does not own acquisition, calibration truth, Jacobian truth, state estimation,
constraint reconciliation, physical observability claims, evidence admission,
sensor deployment or actuator commands.

An OIT result can support a verification argument. It does not verify itself:
the execution producing the result and the independent verification event remain
separate. A physical inference also requires a model-validity argument outside
this numerical instrument.
