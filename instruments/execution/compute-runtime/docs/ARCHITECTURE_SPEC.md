# Deterministic State Architecture — Frozen Specification v1.0.0

Status: **FROZEN**. This document is the interface contract for implementation.
Do not redesign it during implementation unless an explicit contradiction is
discovered; if one is found, document it in `docs/CONTRADICTIONS.md` and stop
for review rather than silently deciding.

## 0. Repository state note

At the time this specification was written, the `notationsystems/Scout-Retrieval-Agent`
repository had no commits on any branch (empty history, no default branch).
The `primitive_5.py … primitive_11.py`, `renderer/index.html`, and `tests/`
files described in the design brief were not present to inspect directly.
This spec is therefore written as a **self-contained target**: it specifies
module boundaries and behavior precisely enough to (a) reproduce the
prototype behavior described in the brief — 10 scalar fields, 0 edges,
deterministic IDs, deterministic projections, live updates, Three.js
rendering — and (b) lay the contracts future subsystems compile against.
If the implementer finds the `primitive_N.py` files already exist (e.g.
added in a parallel branch), §22 explains how to fold them into this
structure without changing observable behavior.

---

## 1. Final Architecture Diagram

```
                         ┌───────────────────────┐
                         │   CANONICAL STATE      │  ← single source of truth
                         │   (Version N)          │
                         └───────────┬────────────┘
                                     │ frozen snapshot
                                     ▼
                         ┌───────────────────────┐
                         │  SCHEMA / VALIDATION   │  (frontend)
                         └───────────┬────────────┘
                                     ▼
                         ┌───────────────────────┐
                         │   STATE PROJECTION     │  project_state()
                         │   (pure, deterministic)│
                         └───────────┬────────────┘
                                     ▼
                         ┌───────────────────────┐
                         │      MORPHO IR         │  domain-neutral IR
                         │  (entities, relations, │
                         │   frames, constraints) │
                         └──────┬───────┬─────┬───┘
                    ┌───────────┘       │     └───────────┐
                    ▼                   ▼                 ▼
           ┌─────────────┐     ┌──────────────┐   ┌───────────────┐
           │  3D BACKEND │     │ 2D/SVG BACKEND│   │ GRAPH BACKEND │  ...future:
           │ (Three.js   │     │  (diagrams)   │   │  (analysis)   │  simulation,
           │  descriptor)│     │               │   │               │  robotics, sci-comp
           └──────┬──────┘     └──────┬───────┘   └───────┬───────┘
                  ▼                    ▼                   ▼
          renderer/index.html      SVG output        graph analysis
          (THREE.* objects live      (DOM/file)          reports
           here ONLY)

  ─────────────────────────── feedback loop (never bypasses validation) ───

  Observation ──▶ Neural Preprocessing ──▶ Structured Observation
       ──▶ Estimator ──▶ Belief/Candidate State ──▶ CANDIDATE DELTA
       ──▶ SCHEMA/VALIDATION ──▶ new CANONICAL STATE (Version N+1)

  Simulation / robotics / scientific-computing backends read a frozen
  projection, execute externally, and return observations through the
  SAME feedback loop above — they never write canonical state directly.
```

Invariants I1–I8 (see brief) hold at every arrow above: arrows point strictly
downward/rightward from Canonical State to backends; the only path back into
Canonical State is the labeled feedback loop, which always passes through
Schema/Validation.

---

## 2. Final Module Boundaries

```
core/
  canonical/
    schema.py        # StateSchema, FieldSchema, EdgeSchema, SchemaVersion
    state.py          # CanonicalState, Field, EdgeRecord (immutable)
    validation.py      # validate_candidate(), ValidationError
    version.py          # Version, VersionId, VersionStore
    delta.py             # StateDelta, Change, diff(), candidate deltas
  projection/
    project.py            # project_state(version) -> ProjectedState (pure)

morpho/
  lexer.py                 # tokenizer for Morpho HDL
  parser.py                  # -> Morpho AST
  ast.py                       # AST node types
  ir.py                          # Morpho IR semantic model (§8)
  compiler.py                      # ProjectedState -> Morpho IR (pure)
  identity.py                        # deterministic id derivation (§9)
  provenance.py                        # ProvenanceRecord (§10)

backends/
  threejs/
    compiler.py     # Morpho IR -> ThreeJSSceneDescriptor (declarative JSON)
  diagram/
    compiler.py       # Morpho IR -> SVGDocument (declarative)
  graph/
    analysis.py         # Morpho IR -> graph analysis reports (future, stub ok)
  simulation/
    interface.py          # DynamicsSpec/Action protocols only (§16, stub)
  neural/
    interface.py            # Estimator/Observation protocols only (§17, stub)

runtime/
  feedback_loop.py           # wires candidate deltas through validation (future)

renderer/
  index.html                   # consumes ThreeJSSceneDescriptor; THREE.* lives
                                 # here exclusively; never imports core/ or morpho/

tests/
  test_canonical.py
  test_projection.py
  test_morpho_compiler.py
  test_backends_threejs.py
  test_backends_diagram.py
  test_versioning.py
  test_delta.py
  test_replay.py
```

Rules:
- `core/canonical/` is the only place allowed to construct or mutate a
  `CanonicalState`/`Version`. Every other module receives read-only,
  already-frozen objects.
- `morpho/` never imports from `backends/*` or `renderer/`.
- `backends/*` never import from each other. Each backend depends only on
  `morpho/ir.py` types and its own config type.
- If `primitive_5.py … primitive_11.py` already exist in the repo, keep them
  as thin entrypoints that import and call into the modules above (see §22).
  Do not delete public entrypoints without updating every caller.

---

## 3. Canonical State Specification

```python
FieldType = Literal["scalar", "string", "bool", "vector3", "quaternion"]
# v1 prototype only uses "scalar"; other types are declared here because
# §7/§12 (Morpho, spatial semantics) need them to exist in the type system
# now, even though no field uses them yet.

@dataclass(frozen=True)
class Field:
    id: str            # == field_name; stable identity (I5)
    type: FieldType
    value: JSONScalar   # matches `type`
    unit: str | None = None

@dataclass(frozen=True)
class EdgeRecord:
    id: str
    from_: str          # Field.id or Entity id
    to: str
    type: str            # relationship type tag, e.g. "depends_on"
    attributes: Mapping[str, JSONScalar] = field(default_factory=dict)

@dataclass(frozen=True)
class CanonicalState:
    schema_version: str
    fields: Mapping[str, Field]   # key MUST equal Field.id (I5)
    edges: tuple[EdgeRecord, ...] = ()  # explicit only (I4); empty in v1
```

Invariants enforced by construction (not by convention):
- `CanonicalState` and `Field` are immutable (`frozen=True` or equivalent
  read-only wrapper). Any "update" produces a new `CanonicalState`, never
  mutates in place.
- `fields[key].id == key` for every entry — checked in `validation.py`,
  never silently corrected.
- `edges` contains only entries that were explicitly asserted through the
  validation pipeline (§6). No component may append to `edges` outside
  that pipeline.
- Canonical state contains **no** renderer objects, camera/viewport state,
  layout coordinates, or anything from §7 "Extrinsic Visual State" (see §12).

---

## 4. Version Specification

```python
VersionId = str  # sha256 hex digest, 64 chars

@dataclass(frozen=True)
class ProvenanceInfo:
    author: str                 # "user", "system", "estimator:<name>", etc.
    transaction_id: str          # uuid4, unique per accepted update
    source: str                   # "manual_edit" | "simulation" | "estimator" | "genesis"

@dataclass(frozen=True)
class Version:
    id: VersionId
    parent: VersionId | None       # None only for the genesis version
    state: CanonicalState
    schema_version: str
    provenance: ProvenanceInfo
    timestamp: str                   # ISO-8601 UTC, e.g. "2026-08-22T00:00:00Z"
```

**Version ID algorithm (must be exact, not "a hash"):**

1. Serialize `(schema_version, fields, edges)` — **excluding** `id`,
   `parent`, `provenance`, and `timestamp` — to canonical JSON:
   - `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`
   - Numbers: integers stay integers; floats are formatted via Python
     `repr()`-equivalent round-trip formatting (no trailing zeros
     inconsistency). Booleans as JSON `true`/`false`.
2. `id = sha256(canonical_json.encode("utf-8")).hexdigest()`.

This makes `Version.id` **content-addressed**: two versions with identical
`(schema_version, fields, edges)` always produce the same id regardless of
when or by whom they were created. Timestamp and provenance are metadata,
not part of identity — this is required for I6 (same canonical version +
compiler version + config ⇒ same projection) and for replay determinism
(§19).

`VersionStore` (in-memory for v1, trivially swappable for a persistent
backend later):

```python
class VersionStore(Protocol):
    def put(self, version: Version) -> None: ...
    def get(self, version_id: VersionId) -> Version: ...
    def parent_chain(self, version_id: VersionId) -> list[Version]: ...
    def head(self) -> Version: ...   # most recently accepted version
```

The genesis version (`parent=None`) is created once at system bootstrap
from the schema's declared defaults; it is the only version ever
constructed outside the validation pipeline.

---

## 5. StateDelta Specification

```python
Operation = Literal["add", "remove", "replace"]  # "move", "rename" reserved,
                                                    # not implemented in v1

@dataclass(frozen=True)
class Change:
    path: str                 # e.g. "fields.mass.value", "edges[3].type"
    operation: Operation
    old_value: JSONScalar | None   # None for "add"
    new_value: JSONScalar | None   # None for "remove"
    provenance: ProvenanceInfo

@dataclass(frozen=True)
class StateDelta:
    version_from: VersionId | None   # None if version_to is genesis
    version_to: VersionId
    transaction_id: str
    timestamp: str
    changes: tuple[Change, ...]
```

**Path syntax** (must match exactly, this is what backends and tests key
off of):
- Dot-separated segments for map keys: `fields.mass.value`
- Bracket integer index for sequence elements: `edges[3].type`
- No wildcards, no globs, no relative paths. Every path is absolute from
  the root of `CanonicalState`.

`diff(old: CanonicalState, new: CanonicalState) -> tuple[Change, ...]` is a
pure structural diff: it walks both trees, emits one `Change` per leaf
value that differs, with `operation="add"` for keys present only in `new`,
`"remove"` for keys present only in `old`, `"replace"` otherwise. It does
**not** attempt to detect renames or moves in v1 (those operations are
declared in the enum for forward compatibility only — emitting them is out
of scope now, see §23).

A **CandidateDelta** is the pre-acceptance form used by the future
estimator/simulation feedback loop (§16, §17): identical shape to
`StateDelta` but with `version_to` unset (not yet minted, because minting
happens only after validation accepts it) and an optional `confidence:
float | None` on each `Change`. Validation consumes a `CandidateDelta` and
either mints a real `StateDelta` + new `Version`, or rejects it and
produces `ValidationError`s (§6) — never a partial application.

---

## 6. Schema / Validation Contract

```python
@dataclass(frozen=True)
class FieldConstraints:
    min: float | None = None
    max: float | None = None
    enum: tuple[JSONScalar, ...] | None = None
    pattern: str | None = None   # regex, only for type="string"

@dataclass(frozen=True)
class FieldSchema:
    id: str
    type: FieldType
    unit: str | None = None
    constraints: FieldConstraints = FieldConstraints()
    required: bool = True

@dataclass(frozen=True)
class EdgeSchema:
    type: str
    from_type: str | None = None   # optional constraint on endpoint kind
    to_type: str | None = None

@dataclass(frozen=True)
class StateSchema:
    schema_version: str
    fields: Mapping[str, FieldSchema]
    edges: tuple[EdgeSchema, ...] = ()   # allowed edge *types*; empty ⇒ no
                                            # edges may ever be asserted
                                            # under this schema version
```

**Validation pipeline** (exact stage order, no stage may be skipped):

```
candidate (CandidateDelta or full CanonicalState draft)
      │
      ▼
  1. SCHEMA VALIDATION
     - every touched field id exists in StateSchema.fields
     - value's runtime type matches FieldSchema.type
     - required fields are never removed
     - edge types (if any) exist in StateSchema.edges
      │  fail → reject, return ValidationError[]
      ▼
  2. CONSTRAINT VALIDATION
     - min/max/enum/pattern checks per FieldConstraints
     - relationship-level checks (v1: none defined; extension point)
      │  fail → reject, return ValidationError[]
      ▼
  3. ACCEPT
     - apply changes to produce new CanonicalState
     - mint new Version (parent = current head)
     - append StateDelta to the version's transaction log
     - VersionStore.put(new_version)
```

```python
@dataclass(frozen=True)
class ValidationError:
    path: str
    code: str          # e.g. "TYPE_MISMATCH", "OUT_OF_RANGE", "UNKNOWN_FIELD"
    message: str

def validate_candidate(
    schema: StateSchema, base: CanonicalState, candidate: CandidateDelta
) -> Version | list[ValidationError]:
    ...
```

Rejection never partially applies changes and never creates a `Version`.
This is the **only** legal entry point into producing a new canonical
version — simulation outputs, neural outputs, and manual edits all funnel
through this same function (this is what makes acceptance tests 17/18
provable).

---

## 7. Morpho HDL Grammar

File extension: `.morpho`. Encoding: UTF-8. One document = one compiled
projection of one frozen canonical version.

### 7.A Lexical structure

```
IDENT       := [A-Za-z_][A-Za-z0-9_]*
STRING      := '"' ( [^"\\] | '\\' . )* '"'
NUMBER      := '-'? DIGIT+ ('.' DIGIT+)? (('e'|'E') ('+'|'-')? DIGIT+)?
BOOL        := 'true' | 'false'
COMMENT     := '//' .* NEWLINE | '/*' .*? '*/'
WHITESPACE  := (' ' | '\t' | NEWLINE)+   (insignificant)
```

Keywords (reserved, case-sensitive): `morpho`, `entity`, `relation`,
`derived`, `inferred`, `frame`, `transform`, `group`, `constraint`,
`provenance`, `version`, `from`, `to`, `type`, `confidence`, `parent`,
`position`, `orientation`, `scale`, `members`, `on`, `rule`.

### 7.B Grammar (EBNF)

```ebnf
document      = header , { declaration } ;
header        = "morpho" , STRING , ";" ;   (* morpho grammar/spec version *)

declaration   = entity_decl
              | relation_decl
              | frame_decl
              | group_decl
              | constraint_decl ;

entity_decl   = "entity" , IDENT , "{" , { attr_stmt } , "}" ;

attr_stmt     = IDENT , ":" , value , ";" ;

value         = STRING | NUMBER | BOOL | vector3 | ref | provenance_block ;

vector3       = "[" , NUMBER , "," , NUMBER , "," , NUMBER , "]" ;

ref           = STRING ;   (* references another entity's id *)

relation_decl = [ "derived" | "inferred" ] , "relation" , IDENT , "{" ,
                  "from" , ":" , ref , ";" ,
                  "to" , ":" , ref , ";" ,
                  "type" , ":" , IDENT , ";" ,
                  [ "confidence" , ":" , NUMBER , ";" ] ,
                  [ provenance_block ] ,
                "}" ;

frame_decl    = "frame" , IDENT , "{" ,
                  [ "parent" , ":" , ref , ";" ] ,
                  "position" , ":" , vector3 , ";" ,
                  [ "orientation" , ":" , quaternion , ";" ] ,
                  [ "scale" , ":" , vector3 , ";" ] ,
                "}" ;

quaternion    = "[" , NUMBER , "," , NUMBER , "," , NUMBER , "," , NUMBER , "]" ;
                (* order: x, y, z, w *)

group_decl    = "group" , IDENT , "{" ,
                  "members" , ":" , "[" , ref , { "," , ref } , "]" , ";" ,
                "}" ;

constraint_decl = "constraint" , IDENT , "{" ,
                     "on" , ":" , ref , ";" ,
                     "rule" , ":" , STRING , ";" ,
                     (* rule is an opaque predicate expression string in v1;
                        no expression language is specified yet — see §23 *)
                   "}" ;

provenance_block = "provenance" , "{" ,
                      "source" , ":" , STRING , ";" ,
                      "origin_version" , ":" , STRING , ";" ,
                      [ "confidence" , ":" , NUMBER , ";" ] ,
                    "}" ;
```

### 7.C Minimal example (canonical projection of the v1 prototype)

```morpho
morpho "1.0.0";

entity mass {
    id: "mass";
    type: "scalar";
    value: 10;
    unit: "kg";
    provenance {
        source: "canonical";
        origin_version: "5f2a...c91";
    }
}
```

### 7.D Explicit vs. inferred relation example

```morpho
relation A_depends_on_B {
    from: "A";
    to: "B";
    type: "depends_on";
    provenance {
        source: "canonical";
        origin_version: "5f2a...c91";
    }
}

inferred relation A_near_B {
    from: "A";
    to: "B";
    type: "spatial_adjacency";
    confidence: 0.82;
    provenance {
        source: "graph_backend:adjacency_heuristic_v1";
        origin_version: "5f2a...c91";
    }
}
```

Morpho documents **must not** contain: Three.js objects, WebGL handles,
materials, cameras, DOM references, or arbitrary UI state (per brief §4).
There is no grammar production for any of these — this is enforced by the
grammar itself, not by convention.

---

## 8. Morpho Semantic Model

Constructs defined for v1 (deliberately minimal — brief §5 says "do not add
concepts unnecessarily"): **Entity, Attribute, Relation, Frame, Transform,
Group, Constraint, ProvenanceRecord, VersionReference**.

Deferred (not implemented, no grammar production, may be added later
without breaking this grammar): `DerivedNode`, `Collection`. `Group`
already covers the v1 need for naming a set of entities; `DerivedNode`
requires a compute-graph model that has no consumer yet.

| Construct | Identity | Inputs | Outputs | Invariants | Mutability | Provenance | Canonical or derived |
|---|---|---|---|---|---|---|---|
| Entity | `id: str`, stable (§9) | one canonical `Field` | attributes | `id` unique in document | immutable after compile | required | canonical (1:1 with a `Field`) |
| Attribute | scoped to owning Entity, key = attr name | a `Field.value`/`unit`/`type` | typed value | type must match schema `FieldType` | immutable | inherited from Entity | canonical |
| Relation | `id: str` (declaration name) | two entity refs (`from`,`to`) + `type` | typed edge | if not `derived`/`inferred`, MUST correspond to a canonical `EdgeRecord` | immutable | **required** | canonical if unmarked; derived if `derived`/`inferred` |
| Frame | `id: str` | optional parent frame ref, `Transform` | resolved world transform (computed by consumer, not stored) | acyclic parent chain | immutable | required if derived from anything other than a canonical spatial field | canonical if built from an intrinsic spatial `Field` (§12); else derived |
| Transform | not separately identified; owned by a Frame | position/orientation/scale | — | orientation is a unit quaternion | immutable | inherits owner's | same as owner |
| Group | `id: str` | list of entity/frame refs | named collection | members must exist in document | immutable | optional | derived (organizational, not itself a canonical fact) |
| Constraint | `id: str` | target ref (`on`) + `rule` string | pass/fail predicate (evaluated by consumer) | v1: `rule` is opaque, not evaluated by the compiler | immutable | optional | derived (a validation-time concept surfaced into IR for visibility, not a canonical fact) |
| ProvenanceRecord | not separately identified; attached to the above | source, origin_version, transaction context | — | every derived construct MUST carry one | immutable | n/a (it *is* the provenance) | n/a |
| VersionReference | the `origin_version` string in a ProvenanceRecord | a `VersionId` | — | must resolve to a real `Version` in the `VersionStore` at compile time | immutable | n/a | n/a |

---

## 9. Morpho Identity Model

v1 rule (brief I5, exact chain preserved, no transformation applied):

```
field_name == node_id == cell_id == visual_id == geometry_id
```

That is, for the current flat prototype, `Entity.id` **is** the
`Field.id`, and every downstream identifier used by any backend is the
*same string*, unmodified. There is no hashing, namespacing, or UUID
generation for identity in v1. This is a deliberate constraint, not a
placeholder — do not "improve" it during implementation.

```python
def geometry_id(entity_id: str) -> str: return entity_id
def visual_id(entity_id: str) -> str: return entity_id
def cell_id(entity_id: str) -> str: return entity_id
def node_id(entity_id: str) -> str: return entity_id
```

These four identity functions exist as named, separately-callable
functions (not inlined as `entity.id` everywhere) **specifically** so that
a future schema version can change one of them to a real derivation (e.g.
`geometry_id(entity_id) -> f"geom::{entity_id}"`) without touching call
sites. When that day comes, the change is scoped entirely to
`morpho/identity.py` and must be accompanied by a `schema_version` bump —
see §18 on why identity changes are a schema-version event.

**Explicit non-goal:** do not introduce UUIDs "for convenience" anywhere
in this pipeline. If a future construct needs an identity independent of
`field_name` (e.g. two entities legitimately sharing a name in different
namespaces), that is a schema evolution event requiring a new
`schema_version` and an explicit `MigrationMap` (old_id → new_id) recorded
in that version's provenance — not an ad hoc UUID.

---

## 10. Morpho Provenance Model

```python
@dataclass(frozen=True)
class ProvenanceRecord:
    source: str              # "canonical" | "<backend_name>:<method>" |
                                # "observation" | "simulation" | "neural:<model>"
    origin_version: VersionId  # the frozen canonical version compiled from
    compiler_version: str        # semver of the Morpho compiler that emitted this
    transaction_id: str | None    # set when traceable to a specific accepted delta
    confidence: float | None = None   # only meaningful when source != "canonical"
    timestamp: str = ...                # ISO-8601 UTC, compile time
```

Rules:
- Every canonical-sourced Entity/Attribute/Relation carries
  `source="canonical"`, `confidence=None` (canonical facts are not
  probabilistic), and `origin_version` = the exact `Version.id` frozen for
  that compilation.
- Every derived/inferred construct (marked `derived`/`inferred` in the
  grammar, or produced by a backend's own heuristics, e.g. spatial
  adjacency) **must** carry a `ProvenanceRecord` with `source` naming the
  producing subsystem and method (e.g.
  `"graph_backend:adjacency_heuristic_v1"`), so provenance is
  attributable and re-runnable.
- `compiler_version` is always present — this is what makes I6 checkable:
  given the same `(origin_version, compiler_version, config)` you must
  get byte-identical output (§13, §19).

---

## 11. Graph Semantics

Canonical edges (`CanonicalState.edges`) are the **only** edges that may
ever be asserted without a `derived`/`inferred` marker. v1 ships with zero
edges but the type exists and is validated (§3, §6).

Type-system enforcement (this is a hard compiler rule, not a lint):

```python
InferenceStatus = Literal["explicit", "inferred"]

@dataclass(frozen=True)
class MorphoRelation:
    id: str
    from_id: str
    to_id: str
    type: str
    is_canonical: bool           # True only if backed by a CanonicalState.EdgeRecord
    inference_status: InferenceStatus
    provenance: ProvenanceRecord
    confidence: float | None = None
```

Two independent axes:
- `is_canonical`: was this relation asserted in `CanonicalState.edges`?
  Only the Morpho compiler (never a backend) may set this `True`, and only
  when a matching `EdgeRecord` exists in the frozen version being
  compiled.
- `inference_status`: was this relation *computed* (`"inferred"`, e.g.
  spatial-adjacency, layout proximity, semantic similarity) or *asserted*
  (`"explicit"`, e.g. hand-authored in a diagram tool, or canonical)?

A relation can be `is_canonical=False, inference_status="explicit"` (a
downstream tool explicitly drew a connector that isn't a canonical fact —
legal, but never eligible to silently become canonical). It can never be
`is_canonical=True, inference_status="inferred"` — inference never
produces canonical truth (I3, I4).

**Enforcement of "never silently becomes canonical":** there is no
function anywhere in `backends/*`, `morpho/*`, or `runtime/*` whose return
type is `CanonicalState`, `Version`, or `EdgeRecord`. The only function
that can mint an `EdgeRecord` is `validate_candidate` in
`core/canonical/validation.py` (§6), and it only does so from a
`CandidateDelta` that a human or an upstream system explicitly submitted —
never from a Morpho `MorphoRelation`. This is a one-way data-flow
guarantee enforced by module boundaries (§2), not by a runtime check.

---

## 12. Spatial Semantics

Two disjoint categories:

**Intrinsic spatial state** — may live in `CanonicalState` as a `Field`
with `type="vector3"` or `type="quaternion"`, or as a Morpho `frame_decl`
compiled from such a field. Examples from the brief: molecular
coordinates, robot joint angles, object dimensions, coordinate-frame
relationships, physical attachment. These are facts about the modeled
world and are versioned like any other field.

**Extrinsic visual state** — camera, viewport, visual layout offset,
rendering transform. These **never** appear in `CanonicalState` or in a
Morpho document. They live entirely in backend-specific config passed
alongside the IR at compile time (e.g. `ThreeJSRenderConfig`,
`DiagramLayoutConfig` — see §14/§15). They are recomputable and are never
persisted as part of a `Version` (§18).

Renderer-independent spatial value types (used by both categories, but
only intrinsic ones are ever canonical):

```python
@dataclass(frozen=True)
class Vec3: x: float; y: float; z: float

@dataclass(frozen=True)
class Quaternion: x: float; y: float; z: float; w: float

@dataclass(frozen=True)
class Transform:
    position: Vec3
    orientation: Quaternion = Quaternion(0, 0, 0, 1)
    scale: Vec3 = Vec3(1, 1, 1)

@dataclass(frozen=True)
class CoordinateFrame:
    id: str
    parent: str | None    # ref to another CoordinateFrame.id, or None = world root
    transform: Transform
```

`CoordinateFrame.parent` chains must be acyclic — checked at Morpho
compile time (`compiler.py`), not deferred to a backend. Morpho stops at
`CoordinateFrame`/`Transform`; it never becomes a scene graph with
render-order, visibility flags, or LOD — those are Three.js-backend-only
concerns layered on top at §14.

---

## 13. Projection Contracts

```python
@dataclass(frozen=True)
class ProjectedState:
    source_version: VersionId
    schema_version: str
    fields: Mapping[str, Field]     # defensive copy, same values as source
    edges: tuple[EdgeRecord, ...]

def project_state(version: Version) -> ProjectedState:
    """Pure. No I/O, no randomness, no wall-clock reads.
    Precondition: `version` is an already-frozen, immutable object.
    Postcondition: output shares no mutable references with `version.state`;
    mutating the output (impossible, since it's frozen) can never affect
    `version` or the VersionStore.
    Same `version` in ⇒ byte-identical `ProjectedState` out, always (I6, I7).
    """
```

```python
@dataclass(frozen=True)
class CompilerConfig:
    compiler_version: str    # semver of morpho/compiler.py
    options: Mapping[str, JSONScalar] = field(default_factory=dict)

def compile_morpho(
    projected: ProjectedState, config: CompilerConfig
) -> MorphoDocument:
    """Pure. Same (projected, config) in ⇒ byte-identical MorphoDocument out.
    Never reads VersionStore for anything other than resolving
    `origin_version` references it already has as input data.
    """
```

Both functions are **total** over well-formed input (they do not raise for
any input that already passed schema validation) and **referentially
transparent** — this is what acceptance tests 2, 3, and 14 check directly.

---

## 14. Three.js Backend Contract

```python
@dataclass(frozen=True)
class ThreeJSRenderConfig:
    # extrinsic, non-canonical: camera/viewport defaults, not from Morpho
    camera: Mapping[str, JSONScalar]
    viewport: Mapping[str, JSONScalar]

@dataclass(frozen=True)
class ThreeJSSceneDescriptor:
    geometries: tuple[dict, ...]   # {"id": geometry_id, "kind": ..., "params": ...}
    materials: tuple[dict, ...]
    meshes: tuple[dict, ...]        # {"id": visual_id, "geometry": geometry_id, ...}
    hierarchy: tuple[dict, ...]      # parent/child mesh id pairs, from CoordinateFrame

def compile_threejs(
    ir: MorphoDocument, config: ThreeJSRenderConfig
) -> ThreeJSSceneDescriptor:
    """Pure, declarative. Returns plain JSON-serializable data — never a
    THREE.Object3D, THREE.Mesh, THREE.Material, or WebGL handle."""
```

`renderer/index.html` is the **only** place in the system that constructs
real `THREE.*` objects. It receives a `ThreeJSSceneDescriptor` (as JSON),
instantiates geometries/materials/meshes client-side, and is a pure
consumer: it has no code path, event handler, or callback that writes back
into `CanonicalState`, `Version`, or `ProjectedState` (I3, I8). `geometry_id`
and `visual_id` in the descriptor are the identity-model strings from §9,
so geometry identity survives value changes (acceptance test 8) — the id
never changes when only a `Field.value` changes, only when the field's
`id` itself changes (which, per I5, doesn't happen in v1).

---

## 15. Diagram / SVG Backend Contract

```python
@dataclass(frozen=True)
class DiagramLayoutConfig:
    layout_algorithm: str   # e.g. "grid_v1" — must be deterministic
    spacing: float
    canvas: Mapping[str, JSONScalar]   # extrinsic, non-canonical

def compile_svg(ir: MorphoDocument, config: DiagramLayoutConfig) -> str:
    """Pure. Returns a complete SVG document string.
    `layout_algorithm` MUST be a deterministic pure function of
    (ir, config) — no randomized layout, no simulated annealing with an
    unseeded RNG. If a stochastic layout algorithm is ever added, it must
    take an explicit seed that becomes part of `config` (and therefore
    part of what determinism is checked against)."""
```

Same declarative-output discipline as §14: the SVG string is the backend's
entire output contract. No DOM references, no live bindings back to
canonical state.

---

## 16. Future Simulation Backend Contract (interfaces only — no implementation)

```python
class DynamicsSpec(Protocol):
    """Describes how a system evolves; itself sourced from canonical state
    or a schema-declared config, never authored ad hoc by a backend."""
    def describe(self) -> Mapping[str, JSONScalar]: ...

@dataclass(frozen=True)
class Action:
    id: str
    payload: Mapping[str, JSONScalar]

@dataclass(frozen=True)
class CandidateNextState:
    """Output of a simulation step. NOT a CanonicalState — must pass
    through the same validation pipeline as any other candidate (§6)."""
    based_on_version: VersionId
    proposed_changes: tuple[Change, ...]
    provenance: ProvenanceInfo
```

Flow (brief §11): `State + DynamicsSpec + Action → CandidateNextState →
validate_candidate() → new Version | ValidationError[]`. Simulation
engines (Python, CUDA, LAMMPS, robotics simulators, physics engines) are
**execution targets** that consume a `ProjectedState`/`MorphoDocument` and
produce a `CandidateNextState`; they are never given write access to
`VersionStore`. **Do not implement a simulation engine now** — this
section exists so the eventual implementation has a fixed seam to build
against (§23).

---

## 17. Future Neural / Estimation Contract (interfaces only — no implementation)

```python
@dataclass(frozen=True)
class Observation:
    raw: Any
    source: str
    timestamp: str

@dataclass(frozen=True)
class StructuredObservation:
    fields: Mapping[str, JSONScalar]
    provenance: ProvenanceInfo

class Estimator(Protocol):
    """Consumes structured observations + optionally current canonical
    state; produces a belief/candidate — never a Version directly."""
    def estimate(
        self, obs: StructuredObservation, current: ProjectedState
    ) -> "BeliefState": ...

@dataclass(frozen=True)
class BeliefState:
    candidate: CandidateNextState   # same shape as §16; validated identically
    confidence: float
```

Flow (brief §12): `Observation → neural preprocessing →
StructuredObservation → Estimator → BeliefState → validate_candidate() →
Version | ValidationError[]`. Neural systems may consume canonical state
(read-only, via `ProjectedState`) and may produce predictions, candidates,
inferred relationships (as Morpho `inferred relation` — §7.D), or
observations — but the **only** function capable of minting a new
`Version` from any of this is the one shared `validate_candidate` in §6.
**Do not implement Kalman filtering, Bayesian inference, or a neural
estimator now** (§23) — implement only these protocol shapes so §16/§17
compose with §6 without rework later.

---

## 18. Persistence / Snapshot Contract

**Persistent Computational State** (must survive process restart, is the
authoritative record):
- Every `Version` (id, parent, state, schema_version, provenance,
  timestamp) — serialized via the same canonical-JSON algorithm as §4,
  keyed by `VersionId` in `VersionStore`.
- Nothing else is required to persist correctness; everything downstream
  is recomputable from a `Version` plus the pinned `compiler_version` in
  its provenance chain.

**Recomputable Runtime State** (never persisted as source of truth; may be
cached, but cache is disposable):
- `ProjectedState`, `MorphoDocument` — deterministic pure functions of a
  `Version` + config (§13), safe to cache keyed by
  `(version_id, compiler_version, config_hash)`, safe to evict/recompute
  at any time.
- `ThreeJSSceneDescriptor`, SVG output, graph analysis reports — same
  reasoning, one level further downstream.
- THREE.js objects, WebGL handles, meshes, camera objects, DOM state,
  transient layout/viewport state — **never** persisted, never cached
  beyond the browser session; these belong exclusively to
  `renderer/index.html`'s in-memory runtime (I8).

A schema-version bump (§9's identity-change scenario, or any change to
`FieldSchema`/`EdgeSchema`) is the one event that invalidates the "same
version_id ⇒ same everything downstream" guarantee across compiler
upgrades — which is exactly why `compiler_version` and `schema_version`
are both recorded per-`Version` rather than assumed global.

---

## 19. Deterministic Replay Contract

```python
def restore_projection(store: VersionStore, version_id: VersionId,
                        config: CompilerConfig) -> ProjectedState:
    version = store.get(version_id)
    return project_state(version)

# Contract (acceptance test 14):
# restore_projection(store, v.id, config) == project_state(v)
# for the SAME v.id, regardless of how much time has passed or how many
# other versions have been created since, PROVIDED `config.compiler_version`
# matches what was pinned at compile time. A compiler upgrade is expected
# to change output — that is not a replay-determinism violation, it is a
# new compiler_version producing (correctly) different output for an old
# input; replay determinism is scoped to "same version + same compiler".
```

Because `VersionId` is content-addressed (§4) and `project_state`/
`compile_morpho` are pure (§13), replay determinism follows structurally
from those two properties — it does not need separate machinery. The test
in §21 exists to catch a *regression* of those properties (e.g. someone
introducing dict-ordering nondeterminism or a wall-clock read into a
"pure" function), not to implement anything new.

---

## 20. Failure-Mode Analysis

| Failure mode | Where it would sneak in | Prevention |
|---|---|---|
| Non-deterministic dict/set ordering leaking into hashes or IR | canonical JSON serialization, Morpho compiler iterating `fields` | canonical serialization always sorts keys (§4); Morpho compiler iterates fields in a fixed, explicit order (e.g. sorted by id), never raw dict iteration order without sorting |
| Floating-point formatting drift between platforms | Version ID hashing, Morpho `NUMBER` emission | fixed formatting rule specified in §4; same rule reused wherever a float is serialized |
| Timestamp/wall-clock leaking into content identity | `Version.id`, cache keys | `Version.id` hash explicitly excludes `timestamp` and `provenance` (§4) |
| Shared mutable references letting a downstream consumer mutate upstream state | `project_state`, backend compilers returning references into `CanonicalState` | all dataclasses `frozen=True`; `ProjectedState`/`MorphoDocument`/descriptors hold copies or immutable structures only |
| Renderer or backend silently promoting an inferred/derived construct into canonical state | a well-meaning "convenience" write-back API in `renderer/index.html` or `backends/*` | no function outside `core/canonical/validation.py` returns `CanonicalState`/`Version`/`EdgeRecord` (§11); enforced by module boundary, verified by test (acceptance 5, 6, 7) |
| Id collisions when future stable-id schemes are introduced | `morpho/identity.py` after a schema bump | identity changes are gated behind a `schema_version` bump + explicit `MigrationMap` (§9), never introduced silently |
| Simulation/neural output bypassing validation "just this once" for latency | `runtime/feedback_loop.py` | the loop has exactly one exit into canonical state — `validate_candidate` — no alternate fast path exists in the interface (§16, §17) |
| Schema drift without a version bump (field type or constraint changes silently) | `core/canonical/schema.py` edits | any change to `StateSchema` requires a `schema_version` string bump; validation rejects a candidate whose declared `schema_version` doesn't match the active schema |
| Partial application on validation failure | `validate_candidate` | function returns either a fully-applied new `Version` or a list of `ValidationError`s — no third, partial-write outcome exists in the return type |
| Concurrent candidate updates racing on the same parent version | `VersionStore.put` under concurrent callers | **out of scope for v1** (single-writer prototype); flagged here so a future multi-writer design knows to add optimistic-concurrency (parent-version check-and-set) rather than silently allowing lost updates |

---

## 21. Test Plan

Each brief acceptance test maps to a concrete test, grouped by module.
"Given" fixtures reuse the same genesis `Version` unless noted.

**`tests/test_projection.py`**
1. *All canonical fields survive projection* — `project_state(v).fields ==
   v.state.fields` for all 10 fields, value-for-value.
2. *Canonical state remains unchanged by projection* — `id(v.state)`
   before/after `project_state(v)` is unchanged, and
   `v.state == deepcopy_taken_before_call` (mutation-detection via a
   pre-call deep copy compared post-call).
3. *Same canonical version produces identical Morpho IR* —
   `compile_morpho(project_state(v), cfg) == compile_morpho(project_state(v), cfg)`
   called twice, asserted structurally equal (and byte-equal after
   canonical serialization).

**`morpho/test_identity.py`**
4. *Identity remains stable* — for every field, `geometry_id(f.id) ==
   visual_id(f.id) == cell_id(f.id) == node_id(f.id) == f.id`, and this
   holds across two versions where only `value` changed.

**`core/canonical/test_validation.py`**
5. *No inferred edges enter canonical state* — construct a
   `MorphoRelation` with `inference_status="inferred"`; assert there is no
   code path from it to `EdgeRecord`/`CanonicalState` (static: no such
   function exists; dynamic: attempting to feed it to
   `validate_candidate` type-checks fail / raises).
6. *Inferred edges, when introduced, are marked derived/inferred* — parse
   a `.morpho` document containing an `inferred relation`; assert the
   resulting `MorphoRelation.inference_status == "inferred"` and
   `is_canonical == False`.

**`renderer/` manual + `tests/test_backends_threejs.py`**
7. *Renderer cannot mutate canonical state* — static check: grep/AST-scan
   `renderer/index.html`'s JS for any import/reference to canonical-state
   mutation endpoints (there are none exposed); plus a descriptor-level
   test that `compile_threejs` output contains no callback/handle capable
   of writing back.
8. *Geometry identity survives value changes* — compile scene descriptor
   for version N and N+1 (only a field value changed); assert
   `geometries[i].id` and `meshes[i].id` are unchanged between the two
   descriptors for that entity.
9. *Deleted entities remove downstream artifacts* — remove a field via a
   validated delta (once removal is supported by a schema with
   `required=False`); assert the next `compile_threejs`/`compile_svg`
   output no longer references that entity's `geometry_id`/`visual_id`.

**`core/canonical/test_delta.py`**
10. *Nested state changes produce path-level deltas* — change
    `fields.mass.value` only; assert `diff()` returns exactly one `Change`
    with `path == "fields.mass.value"`, not a whole-field or whole-state
    replace.

**`core/canonical/test_versioning.py`**
11. *Every accepted state update produces a new version* — call
    `validate_candidate` with a valid candidate; assert `VersionStore`
    gained exactly one new entry with a new `VersionId`.
12. *Versions have parent relationships* — assert `new_version.parent ==
    old_version.id`.
13. *Previous versions remain recoverable* — after several accepted
    updates, assert `VersionStore.get(v1.id) == v1` unchanged.

**`tests/test_replay.py`**
14. *Projection from a restored version equals projection from the
    original version* — `restore_projection(store, v.id, cfg) ==
    project_state(v)` (§19).

**`morpho/test_grammar.py`**
15. *Morpho contains no renderer-specific objects* — parse every `.morpho`
    fixture; assert the AST/IR type set is exactly the §8 construct list
    (no `THREE`, `WebGL`, `camera`, `material` node types exist in the
    grammar at all — this is a grammar-level guarantee, testable by
    asserting the parser has no production containing those keywords).

**`tests/test_backends_threejs.py`**
16. *Three.js is a backend, not a source of truth* — assert
    `backends/threejs/compiler.py` has zero imports from
    `core/canonical/*` other than the frozen types it reads (no
    `VersionStore.put`, no validation calls).

**`runtime/test_feedback_loop.py`** (interface-level tests against the
stubs in §16/§17; no real simulator/estimator required)
17. *Simulation outputs cannot bypass validation* — feed a
    `CandidateNextState` from a mock simulator through the feedback loop;
    assert the only way it becomes a `Version` is via
    `validate_candidate`, and a candidate violating a constraint is
    rejected with `ValidationError`, not silently accepted.
18. *Neural outputs cannot bypass validation* — same test shape as 17,
    with a mock `Estimator`/`BeliefState`.

---

## 22. Migration Plan from the Current Prototype

Applies once the actual `primitive_5.py … primitive_11.py`,
`renderer/index.html`, and `tests/` are available in this branch (per §0,
they were not present when this spec was written).

1. **Do not touch behavior first.** Before any refactor, run the existing
   test suite and record it passing. This is the regression baseline for
   every step below.
2. **Rename, don't rewrite, the primitive-5 role.** Per brief §2:
   `primitive_5.py`'s function currently named/described as "State
   Estimation" is renamed to reflect **State Projection**
   (`project_state`), matching §13 exactly. Its behavior (identity/pass-
   through transform) does not change — only its name, docstring, and any
   exported symbol name. A true estimator (§17) is net-new code, added
   later, never by repurposing this function.
3. **Introduce `Version`/`VersionStore` as a wrapper, not a rewrite.**
   Treat the current live in-memory state as the `state` of a single
   genesis `Version`. Every subsequent live update becomes a call to
   `validate_candidate` (§6) that mints a new `Version`, preserving the
   existing "live state updates" UX from outside (brief §14) while
   satisfying I6/I7 underneath.
4. **Extract the Morpho compiler as its own module.** Whatever
   `primitive_7.py`–`primitive_9.py` currently do to go from state to
   Three.js input, split it at the IR boundary: canonical-state-to-Morpho-
   IR becomes `morpho/compiler.py` (§7/§8), Morpho-IR-to-scene-descriptor
   becomes `backends/threejs/compiler.py` (§14). `renderer/index.html`'s
   actual rendered output must be pixel-for-pixel unchanged after this
   split — it only changes where the descriptor comes from.
5. **Formalize the implicit schema.** Write a `StateSchema` (§6) that
   exactly describes the current 10 fields (types, and any constraints
   already implicitly enforced by existing validation code, if any).
   `schema_version` starts at `"1.0.0"`.
6. **Replace the added/removed/changed/unchanged model** wherever it
   exists today with `diff()`/`StateDelta` (§5) — same information,
   path-addressed instead of bucket-addressed.
7. **Add the §21 tests alongside, not instead of, existing tests.** Keep
   every existing test green throughout.
8. **Keep `primitive_5.py … primitive_11.py` and `renderer/index.html` as
   the public entrypoints.** Internally they import from `core/`,
   `morpho/`, and `backends/` (§2). Do not rename or remove them unless
   the user explicitly asks — external callers/scripts may depend on
   those names.

If, instead, the repository is genuinely starting from nothing (as it was
at spec-writing time), skip straight to implementing §2's module layout
directly, using this migration plan's ordering (schema → canonical state →
versioning → delta → projection → Morpho compiler → backends → renderer)
as the build order, and implement the brief's described prototype
behavior (10 fields, 0 edges, deterministic ids/projections, live updates,
Three.js rendering) as the first milestone before adding anything from
§16/§17.

---

## 23. Explicit List of Things NOT to Implement Yet

Do not implement any of the following now. Where a contract above defines
an interface for one of these (§16, §17), implement only the interface
shapes — no logic behind them.

- Kalman filtering or any Bayesian state estimator
- Neural estimation models of any kind
- Distributed consensus / multi-writer conflict resolution for
  `VersionStore` (single-writer only in v1; §20 flags the seam)
- Database clustering/replication
- Merkle trees (content-addressing via a flat sha256 per `Version` is
  sufficient; no tree structure over versions is needed yet)
- CRDTs
- A general ontology/reasoning system beyond the fixed `StateSchema`
  constraints in §6
- A physics simulation engine (Python, CUDA, LAMMPS, or otherwise) — only
  the `DynamicsSpec`/`Action`/`CandidateNextState` interface shapes (§16)
- GPU-accelerated simulation
- Spatial indexing structures (octrees, BVH, k-d trees) beyond the plain
  `CoordinateFrame` parent/child list in §12
- An expression/predicate language for `constraint_decl.rule` — it stays
  an opaque string in v1 (§7.B); do not build a rule evaluator
- `move`/`rename` delta operations — the `Operation` enum reserves the
  names (§5) but `diff()` never emits them yet
- Stable ids independent of `field_name` — §9's `MigrationMap` mechanism
  is specified but not triggered until a real schema evolution needs it
- Multi-user auth/permissions on `VersionStore` writes
- Any caching layer beyond "recomputable, therefore safe to cache" being
  noted in §18 — no cache implementation is required for v1
- Undo/redo UI, branching/merging of version history, or any UI beyond
  what already exists in `renderer/index.html`
