"""Phase 12: real data ingestion, end to end.

    external data -> adapter -> CandidateDelta -> validate_candidate()
        -> Version -> CanonicalState -> Morpho IR -> Three.js/SVG/Graph

Proves the original source identity traces all the way from a JSON
record or a CSV row to a canonical field, to a Morpho entity, to every
backend representation -- and that JSON, CSV, and a manually-constructed
CanonicalState carrying equivalent information converge on equivalent
canonical semantics.
"""

import ast as pyast
from pathlib import Path

from adapters.csv_adapter import CSVAdapter, build_candidate_from_rows, parse_csv_rows
from adapters.interface import ExternalRecord, build_candidate_delta
from adapters.json_adapter import JSONAdapter, infer_schema_from_record
from backends.diagram.compiler import DiagramLayoutConfig, compile_svg
from backends.graph.analysis import analyze
from backends.threejs.compiler import ThreeJSRenderConfig, compile_threejs
from core.canonical.delta import CandidateDelta
from core.canonical.schema import FieldConstraints, FieldSchema, StateSchema
from core.canonical.state import CanonicalState
from core.canonical.validation import validate_candidate
from core.projection.project import project_state
from morpho.compiler import CompilerConfig, compile_morpho

REPO_ROOT = Path(__file__).resolve().parent.parent

SAMPLE_JSON_RECORD = {
    "sample_id": "P-001",
    "temperature_C": 185.0,
    "pressure_MPa": 4.2,
    "viscosity_Pa_s": 1250.0,
    "tensile_strength_MPa": 42.7,
    "elongation_percent": 180.0,
    "processing_time_s": 94.0,
    "material": "TPU",
}


def _ingest_json(raw: dict, source: str):
    record = ExternalRecord(raw=raw, source=source)
    schema = infer_schema_from_record(record, schema_version="ingested-1.0.0")
    base = CanonicalState(schema_version=schema.schema_version, fields={}, edges=())
    candidate = build_candidate_delta(
        JSONAdapter(), record, version_from=None, transaction_id="tx-json", timestamp="2026-08-22T00:00:00Z"
    )
    result = validate_candidate(schema, base, candidate)
    assert not isinstance(result, list), result
    return result, schema


# -- 1. JSON source -> canonical field --------------------------------------


def test_json_source_reaches_canonical_field_with_traceable_provenance():
    version, _schema = _ingest_json(SAMPLE_JSON_RECORD, source="lab_run_42")
    assert version.state.fields["temperature_C"].value == 185.0
    assert version.state.fields["material"].value == "TPU"

    # Provenance traces back to the exact source this data came from.
    change = None
    # validate_candidate doesn't retain the original changes on Version,
    # but the Version's own top-level provenance is derived from
    # candidate.changes[0].provenance (core/canonical/validation.py) --
    # confirm that provenance names this exact adapter and source.
    assert version.provenance.source.startswith("json_adapter:lab_run_42")


def test_json_field_identity_matches_original_key_for_flat_fields():
    version, _schema = _ingest_json(SAMPLE_JSON_RECORD, source="lab_run_42")
    for key in SAMPLE_JSON_RECORD:
        assert key in version.state.fields
        # field_identity_is_the_key (I5): identity is the key, never the value
        assert version.state.fields[key].id == key  # I5: no silent renaming


# -- nested structures and arrays --------------------------------------------


def test_nested_json_preserves_recoverable_path_in_field_id():
    raw = {"material": {"polymer": {"molecular_weight": 85000, "dispersity": 1.72}}}
    version, _schema = _ingest_json(raw, source="nested_demo")
    assert version.state.fields["material__polymer__molecular_weight"].value == 85000
    assert version.state.fields["material__polymer__dispersity"].value == 1.72
    # The original nested path is recoverable by splitting on "__" --
    # not lost, just linearized (see docs/DATA_CAPABILITIES.md).
    assert "material__polymer__molecular_weight".split("__") == ["material", "polymer", "molecular_weight"]


def test_array_of_records_preserves_sequence_order_via_index():
    raw = {
        "measurements": [
            {"time_s": 0, "stress_MPa": 2.1},
            {"time_s": 1, "stress_MPa": 2.8},
            {"time_s": 2, "stress_MPa": 3.7},
        ]
    }
    version, _schema = _ingest_json(raw, source="sequence_demo")
    assert version.state.fields["measurements__0__stress_MPa"].value == 2.1
    assert version.state.fields["measurements__1__stress_MPa"].value == 2.8
    assert version.state.fields["measurements__2__stress_MPa"].value == 3.7


def test_explicit_units_and_timestamp_are_preserved_when_supplied():
    raw = {"temperature": {"value": 185.0, "unit": "C", "timestamp": "2026-08-20T10:00:00Z"}}
    record = ExternalRecord(raw=raw, source="envelope_demo")
    changes = JSONAdapter().normalize(record)
    assert changes[0].new_value["unit"] == "C"
    assert changes[0].provenance.timestamp == "2026-08-20T10:00:00Z"

    schema = infer_schema_from_record(record, schema_version="ingested-1.0.0")
    base = CanonicalState(schema_version=schema.schema_version, fields={}, edges=())
    candidate = build_candidate_delta(JSONAdapter(), record, None, "tx", "2026-08-22T00:00:00Z")
    version = validate_candidate(schema, base, candidate)
    assert not isinstance(version, list), version
    assert version.state.fields["temperature"].unit == "C"


def test_relationships_become_canonical_edges_not_a_second_model():
    raw = {
        "A": 1,
        "B": 2,
        "relationships": [{"from": "A", "to": "B", "type": "depends_on"}],
    }
    record = ExternalRecord(raw=raw, source="graph_demo")
    schema = infer_schema_from_record(record, schema_version="ingested-1.0.0", edge_types=("depends_on",))
    base = CanonicalState(schema_version=schema.schema_version, fields={}, edges=())
    candidate = build_candidate_delta(JSONAdapter(), record, None, "tx", "2026-08-22T00:00:00Z")
    version = validate_candidate(schema, base, candidate)
    assert not isinstance(version, list), version
    assert len(version.state.edges) == 1
    assert version.state.edges[0].from_ == "A" and version.state.edges[0].to == "B"

    # And it compiles into a real, canonical (not inferred) MorphoRelation.
    ir_doc = compile_morpho(project_state(version), CompilerConfig())
    assert len(ir_doc.relations) == 1
    assert ir_doc.relations[0].is_canonical is True
    assert ir_doc.relations[0].inference_status == "explicit"


# -- 2. CSV source -> canonical field ----------------------------------------


def test_csv_source_reaches_canonical_field_with_traceable_provenance():
    csv_text = "sample_id,temperature_C,pressure_MPa\nP001,180,4.1\n"
    rows = parse_csv_rows(csv_text, source="batch1.csv")
    record = rows[0]
    schema = StateSchema(
        schema_version="ingested-csv-1.0.0",
        fields={
            "sample_id": FieldSchema(id="sample_id", type="string", required=False),
            "temperature_C": FieldSchema(id="temperature_C", type="scalar", required=False),
            "pressure_MPa": FieldSchema(id="pressure_MPa", type="scalar", required=False),
        },
    )
    base = CanonicalState(schema_version=schema.schema_version, fields={}, edges=())
    candidate = build_candidate_delta(CSVAdapter(), record, None, "tx-csv", "2026-08-22T00:00:00Z")
    version = validate_candidate(schema, base, candidate)
    assert not isinstance(version, list), version
    assert version.state.fields["temperature_C"].value == 180
    assert version.provenance.source == "csv_adapter:batch1.csv:row0"


def test_csv_multi_row_disambiguates_without_losing_any_sample():
    csv_text = "sample_id,temperature_C\nP001,180\nP002,185\nP003,190\n"
    rows = parse_csv_rows(csv_text, source="batch1.csv")
    changes = build_candidate_from_rows(rows, id_column="sample_id")
    schema = StateSchema(
        schema_version="ingested-csv-1.0.0",
        fields={c.new_value["id"]: FieldSchema(id=c.new_value["id"], type=c.new_value["type"], required=False) for c in changes},
    )
    base = CanonicalState(schema_version=schema.schema_version, fields={}, edges=())
    candidate = CandidateDelta(version_from=None, transaction_id="tx-multi", timestamp="2026-08-22T00:00:00Z", changes=changes)
    version = validate_candidate(schema, base, candidate)
    assert not isinstance(version, list), version
    assert version.state.fields["P001__temperature_C"].value == 180
    assert version.state.fields["P002__temperature_C"].value == 185
    assert version.state.fields["P003__temperature_C"].value == 190  # all 3 samples present, none overwritten


# -- 3 & 4. canonical field -> Morpho entity -> every backend --------------


def test_canonical_field_reaches_morpho_entity_and_every_backend_representation():
    version, _schema = _ingest_json(SAMPLE_JSON_RECORD, source="lab_run_42")
    ir_doc = compile_morpho(project_state(version), CompilerConfig())

    entity = ir_doc.entity_by_id("temperature_C")
    assert entity is not None
    assert entity.attributes["value"] == 185.0
    assert entity.provenance.origin_version == version.id
    assert entity.provenance.source == "canonical"  # canonical once inside the IR, regardless of ingestion source

    scene = compile_threejs(ir_doc, ThreeJSRenderConfig())
    assert any(m["id"] == "temperature_C" for m in scene.meshes)

    svg = compile_svg(ir_doc, DiagramLayoutConfig())
    assert 'data-entity-id="temperature_C"' in svg

    report = analyze(ir_doc)
    assert "temperature_C" in report.adjacency


# -- 7. representation convergence: JSON, CSV, manual construction ---------


def test_json_csv_and_manual_construction_converge_on_equivalent_semantics():
    """Different sources, different provenance, SAME semantic field
    values -- the central claim of Phase 12 §7."""
    shared_values = {"temperature_C": 180.0, "pressure_MPa": 4.1}

    json_record = ExternalRecord(raw=dict(shared_values), source="json_source")
    json_version, json_schema = _ingest_json(shared_values, source="json_source")

    csv_text = "temperature_C,pressure_MPa\n180.0,4.1\n"
    csv_rows = parse_csv_rows(csv_text, source="csv_source")
    csv_schema = StateSchema(
        schema_version="ingested-1.0.0",
        fields={
            "temperature_C": FieldSchema(id="temperature_C", type="scalar", required=False),
            "pressure_MPa": FieldSchema(id="pressure_MPa", type="scalar", required=False),
        },
    )
    csv_base = CanonicalState(schema_version=csv_schema.schema_version, fields={}, edges=())
    csv_candidate = build_candidate_delta(CSVAdapter(), csv_rows[0], None, "tx-csv", "2026-08-22T00:00:00Z")
    csv_version = validate_candidate(csv_schema, csv_base, csv_candidate)
    assert not isinstance(csv_version, list), csv_version

    manual_schema = StateSchema(
        schema_version="ingested-1.0.0",
        fields={
            "temperature_C": FieldSchema(id="temperature_C", type="scalar", default=180.0),
            "pressure_MPa": FieldSchema(id="pressure_MPa", type="scalar", default=4.1),
        },
    )
    from core.canonical.version import create_genesis_version

    manual_version = create_genesis_version(manual_schema, "2026-08-22T00:00:00Z")

    # Semantic fields converge: same ids, same values.
    for field_id in shared_values:
        assert json_version.state.fields[field_id].value == csv_version.state.fields[field_id].value
        assert json_version.state.fields[field_id].value == manual_version.state.fields[field_id].value

    # Provenance/source legitimately differs -- convergence is about
    # semantics, not about erasing where the data came from.
    assert json_version.provenance.source != csv_version.provenance.source
    assert json_version.provenance.source != manual_version.provenance.source

    # And all three converge to the same Morpho-IR-level representation
    # for the shared fields once compiled.
    json_ir = compile_morpho(project_state(json_version), CompilerConfig())
    csv_ir = compile_morpho(project_state(csv_version), CompilerConfig())
    manual_ir = compile_morpho(project_state(manual_version), CompilerConfig())
    for field_id in shared_values:
        assert json_ir.entity_by_id(field_id).attributes["value"] == csv_ir.entity_by_id(field_id).attributes["value"]
        assert json_ir.entity_by_id(field_id).attributes["value"] == manual_ir.entity_by_id(field_id).attributes["value"]


# -- validation still gates ingested data exactly as strictly as ever ------


def test_ingested_data_violating_an_authored_constraint_is_still_rejected():
    raw = {"temperature_C": -500.0}  # physically implausible, and the
    # schema below says so explicitly -- ingestion does not bypass
    # constraint checking just because the data came from an adapter.
    record = ExternalRecord(raw=raw, source="bad_sensor")
    schema = StateSchema(
        schema_version="ingested-1.0.0",
        fields={
            "temperature_C": FieldSchema(
                id="temperature_C", type="scalar", required=False,
                constraints=FieldConstraints(min=-273.15),
            )
        },
    )
    base = CanonicalState(schema_version=schema.schema_version, fields={}, edges=())
    candidate = build_candidate_delta(JSONAdapter(), record, None, "tx", "2026-08-22T00:00:00Z")
    result = validate_candidate(schema, base, candidate)
    assert isinstance(result, list)
    assert base.fields == {}  # nothing applied


def test_unsupported_json_leaf_type_is_rejected_by_the_adapter_itself():
    record = ExternalRecord(raw={"bad_field": None}, source="bad_json")
    try:
        JSONAdapter().normalize(record)
        assert False, "expected TypeError for an unsupported JSON leaf type"
    except TypeError:
        pass


# -- dependency direction: adapters never import validation/version internals


def test_adapters_never_import_validation_or_mint_machinery():
    """Static check like the ones already used for validation.py and the
    backends -- but scoped to actual code (imports and call expressions),
    not module docstrings, since both adapter modules' own docstrings
    legitimately explain that they have "no path to validate_candidate"
    (the same self-referential trap the renderer static check hit
    earlier this project -- see tests/test_backends_threejs.py)."""
    import adapters.csv_adapter as csv_adapter_module
    import adapters.json_adapter as json_adapter_module
    import inspect as inspect_module

    for module in (csv_adapter_module, json_adapter_module):
        source = inspect_module.getsource(module)
        tree = pyast.parse(source)
        imported_modules = []
        called_names = set()
        for node in pyast.walk(tree):
            if isinstance(node, pyast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, pyast.ImportFrom) and node.module:
                imported_modules.append(node.module)
            elif isinstance(node, pyast.Call) and isinstance(node.func, pyast.Name):
                called_names.add(node.func.id)
        assert "core.canonical.validation" not in imported_modules
        assert "validate_candidate" not in called_names
        assert "make_version" not in called_names
        assert "create_genesis_version" not in called_names
