"""Retained curved-path candidate comparisons, independent math and offline use."""
import base64
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import runpy

import numpy as np
import pytest

from ciw import curved_path_study as study
from ciw.adapters.protocol import AdapterRefusal
from ciw.geodesic_reference import GeodesicReferenceWorkflow
from ciw.instruments import make_demo_run
from ciw.session import Session
from ciw.telemetry import canonical, digest
from ciw.workbench import Workbench


ROOT = Path(__file__).resolve().parents[1]
KIND = "curved-path-transfer"
OPERATION = "ciw.curved-path-transfer.v1"
LIMITS = {"max_abs_lateral": .01, "max_abs_heading": .01,
          "units": {"length": "m", "angle": "radian"}}
REFERENCE_KEYS = {"source_id", "evidence_id", "bundle_id", "operation_id",
                  "execution_id", "result_id", "numerical_result_id",
                  "verification_id", "runtime_digest"}


def baseline_source():
    return json.loads((ROOT / "examples/curved-path-study/baseline.json").read_bytes())


def request(bundle_id="sha256:" + "0" * 64, candidates=None, **options):
    return study.make_request(bundle_id, candidates if candidates is not None else
                              [{"candidate_id": "small", "initial_heading_radian": .001}],
                              sample_index=options.get("sample_index", 4),
                              limits=options.get("limits", deepcopy(LIMITS)),
                              study_id=options.get("study_id", "curved-test"))


def add_source(workbench, declaration):
    # Retain noncanonical source bytes to exercise evidence identity as bytes.
    raw = b"\n" + json.dumps(declaration, indent=2).encode() + b"\n"
    retained = workbench.add_source({"kind": KIND, "label": "Curved study baseline",
                                    "bytes_b64": base64.b64encode(raw).decode("ascii")})
    return retained, raw


def execute_baseline(workbench, declaration):
    source, raw = add_source(workbench, declaration)
    bundle = workbench.execute({"operation_id": OPERATION, "source_id": source["source_id"]})
    return bundle, raw


def native_data(workbench, row):
    return workbench.get_bundle(row["references"]["bundle_id"])["steps"][0]["result"]["data"]


def reseal(record):
    record["study_digest"] = digest({key: value for key, value in record.items()
                                     if key != "study_digest"})
    return record


def forbidden(*args, **kwargs):
    raise AssertionError("Retained study inspection must not execute a provider or study")


@pytest.fixture(scope="module")
def repositories():
    checkout = os.environ.get("CIW_CSG_REPO")
    if not checkout:
        pytest.skip("Set CIW_CSG_REPO to the pinned curved-surface provider checkout")
    return {"csg": checkout}


@pytest.fixture(scope="module")
def retained(repositories):
    workbench = Workbench()
    workbench.bind_workflow(KIND, repositories)
    baseline, raw = execute_baseline(workbench, baseline_source())
    candidates = [{"candidate_id": "small", "initial_heading_radian": .001},
                  {"candidate_id": "opposite", "initial_heading_radian": -.001}]
    record = study.run_study(workbench, request(baseline["bundle_id"], candidates))
    return workbench.serialize(), record, raw


@pytest.fixture
def reopened(retained):
    snapshot, record, raw = retained
    return Workbench.restore(snapshot), deepcopy(record), raw


def test_request_is_bounded_data_and_copies_arguments():
    candidates = [{"candidate_id": "small", "initial_heading_radian": .001}]
    limits = deepcopy(LIMITS)
    result = request(candidates=candidates, limits=limits)
    assert result["schema"] == "ciw.curved-path-study-request.v1"
    assert result["candidates"] == candidates
    assert result["limits"] == limits
    candidates[0]["initial_heading_radian"] = .1
    limits["units"]["length"] = "mm"
    assert result["candidates"][0]["initial_heading_radian"] == .001
    assert result["limits"]["units"]["length"] == "m"


@pytest.mark.parametrize("candidate", [
    {}, {"candidate_id": "x"}, {"initial_heading_radian": .001},
    {"candidate_id": "", "initial_heading_radian": .001},
    {"candidate_id": True, "initial_heading_radian": .001},
    {"candidate_id": "x", "initial_heading_radian": True},
    {"candidate_id": "x", "initial_heading_radian": float("nan")},
    {"candidate_id": "x", "initial_heading_radian": float("inf")},
    {"candidate_id": "x", "initial_heading_radian": .100001},
    {"candidate_id": "x", "initial_heading_radian": -.100001},
    {"candidate_id": "x", "initial_heading_radian": .001, "initial_lateral": 0},
])
def test_candidate_encoding_and_declared_envelope_refuse(candidate):
    with pytest.raises(ValueError):
        request(candidates=[candidate])


@pytest.mark.parametrize("candidates", [[], None, {}, "heading", [True],
    [{"candidate_id": "same", "initial_heading_radian": .001},
     {"candidate_id": "same", "initial_heading_radian": .002}],
    [{"candidate_id": "baseline", "initial_heading_radian": .001}],
])
def test_candidate_catalog_refuses_missing_ambiguous_or_reserved_ids(candidates):
    with pytest.raises(ValueError):
        study.make_request("sha256:" + "0" * 64, candidates, sample_index=4,
                           limits=deepcopy(LIMITS), study_id="curved-test")


@pytest.mark.parametrize("sample_index", [True, -1, 1.0, "1", None, 128])
def test_sample_index_rejects_noninteger_or_outside_native_envelope(sample_index):
    with pytest.raises(ValueError):
        request(sample_index=sample_index)


@pytest.mark.parametrize("limits", [
    {}, {**LIMITS, "max_abs_lateral": True}, {**LIMITS, "max_abs_heading": -1},
    {**LIMITS, "max_abs_heading": float("nan")},
    {**LIMITS, "units": {"length": "m", "angle": "degree"}},
    {**LIMITS, "units": {"length": "unknown", "angle": "radian"}},
    {**LIMITS, "extra": 1},
])
def test_limit_encoding_and_unit_refusals(limits):
    with pytest.raises(ValueError):
        request(limits=limits)


@pytest.mark.parametrize("field,value", [
    ("arclength", [0, 0]), ("arclength", [1, 2]), ("arclength", [0, 8]),
    ("arclength", [0, True]),
    ("units", {"length": "unknown", "angle": "radian"}),
    ("starting_covariance", {"matrix": [[1, 2], [2, 1]], "basis": "assumed", "note": "indefinite"}),
    ("starting_covariance", {"matrix": [[1, .1], [0, 1]], "basis": "assumed", "note": "asymmetric"}),
    ("starting_covariance", {"matrix": [[1, 0], [0, 1]], "basis": "measured", "note": "not measured"}),
])
def test_invalid_baseline_sources_refuse_without_mutating_workbench(field, value, monkeypatch):
    workbench = Workbench()
    before = workbench.serialize()
    source = baseline_source()
    source[field] = value
    monkeypatch.setattr(GeodesicReferenceWorkflow, "_adapters", forbidden)
    with pytest.raises(ValueError):
        add_source(workbench, source)
    assert workbench.serialize() == before


def test_unknown_baseline_refuses_before_any_workbench_mutation():
    workbench = Workbench()
    before = workbench.serialize()
    with pytest.raises(ValueError):
        study.run_study(workbench, request())
    assert workbench.serialize() == before


def test_native_rows_preserve_declared_sources_and_separate_identities(reopened):
    workbench, record, raw = reopened
    assert record["schema"] == "ciw.curved-path-study.v1"
    assert record["replay_of"] is None
    assert record["baseline"]["candidate_id"] == "baseline"
    source_declaration = baseline_source()
    rows = [record["baseline"], *record["candidates"]]
    for row in rows:
        refs = row["references"]
        assert set(refs) == REFERENCE_KEYS
        assert refs["operation_id"] == OPERATION
        assert refs["execution_id"] != refs["result_id"] != refs["numerical_result_id"]
        source = workbench.get_source(refs["source_id"])
        assert source["evidence_id"] == refs["evidence_id"]
        content = json.loads(base64.b64decode(source["bytes_b64"]))
        for fixed in ("configuration", "arclength", "gaussian_curvature", "units",
                      "starting_covariance", "relative_tolerance"):
            assert content[fixed] == source_declaration[fixed]
        assert content["initial_perturbation"][0] == 0
        bundle = workbench.get_bundle(refs["bundle_id"])
        step = bundle["steps"][0]
        for field in ("operation_id", "execution_id", "result_id", "numerical_result_id"):
            assert refs[field] == step[field]
        assert refs["verification_id"] == bundle["verification"]["verification_id"]
        assert bundle["verification"]["independent"] is False
        assert row["summary"]["calibration"]["bound"] is False
        assert row["summary"]["covariance_scope"] == "conditional_marginal_at_each_arclength"
    assert base64.b64decode(workbench.get_source(rows[0]["references"]["source_id"])["bytes_b64"]) == raw
    assert len({r["references"]["execution_id"] for r in rows}) == len(rows)
    assert len({r["references"]["result_id"] for r in rows}) == len(rows)


def test_native_selected_response_matches_independent_constant_curvature_reference(reopened):
    workbench, record, _ = reopened
    source = baseline_source()
    k = source["gaussian_curvature"]
    s = source["arclength"][record["request"]["sample_index"]]
    if k > 0:
        a, b = math.cos(math.sqrt(k)*s), math.sin(math.sqrt(k)*s)/math.sqrt(k)
    elif k < 0:
        a, b = math.cosh(math.sqrt(-k)*s), math.sinh(math.sqrt(-k)*s)/math.sqrt(-k)
    else:
        a, b = 1, s
    phi = np.array([[a, b], [-k*b, a]])
    base_heading = source["initial_perturbation"][1]
    for proposed, row in zip(record["request"]["candidates"], record["candidates"]):
        heading = proposed["initial_heading_radian"]
        response = row["response"]
        np.testing.assert_allclose(response["jacobian"], phi, rtol=2e-6, atol=2e-7)
        assert response["delta"] == [0, heading-base_heading]
        np.testing.assert_allclose(response["baseline_output"], phi @ [0, base_heading], rtol=2e-6, atol=2e-9)
        np.testing.assert_allclose(response["model_output"], phi @ [0, heading], rtol=2e-6, atol=2e-9)
        np.testing.assert_allclose(response["predicted_output"], response["model_output"], rtol=2e-15, atol=1e-18)
        np.testing.assert_allclose(response["residual"], [0, 0], rtol=0, atol=1e-18)
        actual = native_data(workbench, row)
        index = record["request"]["sample_index"]
        assert response["model_output"] == [actual["separation"][index], actual["heading_change"][index]]
        endpoint = source["arclength"][-1]
        if k > 0:
            end_a = math.cos(math.sqrt(k)*endpoint)
            end_b = math.sin(math.sqrt(k)*endpoint)/math.sqrt(k)
        elif k < 0:
            end_a = math.cosh(math.sqrt(-k)*endpoint)
            end_b = math.sinh(math.sqrt(-k)*endpoint)/math.sqrt(-k)
        else:
            end_a, end_b = 1, endpoint
        end_phi = np.array([[end_a, end_b], [-k*end_b, end_a]])
        c0 = np.asarray(source["starting_covariance"]["matrix"])
        np.testing.assert_allclose(row["summary"]["endpoint"]["covariance"],
                                   end_phi @ c0 @ end_phi.T, rtol=2e-6, atol=2e-10)
        assert row["summary"]["validity"] == actual["record"]["validity"]
        assert row["summary"]["resolution"] == actual["record"]["resolution"]


def test_semantics_do_not_upgrade_assumptions_or_read_only_authority(reopened):
    _, record, _ = reopened
    semantics, authority = record["semantics"], record["authority"]
    assert semantics["coordinate_order"] == ["lateral", "heading"]
    assert semantics["units"] == ["m", "radian"]
    assert semantics["independent_variable"] == "arclength"
    assert semantics["scope"] == "same_linearized_model_consistency"
    assert semantics["covariance"] == "assumed_conditional_marginals; joint_cross_arclength_and_candidate_covariance_not_supplied"
    assert semantics["limits_scope"] == "predicted_samples_only_without_uncertainty_or_integration_error_margin"
    assert authority["numerical_replay"] == "not_performed_by_inspection"
    assert authority["physical_validation"] == "not_established"
    assert authority["state_admission"] == "not_performed"
    assert authority["hardware_actuation"] == "not_performed"
    assert authority["optimality"] == "not_claimed"


def test_inspection_save_load_and_workspace_reopen_are_provider_free(retained, tmp_path, monkeypatch):
    snapshot, record, _ = retained
    monkeypatch.setattr(GeodesicReferenceWorkflow, "_adapters", forbidden)
    monkeypatch.setattr(study, "run_study", forbidden)
    monkeypatch.setattr(study, "_assemble_study", forbidden)
    workbench = Workbench.restore(snapshot)
    before = workbench.serialize()
    inspected = study.inspect_study(workbench, record)
    assert inspected == record and inspected is not record
    inspected["candidates"][0]["candidate_id"] = "edited-copy"
    assert record["candidates"][0]["candidate_id"] == "small"
    path = tmp_path / "study.json"
    study.save_study(path, workbench, record)
    assert study.load_study(path, workbench) == record
    assert workbench.serialize() == before
    session = Session(make_demo_run(), tmp_path / "original")
    session.workbench = workbench
    workspace_path = session.save_workspace(tmp_path / "workspace.json")
    reopened_session = Session.from_workspace(workspace_path, tmp_path / "reopened")
    assert study.load_study(path, reopened_session.workbench) == record
    with pytest.raises((AdapterRefusal, ValueError)):
        study.replay_study(reopened_session.workbench, record)
    assert reopened_session.workbench.serialize() == before


@pytest.mark.parametrize("reference", sorted(REFERENCE_KEYS))
def test_missing_retained_identity_refuses_even_with_resealed_digest(reopened, reference):
    workbench, record, _ = reopened
    del record["candidates"][0]["references"][reference]
    with pytest.raises(ValueError):
        study.inspect_study(workbench, reseal(record))


@pytest.mark.parametrize("mutation", [
    lambda r: r["semantics"].update(independent_variable="time"),
    lambda r: r["semantics"].update(frame="another frame"),
    lambda r: r["semantics"].update(units=["mm", "radian"]),
    lambda r: r["semantics"].update(sample_index=True),
    lambda r: r["authority"].update(state_admission="performed"),
    lambda r: r["authority"].update(physical_validation="established"),
    lambda r: r["candidates"][0]["summary"]["endpoint"]["covariance"][0].__setitem__(0, 0.5),
    lambda r: r["candidates"][0]["summary"].update(max_abs_lateral=True),
    lambda r: r["candidates"][0]["response"]["model_output"].__setitem__(0, .05),
    lambda r: r["candidates"][0]["response"]["jacobian"][0].reverse(),
    lambda r: r["candidates"][0]["references"].update(execution_id=r["baseline"]["references"]["execution_id"]),
])
def test_resealed_meaning_numeric_or_lineage_tamper_refuses(reopened, mutation):
    workbench, record, _ = reopened
    before = workbench.serialize()
    mutation(record)
    with pytest.raises(ValueError):
        study.inspect_study(workbench, reseal(record))
    assert workbench.serialize() == before


def test_study_is_not_portable_without_its_retained_dependencies(reopened):
    _, record, _ = reopened
    with pytest.raises(ValueError):
        study.inspect_study(Workbench(), record)


def test_original_study_cannot_claim_replay_without_native_receipts(reopened):
    workbench, record, _ = reopened
    record["replay_of"] = "sha256:" + "a" * 64
    with pytest.raises(ValueError):
        study.inspect_study(workbench, reseal(record))


def test_candidate_preflight_checks_all_headings_before_mutation(reopened, monkeypatch):
    workbench, record, _ = reopened
    before = workbench.serialize()
    maximum = record["baseline"]["summary"]["validity"]["max_heading"]
    outside = math.nextafter(maximum, math.inf)
    candidates = [{"candidate_id": "would-be-valid", "initial_heading_radian": .001},
                  {"candidate_id": "outside", "initial_heading_radian": outside}]
    monkeypatch.setattr(workbench, "add_source", forbidden)
    monkeypatch.setattr(workbench, "execute", forbidden)
    with pytest.raises(ValueError):
        study.run_study(workbench, request(record["baseline"]["references"]["bundle_id"], candidates))
    assert workbench.serialize() == before


@pytest.mark.parametrize("change", ["units", "sample"])
def test_study_preflight_rejects_mismatched_units_or_missing_sample(reopened, change, monkeypatch):
    workbench, record, _ = reopened
    options = {"limits": {**LIMITS, "units": {"length": "mm", "angle": "radian"}}} if change == "units" else {
        "sample_index": len(baseline_source()["arclength"])}
    before = workbench.serialize()
    monkeypatch.setattr(workbench, "add_source", forbidden)
    with pytest.raises(ValueError):
        study.run_study(workbench, request(record["baseline"]["references"]["bundle_id"], **options))
    assert workbench.serialize() == before


def test_nonzero_lateral_baseline_is_outside_heading_only_study(repositories, monkeypatch):
    workbench = Workbench()
    workbench.bind_workflow(KIND, repositories)
    source = baseline_source()
    source["initial_perturbation"][0] = .001
    bundle, _ = execute_baseline(workbench, source)
    before = workbench.serialize()
    monkeypatch.setattr(workbench, "add_source", forbidden)
    monkeypatch.setattr(workbench, "execute", forbidden)
    with pytest.raises(ValueError):
        study.run_study(workbench, request(bundle["bundle_id"]))
    assert workbench.serialize() == before


def test_explicit_replay_preserves_numerical_results_but_records_fresh_occurrences(reopened, repositories, tmp_path):
    workbench, original, _ = reopened
    workbench.bind_workflow(KIND, repositories)
    replay = study.replay_study(workbench, original)
    assert replay["replay_of"] == original["study_digest"]
    assert replay["study_digest"] != original["study_digest"]
    assert study.inspect_study(workbench, replay) == replay
    old_rows, new_rows = [original["baseline"], *original["candidates"]], [replay["baseline"], *replay["candidates"]]
    for old, new in zip(old_rows, new_rows):
        assert old["candidate_id"] == new["candidate_id"]
        assert old["summary"] == new["summary"]
        for field in ("source_id", "evidence_id", "operation_id", "numerical_result_id", "runtime_digest"):
            assert old["references"][field] == new["references"][field]
        for field in ("bundle_id", "execution_id", "result_id", "verification_id"):
            assert old["references"][field] != new["references"][field]
    path = tmp_path / "replay.json"
    study.save_study(path, workbench, replay)
    assert study.load_study(path, Workbench.restore(workbench.serialize())) == replay


def test_retained_study_files_are_canonical_bounded_and_never_overwritten(reopened, tmp_path):
    workbench, record, _ = reopened
    path = tmp_path / "study.json"
    study.save_study(path, workbench, record)
    original_bytes = path.read_bytes()
    assert original_bytes == canonical(record)
    with pytest.raises(FileExistsError):
        study.save_study(path, workbench, record)
    assert path.read_bytes() == original_bytes
    bad = tmp_path / "malformed.json"
    for raw in (b" " + original_bytes, b'{"schema":1,"schema":2}', b"[]",
                b" " * (study.MAX_BYTES + 1)):
        bad.write_bytes(raw)
        with pytest.raises(ValueError):
            study.load_study(bad, workbench)


def test_cli_inspects_saved_workspace_without_a_provider(reopened, tmp_path, monkeypatch, capsys):
    workbench, record, _ = reopened
    session = Session(make_demo_run(), tmp_path / "session")
    session.workbench = workbench
    workspace = session.save_workspace(tmp_path / "workspace.json")
    destination = tmp_path / "study.json"
    study.save_study(destination, workbench, record)
    monkeypatch.setattr(GeodesicReferenceWorkflow, "_adapters", forbidden)
    monkeypatch.setattr(study, "run_study", forbidden)
    monkeypatch.setattr(study, "_assemble_study", forbidden)
    main = runpy.run_path(str(ROOT / "scripts/check_curved_path_study.py"))["main"]
    assert main(["inspect", "--workspace", str(workspace), "--study", str(destination)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["study_digest"] == record["study_digest"]
    assert result["authority"]["numerical_replay"] == "not_performed_by_inspection"


def test_cli_refuses_invalid_candidates_before_binding_or_baseline_execution(tmp_path, monkeypatch, capsys):
    main = runpy.run_path(str(ROOT / "scripts/check_curved_path_study.py"))["main"]
    spec = tmp_path / "spec.json"
    spec.write_bytes(canonical({"study_id": "invalid", "sample_index": 0,
        "candidates": [{"candidate_id": "bad", "initial_heading_radian": True}],
        "limits": LIMITS}))
    monkeypatch.setattr(Workbench, "bind_workflow", forbidden)
    output = tmp_path / "refused"
    assert main(["run", "--source", str(ROOT / "examples/curved-path-study/baseline.json"),
                 "--spec", str(spec), "--csg-repo", str(tmp_path / "missing-provider"),
                 "--output", str(output)]) == 2
    assert "refused" in capsys.readouterr().err
    assert not (output / "study.json").exists()
    assert not (output / "workspace.json").exists()


def test_cli_refuses_existing_output_without_overwriting(tmp_path, monkeypatch, capsys):
    main = runpy.run_path(str(ROOT / "scripts/check_curved_path_study.py"))["main"]
    output = tmp_path / "prior"
    output.mkdir()
    marker = output / "study.json"
    marker.write_bytes(b"prior evidence")
    monkeypatch.setattr(Workbench, "bind_workflow", forbidden)
    assert main(["run", "--source", str(tmp_path / "source.json"),
                 "--spec", str(tmp_path / "spec.json"), "--csg-repo", str(tmp_path / "provider"),
                 "--output", str(output)]) == 2
    assert "refused" in capsys.readouterr().err
    assert marker.read_bytes() == b"prior evidence"


def test_retained_componentwise_thresholds_include_equality_and_adjacent_sides(reopened, monkeypatch):
    workbench, original, _ = reopened
    before = workbench.serialize()
    monkeypatch.setattr(workbench, "execute", forbidden)
    monkeypatch.setattr(GeodesicReferenceWorkflow, "_adapters", forbidden)
    monkeypatch.setattr(study, "run_study", forbidden)
    selected = native_data(workbench, original["candidates"][0])
    for component, channel in (("lateral", "separation"), ("heading", "heading_change")):
        maximum = max(abs(value) for value in selected[channel])
        assert maximum > 0
        for threshold, expected in ((math.nextafter(maximum, 0), "exceeds"),
                                    (maximum, "within"),
                                    (math.nextafter(maximum, math.inf), "within")):
            record = deepcopy(original)
            record["request"]["limits"]["max_abs_" + component] = threshold
            # The underlying native results stay fixed; only the declared
            # componentwise comparison and its accounting are changed.
            for row in [record["baseline"], *record["candidates"]]:
                data = native_data(workbench, row)
                row_maximum = max(abs(value) for value in data[channel])
                row["summary"]["sampled_limits"][component] = (
                    "within" if row_maximum <= threshold else "exceeds")
            assert record["candidates"][0]["summary"]["sampled_limits"][component] == expected
            reseal(record)
            assert study.inspect_study(workbench, record) == record
            record["candidates"][0]["summary"]["sampled_limits"][component] = (
                "exceeds" if expected == "within" else "within")
            with pytest.raises(ValueError):
                study.inspect_study(workbench, reseal(record))
    assert workbench.serialize() == before


def test_second_candidate_failure_keeps_first_native_run_without_completed_study(reopened, repositories, monkeypatch):
    workbench, original, _ = reopened
    workbench.bind_workflow(KIND, repositories)
    prior_bundle_ids = {row["bundle_id"] for row in workbench.list_bundles()}
    calls, completed = [], []
    execute = workbench.execute

    def fail_second(payload):
        calls.append(deepcopy(payload))
        if len(calls) == 2:
            raise AdapterRefusal("TEST_SECOND_CANDIDATE", "Injected second-candidate refusal")
        result = execute(payload)
        completed.append(result)
        return result

    monkeypatch.setattr(workbench, "execute", fail_second)
    monkeypatch.setattr(study, "_assemble_study", forbidden)
    candidates = [{"candidate_id": "first", "initial_heading_radian": .001},
                  {"candidate_id": "second", "initial_heading_radian": -.001}]
    result = None
    with pytest.raises(AdapterRefusal, match="Injected second-candidate refusal"):
        result = study.run_study(workbench, request(original["baseline"]["references"]["bundle_id"],
                                                   candidates, study_id="partial-study"))
    assert result is None
    assert len(calls) == 2 and len(completed) == 1
    retained = workbench.list_bundles()
    assert {row["bundle_id"] for row in retained} == prior_bundle_ids | {completed[0]["bundle_id"]}
    native = workbench.get_bundle(completed[0]["bundle_id"])
    assert GeodesicReferenceWorkflow(KIND)._validate(native)
    source = workbench.get_source(completed[0]["source_id"])
    declaration = json.loads(base64.b64decode(source["bytes_b64"]))
    assert declaration["experiment_id"] == "partial-study/first"
    assert declaration["initial_perturbation"] == [0, .001]
    assert all(row["source_id"] != calls[1]["source_id"] for row in retained)
    assert workbench.pending_operations == 0
    # Failure does not erase the previously completed comparison either.
    assert study.inspect_study(workbench, original) == original
