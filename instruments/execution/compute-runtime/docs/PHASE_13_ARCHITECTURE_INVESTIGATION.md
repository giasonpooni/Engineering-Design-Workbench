# Structured-state architecture reference

This reference describes the implemented canonical-state boundary. The complete interface is [Architecture specification](ARCHITECTURE_SPEC.md); [Architecture](ARCHITECTURE.md) maps it to source files.

## Canonical state and projections

`core/canonical/` owns immutable state, content-addressed versions, deltas and validation. An accepted candidate creates a new version. A rejected candidate does not modify the existing version. `core/projection/`, `morpho/` and the backends derive representations from an accepted state.

The Three.js, SVG and graph backends consume the intermediate representation. Rendering does not write canonical state. Simulation and neural backends in this compiler expose interfaces; they are not implementations of physical simulation or learned inference.

## G. Graphs are derived representations

Canonical relationships are explicit `EdgeRecord` values. A graph backend derives its nodes, edges and descriptive metrics from the supplied representation; it does not add inferred relationships to canonical state. In the separate evidence domain, the Trust Graph is likewise a derived view over evidence-pool objects, not an alternate store of truth.

## L. Domain data and capability limits

JSON and CSV adapters normalize external inputs into candidate changes. They do not bypass schema validation or mint versions. Supported input shapes, partial support and unimplemented capabilities are listed in [Data capabilities](DATA_CAPABILITIES.md).

The evidence pool and canonical-state compiler remain distinct object domains. Evidence admission is not canonical-state validation. See [SCOUT architecture](SCOUT_ARCHITECTURE.md) for the evidence-layer contract.

## Validation

`tests/test_architecture_boundaries.py`, `tests/test_data_ingestion.py`, `tests/test_scout_boundaries.py` and the compiler tests check these boundaries. Historical invariant labels are reconciled in [Invariant sets](INVARIANT_SET_RECONCILIATION.md); this reference does not assert a numbered total.
