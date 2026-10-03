"""Independent regression audit of moist/dry boundaries on retained Sessions."""
from contextlib import ExitStack
from copy import deepcopy
import csv
from hashlib import sha256
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from ciw import atmosphere_workflow as workflow
from ciw.atmosphere_contract import example_request as dry_request
from ciw.core.identities import evidence_id, new_identity
from ciw.operations.registry import default_registry
from ciw.operations.runner import check_seal, digest, seal
from ciw.session import Session, read_json, write_json

MOIST_COMPILE = "atmosphere.moist-compile.v1"
MOIST_VERIFY = "atmosphere.moist-verify.v1"
MIXING_RATIO = "water_mixing_ratio_kg_per_kg_dry_air"


def moist_request():
    from ciw.atmosphere_moist_contract import example_request
    return example_request()


@pytest.fixture(scope="module")
def retained_moist(tmp_path_factory):
    directory = tmp_path_factory.mktemp("moist-integration-audit") / "column"
    return directory, workflow.run(moist_request(), directory)


@pytest.fixture(scope="module")
def alternate_moist(tmp_path_factory):
    request = moist_request()
    request["reference"]["temperature_k"] = 303.15
    request["profile"]["wind_enu_m_per_s"] = [12.0, -5.0, 1.0]
    directory = tmp_path_factory.mktemp("moist-audit-alternate") / "column"
    return directory, workflow.run(request, directory)


@pytest.fixture(scope="module")
def retained_dry(tmp_path_factory):
    directory = tmp_path_factory.mktemp("dry-runtime-integration-audit") / "column"
    return directory, workflow.run(dry_request(), directory)


def _contents(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def _no_providers(*, verifier=True, operations=True):
    stack = ExitStack()
    for namespace in ("atmosphere", "atmosphere_moist"):
        stack.enter_context(patch(f"ciw.{namespace}_compiler.compile_atmosphere",
                                  side_effect=AssertionError("atmospheric compiler replay")))
        if verifier:
            stack.enter_context(patch(f"ciw.{namespace}_verification.verify",
                                      side_effect=AssertionError("atmospheric verifier replay")))
    if operations:
        stack.enter_context(patch("ciw.session.execute_operation",
                                  side_effect=AssertionError("operation replay")))
    return stack


def _occurrences(directory):
    workspace = read_json(directory / "workspace.json")
    results = {row["operation_id"]: row for row in workspace["results"]}
    executions = {row["operation_id"]: row for row in workspace["executions"]}
    return workspace, results, executions


def _rewrite_runtime(directory, operation, changes):
    """Coherently relabel metadata without introducing a stale-content error."""
    workspace, results, executions = _occurrences(directory)
    result = results[operation]
    result["runtime"].update(deepcopy(changes))
    executions[operation]["runtime"] = deepcopy(result["runtime"])
    seal(result)
    seal(executions[operation])
    if operation in {workflow.COMPILE, MOIST_COMPILE}:
        verify_id = workflow.VERIFY if operation == workflow.COMPILE else MOIST_VERIFY
        verification = results[verify_id]
        verification["parameters"]["candidate"] = deepcopy(result)
        verification["data"]["candidate_record_digest"] = result["record_digest"]
        executions[verify_id]["parameters"] = deepcopy(verification["parameters"])
        seal(verification)
        seal(executions[verify_id])
        write_json(directory / "verification.json", verification["data"])
    write_json(directory / "workspace.json", workspace)


def test_original_dry_declaration_and_scientific_providers_remain_unchanged():
    """Golden identities were captured at the published dry-only e352164 head."""
    from ciw import atmosphere_contract, atmosphere_compiler, atmosphere_verification
    request = dry_request()
    source = workflow.make_source(request)
    result = atmosphere_compiler.compile_atmosphere(request)
    report = atmosphere_verification.verify(request, result)
    assert digest(request) == "sha256:9dd2d97878dbab940cc21ae6c769746bf4da2c004887267506bcc06f891e7941"
    assert digest(source) == "sha256:cdf22582bfbd63823f5b7f6d77449c49100de65d0674827c12cfe42033874466"
    assert source["evidence_id"] == "sha256:8924fac8ec43317fcda417210e7784d5c08462a61190aa5753f2e66183d2fd20"
    # Preserve exact scientific provider implementations while permitting each
    # platform's original libm rounding. CRLF checkout does not alter identity.
    for module, expected in (
        (atmosphere_contract, "8d5e39e1316d85b37f5c693b935734aba8b173de6b445957f77a1a9616624a05"),
        (atmosphere_compiler, "cecef496f0c12676430df7b41020bce8d0beff7607229b6e057105d6f6fc00f0"),
        (atmosphere_verification, "963963f13a194a4fe35cf7ced4dcb76c32ff004c598bc410e69cb310b06e821d"),
    ):
        original_bytes = Path(module.__file__).read_bytes().replace(b"\r\n", b"\n")
        assert sha256(original_bytes).hexdigest() == expected
    assert result["schema"] == "ciw.atmosphere-result.v1"
    assert report["qualification"]["action"] == "LOCAL"
    assert len(report["checks"]) == 17


def test_moist_operations_are_explicit_and_never_mutate_default_or_impact_registry():
    from ciw import impact_workflow
    assert {row["operation_id"] for row in default_registry().describe()} == {
        "statistics.v1", "spectrum.periodogram.v1"}
    roles = {row["operation_id"]: row["role"] for row in workflow.registry().describe()}
    assert roles[MOIST_COMPILE] == "backend"
    assert roles[MOIST_VERIFY] == "verification"
    assert {MOIST_COMPILE, MOIST_VERIFY}.isdisjoint(
        row["operation_id"] for row in impact_workflow.registry().describe())


@pytest.mark.parametrize("phase", ["backend", "verification"])
@pytest.mark.parametrize("direction", ["dry_to_moist", "moist_to_dry"])
def test_dry_and_moist_operations_reject_cross_profile_before_entering_provider(
        tmp_path, phase, direction):
    if direction == "dry_to_moist":
        source = workflow.make_source(dry_request())
        operation = (MOIST_COMPILE, MOIST_VERIFY)[phase == "verification"]
    else:
        source = workflow.make_source(moist_request())
        operation = (workflow.COMPILE, workflow.VERIFY)[phase == "verification"]
    session = Session(source, tmp_path / "session", operations=workflow.registry())
    with _no_providers(operations=False):
        refused = workflow._execute(session, operation, {})
        assert refused["status"] == "refused"
        assert refused["execution"]["refusal"]["code"] == "invalid_operation"
        assert not session.results and len(session.executions) == 1
        session.save_workspace(tmp_path / "refused.json")
        restored = Session.from_workspace(tmp_path / "refused.json", tmp_path / "restored")
    assert not restored.results and len(restored.executions) == 1


@pytest.mark.parametrize("profile", ["elastic", "crush", "plate"])
@pytest.mark.parametrize("phase", ["backend", "verification"])
@pytest.mark.parametrize("direction", ["moist_to_impact", "impact_to_moist"])
def test_moist_and_impact_operations_reject_before_entering_either_numerical_provider(
        tmp_path, profile, phase, direction):
    from ciw import impact_workflow
    from ciw.impact_contract import example_request as elastic_request
    from ciw.impact_crush_contract import example_request as crush_request
    from ciw.impact_plate_contract import example_request as plate_request
    factories = {"elastic": elastic_request, "crush": crush_request, "plate": plate_request}
    identifiers = {
        "elastic": (impact_workflow.SIMULATE, impact_workflow.VERIFY),
        "crush": (impact_workflow.CRUSH_SIMULATE, impact_workflow.CRUSH_VERIFY),
        "plate": (impact_workflow.PLATE_SIMULATE, impact_workflow.PLATE_VERIFY),
    }
    if direction == "moist_to_impact":
        source = workflow.make_source(moist_request())
        operation = identifiers[profile][phase == "verification"]
    else:
        source = impact_workflow.make_source(factories[profile]())
        operation = (MOIST_COMPILE, MOIST_VERIFY)[phase == "verification"]
    registry = workflow.registry()
    for operation_binding in impact_workflow.operations():
        registry.register(operation_binding)
    session = Session(source, tmp_path / "session", operations=registry)
    with ExitStack() as stack:
        stack.enter_context(_no_providers(operations=False))
        for namespace in ("impact", "impact_crush", "impact_plate"):
            stack.enter_context(patch(f"ciw.{namespace}_solver.simulate",
                                      side_effect=AssertionError("impact solver entered")))
            stack.enter_context(patch(f"ciw.{namespace}_verification.verify",
                                      side_effect=AssertionError("impact verifier entered")))
        refused = workflow._execute(session, operation, {})
        assert refused["status"] == "refused"
        assert refused["execution"]["refusal"]["code"] == "invalid_operation"
        assert not session.results and len(session.executions) == 1


def test_moist_source_declares_one_configuration_and_never_relabels_profile_as_evidence():
    request = moist_request()
    with _no_providers():
        source = workflow.make_source(request)
        assert workflow.source_request(source) == request
    assert source["time_s"] == [0.0]
    assert source["metadata"]["sample_count"] == 1
    assert source["metadata"]["manifest"]["supported_operations"] == [MOIST_COMPILE, MOIST_VERIFY]
    assert all(len(row["values"]) == 1 for row in source["channels"].values())
    assert not {"relative_humidity", "humidity", "liquid_equilibrium_dew_point_k",
                "water_vapour_pressure_pa", "density_kg_per_m3"} & set(source["channels"])
    assert source["evidence_id"] != workflow.make_source(dry_request())["evidence_id"]


@pytest.mark.parametrize("mutation", ["water", "origin", "wind", "source", "time"])
def test_moist_declaration_and_source_context_changes_bind_new_evidence(mutation):
    request = moist_request()
    original = workflow.make_source(request)
    if mutation == "water":
        request["profile"][MIXING_RATIO] = 0.01
    elif mutation == "origin":
        request["reference"]["height_origin_m"] = 1500.0
    elif mutation == "wind":
        request["profile"]["wind_enu_m_per_s"] = [8.0, -4.0, 1.0]
    elif mutation == "source":
        request["reference"]["context"]["source_ref"] = "declared.moist-boundary"
        request["reference"]["context"]["source_kind"] = "declared_environment"
    else:
        request["reference"]["context"]["valid_time_utc"] = "2026-10-03T06:00:00Z"
    changed = workflow.make_source(request)
    assert changed["evidence_id"] != original["evidence_id"]
    assert changed["run_id"] != original["run_id"]
    assert workflow.source_request(changed) == request


def test_moist_inspection_and_generic_reopen_never_replay_providers_or_activate_ops(
        tmp_path, retained_moist):
    directory, original = retained_moist
    before = _contents(directory)
    with _no_providers():
        assert workflow.inspect(directory) == original
        restored = Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert _contents(directory) == before
    assert len(restored.results) == len(restored.executions) == 2
    assert {MOIST_COMPILE, MOIST_VERIFY}.isdisjoint(
        row["operation_id"] for row in restored.operations.describe())


@pytest.mark.parametrize("command", ["verify", "csv", "handoff"])
def test_moist_fresh_commands_use_one_validated_snapshot(
        tmp_path, retained_moist, alternate_moist, command):
    first = workflow._read(retained_moist[0])
    second = workflow._read(alternate_moist[0])
    with patch.object(workflow, "_read", side_effect=[first, second]) as read:
        if command == "verify":
            checked = workflow.verify_retained(retained_moist[0])
            assert checked["result_id"] == first[1]["result_id"]
            assert checked["evidence_id"] == first[0].run["evidence_id"]
            assert checked["recomputed_report_digest"] == first[2]["data"]["report"]["record_digest"]
        elif command == "csv":
            output = tmp_path / "single-snapshot.csv"
            exported = workflow.export_csv(retained_moist[0], output)
            header, *rows = list(csv.reader(output.read_text(encoding="utf-8").splitlines()))
            index = header.index("relative_humidity")
            assert float(rows[0][index]) == first[1]["data"]["profile"]["relative_humidity"][0]
            assert float(rows[0][index]) != second[1]["data"]["profile"]["relative_humidity"][0]
            assert exported["source_result_id"] == first[1]["result_id"]
        else:
            output = tmp_path / "single-snapshot.json"
            workflow.export_handoff(retained_moist[0], output, sample_index=0, provider="impact")
            payload = read_json(output)
            assert payload["source_evidence_id"] == first[0].run["evidence_id"]
            assert payload["source_result_id"] == first[1]["result_id"]
            assert payload["source_record_digest"] == first[1]["record_digest"]
            assert payload["verification_id"] == first[2]["data"]["verification_id"]
            assert payload["recomputed_report_digest"] == first[2]["data"]["report"]["record_digest"]
            assert payload["environment"]["relative_humidity"] == first[1]["data"]["profile"]["relative_humidity"][0]
            assert payload["environment"]["relative_humidity"] != second[1]["data"]["profile"]["relative_humidity"][0]
        assert read.call_count == 1


def test_fresh_moist_verification_and_exports_are_read_only_and_preserve_occurrence_ids(
        tmp_path, retained_moist):
    directory, original = retained_moist
    before = _contents(directory)
    with _no_providers(verifier=False):
        checked = workflow.verify_retained(directory)
        exported = workflow.export_csv(directory, tmp_path / "column.csv")
        handed_off = workflow.export_handoff(directory, tmp_path / "boundary.json",
                                            sample_index=1, provider="fluid")
    assert checked["status"] == "LOCAL"
    assert checked["fresh_numerical_verification"] is True
    assert checked["fresh_execution"] is False
    for key in ("evidence_id", "result_id", "execution_id", "verification_id"):
        assert checked[key] == original[key]
    assert exported["source_result_id"] == handed_off["source_result_id"] == original["result_id"]
    assert exported["source_execution_id"] == handed_off["source_execution_id"] == original["execution_id"]
    assert _contents(directory) == before


@pytest.mark.parametrize("provider", ["impact", "fluid", "render"])
def test_moist_handoff_preserves_exact_composition_without_transport_or_receiver_claims(
        tmp_path, retained_moist, provider):
    from ciw.atmosphere_moist_contract import FRAME
    directory, original = retained_moist
    before = _contents(directory)
    output = tmp_path / (provider + ".json")
    with _no_providers(verifier=False):
        exported = workflow.export_handoff(directory, output, sample_index=2, provider=provider)
    payload = read_json(output)
    check_seal(payload)
    _, candidate, _ = workflow._read(directory)
    assert payload["schema"] == "ciw.atmosphere-moist-handoff.v1"
    assert payload["composition"] == "dry_air_water_vapour"
    assert payload["frame"] == FRAME
    assert payload["context"] == moist_request()["reference"]["context"]
    assert payload["height_m"] == 500.0
    assert payload["absolute_height_m"] == payload["reference_height_origin_m"] + 500.0
    assert payload["environment"]["relative_humidity"] == candidate["data"]["profile"]["relative_humidity"][2]
    assert payload["environment"][MIXING_RATIO] == candidate["data"]["mixture"][MIXING_RATIO]
    assert payload["environment"]["water_mass_fraction"] == candidate["data"]["mixture"]["water_mass_fraction"]
    assert not {"dynamic_viscosity_pa_s", "kinematic_viscosity_m2_per_s", "material_temperature"} & set(payload["environment"])
    for claim in ("physical_validation_established", "receiver_model_validated",
                  "material_conditioning_established", "forces_computed",
                  "visual_scattering_established", "canonical_state_mutated",
                  "state_admission_performed", "execution_authority",
                  "coordinate_transfer_validated", "geodetic_transform_performed",
                  "moist_transport_law_established", "phase_change_established",
                  "wmo_humidity_conformance_established"):
        assert payload["claims"][claim] is False
    assert payload["claims"]["data_only_environmental_boundary"] is True
    assert payload["source_result_id"] == exported["source_result_id"] == original["result_id"]
    assert payload["source_execution_id"] == original["execution_id"]
    effects = {row["property"]: row["effect"] for row in payload["effects"]}
    assert effects["material_conditioning"] == effects["fluid_dynamics"] == "FORGET"
    assert effects["weather_evolution"] == "FORGET"
    assert effects["transport_law"] == effects["phase_change"] == effects["latent_heat"] == "FORGET"
    assert payload["receiver_requirements"]
    assert _contents(directory) == before


@pytest.mark.parametrize("mutation", ["mixing_ratio", "humidity", "unit", "frame", "context", "claim_alias"])
def test_resealed_moist_handoff_cannot_change_composition_humidity_or_receiver_boundary(
        tmp_path, retained_moist, mutation):
    from ciw.atmosphere_moist_handoff import BINDING_KEYS, validate_handoff
    output = tmp_path / "boundary.json"
    workflow.export_handoff(retained_moist[0], output, sample_index=0, provider="fluid")
    payload = read_json(output)
    _, candidate, _ = workflow._read(retained_moist[0])
    bindings = {name: payload[name] for name in BINDING_KEYS}
    if mutation == "mixing_ratio":
        payload["environment"][MIXING_RATIO] *= 1.001
    elif mutation == "humidity":
        payload["environment"]["relative_humidity"] *= 1.001
    elif mutation == "unit":
        payload["units"]["relative_humidity"] = "%"
    elif mutation == "frame":
        payload["frame"] = "receiver.world.v1"
    elif mutation == "context":
        payload["context"]["valid_time_utc"] = "2026-10-03T08:00:00Z"
    else:
        payload["claims"]["moist_transport_law_established"] = 0
    seal(payload)
    with _no_providers(), pytest.raises(ValueError):
        validate_handoff(moist_request(), candidate["data"], payload, bindings)


@pytest.mark.parametrize("mutation", ["channel", "unit", "instrument", "derived_humidity"])
def test_reidentified_moist_source_cannot_override_exact_configuration_declaration(mutation):
    source = workflow.make_source(moist_request())
    name = next(iter(source["channels"]))
    if mutation == "channel":
        source["channels"][name]["values"][0] = 2.0
    elif mutation == "unit":
        source["channels"][name]["unit"] = "mm"
        source["metadata"]["manifest"]["units"][name] = "mm"
    elif mutation == "instrument":
        source["instrument"] = "fabricated-moist-observations.v1"
    else:
        source["channels"]["measured_relative_humidity"] = {"unit": "1", "values": [0.5]}
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError):
        workflow.source_request(source)


@pytest.mark.parametrize("observable", ["viscosity", "clouds", "phase_change", "moist_adiabatic_response"])
def test_moist_requested_unsupported_physics_expands_after_pass_and_blocks_exports(
        tmp_path, observable):
    request = moist_request()
    request["desired_observables"].append(observable)
    directory = tmp_path / "expanded"
    inspected = workflow.run(request, directory)
    assert inspected["status"] == "EXPAND"
    assert all(row["status"] == "PASS" for row in inspected["checks"])
    assert inspected["authority"]["state_admission"] == "not_performed"
    for name, exporter in (
        ("expanded.csv", lambda output: workflow.export_csv(directory, output)),
        ("expanded.json", lambda output: workflow.export_handoff(
            directory, output, sample_index=0, provider="fluid")),
    ):
        output = tmp_path / name
        with pytest.raises(ValueError):
            exporter(output)
        assert not output.exists()


@pytest.mark.parametrize("height_grid", [[0.0, 2000.0], [0.0, 500.0, 1000.0, 1500.0, 2000.0]])
def test_saturation_failure_is_retained_and_refuses_before_expansion_on_sparse_or_dense_grid(
        tmp_path, height_grid):
    request = moist_request()
    request["reference"].update(temperature_k=293.15, pressure_pa=110000.0)
    request["profile"][MIXING_RATIO] = 0.02
    request["sampling"]["height_m"] = height_grid
    request["desired_observables"].extend(["clouds", "viscosity"])
    directory = tmp_path / "saturated"
    inspected = workflow.run(request, directory)
    assert inspected["status"] == "REFUSE"
    assert any(row["status"] == "FAIL" for row in inspected["checks"])
    session, candidate, verification = workflow._read(directory)
    assert len(session.executions) == len(session.results) == 2
    assert max(candidate["data"]["profile"]["relative_humidity"]) > 1.0
    assert verification["data"]["report"]["qualification"]["action"] == "REFUSE"
    assert len(candidate["data"]["profile"]["relative_humidity"]) == len(height_grid)
    assert not {"condensate", "cloud_water", "dynamic_viscosity_pa_s"} & set(candidate["data"]["profile"])
    with _no_providers():
        assert workflow.inspect(directory) == inspected
    for name, exporter in (
        ("saturated.csv", lambda output: workflow.export_csv(directory, output)),
        ("saturated.json", lambda output: workflow.export_handoff(
            directory, output, sample_index=0, provider="impact")),
    ):
        output = tmp_path / name
        with pytest.raises(ValueError):
            exporter(output)
        assert not output.exists()


def test_near_ceiling_humidity_cannot_be_clipped_into_local_by_quadrature_bias(tmp_path):
    """A finite Simpson bias must not turn the independent domain guard off."""
    from ciw.atmosphere_moist_compiler import compile_atmosphere
    request = moist_request()
    request["profile"][MIXING_RATIO] = 0.010478377852971083
    request["sampling"]["height_m"] = [0.0, 2000.0]
    request["tolerances"]["constitutive_relative"] = 0.01
    request["desired_observables"].append("clouds")
    candidate = compile_atmosphere(request)
    assert candidate["profile"]["relative_humidity"][-1] > 0.95
    # The true candidate lies just above the hard envelope. Its tiny changed
    # humidity can satisfy ordinary constitutive tolerances; those tolerances
    # must never relax the independent unsaturation domain.
    candidate["profile"]["relative_humidity"][-1] = 0.95
    seal(candidate)
    directory = tmp_path / "near-ceiling"
    with patch("ciw.atmosphere_moist_compiler.compile_atmosphere", return_value=candidate):
        inspected = workflow.run(request, directory)
    assert inspected["status"] == "REFUSE"
    assert any(row["status"] == "FAIL" for row in inspected["checks"])
    for name, exporter in (
        ("ceiling.csv", lambda output: workflow.export_csv(directory, output)),
        ("ceiling.json", lambda output: workflow.export_handoff(
            directory, output, sample_index=1, provider="fluid")),
    ):
        output = tmp_path / name
        with pytest.raises(ValueError):
            exporter(output)
        assert not output.exists()


@pytest.mark.parametrize("lapse", [0.0, 5e-324, 0.0065])
def test_zero_water_limit_matches_prior_dry_fields_on_the_same_runtime(lapse):
    from ciw.atmosphere_compiler import compile_atmosphere as dry_compile
    from ciw.atmosphere_moist_compiler import compile_atmosphere as moist_compile
    request = moist_request()
    request["profile"].update({MIXING_RATIO: 0.0, "lapse_rate_k_per_m": lapse})
    dry = dry_request()
    dry["reference"].update(deepcopy(request["reference"]))
    dry["profile"].update(lapse_rate_k_per_m=lapse,
                          wind_enu_m_per_s=request["profile"]["wind_enu_m_per_s"])
    dry["sampling"] = deepcopy(request["sampling"])
    moist_profile = moist_compile(request)["profile"]
    dry_profile = dry_compile(dry)["profile"]
    for field in ("height_m", "temperature_k", "pressure_pa", "density_kg_per_m3", "wind_enu_m_per_s"):
        assert moist_profile[field] == dry_profile[field]
    assert moist_profile["frozen_sound_speed_m_per_s"] == dry_profile["sound_speed_m_per_s"]
    assert moist_profile["frozen_potential_temperature_k"] == dry_profile["potential_temperature_k"]
    assert moist_profile["relative_humidity"] == [0.0] * len(dry_profile["height_m"])
    assert moist_profile["liquid_equilibrium_dew_point_k"] == [None] * len(dry_profile["height_m"])
    assert "dynamic_viscosity_pa_s" not in moist_profile


def test_zero_water_csv_and_handoff_retain_null_dew_point_without_transport_law(tmp_path):
    request = moist_request()
    request["profile"][MIXING_RATIO] = 0.0
    directory = tmp_path / "zero-water"
    assert workflow.run(request, directory)["status"] == "LOCAL"
    output = tmp_path / "dry-limit.csv"
    workflow.export_csv(directory, output)
    header, *rows = list(csv.reader(output.read_text(encoding="utf-8").splitlines()))
    dew_point_column = header.index("liquid_equilibrium_dew_point_k")
    assert all(row[dew_point_column] == "" for row in rows)
    assert "dynamic_viscosity_pa_s" not in header
    handed_off = tmp_path / "dry-limit.json"
    workflow.export_handoff(directory, handed_off, sample_index=0, provider="impact")
    payload = read_json(handed_off)
    assert payload["environment"]["liquid_equilibrium_dew_point_k"] is None
    assert "dynamic_viscosity_pa_s" not in payload["environment"]


@pytest.mark.parametrize("sample_index,provider", [(True, "impact"), (-1, "impact"),
                                                   (129, "impact"), (0, "importlib.weather")])
def test_invalid_moist_handoff_selector_rejects_before_numerical_replay_or_output(
        tmp_path, retained_moist, sample_index, provider):
    output = tmp_path / "invalid.json"
    with _no_providers(), pytest.raises(ValueError):
        workflow.export_handoff(retained_moist[0], output, sample_index=sample_index, provider=provider)
    assert not output.exists()


def test_coherent_forged_humidity_needs_fresh_verification_before_every_export(
        tmp_path, retained_moist):
    from ciw.atmosphere_moist_preservation import build
    directory = tmp_path / "forged"
    shutil.copytree(retained_moist[0], directory)
    workspace, results, executions = _occurrences(directory)
    candidate, verification = results[MOIST_COMPILE], results[MOIST_VERIFY]
    # An interior humidity change leaves extrema and terminal summaries intact.
    candidate["data"]["profile"]["relative_humidity"][1] *= 1.001
    seal(candidate["data"])
    seal(candidate)
    payload = verification["data"]
    report = payload["report"]
    report["candidate_digest"] = candidate["data"]["record_digest"]
    seal(report)
    verification["parameters"]["candidate"] = deepcopy(candidate)
    payload["candidate_record_digest"] = candidate["record_digest"]
    executions[MOIST_VERIFY]["parameters"] = deepcopy(verification["parameters"])
    seal(verification)
    seal(executions[MOIST_VERIFY])
    write_json(directory / "workspace.json", workspace)
    write_json(directory / "verification.json", payload)
    write_json(directory / "preservation.json", build(moist_request(), candidate["data"], report))
    before = _contents(directory)
    with _no_providers():
        assert workflow.inspect(directory)["status"] == "LOCAL"
    with _no_providers(verifier=False), pytest.raises(ValueError, match="recomputation differs"):
        workflow.verify_retained(directory)
    for name, exporter in (
        ("forged.csv", lambda output: workflow.export_csv(directory, output)),
        ("forged.json", lambda output: workflow.export_handoff(
            directory, output, sample_index=1, provider="impact")),
    ):
        output = tmp_path / name
        with pytest.raises(ValueError, match="recomputation differs"):
            exporter(output)
        assert not output.exists()
    assert _contents(directory) == before


def test_duplicate_moist_scientific_verification_identity_is_rejected_by_generic_session(
        tmp_path, retained_moist):
    directory = tmp_path / "duplicate"
    shutil.copytree(retained_moist[0], directory)
    workspace, results, executions = _occurrences(directory)
    duplicated = deepcopy(results[MOIST_VERIFY])
    duplicate_execution = deepcopy(executions[MOIST_VERIFY])
    duplicated["result_id"] = new_identity("result")
    duplicated["execution_id"] = new_identity("execution")
    duplicate_execution["execution_id"] = duplicated["execution_id"]
    duplicate_execution["result_id"] = duplicated["result_id"]
    seal(duplicated)
    seal(duplicate_execution)
    workspace["results"].append(duplicated)
    workspace["executions"].append(duplicate_execution)
    write_json(directory / "workspace.json", workspace)
    before = _contents(directory)
    with _no_providers(), pytest.raises(ValueError, match="Duplicate atmosphere verification"):
        Session.from_workspace(directory / "workspace.json", tmp_path / "reopened")
    assert _contents(directory) == before


@pytest.mark.parametrize("field,value", [("schema", "importlib.ciw.weather"),
                                         ("scope", "global_moist_forecast")])
def test_unknown_moist_scope_refuses_before_creating_destination(tmp_path, field, value):
    request = moist_request()
    request[field] = value
    output = tmp_path / "invalid"
    with _no_providers(), pytest.raises(ValueError):
        workflow.run(request, output)
    assert not output.exists()


def test_boolean_water_mixing_ratio_is_not_a_numeric_alias(tmp_path):
    request = moist_request()
    request["profile"][MIXING_RATIO] = False
    output = tmp_path / "invalid"
    with _no_providers(), pytest.raises(ValueError):
        workflow.run(request, output)
    assert not output.exists()


@pytest.mark.parametrize("profile", ["dry", "moist"])
@pytest.mark.parametrize("phase", ["compiler", "verifier"])
@pytest.mark.parametrize("mutation", ["wrong_provider", "wrong_scope"])
def test_runtime_profile_labels_cannot_be_coherently_resealed_as_another_provider(
        tmp_path, retained_dry, retained_moist, profile, phase, mutation):
    original = retained_dry if profile == "dry" else retained_moist
    directory = tmp_path / "mislabeled"
    shutil.copytree(original[0], directory)
    operation = ({"compiler": workflow.COMPILE, "verifier": workflow.VERIFY} if profile == "dry"
                 else {"compiler": MOIST_COMPILE, "verifier": MOIST_VERIFY})[phase]
    changes = {"provider": "arbitrary.external.weather." + phase} if mutation == "wrong_provider" else {
        "scope": "global_phase_changing_weather_forecast"}
    _rewrite_runtime(directory, operation, changes)
    before = _contents(directory)
    with _no_providers(), pytest.raises(ValueError):
        Session.from_workspace(directory / "workspace.json", tmp_path / "generic-reopen")
    with _no_providers(), pytest.raises(ValueError):
        workflow.inspect(directory)
    assert _contents(directory) == before


@pytest.mark.parametrize("profile", ["dry", "moist"])
@pytest.mark.parametrize("phase", ["compiler", "verifier"])
def test_retained_runtime_hash_identifies_history_without_requiring_current_code(
        tmp_path, retained_dry, retained_moist, profile, phase):
    original = retained_dry if profile == "dry" else retained_moist
    directory = tmp_path / "historical"
    shutil.copytree(original[0], directory)
    operation = ({"compiler": workflow.COMPILE, "verifier": workflow.VERIFY} if profile == "dry"
                 else {"compiler": MOIST_COMPILE, "verifier": MOIST_VERIFY})[phase]
    _rewrite_runtime(directory, operation, {"code_sha256": "1" * 64})
    before = _contents(directory)
    with _no_providers():
        inspected = workflow.inspect(directory)
        restored = Session.from_workspace(directory / "workspace.json", tmp_path / "generic-reopen")
    assert inspected["status"] == "LOCAL"
    assert inspected["result_id"] == original[1]["result_id"]
    assert len(restored.results) == len(restored.executions) == 2
    with _no_providers(verifier=False):
        checked = workflow.verify_retained(directory)
    assert checked["status"] == "LOCAL"
    assert checked["fresh_numerical_verification"] is True
    assert checked["recomputed_with_runtime"]["code_sha256"] != "1" * 64
    assert _contents(directory) == before


@pytest.mark.parametrize("profile", ["dry", "moist"])
@pytest.mark.parametrize("phase", ["compiler", "verifier"])
@pytest.mark.parametrize("mutation", ["hash_null", "hash_uppercase", "runtime_extra",
                                     "environment_extra", "floating_point", "python_alias"])
def test_retained_atmospheric_runtime_requires_well_formed_data_only_provenance(
        tmp_path, retained_dry, retained_moist, profile, phase, mutation):
    original = retained_dry if profile == "dry" else retained_moist
    directory = tmp_path / "malformed-runtime"
    shutil.copytree(original[0], directory)
    operation = ({"compiler": workflow.COMPILE, "verifier": workflow.VERIFY} if profile == "dry"
                 else {"compiler": MOIST_COMPILE, "verifier": MOIST_VERIFY})[phase]
    changes = {
        "hash_null": {"code_sha256": None},
        "hash_uppercase": {"code_sha256": "A" * 64},
        "runtime_extra": {"import_path": "external.weather.provider"},
        "environment_extra": {"environment": {"python": "3.12.14", "floating_point": "binary64", "extra": True}},
        "floating_point": {"environment": {"python": "3.12.14", "floating_point": "decimal64"}},
        "python_alias": {"environment": {"python": True, "floating_point": "binary64"}},
    }[mutation]
    _rewrite_runtime(directory, operation, changes)
    before = _contents(directory)
    with _no_providers(), pytest.raises(ValueError):
        Session.from_workspace(directory / "workspace.json", tmp_path / "generic-reopen")
    with _no_providers(), pytest.raises(ValueError):
        workflow.inspect(directory)
    assert _contents(directory) == before
