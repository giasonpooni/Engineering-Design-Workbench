# Concerns audit: delivered capability versus architecture

Audit date: **2026-10-03**. Source baseline:
`cbb1db3aa2ad7287c2587b5e542f6a7d90cfb88f`.
Input: the user-supplied `Pasted text(20261003-044903).txt`.
This audit checks that critique against merged source. It preserves implemented
contracts and does not turn product intent into qualification.

The central concern remains valid: consistent architecture is insufficient
evidence of a delivered scientific or operational capability. Several specific
absence claims in the attachment are now stale. The current code has a typed
machine profile, versioned project graph, bounded Julia/Python interoperability,
registered JuliaControl/JuMP profiles and finite offline acquisition. Their
bounded implementations do not close the broader physical-validation, MCP,
equipment or safety-case gates.

## Concern-to-evidence mapping

| Attached concern | Merged evidence | Assessment and next acceptance condition |
| --- | --- | --- |
| Replay exists but general downstream invalidation does not | [workbench](../src/ciw/workbench.py) retains sources/results and fresh replay; [project model](../src/ciw/project_model.py) reports `needs_reevaluation`. This increment adds [dependency projection](../src/ciw/dependency_graph.py) and [correction journal](../src/ciw/correction_journal.py) over retained identities. | **Partial, advanced in this increment.** Accepted local source reviews now mark aliases and direct/transitive descendants stale without changing old evidence. Explicit source/bundle/execution/result/claim dependencies are projected; unknown native input references remain unresolved. Universal dependency inference remains absent. |
| A machine model is still a pile of JSON | [machine manifest](../src/ciw/machine_manifest.py), [registered workflow](../src/ciw/machine_workflow.py), [contract foundations](CONTRACT_FOUNDATIONS.md); [manifest tests](../tests/test_machine_manifest.py), [lifecycle tests](../tests/test_machine_workflow.py). | **Implemented for one read-only profile.** Evidence/firmware/homing/count basis, frame, clock and six-coordinate covariance are checked. A content-bound declaration is not commissioned machinery or a universal machine schema. |
| Continuous self-calibration is not delivered | Existing calibration/monitoring plus the new [journal](../src/ciw/correction_journal.py) and [synthetic correction gate](../scripts/check_correction_loop.py) through `ciw.encoder-position.v1`. | **Partial, advanced in this increment.** Explicit proposal/local review, stale descendants and corrected fresh execution now run for one synthetic offset fixture. No continuous correction controller, sensor commissioning, physical calibration or ESM admission is established. |
| Physical acquisition is absent | [dataset](../src/ciw/acquired_dataset.py), [snapshot adapter](../src/ciw/adapters/ppda_acquisition.py), [window](../src/ciw/acquired_window.py), [guide](ACQUIRED_DATASET.md). | **Qualification needed.** Finite offline snapshot acquisition/import exists; arbitrary hardware polling and the live gateway are absent. Imported/reprocessed bytes do not establish newly measured physical observations. |
| Julia/Python interoperability is only stated | [Julia oscillator](../src/ciw/julia_oscillator.py), [native contracts](../src/ciw/native_interop_contract.py), [workflow](../src/ciw/native_interop.py), generated environments and [historical validation](NATIVE_INTEROP_VALIDATION.md). | **Implemented for bounded profiles.** Actual historical cross-language execution is recorded. Shared thermal plant/sensor model, observer comparison and general ModelingToolkit interoperability remain open. Transport doubles are not native execution. |
| JuliaControl and JuMP are not operations | `control-oscillator.v1` and `design-qp.v1` dispatch through `ciw.native-interop.v1`; [guide](NATIVE_INTEROP.md), [contracts](../src/ciw/native_interop_contract.py), [worker](../runtimes/native-interop/worker.jl), [responsibilities](EXECUTION_RESPONSIBILITIES.md). | **Stale absence claim.** Registered profiles use ControlSystemsBase.lsim and JuMP/HiGHS with bounded independent checks. The older standalone scalar JuMP study remains unregistered. Neither supplies universal optimization/control. |
| Universal claim graph / executable safety case is absent | Existing project/check/proof surfaces plus new predicted/estimated claims bound to artifact identities in the [journal](../src/ciw/correction_journal.py). | **Partial, advanced in this increment.** Local claims acquire dependency status while retaining `not_verified`, unadmitted and unauthorized status. No checker/premise/operational-policy proof graph, hybrid CPS proof or regulator qualification is established. The obligation planner and ordinary PLSR wrappers retain their prior limits. |
| Verified and Authorized must be separate | [runner](../src/ciw/operations/runner.py) initializes `verification_id: null` and `verification_status: not_verified`; workflow validators fix physical/admission/actuation authority; [native tamper tests](../tests/test_native_interop.py), [study tamper tests](../tests/test_jump_design.py). | **Enforced as refusal of authority in scientific paths.** This is not a deployed authorization system. Trusted issuer/grants, expiry/revocation, dispatch fencing and recovery are specified in the [acceptance plan](DEVICE_GATEWAY_ACCEPTANCE.md), not implemented. |
| AI as researcher through MCP is only planned | Local [server](../src/ciw/server.py), [session](../src/ciw/session.py), [CLI](../src/ciw/cli.py), [workbench](../src/ciw/workbench.py); no MCP server/transport/dependency in the baseline. | **Planned.** A bounded optional adapter can reuse these APIs; the WebSocket protocol is not MCP. An assistant must not fabricate evidence, qualification or action authority. |
| Broad mathematical breakthroughs exceed delivered math | [native profiles](../src/ciw/native_interop_contract.py), [interval](INTERVAL_REQUIREMENT.md), [geometry](GEOMETRY_RESEARCH.md), [free-energy scope](VARIATIONAL_FREE_ENERGY.md), [design](IDENTIFIED_DESIGN.md). | **Valid scope concern.** Bounded interval arithmetic, QP/design and Catalyst symbolic reaction construction exist. No general high-dimensional nonlinear UQ, GA dynamics, streaming TDA, hybrid CPS verification or universal symbolic/numeric solver is established. |

## Documentation corrections

1. Replaced `docs/INTEGRATION_COVERAGE.md`, which at the baseline contained only
   the unresolved text `@/tmp/mcp_content_only.md`, with a source-linked scope
   matrix. A filename include is not a coverage artifact.
2. Clarified registered bounded JuliaControl/JuMP profiles in
   [WORKBENCH_OVERVIEW.md](WORKBENCH_OVERVIEW.md) and
   [UNIMPLEMENTED_DIRECTIONS.md](UNIMPLEMENTED_DIRECTIONS.md). General
   scientific-core/plant-sensor interoperability remains planned. The baseline
   candidate-extension wording no longer obscures the merged native profiles.
3. Distinguish finite offline acquisition from physical sensor commissioning.
   Source lineage and calibration obligations remain explicit.
4. Describe the project graph as a provider-free typed declaration/inspection
   operation with pinned-input status. It does not automatically execute a graph
   or serve as a universal safety-case system.
5. Preserve historical validation dates/platforms/pins. Existing reports record
   genuine runs; this source audit does not independently rerun/requalify them.
   Open proof, runtime-portability and physical gates stay open.
6. The attachment's `AGPL-3.0-only` label is not current package metadata:
   [pyproject.toml](../pyproject.toml) declares `AGPL-3.0-or-later`. Consult
   [LICENSE](../LICENSE), source notices and individual provider terms. This
   audit makes no licence change.

The replacement matrix is the present scope reference. Earlier dated reports
remain historical evidence rather than being rewritten as new gate results.

## Correction increment implemented and run

The [journal](../src/ciw/correction_journal.py) and
[dependency projection](../src/ciw/dependency_graph.py) extend the shared
session. Requests `claim.add`, `correction.propose`, `correction.review` and
`dependency.inspect` use the same structured boundary. Saved workspaces retain
the journal; CLI dependency inspection and socket `dependencies.changed`
notifications expose the status without a second scientific store.

Proposals/rejections are inert. One final accepted local review withdraws the
old source from current dependency use, including aliases of the same evidence,
and marks downstream retained artifacts/claims stale. It never overwrites
source, execution, result or verification records. An old-source reexecution
remains historical and stale. Reviewer names are caller declarations, not
authenticated people or operating-policy issuers.

The graph uses retained source/bundle links, native execution input references,
result identities and explicit upstream references, including JSPT's
`source_result_id`, residual-monitor upstream and native trajectory/force links.
Unknown native input references are reported unresolved rather than guessed.
It is a bounded explicit dependency projection, not universal model semantics
or automatic discovery of every evidential relationship.

Each journal mutation atomically checkpoints the event with all retained source
and result dependencies before publishing it. The withheld reference is a
data-only `reference-evidence` source and an explicit residual-claim premise;
its correction can mark that claim stale without withdrawing the encoder result.

[scripts/check_correction_loop.py](../scripts/check_correction_loop.py) ran the
actual registered provider-free encoder operation against original and corrected
fixture sources. At 300 decoded counts the original position was `1.001 m`;
the held-out synthetic reference was `0.998 m`. The `0.003 m` residual exceeded
a `0.0005 m` diagnostic bound. The corrected `x0 = 0.997 m` produced `0.998 m`
and residual zero. The original, corrected and reference fixture bytes and
digests travel with the saved review bundle.

The gate checked inert proposals, direct/transitive staleness after acceptance,
fresh result/execution identities, unchanged old artifacts, late historical
reexecution staying stale and exact offline reopen. The fixture is synthetic;
its threshold is diagnostic, not a confidence interval or uncertainty bound.
Claims stay `not_verified`, unadmitted and unauthorized. This run creates no
ESM admission, canonical-state mutation, live grant, physical measurement,
physical calibration or platform-wide safety certification.

Malformed/resealed journals, stale reviews, capacity limits, source-label aliases,
storage rollback and offline restore now have passing tests. Actual instrument
calibration, authenticated review, general claim-proof policy and physical
deployment gates remain open.

## Evidence collected in this audit

Merged source, manifests, tests and dated reports were inspected at the baseline
above. The new provider-free correction gate was executed as described here.
No Julia, SCR, SP1, sensor, actuator or private scientific provider was rerun by
this audit. [Correction validation](CORRECTION_LOOP_VALIDATION.md) records the
executed source/installed-wheel checks and broad regression counts. Optional
provider skips are not qualifications of those providers.
