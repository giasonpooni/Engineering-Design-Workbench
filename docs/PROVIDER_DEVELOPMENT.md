# Provider development sequence

PDT is being developed as a programmable computational laboratory. Its shared
investigation lifecycle connects questions, model versions, observations,
assumptions, candidate designs, executions, results and scoped checks. The
terminal, Python API and graphical clients use the same operation layer; an
LLM is optional. See [consolidation](CONSOLIDATION.md) for the proposed typed
composition and dependency model, and [coverage](INTEGRATION_COVERAGE.md) for
what is executable today.

The supplied technology catalogue is a set of possible providers, architectural
references and research candidates. It is not an installation list. Every
increment needs the same acceptance record:

**Scientific question → supported contract → exact implementation → independent
reference → failure cases → retained result → measured cost.**

| Increment | Bounded experiment and completion evidence |
| --- | --- |
| Native interoperability | Finish qualification/review of the existing Rust-supervised C++/Julia profiles; preserve explicit platform, proof and deployment gates |
| Validated numerical bounds | [Scalar-square error enclosure](INTERVAL_REQUIREMENT.md), exact rational fixtures, rounding bindings and correct inconclusive results |
| Factor-graph estimation | Evaluate a GTSAM profile against a small known estimate and an unobservable case; retain frame, residual, prior and dependence semantics; consider Stone Soup for comparative experiments |
| Local-response operators | Support declared dense, sparse and matrix-free `F(x)`, `Jv`, `Jᵀw`; test adjoint consistency and an independent derivative reference |
| Materials calculation | Evaluate a bounded MolSSI/QCSchema/QCEngine provider; retain native records and explicit property/scale-transfer models |
| Scientific fields | Evaluate a PyVista/VTK view with geometry/field identities, units and recorded slice/resampling transformations |
| Physical validation | A held-out thermal, cooling or resin-processing experiment with an independent reference and explicit uncertainty |

Except for the linked native and interval increments, these rows remain proposed
evaluation work, not registered or qualified capabilities. Private provider
access and hosted runtime qualification remain explicit deployment gates.

## Composition obligations

Symbolic compilation (SymPy/ModelingToolkit) must be code-owned and registered;
data requests cannot supply executable expressions. A response operator must
declare units, coordinate order, domain and supported derivative meaning.
Matching array sizes do not establish a physical coupling.

Numerical enclosures, probabilistic uncertainty, deterministic error bounds,
physical validation, cryptographic execution checks and operational permission
have separate meanings. Retention and replay do not admit a scientific claim
into ESM. Operational trace identifiers can link to scientific execution IDs;
they must not replace them.

Scientific dependencies and scheduler call history are different relationships.
Evaluate AiiDA when an actual workflow needs scheduler/HPC management. Preserve
native provenance while mapping selected dependencies into PDT and ESM.

Design geometry, analysis meshes/fields and inspection scenes have distinct
authority. CAD-to-mesh conversion, field resampling, CRS transformations and
scene projection are declared derived operations. A geographic transform is
not a survey calibration. Arrow IPC and in-process columnar exchange are
candidate data transports; neither defines scientific meaning or ownership.

Molecular representation is distinct from a material specimen. A future polymer
profile needs formulation, chain/distribution assumptions, processing and
measurement conditions, and explicit models between molecular and engineering
scales. Chemical and thermal coupling requires energy/transport equations and
tests; the current isothermal A-to-B benchmark does not supply them.

## Evaluate only when a workload requires it

FEniCSx heat/refinement, OpenModelica/FMI, Ceres fitting, RDKit/PySCF molecular
work, HOOMD/LAMMPS particle models, Geomstats and GeometricKernels are candidates
for bounded reference comparisons. None is qualified by its repository name.
Different torus geometries, Jacobi polynomial filters, Jacobi fields and
Jacobians must retain distinct semantics. Shape-constrained feature calibration
does not establish metrological calibration.

Acceleration earns adoption through complete-workload accuracy, latency, memory
and transfer measurements, with arithmetic/reduction policies declared. Keep
independent references and refusals. Additional graphics engines, proof systems,
hardware programmes or ledgers require a specific unmet workload.

A future end-to-end material investigation could compare heating schedules
under conversion and temperature requirements, use new observations to challenge
the model, and retain unsuccessful candidates. That example is a product goal,
not a qualified manufacturing instruction or an implemented universal solver.
