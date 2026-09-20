# Scientific Computation Runtime documentation

**Versioned scientific state, declared computational workloads, and provenance-bearing execution.**

Notation Systems develops computational instrumentation and operates
provenance-bearing computational corpora. This repository provides explicit
scientific computation, dispatch, operation history and verification alongside
its existing state and evidence packages. Its full technical name is Scientific
Computation Runtime. Attention is one implemented workload, alongside numerical
and structural workloads; it does not define the whole runtime.

## Component responsibilities

| Component | Responsibility |
| --- | --- |
| [Scientific Computation Runtime](https://github.com/giasonpooni/Scientific-Computation-Runtime) | Declare, execute and record scientific computations and their verification. |
| [Provenance-Preserving Data Acquisition](https://github.com/giasonpooni/Provenance-Preserving-Data-Acquisition) | Acquire observations with source identity, extraction lineage and missingness. |
| [Evidence and State Management](https://github.com/giasonpooni/Evidence-and-State-Management) | Govern evidence, time-qualified state, admission, review and release across scientific and physical-economy domains. |
| [Geospatial State Visualization](https://github.com/giasonpooni/Geospatial-State-Visualization) | Present geographic and temporal state through a read-only globe interface. |
| [State Estimation Evaluation Testbed](https://github.com/giasonpooni/State-Estimation-Evaluation-Testbed) | Specify evaluation of state reconstruction under observation degradation; implementation status is tracked in that repository. |
| [Constraint-Based State Reconciliation](https://github.com/giasonpooni/Constraint-Based-State-Reconciliation) | Specify correction against declared constraints with uncertainty and diagnostics; implementation status is tracked in that repository. |
| [Computational Instrumentation Workbench](https://github.com/giasonpooni/Computational-Instrumentation-Workbench) | Operate and inspect instruments through sessions, adapters and replay. |

This map describes responsibilities. It does not assert that every connection is
implemented, every specification is executable, or every computation is proved.
The runtime's existing evidence, compiler, renderer and local `workbench/` CLI
remain available. New integrations extend their declared boundaries. They do not
create a second authority for canonical state or an alternative execution ledger.

## Start here

- [Repository overview](../README.md): implemented surface and package layout.
- [Architecture](ARCHITECTURE.md): runtime paths and the canonical-state compiler.
- [Rust execution architecture](RUST_EXECUTION_ARCHITECTURE.md): execution and verification contracts.
- [Engine seam](ENGINE_SEAM.md): shared request/result obligations and differing numerical methods.
- [Hardmax-attention workload](TRANSFORMER_ENGINE.md): representation, inference, batching and measured limits.
- [Data capabilities](DATA_CAPABILITIES.md): the Phase 12 compiler/adapter capability matrix, with its original scope.

## Compatibility and historical records

The repository name is a location and display identity. The following remain
unchanged unless a separate, explicit contract migration is justified:

- `ste.*`, `scout.*`, schema and operation identifiers, commitment tags and package imports.
- The root distribution name `deterministic-state-architecture` and derived distributions `canonical-state` and `provenance-pool`.
- Evidence content identifiers, execution attempts, results, verification statements and saved histories.
- Historical commit pins, build recipes, registered artifacts and staging-path components such as `Scout-Retrieval-Agent`.
- The frozen [Deterministic State Architecture specification](ARCHITECTURE_SPEC.md), its version and the protected invariants it defines.

`STE` in existing implementation records and the apparatus compatibility label
refers to Scientific Computation Runtime. Document filenames such as
`STE_EXECUTION_VERTICAL.md` remain stable links. Stage-specific measurements are
records of those runs, not fresh performance claims. Earlier statements such as
"future backend" must be read with their phase context and later implementation
records. For example, the [zkVM adapter boundary](ZKVM_ADAPTER_BOUNDARY.md) is the
original seam contract; the Stage 2, Stage 3 and Stage 6 records describe later
SP1, Nexus and RISC Zero implementations.

The old repository spelling in the Stage 8 rename record remains historical.
Current source/download locations use the renamed repository. Release-template
metadata points to the same current source repository while package identities
remain stable. No proof or evidence record is rewritten to make its spelling
match a current display name.

## Execution and verification records

| Record | Scope |
| --- | --- |
| [Execution vertical](STE_EXECUTION_VERTICAL.md) | Stage 1: specification, native process boundary and execution record. |
| [Verification substrate](STE_VERIFICATION_SUBSTRATE.md) | Stage 2: SP1 proof and verifier path. |
| [Nexus backend](STE_NEXUS_BACKEND.md) | Stage 3: second backend behind the common boundary. |
| [Workload generalization](STE_STAGE4_GENERALIZATION.md) | Stage 4: numerical and external workloads, with proof coverage stated separately. |
| [Reproducible builds](STE_STAGE5_REPRODUCIBLE_BUILDS.md) | Stage 5: guest recipes, artifact identity and registry checks. |
| [Campaign execution](STE_STAGE6_CAMPAIGN.md) | Stage 6: multi-workload campaigns and RISC Zero backend. |
| [Verification policy](STE_STAGE7_VERIFICATION_POLICY.md) | Stage 7: policy decisions above proof capabilities. |
| [Warrant reuse](STE_STAGE8_WARRANT_REUSE.md) | Stage 8: proof artifact cache with verification on reuse. |
| [Proof generation scheduling](STE_STAGE9_SERIALIZED_PROOF_GENERATION.md) | Stage 9: proof-generation work and attributable failures. |
| [Reusable verification artifacts](STE_STAGE10_VERIFICATION_ARTIFACT.md) | Stage 10: measured verification overhead. |
| [Proof manufacturing throughput](STE_STAGE11_PROOF_MANUFACTURING.md) | Stage 11: measured resource limits and concurrency controls. |
| [Molecular/crystal inputs](STE_MOLECULAR_CRYSTAL_VERTICAL.md) | Structural input representations and lowering. |
| [Execution substrate report](PHASE_129_EXECUTION_SUBSTRATE.md) | Phase 129 implementation record. |
| [Semantic boundary](RUST_EXECUTION_SEMANTIC_BOUNDARY.md) | Phase 127 record; revised by Phases 128–129. |
| [Substrate reconnaissance](RUST_EXECUTION_SUBSTRATE_RECON.md) | Phase 126 inspection of explicitly pinned external sources. |
| [zkVM adapter boundary](ZKVM_ADAPTER_BOUNDARY.md) | Original backend-neutral adapter contract. |

## State, evidence and scientific interpretation

- [Frozen specification](ARCHITECTURE_SPEC.md) and [recorded contradictions](CONTRADICTIONS.md).
- [Structured-state reference](PHASE_13_ARCHITECTURE_INVESTIGATION.md), [evidence-pool reference](PHASE_14_DATA_POOL_ARCHITECTURE.md), and [computational evidence](COMPUTATIONAL_COMMONS.md).
- [SCOUT architecture](SCOUT_ARCHITECTURE.md), [retrieval architecture](RETRIEVAL_ARCHITECTURE.md), and [experiment architecture](EXPERIMENT_ARCHITECTURE.md), retaining the scope of their original phases.
- [Numerics](NUMERICS.md), [reduction determinism](REDUCTION_DETERMINISM.md), and [replicate pairing](REPLICATE_PAIRING.md).

## Architecture and recorded measurements

These documents describe invariant enforcement and measurements against named
repository snapshots. Their corpus counts and bindings are not a live inventory
of the renamed stack.

- [Architecture synchronization](ARCHITECTURE_SYNC.md), [derived invariant register](DERIVED_INVARIANT_REGISTER.md), and [invariant-set reconciliation](INVARIANT_SET_RECONCILIATION.md).
- [Core identity](CORE_IDENTITY.md), [ecosystem register](ECOSYSTEM_REGISTER.md), and [API planes](API_PLANES.md).
- [Canonical-state reachability](CANONICAL_STATE_REACHABILITY.md), [chemistry reachability](CHEMISTRY_REACHABILITY.md), [projection conformance](PROJECTION_CONFORMANCE.md), and [recomputability](RECOMPUTABILITY.md).

Generated files in `architecture/exchange/` and `architecture/generated/` remain
outputs of their declared generators. Their identities and measured bindings
are not cosmetically regenerated for a repository rename.

## Releases and verification scope

- [Derived distributions](OPEN_SOURCE_RELEASE.md).
- [Canonical-state distribution](CANONICAL_STATE_RELEASE.md).
- [Publishing procedure](PUBLISHING.md).

The release workflow checks derivation, installation, package metadata and
release refusal tests for the two derived distributions. A green release run
does not verify every native workload or proof backend. The full runtime suite
has additional environment requirements, including native executables, external
engines and prover toolchains/artifacts. Consult the corresponding execution
record before interpreting a skipped test or historical benchmark.

A valid computation and a valid physical measurement are separate claims.
Verification applies to the named program, inputs and statement; admission
continues to govern evidence. The rename introduces no new mathematical method,
physical validation result or implementation maturity claim.
