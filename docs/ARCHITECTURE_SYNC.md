# Project-Wide Architecture Synchronization — Implemented

Core version: **core@1.0.0**, declared in `architecture/core.yaml` —
NOT in `invariants.yaml` and NOT derived from packaging. A package
version moves on any release; a core-schema version moves only under
`bend_protocol`, so the two are decoupled deliberately and the
declaration denies the coupling explicitly. Every architecture artifact
pins the declared version and the conformance gate refuses a mismatch,
which is what gives `bend_protocol` teeth: moving the version stops the
whole repository conforming at once. See
`docs/DERIVED_INVARIANT_REGISTER.md` §1.

## Phase 0 — inspection results (facts, before any change)

- None of `invariants.yaml` / `evidence_class.yaml` /
  `model_binding.yaml` / `functions.yaml` / doctrine files / CI
  workflows / generator infrastructure existed. All were created bound
  to real, inspected state — nothing fabricated.
- `extraction_method` is the existing ingest-time declaration, inside
  `Observation`'s content-addressed identity (immutable structurally).
- Production observation-minting seams: `scout/pipeline.py`
  (documents), `execution/dispatcher.py` → `materials/results.py`
  (`simulation:*` results), `experiment/step.py` (dispatch),
  `evidence/{types,admission,pool}.py` (constructor/gate/store).
- `ActionCandidate` (optimizer output) is not an admissible type; no
  optimizer module holds a pool write.
- `EvidencePool` has **no persistence layer** — no legacy records
  exist (unclassified backlog = 0).
- `core/canonical` already provides content-addressed canonical-state
  versioning (`VersionId` over schema_version/fields/edges).
- No hosted model binding is instantiated anywhere in runtime (no
  client, key, or call site).
- Chemistry concepts already generic: see `concept_reconciliation` in
  `architecture/verticals/chemistry/vertical.yaml`.

## Implemented

- **Acquisition-first loop** bound to real edges
  (`architecture/invariants.yaml: control_loop`), with the return edge
  enforced executably: the set of modules that mint/write observations
  is closed and ratcheted
  (`test_return_edge_only_declared_seams_mint_observations`).
- **class_assigned_at_ingest** — `evidence/classes.py::class_of`, a
  total fail-closed map from the declared extraction method to
  {measured, asserted, computed, derived}; immutability is structural
  (the declaration is inside the content-addressed id). No production
  path mints `measured`; `simulation:*` can never class as measured
  (COMPUTATION ≠ MEASUREMENT, executable).
- **proposals_are_not_evidence** — structural (no admissible form; no
  optimizer pool writes), locked by source-scan + refusal tests.
- **Registries** — `architecture/{invariants,evidence_class,
  model_binding,vocabulary_map}.yaml`, `_probes/generality.yaml`,
  `verticals/chemistry/vertical.yaml`; all parse, all pin core@1.0.0.
- **Doctrine generator** — `architecture/doctrine_generator.py`:
  doctrine is a generated projection of the canonical YAML
  (`architecture/generated/doctrine/*.md`, committed); deterministic;
  vendor-free (self-linted); budgeted (4000 chars, fail closed);
  `conformance.check_doctrine_current` regenerates and diffs —
  non-zero diff fails, so manual edits to the projection cannot
  survive. No CI infrastructure exists; the test suite is the gate and
  future CI calls the same functions.
- **Snapshot verification boundary** —
  `architecture/snapshot_verification.py`: `pin_accepted` +
  `behavioral_canary` (structured-field scoring, never output hashes;
  measured noise floor; committed threshold; breach = halt ingest +
  diff + human re-pin). Exercised against the repository's real
  deterministic extractor (noise floor measured exactly 0.0 over 3
  runs). No fake vendor echo-probe exists anywhere.
- **Agent-execution retention** — `architecture/retention.py`:
  the mandatory audit record (binding, snapshot identity or explicit
  "unavailable", adapter version, doctrine hash, prompt, input/output
  fingerprints, timestamp, lineage), self-consistent or refused.
- **Quarantine** — `evidence/quarantine.py`: rejected candidates
  retained with failing invariant ids, per-invariant rejection metrics,
  and no force path (asserted by test).
- **Chemistry identity** — `structures/substance.py`:
  `ResolutionPolicy` (tautomer/stereo/salt_solvate/isotope, versioned,
  in the identity), merge guard blocking policy mismatch;
  `DistributionIdentity` for polymer/formulation/batch (structure
  string alone inadmissible).
- **Properties/quantities** — `structures/quantity.py`: typed
  quantities with explicit `uncertainty_kind` (absent ≠ lost);
  context-free properties refused.
- **Method blocks** — `structures/method_blocks.py`: quantum/md/ml
  blocks gate canonical assertion; applicability-domain check;
  exercised against the real argon MD inputs.
- **Conformance gate** — `architecture/conformance.py`:
  vertical_contract + core-closure + doctrine-current + vendor lint;
  unconformant and stale-core verticals refused (tested).

## Verified (all executed this phase)

Fast suite **1960 passed** (1944 pre-existing + 16 new architecture
locks); chemistry vertical 12/12 with a real Nexus proof and a real
GROMACS run; warm structural campaign end-to-end (warrant reuse + SP1
verifier artifact): 2.3 s, dual warrants on water, evidence invariance
asserted. All firewall locks (phases 105/108/112b/115) pass.

## Preserved / Extended / Qualified / Bent

- **Preserved**: every STE mechanism (ExecutionSpecification,
  ExecutionResult, OperationTrace, ProofBackend, VerifiedExecution,
  WarrantCache, SP1 verification artifact, all backends, campaign
  policy, structures, GROMACS boundary) — untouched and re-verified.
  The phase-105/108/112b/115 firewalls were honored, not weakened: the
  chemistry gates were placed in `structures/` (the vertical extension
  package outside the firewalled core packages) after the locks caught
  the first placement; `Quarantine` became a plain class like the pool.
- **Extended** (supersets): everything under Implemented.
- **Qualified**: method blocks narrow `execution_recorded` for
  canonical assertion inside the chemistry vertical; admissibility
  classes narrow reproducibility per-vertical. Core semantics
  unchanged.
- **Bent**: **none** — and since 2026-08-26 that is measured against a
  probe carrying a computation property, which it previously was not
  (§2 of the register record states exactly how narrow the evidence had
  been). The generality probe found one candidate bend —
  `evidence_append_only` has no tombstone semantics, so a
  revocation-compelling source cannot be onboarded — and it is
  RECORDED as a core limitation requiring a version increment when
  addressed, not silently patched.

## Generator / Canary / Migration / Probe state

- Generator: canonical sources authoritative; regeneration
  deterministic (tested); committed projection current (diff = 0);
  budget enforced; vendor lint enforced.
- Canary: binding `rule-based-extractor` (the deterministic reference),
  fixtures v1 in-repo, noise floor **0.0 measured over 3 runs**,
  threshold 0.0, current result 1.0 (pass). Hosted bindings: none
  instantiated; each must recalibrate its own noise floor with
  provenance. Residual: drift behind a stable id is detectable, not
  provable; drift under the noise floor is undetectable by
  construction.
- Migration: legacy records 0 (no persistence layer); rules registered
  for when persistence lands; no bypass path exists.
- Probe: evaluated against core@1.0.0 — non_reproducible: no bend
  (admissibility classes qualify); revocable_record: candidate bend
  recorded (tombstones absent); cohort_identity /
  uncontrolled_conditions: untested, recorded as unknown, not guessed;
  recursive_computation: `none_at_the_execution_boundary` -- NOT a bare
  `none`, deliberately, because it does not mean what the observation
  rows' `none` means. No bend on structural grounds (an N-iteration
  estimator is one ExecutionSpecification, so one computation identity
  and one trace occurrence at the boundary this repository owns), with
  the evidence boundary recorded — the lineage-depth half is
  `generation_depth_bounded`, owned by the acquisition layer, and is
  not falsifiable from this repository's ledgers.
  **The computation-property key was ABSENT until 2026-08-26.** Every
  `Bent: zero` claimed before that date was measured against a probe
  whose properties were all properties of an OBSERVATION, structurally
  unable to falsify anything about computation — narrower evidence than
  the claim implied. See `docs/DERIVED_INVARIANT_REGISTER.md` §2.

## Identity decisions

Substance identity commits to (representation, representation_version,
resolution_policy); the policy is part of the identity so merges CHECK
rather than infer. Default policy dimensions all `distinct` (the
conservative pole); `normalized` tautomer handling requires an explicit
rule id. Distribution kinds require their full field sets. Rationale
throughout: merging on false identity validates provenance while
corrupting science — the failure the addendum names.

## Claim classification

**MEASURED**: the inspection facts; noise floor 0.0/3 runs; all test
counts; the campaign numbers. **STRUCTURALLY GUARANTEED**: class
immutability (content-addressed identity), no proposal write path, no
force path, doctrine-diff gate, frozen record types. **CALLER-DECLARED**:
extraction methods, identity policies, method blocks, worker limits,
the intended role topology. **EXTERNALLY UNVERIFIABLE**: served-weight
identity behind any future hosted binding; drift below the noise floor.

## Unresolved (carried forward, visibly)

- `multi_writer.write_conflict` — merge policy for concurrent canonical
  assertions (unblocked by the identity-policy work; undecided).
- `builder_check_lineage` — whether enforcement-code review must be
  cross-vendor (authorship recorded in model_binding.yaml; process
  decision, flagged).
- `attested_snapshot_identity` — unavailable for hosted bindings
  (available for guest ELFs via reproducible builds).
- capabilities 5–9 — acceptance criteria still required.
- tombstone/defeasance semantics — the recorded candidate bend.
