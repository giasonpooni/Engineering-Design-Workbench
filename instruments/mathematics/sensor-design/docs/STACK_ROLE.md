# Stack role and authority

This public instrument extends the computational instrument set with advisory evaluation of supplied measurement alternatives. It owns one bounded calculation and its diagnostics.

| Instrument or authority | Relationship |
| --- | --- |
| Observability and Identifiability Testbed (OIT) | Can explain which modeled parameter directions remain unsupported; supplies context, not an automatic placement decision |
| Jacobian and Sensitivity Propagation Testbed (JSPT) | Can supply derivatives already aligned to the declared parameter coordinates |
| Experiment Design and Sensor Placement Testbed | Calculates candidate Fisher information and ranks a finite supplied set |
| Operator / governed workbench | Reviews feasibility, cost, relevance, and model validity; separately authorizes measurement |
| Provenance-Preserving Data Acquisition (PPDA) | Records actual acquired evidence after separate authorization |
| State inference and evaluation instruments | Consume observations and evaluate estimates through their own contracts |

These are compatibility relationships, not implemented network connections. Core numerical use has no dependency on sibling repositories, no acquisition adapter, and no write path to a workbench or device. The synthetic replay works independently. An optional adapter uses the existing, source-pinned SET validator to export a conforming result artifact. That adapter does not establish CIW native execution, governed evidence admission, or acquisition authority.

Candidate information and posterior precision remain mathematical results. They do not become evidence of real sensor quality, calibration, or model correctness merely by being ranked. Input candidate identity, computation semantics, execution records, and independent verification retain separate meanings. External orchestration can bind a ranked result to its source evidence and execution without transferring command authority into this numerical package.

The name includes experiment design and sensor placement because the same local information calculation can support either task. This foundation contains no location generator, continuous optimizer, geodesic solver, materials model, or plant controller. Any physical application must supply candidate models and feasibility constraints through separately validated instruments and operator review.
