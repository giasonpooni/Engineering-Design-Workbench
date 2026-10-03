from copy import deepcopy

import pytest

from ciw.polymer_contract import example_request, validate_request
from ciw.polymer_metrology import assess_metrology


def dim(request):
    return next(s for s in request["sensors"] if s["quantity"] == "part_dimension")


@pytest.mark.parametrize("process", ["injection_molding", "extrusion_blow_molding"])
def test_process_specific_examples_are_valid_detached_declarations(process):
    request = example_request(process)
    validated = validate_request(request)
    assert validated == request and validated is not request
    assert validated["source_kind"] == "synthetic"
    if process == "extrusion_blow_molding":
        assert not validated["model"]["cavity_arrival"]["pressure_sensor_ids"]


@pytest.mark.parametrize("value,uncertainty,status", [(0.0200, .00001, "CONFORMING"),
                                                     (0.0202, .00001, "NONCONFORMING"),
                                                     (0.0201, .00001, "INDETERMINATE")])
def test_uncertainty_guard_band_at_specification_boundary(value, uncertainty, status):
    request = example_request()
    dim(request)["samples"][-1].update(value=value, standard_uncertainty=uncertainty)
    result = assess_metrology(validate_request(request))
    assert result["status"] == status
    assert result["quantities"][0]["interval"] == pytest.approx([value - 2 * uncertainty, value + 2 * uncertainty])


@pytest.mark.parametrize("change,reason", [("missing", "missing_or_stale_required_channel"),
                                         ("stale", "missing_or_stale_required_channel"),
                                         ("condition", "measurement_condition_differs_from_specification")])
def test_missing_stale_and_hot_part_condition_never_pass(change, reason):
    request = example_request()
    if change == "missing":
        dim(request)["samples"] = []
    elif change == "stale":
        dim(request)["samples"][-1]["time_s"] = 8.0
    else:
        request["tolerances"][0]["condition"] = "conditioned"
    result = assess_metrology(validate_request(request))
    assert result["status"] == "INDETERMINATE"
    assert result["quantities"][0]["reason"] == reason
    assert result["quantities"][0]["interval"] is None


def test_conflicting_sensors_use_union_instead_of_false_precision():
    request = example_request()
    dim(request)["samples"][-1]["value"] = 0.0200
    second = deepcopy(dim(request))
    second["sensor_id"] = "dimension-2"
    second["samples"][-1]["value"] = .0202
    request["sensors"].append(second)
    result = assess_metrology(validate_request(request))
    assert result["status"] == "INDETERMINATE"
    assert result["quantities"][0]["interval"] == pytest.approx([.01998, .02022])
    assert "no_independence_assumption" in result["fusion_method"]


def test_unaligned_duplicate_quantity_abstains_and_preserves_rows():
    request = example_request()
    second = deepcopy(dim(request))
    second["sensor_id"] = "dimension-2"
    second["samples"][-1]["time_s"] = 9.5
    request["sensors"].append(second)
    result = assess_metrology(validate_request(request))
    assert result["status"] == "INDETERMINATE"
    assert result["quantities"][0]["reason"] == "sensor_times_exceed_declared_skew"
    assert {r["status"] for r in result["measurements"] if r["quantity"] == "part_dimension"} == {"UNALIGNED"}


@pytest.mark.parametrize("change", ["nan", "boolean", "unit", "clock", "frame", "duplicate",
                                    "time", "calibration", "origin", "uncertainty", "extra"])
def test_invalid_sensor_contracts_refuse(change):
    request = example_request()
    sensor = dim(request)
    if change == "nan":
        sensor["samples"][0]["value"] = float("nan")
    elif change == "boolean":
        sensor["samples"][0]["standard_uncertainty"] = True
    elif change == "unit":
        sensor["unit"] = "mm"
    elif change == "clock":
        sensor["clock_id"] = "unaligned"
    elif change == "frame":
        sensor["frame"] = "camera"
    elif change == "duplicate":
        request["sensors"].append(deepcopy(sensor))
    elif change == "time":
        sensor["samples"][1]["time_s"] = sensor["samples"][0]["time_s"]
    elif change == "calibration":
        sensor["calibration_ref"] = "unknown"
    elif change == "origin":
        sensor["origin"] = "observed"
    elif change == "uncertainty":
        sensor["samples"][0]["standard_uncertainty"] = -1
    else:
        sensor["endpoint"] = "plc.write"
    with pytest.raises(ValueError):
        validate_request(request)


def test_retained_observation_label_does_not_establish_physical_traceability():
    request = example_request()
    request["source_kind"] = "retained_observation"
    for sensor in request["sensors"]:
        sensor["origin"] = "observed"
    result = assess_metrology(validate_request(request))
    assert result["authority"]["physical_validation"] == "not_established"
    assert result["authority"]["calibration_traceability"] == "not_established"
