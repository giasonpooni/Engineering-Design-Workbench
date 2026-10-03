"""Source identity, dimensional provenance and bounded STEP grammar gates."""
from pathlib import Path

import pytest

from ciw.ifc_subset_verifier import inspect_source, scan


ROOT = Path(__file__).resolve().parents[1]
TARGET = {"ifc_class": "IfcBuildingStorey", "global_id": "CIWSTOREY00000000000015",
          "quantity": "ClearHeight"}


@pytest.fixture
def room():
    return (ROOT / "examples/bim-quantity/room.ifc").read_bytes()


def extra(room, records):
    return room.replace(b"ENDSEC;\nEND-ISO-10303-21;", records + b"\nENDSEC;\nEND-ISO-10303-21;")


def test_exact_source_quantity_links_and_project_units(room):
    result = inspect_source(room, TARGET)
    assert result["source_schema"] == "IFC4"
    assert result["source_step_id"] == 15
    assert result["quantity_step_id"] == 29
    assert result["nominal_metres"] == 3.0
    assert result["prior_sigma_metres"] == 0.01
    assert result["raw_quantity_inventory"] == [TARGET,
        {"ifc_class": "IfcSpace", "global_id": "CIWSPACE00000000000300", "quantity": "Length"},
        {"ifc_class": "IfcSpace", "global_id": "CIWSPACE00000000000300", "quantity": "Width"}]
    assert result["length_units"] == [{"step_id": 2, "kind": "SI", "name": "METRE",
                                      "prefix": None, "scale_to_metres": 1.0,
                                      "normalization_required": False,
                                      "accepted_by_current_adapter": True}]


def test_header_data_text_does_not_choose_data_section(room):
    raw = room.replace(b"'room.ifc'", b"'notes DATA; filename.ifc'")
    assert inspect_source(raw, TARGET)["quantity_step_id"] == 29


@pytest.mark.parametrize("ending", [b"", b"END-ISO", b"END-ISO-10303-21", b"END-ISO-10303-21;garbage",
                                    b"END-ISO-10303-21;\n#999=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);"])
def test_exchange_requires_complete_final_closure(room, ending):
    raw = room.replace(b"END-ISO-10303-21;", ending)
    with pytest.raises(ValueError):
        scan(raw)


@pytest.mark.parametrize("raw", [b"ISO-10303-21;HEADER;", b"ISO-10303-21;HEADER;FILE_SCHEMA((",
                                b"ISO-10303-21;HEADER;FILE_SCHEMA(('IFC4'));ENDSEC;DATA;#1=IFCPROJECT(("])
def test_truncation_is_a_verification_refusal(raw):
    with pytest.raises(ValueError):
        scan(raw)


def test_schema_is_read_from_header_not_invented(room):
    with pytest.raises(ValueError, match="bounded IFC4"):
        inspect_source(room.replace(b"('IFC4')", b"('IFC2X3')"), TARGET)
    with pytest.raises(ValueError, match="FILE_SCHEMA"):
        scan(room.replace(b"FILE_SCHEMA(('IFC4'));", b""))


def test_ambient_length_unit_is_not_project_authority(room):
    raw = extra(room, b"#4=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);")
    result = inspect_source(raw, TARGET)
    assert [row["step_id"] for row in result["length_units"]] == [2]
    assert result["unit_context"]["scale_to_metres"] == 1.0


@pytest.mark.parametrize("assignment", [b"#3=IFCUNITASSIGNMENT(());", b"#3=IFCUNITASSIGNMENT((#999));",
                                        b"#3=IFCUNITASSIGNMENT((2.));", b"#3=IFCUNITASSIGNMENT();"])
def test_malformed_or_empty_active_project_units_refuse(room, assignment):
    raw = room.replace(b"#3=IFCUNITASSIGNMENT((#2));", assignment)
    with pytest.raises(ValueError):
        inspect_source(raw, TARGET)


def test_project_without_assignment_cannot_borrow_ambient_si(room):
    raw = room.replace(b"$,$,$,$,$,#3);", b"$,$,$,$,$,$);")
    with pytest.raises(ValueError, match="explicit project"):
        inspect_source(raw, TARGET)


def test_project_units_normalize_the_source_mean(room):
    raw = room.replace(b"#2=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);",
                       b"#2=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);")
    result = inspect_source(raw, TARGET)
    assert result["nominal_metres"] == .003
    # Default uncertainty is an existing policy in metres, not a file length.
    assert result["prior_sigma_metres"] == .01
    assert result["length_units"][0]["normalization_required"] is True


def test_unit_context_order_matches_native_step_id_order(room):
    raw = extra(room, b"#0=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);")
    raw = raw.replace(b"#3=IFCUNITASSIGNMENT((#2));", b"#3=IFCUNITASSIGNMENT((#2,#0));")
    result = inspect_source(raw, TARGET)
    assert [row["step_id"] for row in result["length_units"]] == [0, 2]
    assert result["unit_context"]["source_step_id"] == 0


@pytest.mark.parametrize("unit", [b"#2", b"*"])
def test_quantity_local_unit_is_not_silently_ignored(room, unit):
    raw = room.replace(b"IFCQUANTITYLENGTH('ClearHeight',$,$,3.)",
                       b"IFCQUANTITYLENGTH('ClearHeight',$," + unit + b",3.)")
    with pytest.raises(ValueError, match="unit override"):
        inspect_source(raw, TARGET)


@pytest.mark.parametrize("quantity_type", [b"IFCQUANTITYAREA", b"IFCQUANTITYVOLUME"])
def test_same_named_area_or_volume_is_not_a_length(room, quantity_type):
    raw = room.replace(b"IFCQUANTITYLENGTH('ClearHeight'", quantity_type + b"('ClearHeight'")
    with pytest.raises(ValueError, match="quantity type"):
        inspect_source(raw, TARGET)


def test_missing_target_quantity_stays_missing(room):
    raw = room.replace(b"IFCQUANTITYLENGTH('ClearHeight'", b"IFCQUANTITYLENGTH('Unknown'")
    assert inspect_source(raw, TARGET)["quantity_step_id"] is None


def test_duplicate_source_object_identity_refuses(room):
    raw = extra(room, b"#16=IFCBUILDINGSTOREY('CIWSTOREY00000000000015',$,'Other',$,$,#20,$,$,$,$);")
    with pytest.raises(ValueError, match="duplicated"):
        inspect_source(raw, TARGET)


def test_duplicate_source_quantity_refuses(room):
    raw = extra(room, b"#30=IFCQUANTITYLENGTH('ClearHeight',$,$,4.);")
    raw = raw.replace(b"$,$,(#29));", b"$,$,(#29,#30));")
    with pytest.raises(ValueError, match="Ambiguous source target quantity"):
        inspect_source(raw, TARGET)


@pytest.mark.parametrize("unit", [b"#2", b"*"])
def test_sigma_property_unit_override_refuses(room, unit):
    raw = extra(room, b"#50=IFCPROPERTYSINGLEVALUE('ClearHeightSigma',$,IFCLENGTHMEASURE(.02)," + unit + b");\n"
                     b"#51=IFCPROPERTYSET('sigma-pset',$,'GAT_Uncertainty',$,(#50));\n"
                     b"#52=IFCRELDEFINESBYPROPERTIES('sigma-rel',$,$,$,(#15),#51);")
    with pytest.raises(ValueError, match="sigma unit override"):
        inspect_source(raw, TARGET)


def test_sigma_override_follows_source_links_and_si_scale(room):
    raw = extra(room, b"#50=IFCPROPERTYSINGLEVALUE('ClearHeightSigma',$,IFCLENGTHMEASURE(.02),$);\n"
                     b"#51=IFCPROPERTYSET('sigma-pset',$,'GAT_Uncertainty',$,(#50));\n"
                     b"#52=IFCRELDEFINESBYPROPERTIES('sigma-rel',$,$,$,(#15),#51);")
    assert inspect_source(raw, TARGET)["prior_sigma_metres"] == .02


@pytest.mark.parametrize("change", ["dangling-quantity", "short-project", "short-quantity", "short-relationship"])
def test_malformed_consumed_source_links_refuse_cleanly(room, change):
    replacements = {
        "dangling-quantity": (b"$,$,(#29));", b"$,$,(#999));"),
        "short-project": (b"#1=IFCPROJECT('CIWPROJECT000000000001',$,'Quantity fixture',$,$,$,$,$,#3);", b"#1=IFCPROJECT('short');"),
        "short-quantity": (b"#29=IFCQUANTITYLENGTH('ClearHeight',$,$,3.);", b"#29=IFCQUANTITYLENGTH('ClearHeight');"),
        "short-relationship": (b"#27=IFCRELDEFINESBYPROPERTIES('CIWPROPERTIES0000000027',$,$,$,(#15),#28);", b"#27=IFCRELDEFINESBYPROPERTIES('short');"),
    }
    before, after = replacements[change]
    with pytest.raises(ValueError):
        inspect_source(room.replace(before, after), TARGET)


def test_supported_target_profile_is_required_even_for_missing_quantities(room):
    with pytest.raises(ValueError, match="outside"):
        inspect_source(room, {**TARGET, "quantity": "Area"})
