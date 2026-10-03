"""DSP Session identity, retention, refusal and fresh-replay qualification."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw import dsp_pipeline as net_dsp
from ciw.core.identities import content_identity
from ciw.net import main
pytest.importorskip("stfe_dsp.dsp", reason="Optional DSP instrument; dedicated DSP CI requires installation and no skips")
from stfe_dsp.pipeline import run_pipeline, validate_request


def request():
    return {"schema": "stfe.dsp-pipeline.v1", "provenance": {"source": "synthetic:test"},
        "signals": {"p": {"source_id": "synthetic:pressure", "unit": "Pa", "clock_id": "test-clock",
            "sample_rate_hz": 8.0, "time_s": [i / 8 for i in range(32)], "values": [float(i % 4) for i in range(32)]}},
        "steps": [{"id": "quality", "input": "p", "method": "quality", "parameters": {}},
            {"id": "filtered", "input": "quality", "method": "filter", "parameters": {
                "family": "fir", "taps": [0.25, 0.5, 0.25], "mode": "causal"}}]}


def test_full_session_replay_separates_identities_and_preserves_source(tmp_path):
    source = request()
    original = deepcopy(source)
    first = net_dsp.run(source, tmp_path / "first")
    assert first["status"] == "completed", first
    before = {p.name: p.read_bytes() for p in (tmp_path / "first").iterdir() if p.is_file()}
    replay = net_dsp.replay(tmp_path / "first", tmp_path / "replay", atol=0.0, rtol=0.0)
    assert replay["status"] == "PASS"
    assert replay["original_execution_id"] != replay["replay_execution_id"]
    assert replay["original_result_id"] != replay["replay_result_id"]
    assert replay["verification_id"].startswith("verification-")
    assert replay["source_evidence_id"] == first["evidence_id"]
    assert replay["runtime_match"] is True
    assert source == original
    assert before == {p.name: p.read_bytes() for p in (tmp_path / "first").iterdir() if p.is_file()}
    workspace = json.loads((tmp_path / "replay/workspace.json").read_text())
    assert workspace["results"][0]["verification_id"] is None
    assert workspace["results"][0]["verification_status"] == "not_verified"


def test_inspection_does_not_load_numerical_provider(tmp_path):
    net_dsp.run(request(), tmp_path / "bundle")
    import builtins
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name in {"stfe", "stfe_dsp", "scipy"} or name.startswith(("stfe.", "stfe_dsp.", "scipy.")):
            raise AssertionError("Inspection attempted numerical provider import")
        return original(name, *args, **kwargs)
    with patch.object(builtins, "__import__", guarded):
        summary = net_dsp.inspect(tmp_path / "bundle")
    assert summary["status"] == "completed"
    assert summary["fresh_execution"] is False
    assert summary["numerical_verification"] == "not_performed"


def test_broken_raw_grid_quality_is_inspectable_without_relaxing_run_contract(tmp_path):
    source = request()
    source["steps"] = source["steps"][:1]
    source["signals"]["p"]["time_s"][4] = source["signals"]["p"]["time_s"][3]
    source["signals"]["p"]["values"][9] = None
    report = net_dsp.run(source, tmp_path / "quality")
    assert report["status"] == "completed", report
    source["steps"].extend(request()["steps"][1:])
    refused = net_dsp.run(source, tmp_path / "refused")
    assert refused["status"] == "refused"
    assert refused["result_id"] is None
    assert net_dsp.inspect(tmp_path / "refused")["status"] == "refused"


@pytest.mark.parametrize("mutation", ["forward", "duplicate", "missing_quality", "analysis_as_signal", "arbitrary_method"])
def test_pipeline_declared_graph_refuses_invalid_paths(mutation):
    source = request()
    if mutation == "forward":
        source["steps"][0]["input"] = "filtered"
    elif mutation == "duplicate":
        source["steps"][1]["id"] = "quality"
    elif mutation == "missing_quality":
        source["steps"] = source["steps"][1:]
        source["steps"][0]["input"] = "p"
    elif mutation == "analysis_as_signal":
        source["steps"][0]["method"] = "welch"
    else:
        source["steps"][1]["method"] = "python.eval"
    with pytest.raises(ValueError):
        validate_request(source)


@pytest.mark.parametrize("field", ["request_ref", "stage_input", "stage_method", "effective_params", "authority"])
def test_resealed_payload_cannot_change_bindings(field):
    source = request()
    result = run_pipeline(source)
    if field == "request_ref":
        result["request_ref"] = "sha256:" + "0" * 64
    elif field == "stage_input":
        result["stages"][1]["result"]["input_ref"] = "sha256:" + "0" * 64
    elif field == "stage_method":
        result["stages"][1]["method"] = "detrend"
    elif field == "effective_params":
        result["stages"][1]["result"]["parameters"]["taps"] = [1.0]
    else:
        result["authority"]["state_admission"] = "performed"
    with pytest.raises(ValueError):
        net_dsp.validate_payload(net_dsp.OPERATION, result, net_dsp.make_source(source), {}, {})


def test_request_sidecar_tamper_refused(tmp_path):
    net_dsp.run(request(), tmp_path / "bundle")
    sidecar = tmp_path / "bundle/request.json"
    data = json.loads(sidecar.read_text())
    data["signals"]["p"]["unit"] = "m"
    sidecar.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="sidecar"):
        net_dsp.inspect(tmp_path / "bundle")


def test_create_only_cli_and_request_run(tmp_path, capsys):
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request()))
    args = ["dsp", "pipeline", "run", "--request", str(path), "--output-dir", str(tmp_path / "bundle")]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "completed"
    assert main(args) == 1
    capsys.readouterr()
    assert main(["dsp", "pipeline", "inspect", str(tmp_path / "bundle")]) == 0


def test_tolerant_comparison_and_boolean_type_safety():
    assert net_dsp._compare({"x": [1.0]}, {"x": [1.0 + 1e-8]}, 1e-7, 0)["status"] == "PASS"
    assert net_dsp._compare({"x": [1.0]}, {"x": [1.01]}, 1e-7, 0)["status"] == "FAIL"
    assert net_dsp._compare({"x": [0]}, {"x": [False]}, 1, 0)["status"] == "FAIL"


def test_pump_truth_does_not_influence_detection_and_edges_are_retained():
    from stfe_dsp.pump import make_pump_request
    source = make_pump_request(seed=7)
    first = run_pipeline(source)
    net_dsp.validate_payload(net_dsp.OPERATION, first, net_dsp.make_source(source), {}, {})
    source.pop("ground_truth")
    second = run_pipeline(source)
    assert first["stages"] == second["stages"]
    comparison = first["diagnostics"]["synthetic_event_comparison"]
    assert comparison["ground_truth_used_for_detection"] is False
    assert comparison["candidate_count"] > 0
    feature = next(s["result"] for s in first["stages"] if s["method"] == "features")
    assert feature["contract"]["pipeline_effective_valid_sample_range"] == [42, 2006]
    assert feature["contract"]["includes_boundary_affected_samples"] is True


def test_clock_mismatch_never_becomes_truth_overlap():
    from stfe_dsp.pump import make_pump_request
    source = make_pump_request(seed=7)
    source["ground_truth"]["events"][0]["clock_id"] = "unrelated-clock"
    comparison = run_pipeline(source)["diagnostics"]["synthetic_event_comparison"]
    assert all(not row["overlapping_candidates"] for row in comparison["comparisons"])


def test_dsp_reader_uses_declared_budget_above_control_document_limit(tmp_path):
    path = tmp_path / "large.json"
    document = {"metadata": "x" * (9 * 1024 * 1024)}
    net_dsp.save_new(path, document)
    assert net_dsp.read_bounded(path) == document


def test_unicode_source_and_integer_parameters_remain_valid(tmp_path):
    source = request()
    source["provenance"]["label"] = "pression à Montréal"
    source["steps"][1]["parameters"]["taps"] = [1, 0]
    assert net_dsp.run(source, tmp_path / "unicode")["status"] == "completed"


@pytest.mark.parametrize("tolerance", [True, -1.0, float("nan"), float("inf")])
def test_invalid_replay_tolerances_refuse_before_output(tmp_path, tolerance):
    with pytest.raises(ValueError):
        net_dsp.replay(tmp_path / "absent", tmp_path / "new", atol=tolerance)
    assert not (tmp_path / "new").exists()
