"""Held-out comparison tests use synthetic fixtures, never claimed experiments."""
from contextlib import ExitStack
from copy import deepcopy
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import shutil
from unittest.mock import patch

import numpy as np
import pytest
from ciw import fluid_experiment as e, fluid_experiment_contract as c, fluid_experiment_statistics as statistics
from ciw import fluid_workflow as fluid, fluid_contract
from ciw.operations.runner import digest, seal
from ciw.operations.registry import default_registry
from ciw.session import Session, read_json, write_json
from ciw.core.identities import evidence_id


@pytest.fixture(autouse=True)
def clean_owned_test_files(tmp_path):
    yield
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    root = tmp_path_factory.mktemp("experiment-model")
    request = fluid_contract.example_request("reservoir")
    request["clock"]["duration_s"] = 0.4
    request["clock"]["coarse_step_count"] = 32
    assert fluid.run(request, root / "model")["status"] == "LOCAL"
    session, candidate, verification = fluid._read(root / "model")
    trace = candidate["data"]["resolutions"]["finer"]["trace"]
    yield root / "model", request, trace
    shutil.rmtree(root)


def inputs(root, model, *, kind="synthetic_fixture", offset=0.0, mutate=None):
    root.mkdir(parents=True, exist_ok=True)
    _, request, trace = model
    metadata = e.template()["metadata"]
    metadata["target_request_digest"] = digest(request)
    metadata["provenance"]["source_kind"] = kind
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(e.template()["csv_header"])
    for i, index in enumerate((8, 24, 40)):
        writer.writerow(["s" + str(i), trace["time_s"][index], "holdout", trace["head1_m"][index] + offset])
    raw = out.getvalue()
    metadata["csv_sha256"] = "sha256:" + sha256(raw.encode()).hexdigest()
    if mutate:
        mutate(metadata)
    csv_path, metadata_path = root / "input.csv", root / "input.json"
    csv_path.write_bytes(raw.encode())
    metadata_path.write_bytes(json.dumps(metadata).encode())
    return csv_path, metadata_path, metadata


@pytest.fixture(scope="module")
def comparison(tmp_path_factory, model):
    root = tmp_path_factory.mktemp("experiment-comparison")
    csv_path, metadata_path, metadata = inputs(root, model)
    ingestion = e.ingest(csv_path, metadata_path, root / "ingested")
    result = e.compare(model[0], root / "ingested", root / "compared")
    yield root, ingestion, result
    shutil.rmtree(root)


def test_synthetic_pipeline_has_occurrence_separation_without_measured_support(comparison):
    root, ingestion, result = comparison
    assert ingestion["status"] == "INGESTED"
    assert result["status"] == "LOCAL" and result["outcome"] == "EMPIRICALLY_COMPATIBLE"
    assert result["conditional_measured_support"] is False
    assert result["authority"]["physical_validation"] == "not_established"
    session, candidate, verification = e._load(root / "compared")
    assert session.run["time_s"] != [0.0]
    assert session.run["channels"]["head1_m"]["unit"] == "m"
    assert session.run["evidence_id"] == ingestion["evidence_id"]
    assert candidate["operation_id"] == e.COMPARE_OPERATION
    assert verification["operation_id"] == e.VERIFY_OPERATION
    assert candidate["execution_id"] != verification["execution_id"]
    model = candidate["parameters"]["model"]
    assert model["source"]["evidence_id"] != session.run["evidence_id"]
    assert candidate["data"]["model_verification_id"] == model["fresh_verification"]["verification_id"]


def test_fresh_independent_verification_retains_witness_and_leaves_archive(comparison):
    root, _, retained = comparison
    before = {p: p.read_bytes() for p in (root / "compared").rglob("*") if p.is_file()}
    first, second = e.verify_retained(root / "compared"), e.verify_retained(root / "compared")
    assert first["fresh_verification_id"] != retained["verification_id"] != second["fresh_verification_id"]
    assert first["fresh_verification_id"] != second["fresh_verification_id"]
    assert first["fresh_verification_record"]["verification_id"] == first["fresh_verification_id"]
    assert first["fresh_verification_record"]["report"]["qualification"] == "LOCAL"
    assert before == {p: p.read_bytes() for p in (root / "compared").rglob("*") if p.is_file()}


def test_reopen_and_inspect_do_not_execute_model_statistics_or_factorizations(comparison):
    root, _, retained = comparison
    with ExitStack() as stack:
        for target in ("ciw.fluid_experiment_statistics.compute", "ciw.fluid_experiment_statistics.validate_covariances", "ciw.fluid_experiment_statistics.project",
                       "ciw.fluid_reservoir_verification.verify", "ciw.fluid_reservoir_solver.simulate", "numpy.linalg.eigvalsh", "numpy.linalg.cholesky", "ciw.session.execute_operation"):
            stack.enter_context(patch(target, side_effect=AssertionError("Numerical replay")))
        assert e.inspect(root / "compared") == retained
        assert e.inspect(root / "ingested")["status"] == "INGESTED"


def test_default_registry_refuses_and_archive_never_activates(comparison, tmp_path):
    root, _, _ = comparison
    source = e._load(root / "ingested")[0].run
    session = Session(source, tmp_path / "default", operations=default_registry())
    reply = e._execute(session, e.COMPARE_OPERATION, {})
    assert reply["status"] == "refused"
    assert not session.results
    reopened, candidate, verification = e._load(root / "compared")
    assert all(row["operation_id"] not in {e.COMPARE_OPERATION, e.VERIFY_OPERATION} for row in reopened.operations.describe())


@pytest.mark.parametrize("change,match", [
    (lambda m: m["observation_operator"]["channels"][0].update(unit="cm"), "SI"),
    (lambda m: m.update(coordinate_frame="another-frame"), "coordinate"),
    (lambda m: m.update(baseline="absolute_pressure"), "baseline"),
    (lambda m: m["clock"].update(scale=True), "finite"),
    (lambda m: m["clock"].update(distribution="bounded_uniform"), "Gaussian"),
    (lambda m: m["provenance"].update(acquired_at_utc="2026-99-99T99:99:99Z"), "calendar"),
    (lambda m: m["split"].update(calibration_dataset_ids=[m["split"]["holdout_dataset_id"]]), "overlaps"),
    (lambda m: m["split"].update(parameter_fit_sample_ids=["s1"]), "overlap"),
    (lambda m: m["split"].update(calibration_refs=[m["csv_sha256"]]), "Holdout CSV"),
    (lambda m: m["split"].update(calibration_refs=[]), "references"),
    (lambda m: m["split"].update(fixed_parameters_before_holdout=False), "mandatory"),
    (lambda m: m["uncertainty"].update(terms_mutually_independent=False), "independence"),
    (lambda m: m["uncertainty"].update(axes=list(reversed(m["uncertainty"]["axes"]))), "axes"),
    (lambda m: m["uncertainty"]["measurement"].update(matrix=[[1e-8,2e-8,0],[2e-8,1e-8,0],[0,0,1e-8]]), "semidefinite"),
])
def test_bad_declarations_refused_before_creating_output(tmp_path, model, change, match):
    csv_path, metadata_path, _ = inputs(tmp_path, model, mutate=change)
    with pytest.raises(ValueError, match=match):
        e.ingest(csv_path, metadata_path, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_exact_file_hash_create_only_and_regular_file_boundary(tmp_path, model):
    csv_path, metadata_path, _ = inputs(tmp_path, model)
    original = csv_path.read_bytes()
    csv_path.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="hash"):
        e.ingest(csv_path, metadata_path, tmp_path / "bad")
    csv_path.write_bytes(original)
    linked = tmp_path / "linked.csv"
    linked.symlink_to(csv_path)
    with pytest.raises(ValueError, match="regular"):
        e.ingest(linked, metadata_path, tmp_path / "bad")
    e.ingest(csv_path, metadata_path, tmp_path / "good")
    with pytest.raises(FileExistsError):
        e.ingest(csv_path, metadata_path, tmp_path / "good")
    oversized = tmp_path / "large.csv"
    oversized.write_bytes(b"x" * (c.MAX_INPUT_BYTES + 1))
    with pytest.raises(ValueError, match="budget"):
        e.ingest(oversized, metadata_path, tmp_path / "large")


@pytest.mark.parametrize("kind,offset,outcome,support", [("declared_measured", 0.0, "EMPIRICALLY_COMPATIBLE", True), ("declared_measured", 0.1, "INCOMPATIBLE", False)])
def test_declared_measurements_only_conditional_domain_limited_support(tmp_path, model, kind, offset, outcome, support):
    csv_path, metadata_path, _ = inputs(tmp_path, model, kind=kind, offset=offset)
    e.ingest(csv_path, metadata_path, tmp_path / "ingested")
    result = e.compare(model[0], tmp_path / "ingested", tmp_path / "compared")
    assert result["outcome"] == outcome and result["conditional_measured_support"] is support
    assert result["authority"]["measurement_authenticity"] == "operator_declaration_only"
    assert result["authority"]["physical_validation"] == "not_established"


@pytest.mark.parametrize("mutate", [lambda m: m["uncertainty"]["model_discrepancy"].update(matrix=None), lambda m: m["clock"].update(offset_standard_uncertainty_s=None),
                                  lambda m: m["uncertainty"]["measurement"].update(matrix=[[0.0]*3 for _ in range(3)])])
def test_unknown_or_singular_uncertainty_is_inconclusive(tmp_path, model, mutate):
    csv_path, metadata_path, _ = inputs(tmp_path, model, mutate=mutate)
    e.ingest(csv_path, metadata_path, tmp_path / "ingested")
    result = e.compare(model[0], tmp_path / "ingested", tmp_path / "compared")
    assert result["status"] == "LOCAL" and result["outcome"] == "INCONCLUSIVE"
    assert result["conditional_measured_support"] is False


def test_clock_envelope_no_extrapolation_or_request_mismatch(tmp_path, model):
    for label, mutate, match in (("time", lambda m: m["clock"].update(offset_s=1.0), "inside"),
                                 ("uncertainty", lambda m: m["clock"].update(offset_standard_uncertainty_s=1.0), "inside"),
                                 ("request", lambda m: m.update(target_request_digest="sha256:"+"0"*64), "different")):
        root = tmp_path / label
        csv_path, metadata_path, _ = inputs(root, model, mutate=mutate)
        e.ingest(csv_path, metadata_path, root / "ingested")
        with pytest.raises(ValueError, match=match):
            e.compare(model[0], root / "ingested", root / "rejected")
        assert not (root / "rejected").exists()


def test_common_clock_offset_retains_cross_time_covariance(tmp_path, model):
    csv_path, metadata_path, _ = inputs(tmp_path, model, mutate=lambda m: m["clock"].update(offset_standard_uncertainty_s=0.001))
    e.ingest(csv_path, metadata_path, tmp_path / "ingested")
    e.compare(model[0], tmp_path / "ingested", tmp_path / "compared")
    _, candidate, _ = e._load(tmp_path / "compared")
    data = candidate["data"]
    expected = np.outer(data["prediction_slopes"], data["prediction_slopes"]) * 1e-6
    assert np.array_equal(data["covariance"]["clock_common_offset"], expected)
    assert expected[0, 1] != 0 and data["statistics"]["degrees_of_freedom"] == 3


def test_resealed_candidate_tamper_cannot_pass_fresh_independent_verifier(comparison):
    root, _, _ = comparison
    session, candidate, _ = e._load(root / "compared")
    forged = deepcopy(candidate)
    data = forged["data"]
    data["predicted"][0] += 0.0001
    data["residual"][0] = data["observed"][0] - data["predicted"][0]
    forged["data"] = seal({k:v for k,v in data.items() if k != "record_digest"})
    forged = seal({k:v for k,v in forged.items() if k != "record_digest"})
    e._candidate(session.run, {"candidate": forged})
    verified = e._verify(session.run, {"candidate": forged})
    assert verified["report"]["qualification"] == "REFUSE"
    assert verified["report"]["checks"]["independent_projection"] is False


def test_metadata_receipt_tamper_and_source_resealed_tamper(comparison):
    root, _, _ = comparison
    source = deepcopy(e._load(root / "ingested")[0].run)
    source["channels"]["head1_m"]["values"][0] += 1.0
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError, match="exactly"):
        e.validate_source(source)


@pytest.mark.parametrize("profile", ["wave", "fsi", "molecular", "sph"])
def test_unsupported_observation_operator_refuses_expansion(profile):
    with pytest.raises(ValueError, match="EXPAND"):
        e.template(profile)


@pytest.mark.parametrize("df,x,expected", [(1,3.841458820694124,0.05),(2,5.991464547107979,0.05),(3,7.814727903251179,0.05),(4,9.487729036781154,0.05),(10,18.307038053275146,0.05)])
def test_chi_square_survival_against_declared_nist_critical_values(df,x,expected):
    assert statistics.chi_square_survival(x,df) == pytest.approx(expected,abs=2e-14)
    assert statistics.critical_value(expected,df) == pytest.approx(x,abs=2e-12)


def test_correlations_across_channels_and_times_change_aggregate_statistic(tmp_path, model):
    metadata = e.template()["metadata"]
    metadata["target_request_digest"] = digest(model[1])
    fields = ["head1_m", "piston_displacement_m"]
    metadata["observation_operator"]["channels"] = [{"column": field,"model_field": field,"unit":"m"} for field in fields]
    axes = ["s"+str(i)+"/"+field for i in range(3) for field in fields]
    metadata["uncertainty"]["axes"] = axes
    for term in c.TERMS:
        metadata["uncertainty"][term]["matrix"] = [[0.0]*6 for _ in range(6)]
    metadata["uncertainty"]["measurement"]["matrix"] = [[1e-8 if i==j else 0.5e-8 for j in range(6)] for i in range(6)]
    output = io.StringIO(newline="")
    writer = csv.writer(output); writer.writerow(["sample_id","time_s","role",*fields])
    for i,index in enumerate((8,24,40)):
        writer.writerow(["s"+str(i),model[2]["time_s"][index],"holdout",*[model[2][field][index]+1e-4 for field in fields]])
    raw=output.getvalue();metadata["csv_sha256"]="sha256:"+sha256(raw.encode()).hexdigest()
    (tmp_path/'input.csv').write_bytes(raw.encode());(tmp_path/'input.json').write_text(json.dumps(metadata))
    e.ingest(tmp_path/'input.csv',tmp_path/'input.json',tmp_path/'ingested')
    result=e.compare(model[0],tmp_path/'ingested',tmp_path/'compared')
    assert result['statistics']['degrees_of_freedom']==6
    assert result['statistics']['chi_square']==pytest.approx(6/(1+5*0.5),rel=1e-12)
    assert result['statistics']['chi_square'] != pytest.approx(6.0)


def test_holdout_cannot_define_its_own_uncertainty(tmp_path, model):
    csv_path,metadata_path,_=inputs(tmp_path,model,mutate=lambda m:m['uncertainty']['model_discrepancy'].update(source_refs=[m['csv_sha256']]))
    with pytest.raises(ValueError,match='own uncertainty'):
        e.ingest(csv_path,metadata_path,tmp_path/'rejected')


def test_session_partial_selection_is_refused_as_complete_observation_request(comparison,tmp_path):
    root,_,_=comparison
    session,candidate,_=e._load(root/'compared')
    live=Session(session.run,tmp_path/'selected',operations=e.registry())
    live.selection['interval_s']=[0.0,session.run['time_s'][1]]
    reply=e._execute(live,e.COMPARE_OPERATION,candidate['parameters'])
    assert reply['status']=='refused' and not live.results
    assert 'complete declared observation interval' in reply['execution']['refusal']['message']


def test_cli_experiment_lifecycle_and_saved_audit(comparison,tmp_path,capsys):
    from ciw import fluid_cli
    root,_,_=comparison
    path=tmp_path/'template.json'
    assert fluid_cli.main(['experiment','template','--output',str(path)])==0
    assert read_json(path)['metadata']['provenance']['source_kind']=='synthetic_fixture'
    assert fluid_cli.main(['experiment','template','--output',str(path)])==1
    assert fluid_cli.main(['experiment','inspect',str(root/'compared')])==0
    audit=tmp_path/'audit.json'
    assert fluid_cli.main(['experiment','verify',str(root/'compared'),'--output',str(audit)])==0
    data=read_json(audit)
    assert data['fresh_verification_record']['verification_id']==data['fresh_verification_id']
    assert data['fresh_verification_record']['fresh_model_verification']['record']['verification_id'] != e._load(root/'compared')[1]['parameters']['model']['fresh_verification']['verification_id']
    assert data['conditional_measured_support'] is False
    capsys.readouterr()
