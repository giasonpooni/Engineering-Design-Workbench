# Data Capability Matrix

What this repository can actually accept and transform today, as of
Phase 12. Every claim below is backed by a named, currently-passing
test — not asserted from design intent. Four honest classifications are
used throughout:

- **SUPPORTED** — works end to end, proven by a test, no known gap for
  the stated capability.
- **PARTIALLY SUPPORTED** — works, but with a real, stated scope
  limitation (a fixed representation choice, not a bug).
- **INTERFACE ONLY** — the Protocol/dataclass shape exists and is proven
  to compose correctly with `validate_candidate`, but no real
  implementation (engine, model) exists behind it, by design (§16/§17,
  §23).
- **NOT IMPLEMENTED** — nothing exists yet; would need new code, and in
  some cases a new, explicitly-flagged additive extension.

Do not read a SUPPORTED row as "this is production-grade for every
domain." It means: the concrete case demonstrated by the cited test
works, deterministically, with identity and provenance preserved.

| Data type | Status | Mechanism | Demonstrated by |
|---|---|---|---|
| Scalar measurements | **SUPPORTED** | `Field(type="scalar")` | `tests/test_data_ingestion.py`, `tests/test_time_series_representation.py` |
| Categorical data | **SUPPORTED** | `Field(type="string")` + `FieldConstraints.enum` for a constrained set | `core/canonical/schema.py::FieldConstraints.enum` (pre-existing; no new test needed — this was already fully supported) |
| Vectors | **PARTIALLY SUPPORTED** | `Field(type="vector3")` — fixed length 3 only. No generic N-dimensional vector type. | `tests/test_live_state_bridge.py::test_nested_list_value_change_vector3` |
| Matrices | **NOT IMPLEMENTED** | No 2D tensor field type exists. Would require a new `FieldType` literal (a core/canonical/schema.py extension, same class of change as this phase's `ProvenanceInfo.timestamp` addition, but not built — no concrete requirement forced the decision this phase). | — |
| Time series | **PARTIALLY SUPPORTED** | Each sample becomes its own indexed scalar field (`<channel>_t<index>`); ordering is represented by that naming convention plus explicit `"precedes"` edges between consecutive samples — not a first-class sequence type recognized by the compiler. Ordering is recoverable (index in the id, edge direction) but not enforced or validated as a sequence invariant. | `tests/test_time_series_representation.py`, `tests/test_data_ingestion.py::test_array_of_records_preserves_sequence_order_via_index` |
| Tabular experimental data | **SUPPORTED** | `adapters/csv_adapter.py` — single-row and multi-row (prefixed, non-colliding) ingestion | `tests/test_data_ingestion.py::test_csv_*` |
| Nested JSON / objects | **PARTIALLY SUPPORTED** | `adapters/json_adapter.py` flattens nested keys with a `__` joiner (e.g. `material__polymer__molecular_weight`); the original path is recoverable by splitting on `__`, but CanonicalState has no first-class nested/record field type — it is linearized, not structurally preserved as a tree. | `tests/test_data_ingestion.py::test_nested_json_preserves_recoverable_path_in_field_id` |
| Graphs / relationships | **SUPPORTED** | `CanonicalState.edges` / `EdgeRecord` / `EdgeSchema` (pre-existing, §3/§6); adapters can emit edges directly from a JSON `"relationships"` key or from a fixture's own edge-construction code | `tests/test_data_ingestion.py::test_relationships_become_canonical_edges_not_a_second_model`, `tests/test_time_series_representation.py::test_time_series_ordering_is_visible_as_graph_structure_in_every_backend` |
| Material properties | **SUPPORTED** | Same mechanism as any scalar/categorical measurement, with units on the `Field` itself | `tests/test_data_ingestion.py` (the sample JSON record is exactly this: temperature, pressure, viscosity, tensile strength, etc.) |
| Process parameters | **SUPPORTED** | Same mechanism; demonstrated by the nested `material.processing.*` example and the full time-series fixture | `tests/test_data_ingestion.py::test_nested_json_preserves_recoverable_path_in_field_id`, `tests/test_time_series_representation.py` |
| Simulation outputs | **INTERFACE ONLY** | `backends/simulation/interface.py` (`DynamicsSpec`, `Action`, `CandidateNextState`) — the shape reaches `validate_candidate` via `runtime/feedback_loop.py` with a real accept/reject outcome; no physics/dynamics engine exists behind it (§16, §23, deliberately) | `runtime/test_feedback_loop.py::test_simulation_candidate_*` |
| Sensor streams | **PARTIALLY SUPPORTED** | The adapter boundary + time-series representation prove periodic scalar readings can be ingested and ordered; there is no continuous/streaming ingestion loop, only discrete batch `normalize()` calls — "stream" here means "a series of discrete readings," not a live connection | `tests/test_time_series_representation.py` |
| ML predictions | **INTERFACE ONLY** | `backends/neural/interface.py` (`Estimator`, `BeliefState`) — same proof pattern as simulation outputs; no model exists (§17, §23, deliberately) | `runtime/test_feedback_loop.py::test_neural_belief_*` |
| Optimization candidates | **NOT IMPLEMENTED** | No dedicated interface exists. An optimization candidate is structurally identical to `backends/simulation/interface.py::CandidateNextState` (a proposed next state), so it is trivially reachable through that existing shape — but nothing names or tests "optimization" specifically, so it is not claimed as supported. | — |
| Knowledge-graph data | **PARTIALLY SUPPORTED** | A KG triple maps directly onto one `EdgeRecord` (`from`/`to`/`type`), demonstrated via the JSON adapter's `"relationships"` handling; there is no KG-specific adapter, no external ID namespacing scheme, and no ontology/reasoning layer (explicitly out of scope, §23) | `tests/test_data_ingestion.py::test_relationships_become_canonical_edges_not_a_second_model` |
| External databases | **NOT IMPLEMENTED** | No SQL/database adapter exists. Would follow the exact same pattern as `adapters/json_adapter.py`/`adapters/csv_adapter.py` (a new adapter module implementing the same `Adapter` protocol) — not built this phase because no concrete requirement asked for it. | — |

## How to read "PARTIALLY SUPPORTED" honestly

Three recurring, real limitations show up across several rows above, and
are worth naming once rather than repeating per-row:

1. **No nested/record field type.** `CanonicalState.fields` is, and
   remains, `Mapping[str, Field]` — flat. Nested JSON and multi-sample
   tabular data are both handled by *flattening into disambiguated flat
   field ids* (`__`-joined paths, or `<record_id>__<field>` prefixes),
   never by adding a structural nesting concept to `CanonicalState`
   itself. This was a deliberate choice, not an oversight — see
   `adapters/json_adapter.py`'s module docstring for the reasoning
   (mainly: a literal `.` in a field id would collide with delta-path
   syntax, and CanonicalState's flatness is part of the frozen
   architecture this repository does not redesign).
2. **No first-class sequence/vector/matrix type.** Only `vector3`
   (fixed length 3) exists beyond `scalar`/`string`/`bool`. A time
   series is represented as N separate scalar fields plus explicit
   ordering edges — real, inspectable, but not a single value the type
   system understands as "this is a sequence."
3. **Interface-only means exactly that.** Simulation and ML both have a
   *proven, tested* path from a candidate to a real accepted `Version`
   — that seam is not speculative. What's absent is any actual
   simulation or ML computation behind it, by explicit design
   (§16/§17/§23: "do not implement Kalman filtering... neural
   estimation... physics simulation... yet").
