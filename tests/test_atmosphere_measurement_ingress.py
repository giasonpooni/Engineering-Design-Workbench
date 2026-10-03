"""Declared SI measurement mapping, boundaries and static inspection authority."""
from copy import deepcopy
import csv
import io
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw import atmosphere_measurement_ingress as ingress
from ciw.atmosphere_comparison_contract import make_reference_source, validate_policy, validate_reference
from ciw.control_contracts import MAX_BYTES, bytes_ref
from ciw.operations.runner import check_seal, digest, seal


def _row(field="temperature_k", value="288.15", *, index="0", height="0", **changes):
    row = {
        "sample_index": index, "height_m": height, "quantity": field,
        "value": value, "unit": {"temperature_k": "K", "pressure_pa": "Pa",
                                    "density_kg_per_m3": "kg/m^3", "relative_humidity": "1",
                                    "water_vapour_pressure_pa": "Pa",
                                    "liquid_water_saturation_pressure_pa": "Pa"}[field],
        "uncertainty_kind": "declared_expanded", "absolute_bound": "0.2",
        "coverage_factor": "2", "uncertainty_ref": "declared instrument uncertainty budget",
        "instrument_ref": "sensor:temperature-001", "calibration_ref": "",
    }
    row.update(changes)
    return row


def _csv(rows=None, *, fields=ingress.CSV_FIELDS, line_ending="\r\n"):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator=line_ending)
    writer.writerow(fields)
    for row in [_row()] if rows is None else rows:
        writer.writerow([row[field] for field in fields] if isinstance(row, dict) else row)
    return stream.getvalue().encode("utf-8")


def _declaration(fields=("temperature_k",)):
    return {
        "schema": ingress.DECLARATION_SCHEMA,
        "provenance": {"kind": "declared_measurements", "source_ref": "operator:stable-environment-001",
                       "source_url": None, "independent_of_candidate": False},
        "context": {"frame": "atmosphere.local_enu", "height_origin_m": 0.0,
                    "valid_time_utc": "2026-10-03T12:00:00Z", "humidity_convention": "not_applicable"},
        "thresholds": {field: {"absolute_tolerance": 0.5, "relative_tolerance": 0.0}
                       for field in fields},
    }


def _prepared():
    raw, declaration = _csv(), _declaration()
    return raw, declaration, ingress.prepare(raw, declaration)


def test_preparation_reuses_sealed_reference_policy_and_canonical_evidence():
    raw, declaration, prepared = _prepared()
    assert set(prepared) == {
        "schema", "csv_content_digest", "declaration_digest", "reference", "policy",
        "reference_evidence_id", "observation_count", "scalar_count", "normalization",
        "authority", "record_digest",
    }
    assert prepared["schema"] == ingress.PREPARATION_SCHEMA
    assert prepared["csv_content_digest"] == bytes_ref(raw)
    assert prepared["declaration_digest"] == digest(declaration)
    assert prepared["observation_count"] == prepared["scalar_count"] == 1
    reference, policy = prepared["reference"], prepared["policy"]
    assert validate_reference(reference) == reference
    assert validate_policy(reference, policy) == policy
    assert prepared["reference_evidence_id"] == make_reference_source(reference)["evidence_id"]
    assert prepared["reference_evidence_id"] not in {reference["record_digest"], digest(reference)}
    assert reference["context"] == declaration["context"]
    assert reference["provenance"] == declaration["provenance"]
    assert policy["thresholds"] == declaration["thresholds"]
    assert prepared["authority"] == ingress.AUTHORITY
    assert prepared["normalization"] == ingress.NORMALIZATION
    check_seal(prepared)
    assert not any(name in prepared for name in ("operation_id", "execution_id", "verification_id"))


def test_expanded_uncertainty_is_not_multiplied_by_coverage_factor():
    prepared = ingress.prepare(_csv([_row(absolute_bound="0.2", coverage_factor="2")]), _declaration())
    datum = prepared["reference"]["observations"][0]["quantities"]["temperature_k"]
    assert datum["uncertainty"] == {"kind": "declared_expanded", "absolute_bound": 0.2,
                                     "coverage_factor": 2.0,
                                     "reference": "declared instrument uncertainty budget"}
    assert datum["calibration_ref"] is None
    assert prepared["authority"]["calibration_validation"] == "not_established"


def test_absolute_bound_retains_null_coverage_and_declared_calibration_reference():
    raw = _csv([_row(uncertainty_kind="declared_absolute_bound", coverage_factor="",
                     calibration_ref="certificate:operator-supplied")])
    datum = ingress.prepare(raw, _declaration())["reference"]["observations"][0]["quantities"]["temperature_k"]
    assert datum["uncertainty"]["coverage_factor"] is None
    assert datum["calibration_ref"] == "certificate:operator-supplied"


def test_arbitrary_row_order_has_deterministic_reference_and_distinct_raw_binding():
    rows = [_row("pressure_pa", "100120", index="1", height="100"),
            _row(index="0", height="0"), _row("pressure_pa", "101325", index="0", height="0.0"),
            _row(value="287.5", index="1", height="1e2")]
    declaration = _declaration(("temperature_k", "pressure_pa"))
    first = ingress.prepare(_csv(rows), declaration)
    second = ingress.prepare(_csv(list(reversed(rows))), declaration)
    assert first["reference"] == second["reference"]
    assert first["policy"] == second["policy"]
    assert first["reference_evidence_id"] == second["reference_evidence_id"]
    assert first["csv_content_digest"] != second["csv_content_digest"]
    assert first["observation_count"] == 2 and first["scalar_count"] == 4
    assert [row["sample_index"] for row in first["reference"]["observations"]] == [0, 1]
    assert list(first["reference"]["observations"][0]["quantities"]) == ["pressure_pa", "temperature_k"]


@pytest.mark.parametrize("line_ending", ["\n", "\r\n", "\r"])
def test_valid_csv_line_endings(line_ending):
    assert ingress.prepare(_csv(line_ending=line_ending), _declaration())["scalar_count"] == 1


def test_optional_utf8_bom_changes_raw_identity_and_preserves_reference_identity():
    plain = ingress.prepare(_csv(), _declaration())
    bom = ingress.prepare(b"\xef\xbb\xbf" + _csv(), _declaration())
    assert plain["reference"] == bom["reference"]
    assert plain["reference_evidence_id"] == bom["reference_evidence_id"]
    assert plain["csv_content_digest"] != bom["csv_content_digest"]


def test_csv_quoted_commas_quotes_and_unicode_are_retained():
    text = 'budget: "expanded", instrument \u03a9'
    prepared = ingress.prepare(_csv([_row(uncertainty_ref=text, instrument_ref="sensor:metrology-\u03b1")]),
                               _declaration())
    datum = prepared["reference"]["observations"][0]["quantities"]["temperature_k"]
    assert datum["uncertainty"]["reference"] == text
    assert datum["instrument_ref"] == "sensor:metrology-\u03b1"


@pytest.mark.parametrize("field,token", [
    ("height_m", "1e-400"), ("value", "1e-400"), ("absolute_bound", "1e-400"),
    ("coverage_factor", "1e-400"), ("height_m", "-1e-400"),
])
def test_nonzero_decimal_underflow_never_becomes_exact_zero(field, token):
    with pytest.raises(ValueError, match="underflows binary64"):
        ingress.prepare(_csv([_row(**{field: token})]), _declaration())


@pytest.mark.parametrize("field,token", [
    ("height_m", "-0"), ("height_m", "0e-400"), ("height_m", "+0.0"),
    ("value", ".28815e3"), ("value", "2.8815E+2"), ("value", "288.150"),
])
def test_representable_ascii_decimal_syntax(field, token):
    assert ingress.prepare(_csv([_row(**{field: token})]), _declaration())["scalar_count"] == 1


@pytest.mark.parametrize("token", ["NaN", "nan", "Infinity", "inf", "-inf", "True", "1_000", "0x10",
                                  " 288.15", "288.15 ", "\u0662\u0668\u0668.\u0661\u0665", "", ".", "1e", "1e+",
                                  "1e400", "1" * 129, "0e" + "9" * 100])
def test_invalid_numeric_tokens_are_refused(token):
    with pytest.raises(ValueError):
        ingress.prepare(_csv([_row(value=token)]), _declaration())


@pytest.mark.parametrize("index", ["-1", "+1", "00", "01", "1.0", "1e0", "129", "1000", "True", "", "\u0661"])
def test_sample_index_requires_bounded_explicit_decimal_integer(index):
    with pytest.raises(ValueError):
        ingress.prepare(_csv([_row(index=index)]), _declaration())


@pytest.mark.parametrize("field,value", [
    ("unit", "degC"), ("unit", "k"), ("unit", " K"), ("unit", "K "),
    ("unit", "\u00b0C"), ("unit", ""), ("quantity", "temperature"),
    ("instrument_ref", ""), ("instrument_ref", " "), ("calibration_ref", " "),
    ("uncertainty_ref", ""), ("uncertainty_kind", "standard"),
    ("uncertainty_kind", "rounding_bound"), ("uncertainty_kind", "exact_fixture"),
    ("absolute_bound", "0"), ("absolute_bound", "-1"),
    ("coverage_factor", ""), ("coverage_factor", "0"), ("coverage_factor", "11"),
])
def test_measurement_metadata_and_si_contract_rejections(field, value):
    with pytest.raises(ValueError):
        ingress.prepare(_csv([_row(**{field: value})]), _declaration())


def test_nonexpanded_uncertainty_cannot_smuggle_coverage_factor():
    with pytest.raises(ValueError):
        ingress.prepare(_csv([_row(uncertainty_kind="declared_absolute_bound", coverage_factor="2")]),
                        _declaration())


@pytest.mark.parametrize("absolute_bound,accepted", [("1e-60", True), ("9e-61", False),
                                                     ("1e9", True), ("1.000001e9", False)])
def test_declared_uncertainty_precision_and_budget_edges(absolute_bound, accepted):
    raw = _csv([_row(absolute_bound=absolute_bound)])
    if accepted:
        assert ingress.prepare(raw, _declaration())["scalar_count"] == 1
    else:
        with pytest.raises(ValueError):
            ingress.prepare(raw, _declaration())


@pytest.mark.parametrize("value,accepted", [("1e-20", True), ("9e-21", False),
                                            ("1e6", True), ("1.000001e6", False)])
def test_reference_quantity_precision_and_budget_edges(value, accepted):
    raw = _csv([_row(value=value)])
    if accepted:
        assert ingress.prepare(raw, _declaration())["scalar_count"] == 1
    else:
        with pytest.raises(ValueError):
            ingress.prepare(raw, _declaration())


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "reordered"])
def test_header_must_be_exact(mutation):
    fields = list(ingress.CSV_FIELDS)
    if mutation == "missing":
        fields.pop()
    elif mutation == "extra":
        fields.append("undeclared")
    elif mutation == "duplicate":
        fields[-1] = fields[0]
    else:
        fields.reverse()
    raw = _csv([], fields=fields)
    with pytest.raises(ValueError, match="header"):
        ingress.prepare(raw, _declaration())


@pytest.mark.parametrize("raw", [
    b"", b"\xff", b"\xef\xbb\xbf\xef\xbb\xbf" + _csv(), _csv([]),
    _csv() + b"\r\n", _csv() + b",,,,,,,,,,extra,extra\r\n",
    _csv() + b"missing,cells\r\n", _csv() + b'"unterminated',
    _csv().replace(b"sensor:temperature-001", b'sensor:tempera"ture-001'),
    _csv().replace(b"sensor:temperature-001", b'"sensor:temperature-001"junk'),
    _csv().replace(b"sensor:temperature-001", b"sensor:\x00temperature-001"),
])
def test_invalid_or_ambiguous_csv_is_refused(raw):
    with pytest.raises(ValueError):
        ingress.prepare(raw, _declaration())


@pytest.mark.parametrize("raw", ["text", bytearray(_csv()), memoryview(_csv()), None, b"x" * (MAX_BYTES + 1)],
                         ids=["string", "bytearray", "memoryview", "null", "over-budget"])
def test_raw_bytes_type_and_file_budget(raw):
    with pytest.raises(ValueError):
        ingress.prepare(raw, _declaration())


def test_cell_text_budget():
    with pytest.raises(ValueError, match="text budget"):
        ingress.prepare(_csv([_row(instrument_ref="x" * 513)]), _declaration())


def test_duplicate_quantity_and_conflicting_heights_are_refused():
    with pytest.raises(ValueError, match="Duplicate"):
        ingress.prepare(_csv([_row(), _row()]), _declaration())
    with pytest.raises(ValueError, match="same height"):
        ingress.prepare(_csv([_row(), _row("pressure_pa", "101325", height="1")]),
                        _declaration(("temperature_k", "pressure_pa")))


def test_distinct_height_decimals_cannot_hide_inside_one_binary64_bucket():
    first, second = "0.1", "0.100000000000000001"
    assert float(first) == float(second)
    with pytest.raises(ValueError, match="same height"):
        ingress.prepare(_csv([_row(height=first), _row("pressure_pa", "101325", height=second)]),
                        _declaration(("temperature_k", "pressure_pa")))


def test_signed_zero_heights_have_order_independent_canonical_evidence():
    rows = [_row(height="-0"), _row("pressure_pa", "101325", height="0")]
    declaration = _declaration(("temperature_k", "pressure_pa"))
    first = ingress.prepare(_csv(rows), declaration)
    second = ingress.prepare(_csv(list(reversed(rows))), declaration)
    assert first["reference"] == second["reference"]
    assert first["reference_evidence_id"] == second["reference_evidence_id"]
    assert digest(first["reference"]) == digest(second["reference"])
    assert str(first["reference"]["observations"][0]["height_m"]) == "0.0"


def test_complete_scalar_and_observation_budgets_are_supported():
    values = {"temperature_k": "288.15", "pressure_pa": "101325", "density_kg_per_m3": "1.2",
              "water_vapour_pressure_pa": "1000", "relative_humidity": "0.5",
              "liquid_water_saturation_pressure_pa": "2339.3"}
    rows = [_row(field, value, index=str(index), height=str(index * 10))
            for index in range(129) for field, value in values.items()]
    declaration = _declaration(tuple(values))
    declaration["context"]["humidity_convention"] = "pure_liquid_magnus_17_62_243_12.v1"
    prepared = ingress.prepare(_csv(rows), declaration)
    assert prepared["observation_count"] == 129
    assert prepared["scalar_count"] == 774
    with pytest.raises(ValueError, match="774"):
        ingress.prepare(_csv(rows + [_row(index="128", height="1280")]), declaration)


@pytest.mark.parametrize("path,value", [
    (("schema",), "other.v1"), (("provenance", "kind"), "synthetic_fixture"),
    (("provenance", "kind"), "published_reference"), (("provenance", "source_ref"), ""),
    (("provenance", "source_url"), "file:///tmp/data"),
    (("provenance", "independent_of_candidate"), "true"),
    (("context", "valid_time_utc"), None), (("context", "valid_time_utc"), "2026-10-03T12:00:00-04:00"),
    (("context", "valid_time_utc"), "2026-02-30T12:00:00Z"),
    (("context", "humidity_convention"), "unspecified"), (("context", "height_origin_m"), 10001.0),
    (("thresholds",), {}), (("thresholds", "temperature_k", "relative_tolerance"), 0.051),
    (("thresholds", "temperature_k", "absolute_tolerance"), -1),
])
def test_invalid_declarations_remain_old_contract_rejections(path, value):
    declaration = _declaration()
    target = declaration
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        ingress.prepare(_csv(), declaration)


@pytest.mark.parametrize("group", [None, "provenance", "context", "thresholds"])
def test_declarations_reject_unknown_keys(group):
    declaration = _declaration()
    target = declaration if group is None else declaration[group]
    target["unknown"] = False
    with pytest.raises(ValueError):
        ingress.prepare(_csv(), declaration)


def test_thresholds_must_match_imported_fields_and_are_never_defaulted():
    with pytest.raises(ValueError):
        ingress.prepare(_csv(), _declaration(("temperature_k", "pressure_pa")))
    with pytest.raises(ValueError):
        ingress.prepare(_csv([_row(), _row("pressure_pa", "101325")]), _declaration())


def test_relative_humidity_requires_explicit_supported_definition():
    declaration = _declaration(("relative_humidity",))
    raw = _csv([_row("relative_humidity", "0.5")])
    with pytest.raises(ValueError):
        ingress.prepare(raw, declaration)
    declaration["context"]["humidity_convention"] = "pressure_enhanced_relative_humidity"
    assert ingress.prepare(raw, declaration)["reference"]["context"]["humidity_convention"] == \
        "pressure_enhanced_relative_humidity"


def test_inputs_and_validated_outputs_are_detached():
    raw, declaration = _csv(), _declaration()
    before = deepcopy(declaration)
    prepared = ingress.prepare(raw, declaration)
    assert declaration == before
    validated = ingress.validate_preparation(raw, declaration, prepared)
    validated["reference"]["context"]["frame"] = "changed"
    validated["normalization"]["encoding"] = "changed"
    assert prepared["reference"]["context"]["frame"] == before["context"]["frame"]
    assert prepared["normalization"]["encoding"] == "utf-8"
    prepared["policy"]["thresholds"]["temperature_k"]["absolute_tolerance"] = 3
    assert declaration == before


def test_static_validation_does_not_reparse_csv_or_replay_preparation():
    raw, declaration, prepared = _prepared()
    with patch.object(ingress, "prepare", side_effect=AssertionError("preparation replay")), \
            patch.object(ingress, "_observations", side_effect=AssertionError("CSV mapping replay")), \
            patch("ciw.atmosphere_measurement_ingress.csv.reader", side_effect=AssertionError("CSV parsing replay")):
        assert ingress.validate_preparation(raw, declaration, prepared) == prepared


def test_static_inspection_accepts_coherent_mapping_forgery_and_fresh_mapping_differs():
    raw, declaration, prepared = _prepared()
    prepared["reference"]["observations"][0]["quantities"]["temperature_k"]["value"] += 5.0
    seal(prepared["reference"])
    prepared["reference_evidence_id"] = make_reference_source(prepared["reference"])["evidence_id"]
    seal(prepared)
    assert ingress.validate_preparation(raw, declaration, prepared) == prepared
    assert digest(ingress.prepare(raw, declaration)) != digest(prepared)


@pytest.mark.parametrize("mutation", ["bytes", "declaration", "reference_seal", "policy_seal", "root_seal",
                                      "evidence_id", "count", "boolean_count", "authority", "normalization",
                                      "provenance", "context", "thresholds", "schema", "unknown"])
def test_static_preparation_bindings_seals_and_authority(mutation):
    raw, declaration, prepared = _prepared()
    if mutation == "bytes":
        raw += b"\r\n"
    elif mutation == "declaration":
        declaration["context"]["frame"] = "different"
    elif mutation == "reference_seal":
        prepared["reference"]["observations"][0]["height_m"] = 1.0
    elif mutation == "policy_seal":
        prepared["policy"]["thresholds"]["temperature_k"]["absolute_tolerance"] = 1.0
    elif mutation == "root_seal":
        prepared["record_digest"] = digest("different")
    elif mutation == "evidence_id":
        prepared["reference_evidence_id"] = digest("different")
    elif mutation == "count":
        prepared["observation_count"] = 2
    elif mutation == "boolean_count":
        prepared["scalar_count"] = True
    elif mutation == "authority":
        prepared["authority"]["physical_validation"] = "established"
    elif mutation == "normalization":
        prepared["normalization"]["units"] = "converted"
    elif mutation == "provenance":
        prepared["reference"]["provenance"]["independent_of_candidate"] = True
        seal(prepared["reference"])
        prepared["reference_evidence_id"] = make_reference_source(prepared["reference"])["evidence_id"]
    elif mutation == "context":
        prepared["reference"]["context"]["height_origin_m"] = 1.0
        seal(prepared["reference"])
        prepared["reference_evidence_id"] = make_reference_source(prepared["reference"])["evidence_id"]
    elif mutation == "thresholds":
        prepared["policy"]["thresholds"]["temperature_k"]["absolute_tolerance"] = 1.0
        seal(prepared["policy"])
    elif mutation == "schema":
        prepared["schema"] = "other.v1"
    else:
        prepared["unknown"] = False
    if mutation != "root_seal":
        seal(prepared)
    with pytest.raises(ValueError):
        ingress.validate_preparation(raw, declaration, prepared)


def test_preparation_and_inspection_never_activate_physics_execution_or_network():
    with patch("ciw.atmosphere_compiler.compile_atmosphere", side_effect=AssertionError("physical provider")), \
            patch("ciw.atmosphere_moist_compiler.compile_atmosphere", side_effect=AssertionError("physical provider")), \
            patch("ciw.session.execute_operation", side_effect=AssertionError("operation execution")), \
            patch("socket.create_connection", side_effect=AssertionError("network acquisition")):
        raw, declaration, prepared = _prepared()
        assert ingress.validate_preparation(raw, declaration, prepared) == prepared


def test_documented_measurement_fixture_maps_with_unestablished_authority():
    from ciw.session import loads_json
    directory = Path(__file__).resolve().parents[1] / "examples" / "atmosphere-measurements"
    declaration = loads_json((directory / "declaration.json").read_text(encoding="utf-8"))
    prepared = ingress.prepare((directory / "measurements.csv").read_bytes(), declaration)
    assert prepared["observation_count"] == 1 and prepared["scalar_count"] == 2
    assert prepared["reference"]["provenance"]["independent_of_candidate"] is False
    assert prepared["reference"]["observations"][0]["quantities"]["pressure_pa"]["uncertainty"]["absolute_bound"] == 50.0
    assert prepared["authority"]["measurement_authenticity"] == "not_established"
