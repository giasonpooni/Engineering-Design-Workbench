"""End-to-end evidence, identity, refusal, inspection and replay boundaries."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from ciw import net, weather_contract as contract, weather_workflow as workflow
from ciw.control_contracts import load, save_new
from ciw.core.identities import new_identity
from ciw.operations.runner import seal
from ciw.session import Session


def profiles():
    return sorted(contract.providers())


@pytest.mark.parametrize("profile", profiles())
def test_profile_full_lifecycle_and_separate_identities(tmp_path, profile):
    request = contract.example_request(profile)
    directory = tmp_path / "first"
    result = workflow.run(request, directory)
    assert result["status"] == "LOCAL", result
    assert all(result["checks"].values())
    assert result["context"]["source_kind"] == "synthetic"
    identities = [result[k] for k in ("evidence_id", "execution_id", "result_id",
                                      "verification_execution_id", "verification_id")]
    assert len(set(identities)) == len(identities)
    assert result["fresh_execution"] is result["fresh_numerical_verification"] is False
    before = {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    module, _ = contract.profile(profile)
    with patch.object(module, "compute", side_effect=AssertionError("inspect computed")), \
            patch.object(module, "checks", side_effect=AssertionError("inspect checked")):
        assert workflow.inspect(directory) == result
        Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    verified = workflow.verify_retained(directory)
    assert verified["fresh_numerical_verification"] is True
    replay = workflow.replay(directory, tmp_path / "second")
    assert replay["status"] == "PASS" and replay["result_digest_matches"]
    assert replay["source_execution_id"] != replay["replay_execution_id"]
    output = tmp_path / "export.json"
    assert workflow.export_result(directory, output)["status"] == "exported"
    assert load(output)["values"] == result["values"]
    assert before == {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    assert result["authority"] == contract.AUTHORITY


def test_catalog_visible_from_net_and_every_example_is_detached(capsys):
    assert net.main(["weather", "catalog"]) == 0
    assert set(json.loads(capsys.readouterr().out)["profiles"]) == set(profiles())
    for name in profiles():
        example = contract.example_request(name)
        example["inputs"].clear()
        assert contract.example_request(name)["inputs"]


def test_cli_journey_and_create_only_publication(tmp_path, capsys):
    request, run, replay, export = [tmp_path / name for name in ("request.json", "run", "replay", "export.json")]
    commands = [
        ["example", "thermodynamics", "--output", str(request)],
        ["run", str(request), "--output-dir", str(run)],
        ["inspect", str(run)], ["verify", str(run)],
        ["replay", str(run), "--output-dir", str(replay)],
        ["export", str(run), "--output", str(export)],
    ]
    for command in commands:
        assert net.main(["weather", *command]) == 0
        json.loads(capsys.readouterr().out)
    assert net.main(["weather", *commands[0]]) == 1
    assert json.loads(capsys.readouterr().err)["status"] == "REFUSE"
    assert net.main(["weather", *commands[1]]) == 1
    capsys.readouterr()


@pytest.mark.parametrize("failure", ["source", "candidate", "report", "authority"])
def test_tampered_bundle_refuses(tmp_path, failure):
    directory = tmp_path / "run"
    workflow.run(contract.example_request("thermodynamics"), directory)
    path = directory / "workspace.json"
    workspace = load(path)
    if failure == "source":
        workspace["run"]["metadata"]["weather_request"]["context"]["source_ref"] = "tampered"
    elif failure == "candidate":
        workspace["results"][0]["data"]["values"][next(iter(workspace["results"][0]["data"]["values"]))] = 0
    elif failure == "report":
        workspace["results"][1]["data"]["report"]["status"] = "FAIL"
    else:
        workspace["results"][0]["data"]["authority"]["state_admission"] = "performed"
    path.write_text(json.dumps(workspace))
    with pytest.raises(ValueError):
        workflow.inspect(directory)


def test_fresh_checker_catches_resealed_wrong_values_and_never_calls_compute():
    request = contract.example_request("thermodynamics")
    result = contract.calculate(request)
    name = next(iter(result["values"]))
    result["values"][name] += 100
    seal(result)
    module, _ = contract.profile(request["profile"])
    with patch.object(module, "compute", side_effect=AssertionError("checker invoked producer")):
        assert contract.check(request, result)["status"] == "FAIL"


def test_verification_requires_actual_retained_candidate(tmp_path):
    source = workflow.make_source(contract.example_request("radiation"))
    first = Session(source, tmp_path / "first", operations=workflow.registry())
    candidate = workflow._execute(first, contract.COMPUTE, {})["result"]
    second = Session(source, tmp_path / "second", operations=workflow.registry())
    result = workflow._execute(second, contract.VERIFY, {"candidate": candidate})
    assert result["status"] == "refused" and not second.results
    assert len(second.executions) == 1
    assert "retained" in result["execution"]["refusal"]["message"]


def test_forged_same_source_occurrence_is_not_accepted(tmp_path):
    source = workflow.make_source(contract.example_request("radiation"))
    session = Session(source, tmp_path / "session", operations=workflow.registry())
    candidate = workflow._execute(session, contract.COMPUTE, {})["result"]
    forged = deepcopy(candidate)
    forged["result_id"] = new_identity("result")
    seal(forged)
    assert workflow._execute(session, contract.VERIFY, {"candidate": forged})["status"] == "refused"


@pytest.mark.parametrize("kind", ["calculator", "checker"])
def test_provider_failure_retained_and_inspectable(tmp_path, kind):
    module, _ = contract.profile("radiation")
    with patch.object(module, "compute" if kind == "calculator" else "checks", side_effect=RuntimeError("failure")):
        result = workflow.run(contract.example_request("radiation"), tmp_path / "run")
    assert result["status"] == "REFUSE"
    assert result["refusals"][0]["code"] == "operation_failed"
    assert workflow.inspect(tmp_path / "run") == result
    with pytest.raises(ValueError):
        workflow.export_result(tmp_path / "run", tmp_path / "export.json")


def test_failed_numerical_check_is_retained_and_export_refuses(tmp_path):
    module, _ = contract.profile("radiation")
    with patch.object(module, "checks", return_value={"deliberate_failure": False}):
        result = workflow.run(contract.example_request("radiation"), tmp_path / "run")
    assert result["status"] == "REFUSE" and result["checks"] == {"deliberate_failure": False}
    with pytest.raises(ValueError):
        workflow.export_result(tmp_path / "run", tmp_path / "export.json")


def test_changed_runtime_prevents_replay(tmp_path):
    directory = tmp_path / "run"
    workflow.run(contract.example_request("radiation"), directory)
    with patch.object(workflow, "runtime_identity", return_value={"provider": "changed"}):
        with pytest.raises(ValueError, match="runtime identity"):
            workflow.replay(directory, tmp_path / "second")
    assert not (tmp_path / "second").exists()


def test_unknown_declaration_fields_and_claims_refused_before_write(tmp_path):
    for mutate in (lambda r: r.update(extra=True),
                   lambda r: r.update(profile="dynamic.module.name"),
                   lambda r: r["context"].update(source_kind="observed")):
        request = contract.example_request("radiation")
        mutate(request)
        with pytest.raises(ValueError):
            workflow.run(request, tmp_path / "run")
        assert not (tmp_path / "run").exists()


def test_duplicate_json_keys_rejected(tmp_path, capsys):
    request = tmp_path / "bad.json"
    request.write_text('{"schema":1,"schema":2}')
    assert net.main(["weather", "run", str(request), "--output-dir", str(tmp_path / "run")]) == 1
    assert json.loads(capsys.readouterr().err)["status"] == "REFUSE"


def test_weather_does_not_widen_existing_dry_atmosphere_scope():
    from ciw.atmosphere_contract import EXPANSION_OBSERVABLES, SUPPORTED_OBSERVABLES
    assert {"weather_forecast", "humidity", "precipitation", "radiation"} <= EXPANSION_OBSERVABLES
    assert "weather_forecast" not in SUPPORTED_OBSERVABLES


@pytest.mark.parametrize("profile", ["nwp_transport", "storm_sounding", "water_balance", "snow_ice"])
def test_static_result_contract_rejects_changed_array_shape(profile):
    request = contract.example_request(profile)
    result = contract.calculate(request)
    field = next(key for key, value in result["values"].items() if type(value) is list)
    result["values"][field].pop()
    seal(result)
    with pytest.raises(ValueError, match="array"):
        contract.validate_result(request, result)


def test_static_result_contract_rejects_scalar_replaced_by_array():
    request = contract.example_request("radiation")
    result = contract.calculate(request)
    field = next(iter(result["values"]))
    result["values"][field] = [result["values"][field]]
    seal(result)
    with pytest.raises(ValueError):
        contract.validate_result(request, result)
