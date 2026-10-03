"""Qualified dynamic projection preserves existing state and source boundaries."""
from hashlib import sha256
import json

import pytest

from ciw.control_contracts import validate_state
from ciw.fluid_contract import example_request
from ciw.fluid_handoff import export_snapshot
from ciw.fluid_workflow import _read, run


@pytest.fixture(scope="module")
def reservoir_bundle(tmp_path_factory):
    directory = tmp_path_factory.mktemp("dynamic-handoff") / "reservoir"
    request = example_request("reservoir")
    assert run(request, directory)["status"] == "LOCAL"
    return directory


def snapshot(directory):
    return {str(path.relative_to(directory)): sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*") if path.is_file()}


def test_dynamic_sample_preserves_values_clock_and_occurrences(reservoir_bundle, tmp_path):
    before = snapshot(reservoir_bundle)
    output = tmp_path / "sample.json"
    export_snapshot(reservoir_bundle, output, sample_index=100)
    payload = json.loads(output.read_text())
    session, candidate, verification = _read(reservoir_bundle)
    result = candidate["data"]
    trace = result["resolutions"]["finer"]["trace"]
    projected = payload["state"]
    validate_state(projected)
    assert projected["clock"]["time_s"] == trace["time_s"][100]
    assert projected["clock"]["id"] == session.run["metadata"]["fluid_request"]["clock"]["id"]
    assert projected["identity"]["execution_id"] == candidate["execution_id"]
    for name, variable in projected["variables"].items():
        assert variable == {"value": trace[name][100], "unit": result["units"][name]}
    assert projected["uncertainty"] is None
    assert projected["provenance"]["semantics"] == "simulated"
    assert payload["source_result_id"] == candidate["result_id"]
    assert payload["retained_verification_id"] == verification["data"]["verification_id"]
    assert payload["fresh_verification_id"] != payload["retained_verification_id"]
    assert payload["fresh_verification_record"]["verification_id"] == payload["fresh_verification_id"]
    assert payload["fresh_verification_record"]["candidate_result_id"] == candidate["result_id"]
    assert payload["fresh_verification_record"]["candidate_execution_id"] == candidate["execution_id"]
    assert payload["mapping"]["estimator_execution"] == "not_performed"
    assert snapshot(reservoir_bundle) == before


def test_each_projection_has_fresh_verification_and_is_create_only(reservoir_bundle, tmp_path):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    export_snapshot(reservoir_bundle, first, sample_index=0)
    export_snapshot(reservoir_bundle, second, sample_index=0)
    a, b = (json.loads(path.read_text()) for path in (first, second))
    assert a["state"] == b["state"]
    for key in ("fresh_verification_id", "fresh_verification_execution_id", "fresh_verification_result_id"):
        assert a[key] != b[key]
    original = first.read_bytes()
    with pytest.raises(FileExistsError):
        export_snapshot(reservoir_bundle, first, sample_index=0)
    assert first.read_bytes() == original


@pytest.mark.parametrize("sample", [-1, True, 1.5, 100000])
def test_projection_refuses_invalid_sample_indices(reservoir_bundle, tmp_path, sample):
    output = tmp_path / "blocked.json"
    with pytest.raises(ValueError):
        export_snapshot(reservoir_bundle, output, sample_index=sample)
    assert not output.exists()


def test_projection_refuses_unqualified_extension(tmp_path):
    request = example_request("reservoir")
    request["desired_observables"].append("turbulence")
    directory = tmp_path / "expansion"
    assert run(request, directory)["status"] == "EXPAND"
    with pytest.raises(ValueError, match="LOCAL"):
        export_snapshot(directory, tmp_path / "blocked.json", sample_index=0)


def test_projection_does_not_coerce_spatial_waves_into_two_tank_state(tmp_path):
    directory = tmp_path / "wave"
    assert run(example_request("wave"), directory)["status"] == "LOCAL"
    with pytest.raises(ValueError, match="reservoir profile"):
        export_snapshot(directory, tmp_path / "blocked.json", sample_index=0)
