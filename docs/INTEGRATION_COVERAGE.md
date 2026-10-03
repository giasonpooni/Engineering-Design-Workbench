# Integration coverage and evidence boundaries

Source audit: **2026-10-03**, baseline
`cbb1db3aa2ad7287c2587b5e542f6a7d90cfb88f`. This matrix names merged source
surfaces and their tests; it does not report a new execution of every provider.
The [concerns audit](CONCERNS_AUDIT_2026-10-03.md) separates source inspection
from historical qualification and explains changes relative to the critique.

**Implemented** means a callable implementation and associated contracts are
present. **Bound provider** additionally requires the operator's exact checkout,
executable and dependency closure. A named operation, capability record or
source file establishes neither qualification nor physical validity. An
unavailable provider must refuse rather than manufacture a result.

## Shared host and provider-free foundations

| Surface | Merged implementation and tests | Scope and remaining gate |
| --- | --- | --- |
| Terminal, Python API and local WebSocket session | [session](../src/ciw/session.py), [server](../src/ciw/server.py); [protocol tests](../tests/test_protocol.py), [integration tests](../tests/test_integration.py) | Implemented local host. Remote authentication, multi-user deployment and hard real-time control are not supplied. |
| Statistics and periodogram | `statistics.v1`, `spectrum.periodogram.v1`: [registry](../src/ciw/operations/registry.py), [instruments](../src/ciw/instruments.py); [instrument tests](../tests/test_instruments.py), [runner tests](../tests/test_operation_runner.py) | Implemented bounded analysis. Legacy result envelopes remain `not_verified`; explicit reference checks are separate. |
| Retained source, result, failure, save/reopen and replay | [workbench](../src/ciw/workbench.py), [attempts](../src/ciw/workflow_attempts.py); [session tests](../tests/test_workbench_session.py), [failure-history tests](../tests/test_workflow_failure_history.py) | Implemented catalog and explicit fresh replay. Reopen performs no provider execution. Retained terminal failures are not crash recovery for in-flight work. |
| Encoder/gearbox/leadscrew configuration | `ciw.encoder-position.v1`: [manifest](../src/ciw/machine_manifest.py), [workflow](../src/ciw/machine_workflow.py); [manifest tests](../tests/test_machine_manifest.py), [lifecycle tests](../tests/test_machine_workflow.py) | Implemented evidence-backed, read-only position profile and first-order joint covariance. No document authenticity check, physical commissioning, firmware loading or actuation. |
| Typed project declaration and dependency status | `ciw.project-graph.v1`: [model](../src/ciw/project_model.py), [workflow](../src/ciw/project_workflow.py); [model tests](../tests/test_project_model.py), [lifecycle tests](../tests/test_project_workflow.py) | Implemented append-only typed declarations, separate physical/computation/evidence edges and `needs_reevaluation` for changed pinned inputs. Does not execute declared graph computations or bind every workbench result automatically. |
| Local correction journal and retained-artifact claim graph | [journal](../src/ciw/correction_journal.py), [dependency projection](../src/ciw/dependency_graph.py), [runnable correction gate](../scripts/check_correction_loop.py) | Added in this increment: append-only predicted/estimated claims, source correction proposals and final local reviews. Accepted reviews mark withdrawn source aliases and transitive descendants stale; prior bytes remain unchanged. Reviewer names are declarations, not authenticated principals. Claims stay `not_verified`, unadmitted and unauthorized. Unknown native input references remain explicit. |
| Data-only scalar reference import | [reference contract](../src/ciw/reference_evidence.py), [session tests](../tests/test_correction_session.py) | Retains exact reference source bytes and declared quantity, origin, unit, frame, timestamp and uncertainty. Reference-dependent claims can become stale independently of model outputs. No executable operation or physical acquisition is supplied. |
| Synthetic thermal observer and sensor choice | `ciw.thermal-observer.v1`: [contract](../src/ciw/thermal_contract.py), [reference](../src/ciw/thermal_reference.py), [workflow](../src/ciw/thermal_workflow.py); [contract tests](../tests/test_thermal_contract.py), [lifecycle tests](../tests/test_thermal_workflow.py) | Implemented Python two-capacity model, dropout-aware Joseph update and bounded sensor selection. Julia thermal worker and held-out physical measurements remain separate gates. |
| Capability listing and preflight | [capabilities](../src/ciw/capabilities.py), [doctor](../src/ciw/doctor.py); [capability tests](../tests/test_capabilities.py), [doctor tests](../tests/test_doctor.py) | Implemented data-only listing and local preflight. No universal profile discovery or composition registry; `authorizes_execution: false`, qualification `not_performed`. |
| Retained educational/reference calculations | [learning](../src/ciw/learning.py), [linear response](../src/ciw/linear_response.py), [exact response](../src/ciw/exact_response.py); [learning tests](../tests/test_learning.py), [exact-response tests](../tests/test_exact_response.py) | Implemented narrow teaching/checking surfaces. No universal curriculum, theorem prover or equipment authority. |

## Scientific provider operations

These operations use the shared lifecycle. Provider pins and numerical policy
remain owned by each operating guide and packaged runtime manifest. Synthetic
transport doubles establish contract/retention behavior; required native gates
need actual providers and cannot close with skips.

| Registered surface | Guide and source/tests | Scientific scope and limits |
| --- | --- | --- |
| `ciw.calibrated-observable.v1` | [guide](CALIBRATED_OBSERVABLE.md), [source](../src/ciw/calibrated_observable.py), [tests](../tests/test_calibrated_observable.py) | Bound calibrated-observation and estimation chain; no general physical acquisition or automatic correction loop. |
| `ciw.identified-design.v1` | [guide](IDENTIFIED_DESIGN.md), [source](../src/ciw/identified_design.py), [tests](../tests/test_identified_design.py) | Bound model, prediction and constrained next-observation design. Uncertainty limits remain explicit; selecting a measurement does not perform or authorize it. |
| `ciw.telemetry.v1` | [guide](TELEMETRY.md), [source](../src/ciw/telemetry.py), [tests](../tests/test_telemetry.py) | Bound telemetry processing and retained records; no deadline guarantee from the host. |
| `ciw.calibrated-window.v1` | [guide](CALIBRATED_WINDOW.md), [source](../src/ciw/calibrated_window.py), [tests](../tests/test_calibrated_window.py) | Bound finite calibrated-window workflow; no continuous hardware polling. |
| `ciw.schematic-assessment.v1`, `ciw.numerical-heat.v1` | [guide](DECLARED_WORKLOADS.md), [source](../src/ciw/declared_workload.py), [tests](../tests/test_declared_workloads.py) | Bound schematic assessment and numerical heat computation. Numerical completion is distinct from proof. |
| `ciw.proved-heat.v1` | [guide](PROVED_HEAT.md), [source](../src/ciw/proved_heat.py), [tests](../tests/test_proved_heat.py), [required gate](../scripts/check_proved_heat.py) | Registered integer Jacobi guest and fresh SP1 verifier path. Missing toolchain/ELF/prover refuses. Saved proof outcome is historical, not freshly verified on inspect. Does not verify arbitrary Julia or physical heat. |
| `ciw.schematic-companions.v1` | [guide](INTEGRATED_MODULES.md), [source](../src/ciw/schematic_companions.py), [tests](../tests/test_schematic_companions.py) | Bound selected schematic/JSPT/PLSR companions with retained upstream bindings; continuous linear surrogate scope only. |
| `ciw.bim-quantity.v1` | [guide](INTEGRATED_MODULES.md), [source](../src/ciw/bim_quantity.py), [tests](../tests/test_bim_quantity.py) | Bound IFC quantity conditioning and ledger replay; no surveyed geometry/clearance qualification. |
| `ciw.acquired-dataset.v1`, `ciw.acquired-calibrated-window.v1` | [dataset guide](ACQUIRED_DATASET.md), [stream guide](ACQUIRED_STREAM.md), [dataset source](../src/ciw/acquired_dataset.py), [window source](../src/ciw/acquired_window.py); [dataset tests](../tests/test_acquired_dataset.py), [window tests](../tests/test_acquired_window.py) | Bound finite offline snapshot acquisition/import and calibrated processing. Raw lineage is retained; no general live sensor gateway or fresh physical sample from replay. |
| `ciw.residual-monitor.v1` | [source](../src/ciw/residual_monitor.py), [tests](../tests/test_residual_monitor.py) | Bound CUSUM residual monitor. An alarm is an estimated anomaly, not evidence of a uniquely identified cause. |
| `ciw.measurement-chain.v1` | [guide](../examples/measurement-chain/README.md), [source](../src/ciw/measurement_chain.py), [tests](../tests/test_measurement_chain.py) | Bound RCI → FSRT → JSPT chain with joint covariance; no unsupported independence or automatic physical admission. |
| `ciw.geometric-circle.v1` | [guide](GTE.md), [source](../src/ciw/geometric_circle.py), [tests](../tests/test_geometric_circle.py) | Bound circle eligibility, local geometry and covariance. No general multi-frame geometric-algebra dynamics. |
| `ciw.identified-stability.v1` | [guide](PLSR.md), [source](../src/ciw/identified_stability.py), [tests](../tests/test_identified_stability.py) | Bound discrete identified-model Lyapunov assessment; no continuous-time conversion or universal nonlinear/hybrid safety case. |
| `ciw.flat-torus-reference.v1`, `ciw.curved-path-transfer.v1` | [guide](GEODESIC_REFERENCES.md), [source](../src/ciw/geodesic_reference.py), [tests](../tests/test_geodesic_reference.py) | Bound geodesic reference profiles; no physical navigation qualification. |
| `ciw.covariance-geometry.v1`, `ciw.mesh-path.v1`, `ciw.translation-flow.v1` | [guide](GEOMETRY_RESEARCH.md), [source](../src/ciw/geometry_research.py), [tests](../tests/test_geometry_research.py) | Bound geometry research profiles; representation and numerical scope remain profile-specific. |
| `ciw.variational-free-energy.v1` | [guide](VARIATIONAL_FREE_ENERGY.md), [source](../src/ciw/free_energy_workflow.py), [tests](../tests/test_free_energy_workflow.py) | Bound linear Gaussian/free-energy example, not a general discovery system. |
| `ciw.energy-accuracy.v1` | [guide](ENERGY_ACCURACY.md), [source](../src/ciw/energy_workflow.py), [tests](../tests/test_energy_workflow.py) | Bounded CUDA/NVML bench when host capability is available. Synthetic/retained paths do not establish measured whole-machine energy or calibrated laboratory uncertainty. |
| `ciw.instrument-exchange.v1` | [guide](EXCHANGE.md), [source](../src/ciw/exchange_adapter.py), [tests](../tests/test_exchange_adapter.py) | Bound typed exchange adaptation. Profile semantics/provenance do not supply a universal model compiler. |
| `ciw.julia-oscillator.v1` | [guide](JULIA_OSCILLATOR.md), [source](../src/ciw/julia_oscillator.py), [tests](../tests/test_julia_oscillator.py) | Bound Tsit5 worker with independent Python analytic oracle and fresh replay; no physical validation, sensor-model identification or unrestricted Julia execution. |
| `ciw.native-interop.v1` | [guide](NATIVE_INTEROP.md), [source](../src/ciw/native_interop.py), [contracts](../src/ciw/native_interop_contract.py), [tests](../tests/test_native_interop.py) | Bound SCR profiles for affine arithmetic, oscillator force/energy, Tsit5, ControlSystemsBase, JuMP/QP, Catalyst/Cantera and a scalar interval requirement. Exact runtime closure and independent checks apply. No general ModelingToolkit plant compiler or source-to-binary attestation. |
| `esm.inspect-candidate.v1`, `esm.capture-candidate.v1` | [guide](STATE_DIAGNOSTICS_EVIDENCE.md), [source](../src/ciw/candidate_evidence.py), [tests](../tests/test_workbench_candidates.py) | Explicitly bound ESM candidate inspection/capture. Capture remains unadmitted; no canonical-state mutation, release activation or blanket verification authority. |

The standalone [JuMP adjustment study](DESIGN_ADJUSTMENT.md) is a real worker
with an exact Python checker but no registered operation/execution/result
identity of its own. It differs from the registered `design-qp.v1` profile
inside `ciw.native-interop.v1`.

## Platform claims that remain partial or planned

| Claim | Current evidence | Remaining demonstration |
| --- | --- | --- |
| Incident replay / counterfactual investigation | Retained sources/replay, fresh identities, project status and a local source/bundle/execution/result/claim dependency projection exist. | Concrete incident data and complete workload-specific dependency coverage. Projection uses retained explicit references; it does not infer all scientific dependencies. |
| Adaptive self-calibration | Calibrated windows, residual monitoring and estimation exist. This increment ran a synthetic encoder-offset proposal/review/corrected execution with transitive staleness and offline reopen. | Continuous correction policy, actual instrument/reference evidence and held-out physical improvement. Local review acceptance is not physical calibration or ESM admission. |
| Executable claim graph / safety case | Scoped provider checks, proof profiles and project declarations exist. New predicted/estimated claims depend on retained artifact identities and can become stale. | Checker/premise/operational-policy graph, workload-specific safety proof and hybrid-system proof where needed. New claims remain `not_verified`; no regulator acceptance is claimed. |
| Language-neutral engineering model | Bounded native contracts and genuine historical cross-language cases exist. | Shared thermal plant/sensor model, observer comparison, covariance transform and constrained measurement choice across Python/Julia. |
| AI researcher through MCP | No MCP server/transport/dependency is present in this baseline. Local API exists. | Bounded optional adapter calling the existing API, deterministic refusals, retained proposals and tests; no generated equipment permission. |
| Device authorization and operation | Scientific paths refuse equipment authority; [gateway contract](DEVICE_GATEWAY.md) and [acceptance plan](DEVICE_GATEWAY_ACCEPTANCE.md) are specified. | Trusted issuer/policy, durable dispatch/recovery, simulator qualification and separately commissioned hardware. Acceptance cases are not results. |
| Broad mathematical platform | Local covariance, linear stability, geometry, free-energy, bounded QP and scalar interval profiles exist. | General nonlinear UQ, multi-frame GA, streaming TDA, hybrid CPS proofs and general symbolic/numeric compilation remain provider research. |

## Interpreting validation

Historical genuine execution is recorded in
[native validation](NATIVE_INTEROP_VALIDATION.md),
[reaction validation](REACTION_BENCHMARK_VALIDATION.md) and
[interval requirement](INTERVAL_REQUIREMENT.md). Those records name platforms,
pins, completed cases and open gates. They do not qualify this checkout anew or
the reader's environment.

Source inspection, passing transport doubles, same-runtime replay, independent
numerical agreement, cryptographic proof and physical reference comparisons
support different claims. Successful computation never supplies equipment
authorization. [Execution responsibilities](EXECUTION_RESPONSIBILITIES.md) and
[protocol](PROTOCOL.md) retain these boundaries.

The new [correction gate](../scripts/check_correction_loop.py) was executed in
this increment using the actual provider-free `ciw.encoder-position.v1`
operation. One withheld synthetic point gives original position `1.001 m`
against reference `0.998 m`: residual `0.003 m` exceeds the declared `0.0005 m`
diagnostic bound. A corrected offset produces `0.998 m` with residual zero.
The gate checks inert proposals, transitive staleness after local acceptance,
fresh execution/result identities, unchanged original artifacts, late historical
reexecution remaining stale and exact offline reopen. This demonstrates one
workflow with synthetic fixture evidence, not a calibrated physical instrument,
an independent physical validation or general self-healing behavior.

Journal actions checkpoint their events and complete retained dependencies
together before publication. [Validation results](CORRECTION_LOOP_VALIDATION.md)
record this increment's negative tests, source/installed-wheel gates and optional
provider skips separately.
