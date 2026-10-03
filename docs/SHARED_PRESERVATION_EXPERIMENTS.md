# Shared preservation experiments V1

The common research question is: **which task-relevant properties survive a
transformation between representations?** This increment extends the existing
NET representation, preservation, ingress, identity and production contracts.
It introduces no scheduler, alternative state owner or autonomous production graph.

## Mathematical spine

An underlying object/state X is represented by Rᵢ(X). A transformation T:X→Y
must be distinguished from its coordinate or carrier implementation Tᵢ.
For a declared property I, preservation means I(X)=I(T(X)) only when that
property is actually claimed invariant under T. Estimation deliberately changes
means and covariance; the post-estimation **carrier round-trip** must preserve
the resulting estimate within its declared bounds.

For a vector v, invertible basis matrix P and linear operator A:

- q=P⁻¹v;
- B=P⁻¹AP;
- PBq=Av;
- ΣB=P⁻¹ΣA(P⁻¹)ᵀ and PΣBPᵀ=ΣA;
- G=PᵀP and qᵀGq=vᵀv.

The commutation identity follows by substituting q and B and cancelling PP⁻¹.
Similarity preserves trace, determinant, rank and the characteristic polynomial,
because det(λI−P⁻¹AP)=det(P⁻¹(λI−A)P)=det(λI−A).
A non-orthogonal basis does not preserve the plain Euclidean norm of its
coordinate tuple. A singular operator is a valid information-losing map; a
singular basis matrix is not a valid basis change.

The laboratory evaluates rational examples exactly, computes kernel/image
bases and retains an unchanged-operator counterexample. Its symbolic explanation
is a mathematical derivation; Python evaluation is not a Lean proof certificate.
The existing finite-preservation implementation remains the measure-aware
instrument: equal output distributions can coexist with statewise intervention
failure. Continuous/stochastic generalization remains a later workload.

```sh
net lab --output-dir lab-results
```

Open `examples/representation-laboratory/index.html` locally for editable basis
and operator matrices, prediction checking, a singular refusal and a commuting
calculation. Its JavaScript uses exact rational arithmetic. Browser display
calculations do not issue NET admission receipts.

## External IFC → native CSE → checked carrier

The upstream buildingSMART specimens are retained unmodified with Git blob and
SHA256 identities and CC BY 4.0 attribution. See
`examples/preservation-experiments/external/README.md`.

Two distinct results must remain visible:

1. Unchanged whole architectural IFC lowering is **REFUSED**: the storey lacks
   CSE's required ClearHeight quantity. The unmodified structural beam also has
   a 3-D RefDirection outside native placement support.
2. A narrowly scoped **quantity projection** extracts beam #175 / GlobalId
   `0fqX614OH1YO1Njdxms2$Q`, its declared Length #179 and its declared millimetre
   unit context. It retains the exact original geometry bytes and placement chain
   as audit evidence and creates a separate metre quantity carrier. That carrier
   explicitly has no source spatial authority. Off-scope computational state and
   operational geometry are declared lost rather than silently invented.

Native CSE supplies compilation, its prior policy, Gaussian conditioning,
invariants, IFC/snapshot export and hash-chained ledger replay. The synthetic
independent observation is 2.69 m, variance 0.000025 m². Prior length is 2.7 m,
variance 0.000025 m²; posterior is 2.695 m, variance 0.0000125 m².
The NET checker independently evaluates the scalar Gaussian update and checks
identity, means, full covariance, snapshot identity and ledger replay.

The executed result bridges into a **scoped** interoperability profile,
ingress verification/qualification and candidate IFC↔CSE identity binding.
The existing ingress record keeps its declaration-only `mapping_executed=false`;
a separate executed experiment records `mapping_execution_performed=true` and
binds the diagnostic evidence. The round-trip witness uses the existing typed
preservation verification and admission eligibility gate. No record creates a
canonical entity or performs canonical admission.

A second, synthetic room workload exercises the existing bounded BIM operation
and checks its full native result with the existing operation-specific validator.
It additionally verifies that protected original IFC records survive export.
Mean absolute tolerance is 1e-12; covariance tolerances are rtol=1e-10,
atol=1e-14. Native world and ledger identities are compared exactly.

```sh
PYTHONPATH=src python examples/bim-quantity/make_source.py > /tmp/bim-source.json
net lab --cse-root /operator/pinned-cse \
  --ifc examples/preservation-experiments/external/wall.ifc \
  --source /tmp/bim-source.json \
  --external-scalar-ifc examples/preservation-experiments/external/structural.ifc \
  --global-id '0fqX614OH1YO1Njdxms2$Q' --output-dir physical-results
```

The provider checkout is operator-bound at existing CSE revision
`4b74abda40bba3277de69bf61e9e09283ae2d5b3`. Artifacts cannot select executable
code. The pin checks source/executable/dependency metadata, not OS sandboxing or
supply-chain authenticity of installed libraries.

## Sensor experiment

Two synthetic channels in mm undergo supplied affine calibration x=Gz+b into
metres. Covariance propagates as GΣGᵀ. Gaussian conditioning uses independent
noise, a supplied full prior covariance and the Joseph form for the floating
result. The same update is separately evaluated with exact rational arithmetic;
then a basis change and the laboratory's ordinary preservation gate are applied.
This is a second representation/estimation workload, not a calibrated hardware
experiment. Calibration identity and lack of authentication are explicit.

## 1792 reference workload

`net foundry childhood` reuses the existing NET Session, capability registry,
operation schema validation, graph runner, Worker/Gate separation and production
controller. It snapshots the game-owned source/assets/data, pins the Godot
executable, imports an isolated project and invokes the existing actual keyboard
and physics childhood journey. The recipe captures 13 ordered milestones,
including oral delivery, horse locomotion, practice conflict, tracking, escape
and save/reload. No domain-pose fixtures are used in that journey.

The independent installed gate recomputes 16 predicates rather than trusting
native assertion counts or a game-supplied PASS flag. Save/reload preserves
non-numeric identity/memory fields exactly, with an explicit 1e-12 absolute bound
for numeric serialization drift. A checkpoint rollback is the one declared
exception to increasing clock ticks.

```sh
net foundry childhood --godot /operator/Godot-4.5.1 \
  --game-root /operator/1792 --output-dir childhood-production
```

The read-only player belief projection accepts **received memories only**.
Its two hypotheses and likelihoods are authored gameplay tuning, with conditional
independence explicitly assumed. Report age is retained but not used for decay;
this is not a calibrated temporal hazard estimator. It cannot infer an attacker
identity, receive a future memory or persist extra world authority. It is derived
again after reload, so it adds no new save-state owner. Existing local observation
and interaction gates determine which memories become available.

Human playability, historical authentication and art/geography acceptance remain
separate. The original source-informed courtyard and assets are reused; this
increment does not claim an exact 1792 reconstruction. Foundry source locks retain
the existing historical source manifest and its admitted/deferred distinctions.

The metric accepted integrated playable output / human hours is retained as
**null** until human hours and acceptance are actually measured. Machine runtime
is not substituted for human labor.

## Reproducible coupled qualification

```sh
PYTHONPATH=src python scripts/qualify_shared_preservation.py \
  --cse-root /operator/pinned-cse --godot /operator/Godot-4.5.1 \
  --game-root /operator/1792 --output-dir qualification
```

The script retains positive results, the external full-model refusal and seven
negative cases: missing frame, unit change, source geometry coarsening, identity
alias, missing covariance, singular representation and contradictory metadata.
The laboratory also independently refuses all seven corresponding mapping
faults. Refused/unresolved evidence is retained; it is not overwritten by a
later successful projection. Existing output directories are refused.

The experiment proves these bounded computations and checked predicates. It does
not prove a Universal Adapter, lossless whole-BIM mapping, physical calibration,
historical truth, autonomous production quality or canonical-state admission.
