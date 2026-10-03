"""Retained graphics identities, inert reads, and qualified create-only exports."""
from copy import deepcopy
import base64
from hashlib import sha256
import json
import os
from pathlib import Path

import numpy as np
import pytest

from ciw.core.identities import evidence_id, new_identity
from ciw.operations.runner import digest, seal
from ciw.procedural_contract import example_request
from ciw import procedural_workflow as workflow


def request(profile="sphere"):
    result = example_request(profile)
    result["domain"]["resolution"] = 8
    result["verification"]["field_tolerance"] = 0.15 if profile == "sphere" else 0.4
    return result


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def synchronize(bundle, workspace):
    """Coherently reseal duplicates to test semantics beyond byte integrity."""
    write(bundle / "workspace.json", workspace)
    for record in workspace["results"]:
        write(bundle / (record["result_id"] + ".json"), record)
        if record["operation_id"] == workflow.VERIFY:
            write(bundle / "verification.json", record["data"])
    for record in workspace["executions"]:
        write(bundle / (record["execution_id"] + ".json"), record)


@pytest.fixture
def bundle(tmp_path):
    destination = tmp_path / "retained"
    result = workflow.run(request(), destination)
    assert result["status"] == "LOCAL", result
    return destination


def test_declaration_is_exact_and_not_a_physical_clock():
    first = workflow.make_source(request())
    second = workflow.make_source(request())
    assert first == second
    assert first["evidence_id"] == evidence_id(first)
    assert first["time_s"] == [0.0]
    assert first["metadata"]["manifest"]["role"] == "declared_procedural_program"
    assert "not_physical_time" in first["metadata"]["manifest"]["sampling"]["time_semantics"]
    detached = workflow.source_request(first)
    detached["appearance"]["metallic"] = 0.9
    assert first["metadata"]["procedural_request"]["appearance"]["metallic"] == 0.2


@pytest.mark.parametrize("field", ["instrument", "run_id", "render", "metadata"])
def test_coherently_resealed_noncanonical_source_rejected(field):
    source = workflow.make_source(request())
    if field == "metadata":
        source[field]["provenance"]["source"] = "physical material test"
    elif field == "render":
        source[field] = {"physical": True}
    else:
        source[field] = "forged"
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError):
        workflow.source_request(source)


def test_retained_run_has_separate_occurrences_and_static_flags(bundle):
    read = workflow.read_bundle(bundle)
    summary = read["summary"]
    assert summary["verification_status"] == "PASS"
    assert summary["fresh_execution"] is False
    assert summary["fresh_numerical_verification"] is False
    assert summary["mesh_digest"] == digest(read["artifact"]["mesh"])
    assert summary["artifact_digest"] == read["artifact"]["record_digest"]
    assert len({summary["result_id"], summary["execution_id"], summary["verification_id"],
                summary["verification_execution_id"], summary["evidence_id"]}) == 5
    assert summary["authority"]["manufacturing_suitability"] == "not_established"
    assert summary["authority"]["state_admission"] == "not_performed"


def test_static_inspection_activates_no_scientific_provider(bundle, monkeypatch):
    from ciw import procedural_compiler, procedural_verification, procedural_contract
    def prohibited(*args, **kwargs):
        raise AssertionError("Static reader activated a numerical provider")
    monkeypatch.setattr(procedural_compiler, "generate", prohibited)
    monkeypatch.setattr(procedural_verification, "verify", prohibited)
    monkeypatch.setattr(procedural_contract, "evaluate_field", prohibited)
    retained = {path.name: path.read_bytes() for path in bundle.iterdir()}
    assert workflow.inspect(bundle)["status"] == "LOCAL"
    assert workflow.read_bundle(bundle)["artifact"] is not None
    assert retained == {path.name: path.read_bytes() for path in bundle.iterdir()}


def test_read_bundle_detaches_all_consumers(bundle):
    first = workflow.read_bundle(bundle)
    first["artifact"]["mesh"]["vertices"][0][0] = 123
    first["summary"]["authority"]["state_admission"] = "performed"
    fresh = workflow.read_bundle(bundle)
    assert fresh["artifact"]["mesh"]["vertices"][0][0] != 123
    assert fresh["summary"]["authority"]["state_admission"] == "not_performed"


def test_explicit_verification_invokes_only_independent_verifier(bundle, monkeypatch):
    from ciw import procedural_compiler, procedural_verification
    original = procedural_verification.verify
    calls = []
    def record(*args):
        calls.append(True)
        return original(*args)
    monkeypatch.setattr(procedural_verification, "verify", record)
    monkeypatch.setattr(procedural_compiler, "generate", lambda *args: pytest.fail("Verifier regenerated candidate"))
    checked = workflow.verify_retained(bundle)
    assert calls == [True]
    assert checked["status"] == "LOCAL"
    assert checked["fresh_numerical_verification"] is True
    assert checked["fresh_execution"] is False


def test_replay_keeps_evidence_and_regenerates_all_occurrences(bundle, tmp_path):
    before = workflow.inspect(bundle)
    replay = workflow.replay(bundle, tmp_path / "replayed")
    assert replay["evidence_id"] == before["evidence_id"]
    assert replay["mesh_digest"] == before["mesh_digest"]
    assert replay["artifact_digest"] == before["artifact_digest"]
    for field in ("result_id", "execution_id", "verification_id", "verification_execution_id"):
        assert replay[field] != before[field]
    assert replay["fresh_execution"] and replay["fresh_numerical_verification"]
    assert replay["replay"]["status"] == "PASS"
    assert json.loads((tmp_path / "replayed" / "replay.json").read_text()) == replay["replay"]
    assert workflow.inspect(tmp_path / "replayed")["replay"] == replay["replay"]


def test_replay_receipt_candidate_tampering_is_rejected(bundle, tmp_path):
    output = tmp_path / "replayed"
    workflow.replay(bundle, output)
    receipt = json.loads((output / "replay.json").read_text())
    receipt["candidate_result_id"] = new_identity("result")
    write(output / "replay.json", seal(receipt))
    with pytest.raises(ValueError, match="comparison candidate binding"):
        workflow.inspect(output)


def test_replay_mismatch_retains_fail_comparison_without_rewriting_source(bundle, tmp_path, monkeypatch):
    original_run = workflow.run
    original_bytes = {path.name: path.read_bytes() for path in bundle.iterdir()}
    def altered(declaration, destination):
        declaration = deepcopy(declaration)
        declaration["appearance"]["metallic"] = 0.8
        return original_run(declaration, destination)
    monkeypatch.setattr(workflow, "run", altered)
    output = tmp_path / "different"
    with pytest.raises(ValueError, match="comparison failed"):
        workflow.replay(bundle, output)
    receipt = json.loads((output / "replay.json").read_text())
    assert receipt["status"] == "FAIL"
    assert receipt["mesh_digest_equal"] is True
    assert receipt["artifact_digest_equal"] is False
    assert receipt["evidence_equal"] is False
    assert workflow.verify_retained(output)["replay"]["status"] == "FAIL"
    assert original_bytes == {path.name: path.read_bytes() for path in bundle.iterdir()}


def test_replayed_bundle_verification_and_exports_leave_all_retained_bytes_unchanged(bundle, tmp_path):
    output = tmp_path / "replayed"
    workflow.replay(bundle, output)
    original = {path.name: path.read_bytes() for path in output.iterdir()}
    assert workflow.verify_retained(output)["status"] == "LOCAL"
    workflow.export_obj(output, tmp_path / "replayed.obj")
    workflow.export_json(output, tmp_path / "replayed.json")
    assert original == {path.name: path.read_bytes() for path in output.iterdir()}


def test_obj_round_trip_preserves_binary64_coordinates_and_indices(bundle, tmp_path):
    output = tmp_path / "sphere.obj"
    exported = workflow.export_obj(bundle, output)
    read = workflow.read_bundle(bundle)
    vertices, triangles = [], []
    for line in output.read_text(encoding="ascii").splitlines():
        parts = line.split()
        if parts[0] == "v":
            vertices.append([float(value) for value in parts[1:]])
        elif parts[0] == "f":
            triangles.append([int(value) - 1 for value in parts[1:]])
    assert vertices == read["artifact"]["mesh"]["vertices"]
    assert triangles == read["artifact"]["mesh"]["triangles"]
    sidecar = json.loads(Path(exported["sidecar"]).read_text())
    assert sidecar["output_sha256"] == "sha256:" + sha256(output.read_bytes()).hexdigest()
    assert sidecar["units"] == read["artifact"]["mesh"]["units"]
    assert sidecar["frame"] == read["artifact"]["mesh"]["frame"]
    assert sidecar["mesh_digest"] == read["summary"]["mesh_digest"]
    assert sidecar["claims"]["manufacturing"] == "not_established"


def test_json_export_binds_request_artifact_and_report(bundle, tmp_path):
    output = tmp_path / "sphere.json"
    result = workflow.export_json(bundle, output)
    saved = json.loads(output.read_text())
    read = workflow.read_bundle(bundle)
    assert saved["request"] == read["request"]
    assert saved["artifact"] == read["artifact"]
    assert saved["verification"] == read["report"]
    assert result["verification_id"] == read["summary"]["verification_id"]
    assert saved["recomputed_report_digest"] == saved["verification"]["record_digest"]


@pytest.mark.parametrize("occupied", ["object", "sidecar", "object_symlink", "sidecar_symlink"])
def test_obj_export_preflights_both_create_only_destinations(bundle, tmp_path, occupied):
    output = tmp_path / "sphere.obj"
    sidecar = Path(str(output) + ".json")
    selected = output if occupied.startswith("object") else sidecar
    if occupied.endswith("symlink"):
        try:
            selected.symlink_to(tmp_path / "missing")
        except OSError:
            pytest.skip("Symlink creation unavailable on this platform")
    else:
        selected.write_bytes(b"retain these bytes")
    with pytest.raises(FileExistsError):
        workflow.export_obj(bundle, output)
    if not occupied.endswith("symlink"):
        assert selected.read_bytes() == b"retain these bytes"
    other = sidecar if selected == output else output
    assert not other.exists()


def test_export_performs_fresh_verification_and_does_not_trust_retained_pass(bundle, tmp_path, monkeypatch):
    from ciw import procedural_verification
    original = procedural_verification.verify
    def disagree(*args):
        value = original(*args)
        value["status"] = "FAIL"
        return seal(value)
    monkeypatch.setattr(procedural_verification, "verify", disagree)
    with pytest.raises(ValueError, match="Fresh independent"):
        workflow.export_obj(bundle, tmp_path / "blocked.obj")
    with pytest.raises(ValueError, match="Fresh independent"):
        workflow.export_json(bundle, tmp_path / "blocked.json")
    assert not (tmp_path / "blocked.obj").exists()
    assert not (tmp_path / "blocked.json").exists()


def test_coherently_resealed_report_is_static_data_and_fresh_check_exposes_forgery(bundle):
    workspace = json.loads((bundle / "workspace.json").read_text())
    verification = next(result for result in workspace["results"] if result["operation_id"] == workflow.VERIFY)
    report = verification["data"]["report"]
    report["metrics"]["surface_area"] *= 1.01
    seal(report)
    seal(verification)
    synchronize(bundle, workspace)
    # Content integrity and internally coherent declarations are inspectable;
    # they do not establish the truth of a retained numerical metric.
    assert workflow.inspect(bundle)["status"] == "LOCAL"
    with pytest.raises(ValueError, match="Fresh independent"):
        workflow.verify_retained(bundle)


@pytest.mark.parametrize("name", ["request.json", "workspace.json", "verification.json", "recording"])
def test_duplicate_artifact_tampering_is_rejected(bundle, name):
    selected = (next(path for path in bundle.iterdir() if path.name.startswith("recording-"))
                if name == "recording" else bundle / name)
    value = json.loads(selected.read_text())
    value["unexpected"] = True
    write(selected, value)
    with pytest.raises(ValueError):
        workflow.inspect(bundle)


def test_coherent_verification_binding_forgery_is_rejected(bundle):
    workspace = json.loads((bundle / "workspace.json").read_text())
    verification = next(result for result in workspace["results"] if result["operation_id"] == workflow.VERIFY)
    verification["data"]["candidate_result_id"] = new_identity("result")
    seal(verification)
    synchronize(bundle, workspace)
    with pytest.raises(ValueError, match="binding"):
        workflow.inspect(bundle)


def test_embedded_candidate_must_equal_retained_candidate(bundle):
    workspace = json.loads((bundle / "workspace.json").read_text())
    verification = next(result for result in workspace["results"] if result["operation_id"] == workflow.VERIFY)
    embedded = verification["parameters"]["candidate"]
    embedded["result_id"] = new_identity("result")
    seal(embedded)
    verification["data"].update(candidate_result_id=embedded["result_id"], candidate_record_digest=embedded["record_digest"])
    seal(verification)
    execution = next(entry for entry in workspace["executions"] if entry["execution_id"] == verification["execution_id"])
    execution["parameters"] = deepcopy(verification["parameters"])
    seal(execution)
    synchronize(bundle, workspace)
    with pytest.raises(ValueError, match="retained generator"):
        workflow.inspect(bundle)


def test_duplicate_verification_occurrence_ids_are_rejected(bundle):
    workspace = json.loads((bundle / "workspace.json").read_text())
    records = {result["result_id"]: result for result in workspace["results"]}
    old = next(result for result in records.values() if result["operation_id"] == workflow.VERIFY)
    additional = deepcopy(old)
    additional["result_id"] = new_identity("result")
    additional["execution_id"] = new_identity("execution")
    seal(additional)
    records[additional["result_id"]] = additional
    with pytest.raises(ValueError, match="Duplicate procedural verification"):
        workflow.validate_result_dependencies(records)


def test_live_verification_requires_retained_candidate(bundle):
    workspace = json.loads((bundle / "workspace.json").read_text())
    candidate = next(result for result in workspace["results"] if result["operation_id"] == workflow.GENERATE)
    with pytest.raises(ValueError, match="actually retained"):
        workflow.validate_live_dependency({"candidate": candidate}, {})
    workflow.validate_live_dependency({"candidate": candidate}, {candidate["result_id"]: candidate})


@pytest.mark.parametrize("name", ["unexpected.json", "unexpected_dir", "symlink"])
def test_regular_exact_bundle_tree_is_enforced(bundle, tmp_path, name):
    path = bundle / name
    if name == "unexpected_dir":
        path.mkdir()
    elif name == "symlink":
        try:
            path.symlink_to(bundle / "workspace.json")
        except OSError:
            pytest.skip("Symlink creation unavailable")
    else:
        path.write_text("{}")
    with pytest.raises(ValueError):
        workflow.inspect(bundle)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unavailable")
def test_fifo_rejected_without_blocking(bundle):
    selected = bundle / "request.json"
    selected.unlink()
    os.mkfifo(selected)
    with pytest.raises(ValueError, match="regular"):
        workflow.inspect(bundle)


def test_symlink_bundle_root_rejected(bundle, tmp_path):
    selected = tmp_path / "pointer"
    try:
        selected.symlink_to(bundle, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError, match="directory"):
        workflow.inspect(selected)


@pytest.mark.parametrize("name,limit", [("workspace.json", workflow.MAX_WORKSPACE_BYTES),
                                       ("request.json", workflow.MAX_FILE_BYTES)])
def test_file_budget_checked_before_parsing(bundle, name, limit):
    selected = bundle / name
    with selected.open("wb") as stream:
        stream.seek(limit)
        stream.write(b" ")
    with pytest.raises(ValueError, match="byte budget"):
        workflow.inspect(bundle)


def test_retained_reader_snapshots_each_artifact_once(bundle, monkeypatch):
    original = workflow._regular_bytes
    names = []
    def once(path, limit):
        names.append(path.name)
        assert names.count(path.name) == 1
        return original(path, limit)
    monkeypatch.setattr(workflow, "_regular_bytes", once)
    workflow.read_bundle(bundle)
    assert set(names) == {path.name for path in bundle.iterdir()}


def test_request_validation_before_create_only_run_directory(tmp_path):
    invalid = request()
    invalid["definition"]["expression"] = "__import__('os')"
    destination = tmp_path / "invalid"
    with pytest.raises(ValueError):
        workflow.run(invalid, destination)
    assert not destination.exists()
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep").write_text("untouched")
    with pytest.raises(FileExistsError):
        workflow.run(request(), occupied)
    assert (occupied / "keep").read_text() == "untouched"


def test_generator_numerical_refusal_is_retained(tmp_path):
    declaration = request()
    declaration["definition"] = {"expression": "1", "parameters": {}}
    destination = tmp_path / "empty"
    summary = workflow.run(declaration, destination)
    assert summary["status"] == "REFUSE"
    assert summary["verification_status"] == "not_verified"
    assert len(summary["executions"]) == 1
    assert summary["executions"][0]["status"] == "refused"
    assert workflow.inspect(destination)["fresh_execution"] is False
    assert workflow.verify_retained(destination)["fresh_numerical_verification"] is False


def test_runtime_identity_records_code_and_environment():
    compiler = workflow.runtime_identity("compiler")
    verifier = workflow.runtime_identity("verifier")
    assert compiler["code_sha256"] != verifier["code_sha256"]
    assert compiler["environment"]["numpy"] == np.__version__
    workflow.validate_runtime("compiler", compiler)
    bad = deepcopy(compiler)
    bad["provider"] = "untrusted.saved.module"
    with pytest.raises(ValueError):
        workflow.validate_runtime("compiler", bad)


def representation_request(kind):
    if kind == "surface":
        from ciw.procedural_surface import example_surface
        declaration = example_surface()
        declaration["domain"]["resolution"] = [8, 8]
    else:
        from ciw.procedural_texture import example_texture
        declaration = example_texture()
        declaration["domain"]["resolution"] = [16, 16]
    return declaration


@pytest.fixture(params=["surface", "texture"])
def representation_bundle(tmp_path, request):
    declaration = representation_request(request.param)
    directory = tmp_path / request.param
    summary = workflow.run(declaration, directory)
    assert summary["status"] == "LOCAL", summary
    return request.param, directory, summary


def test_extended_program_definition_and_parameters_bind_source_evidence(representation_bundle):
    kind, directory, summary = representation_bundle
    bundle = workflow.read_bundle(directory)
    assert bundle["request"] == representation_request(kind)
    assert workflow.make_source(bundle["request"])["evidence_id"] == summary["evidence_id"]
    source = workflow.make_source(bundle["request"])
    assert source["metadata"]["coordinate_frame"] == bundle["request"]["domain"]["frame"]
    assert source["metadata"]["manifest"]["frames"] == [bundle["request"]["domain"]["frame"]]
    changed = deepcopy(bundle["request"])
    changed["definition"]["expressions"][0] = "0"
    assert workflow.make_source(changed)["evidence_id"] != summary["evidence_id"]
    assert summary["artifact_kind"] == ("texture" if kind == "texture" else "mesh")
    assert summary["fresh_execution"] and summary["fresh_numerical_verification"]
    if kind == "texture":
        assert summary["mesh_digest"] is None
        assert summary["image_digest"] == summary["output_digest"]
        assert summary["authority"]["gpu_pixel_equivalence"] == "not_established"
    else:
        assert summary["mesh_digest"] == summary["output_digest"]
        assert summary["image_digest"] is None


def test_extended_static_reader_does_not_generate_sample_or_verify(representation_bundle, monkeypatch):
    from ciw import procedural_surface, procedural_texture, procedural_representation_verification
    kind, directory, summary = representation_bundle
    def forbidden(*args, **kwargs):
        raise AssertionError("Static read activated a scientific provider")
    monkeypatch.setattr(procedural_surface, "generate_surface", forbidden)
    monkeypatch.setattr(procedural_surface, "evaluate_uv", forbidden)
    monkeypatch.setattr(procedural_texture, "generate_texture", forbidden)
    monkeypatch.setattr(procedural_texture, "evaluate_uv", forbidden)
    monkeypatch.setattr(procedural_representation_verification, "verify", forbidden)
    inspected = workflow.read_bundle(directory)
    assert inspected["summary"]["output_digest"] == summary["output_digest"]
    assert inspected["summary"]["fresh_execution"] is False


def test_extended_retained_replay_keeps_output_and_fresh_occurrences(representation_bundle, tmp_path):
    kind, directory, summary = representation_bundle
    output = tmp_path / "replayed"
    replayed = workflow.replay(directory, output)
    assert replayed["output_digest"] == summary["output_digest"]
    assert replayed["artifact_digest"] == summary["artifact_digest"]
    assert replayed["evidence_id"] == summary["evidence_id"]
    assert replayed["verification_id"] != summary["verification_id"]
    assert replayed["replay"]["output_digest_equal"] is True
    assert workflow.verify_retained(output)["status"] == "LOCAL"


def test_extended_json_exports_original_program_and_artifact(representation_bundle, tmp_path):
    kind, directory, summary = representation_bundle
    output = tmp_path / "artifact.json"
    exported = workflow.export_json(directory, output)
    retained = workflow.read_bundle(directory)
    value = json.loads(output.read_text())
    assert value["request"] == retained["request"]
    assert value["artifact"] == retained["artifact"]
    assert exported["output_digest"] == summary["output_digest"]
    assert value["authority"] == summary["authority"]


def test_selected_export_reopens_actual_bytes_and_rejects_wrong_kind(representation_bundle, tmp_path):
    kind, directory, summary = representation_bundle
    if kind == "surface":
        exported = workflow.export_obj(directory, tmp_path / "surface.obj")
        with pytest.raises(ValueError, match="texture"):
            workflow.export_png(directory, tmp_path / "wrong.png")
    else:
        exported = workflow.export_png(directory, tmp_path / "texture.png")
        with pytest.raises(ValueError, match="mesh"):
            workflow.export_obj(directory, tmp_path / "wrong.obj")
    receipt = json.loads(Path(exported["sidecar"]).read_text())
    assert receipt["independent_reopen"] == "PASS"
    assert receipt["output_sha256"] == "sha256:" + sha256(Path(exported["file"]).read_bytes()).hexdigest()
    assert receipt["output_digest"] == summary["output_digest"]


def test_manifest_is_single_snapshot_conversion_with_no_artifact_publication(representation_bundle, tmp_path, monkeypatch):
    kind, directory, summary = representation_bundle
    original = workflow._read
    calls = []
    def once(path):
        calls.append(path)
        assert len(calls) == 1
        return original(path)
    monkeypatch.setattr(workflow, "_read", once)
    output = tmp_path / "manifest.json"
    result = workflow.export_manifest(directory, output)
    value = json.loads(output.read_text())
    assert value["format"] == ("obj" if kind == "surface" else "png")
    assert value["artifact_publication"] == "not_performed"
    assert value["independent_reopen"] == "PASS"
    assert result["output_digest"] == summary["output_digest"]
    assert len(calls) == 1


@pytest.mark.parametrize("occupied", ["object", "sidecar"])
def test_png_export_create_only_pair_preflight(tmp_path, occupied):
    directory = tmp_path / "texture"
    workflow.run(representation_request("texture"), directory)
    output = tmp_path / "texture.png"
    sidecar = Path(str(output) + ".json")
    selected = output if occupied == "object" else sidecar
    selected.write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        workflow.export_png(directory, output)
    assert selected.read_bytes() == b"preserve"
    assert not (sidecar if occupied == "object" else output).exists()


def test_png_export_uses_independent_reopened_decoder(tmp_path, monkeypatch):
    from ciw import procedural_representation_verification
    directory = tmp_path / "texture"
    workflow.run(representation_request("texture"), directory)
    original = procedural_representation_verification.decode_texture_png
    calls = []
    def observe(raw, width, height):
        calls.append((raw, width, height))
        return original(raw, width, height)
    monkeypatch.setattr(procedural_representation_verification, "decode_texture_png", observe)
    exported = workflow.export_png(directory, tmp_path / "texture.png")
    assert len(calls) == 1
    assert calls[0][0] == Path(exported["file"]).read_bytes()
    assert calls[0][1:] == (16, 16)


def test_reopen_failure_prevents_png_artifact_and_sidecar_publication(tmp_path, monkeypatch):
    from ciw import procedural_representation_verification
    directory = tmp_path / "texture"
    workflow.run(representation_request("texture"), directory)
    monkeypatch.setattr(procedural_representation_verification, "decode_texture_png", lambda *args: b"forged pixels")
    output = tmp_path / "blocked.png"
    with pytest.raises(ValueError, match="Reopened PNG"):
        workflow.export_png(directory, output)
    assert not output.exists()
    assert not Path(str(output) + ".json").exists()


def test_reopen_failure_prevents_obj_publication(bundle, tmp_path, monkeypatch):
    original = workflow._regular_bytes
    def altered(path, limit):
        raw = original(path, limit)
        if path.suffix == ".obj":
            return raw.replace(b"v ", b"v 0 ", 1)
        return raw
    monkeypatch.setattr(workflow, "_regular_bytes", altered)
    output = tmp_path / "blocked.obj"
    with pytest.raises(ValueError, match="Reopened OBJ"):
        workflow.export_obj(bundle, output)
    assert not output.exists()
    assert not Path(str(output) + ".json").exists()


def test_maximum_texture_can_retain_reopen_and_export_bounded_base64(tmp_path):
    declaration = representation_request("texture")
    declaration["domain"]["resolution"] = [256, 256]
    directory = tmp_path / "maximum"
    summary = workflow.run(declaration, directory)
    assert summary["status"] == "LOCAL", summary
    retained = workflow.read_bundle(directory)
    assert len(retained["artifact"]["image"]["rgba_base64"]) > 65536
    workflow.export_json(directory, tmp_path / "maximum.json")
    workflow.export_png(directory, tmp_path / "maximum.png")
    assert summary["metrics"]["pixel_count"] == 256 * 256


def test_texture_png_roundtrip_equals_retained_pixels(tmp_path):
    from ciw.procedural_representation_verification import decode_texture_png
    directory = tmp_path / "texture"
    workflow.run(representation_request("texture"), directory)
    exported = workflow.export_png(directory, tmp_path / "texture.png")
    image = workflow.read_bundle(directory)["artifact"]["image"]
    decoded = decode_texture_png(Path(exported["file"]).read_bytes(), image["width"], image["height"])
    assert decoded == base64.b64decode(image["rgba_base64"])


def test_legacy_mesh_replay_receipt_remains_static_readable(bundle, tmp_path):
    output = tmp_path / "legacy"
    workflow.replay(bundle, output)
    receipt = json.loads((output / "replay.json").read_text())
    for prefix in ("source_", "candidate_"):
        for field in workflow._OUTPUT_REPLAY_FIELDS:
            receipt.pop(prefix + field)
    receipt.pop("output_digest_equal")
    write(output / "replay.json", seal(receipt))
    assert workflow.inspect(output)["replay"]["status"] == "PASS"


def test_legacy_runtime_scope_environment_remain_accepted():
    runtime = workflow.runtime_identity("compiler")
    runtime["scope"] = "declared_visual_implicit_surface_only"
    runtime["environment"].pop("zlib")
    runtime["environment"].pop("zlib_compiled")
    workflow.validate_runtime("compiler", runtime)


def test_texture_source_binds_uv_frame_and_rejects_resealed_cartesian_alias():
    declaration = representation_request("texture")
    source = workflow.make_source(declaration)
    assert source["metadata"]["coordinate_frame"] == "procedural.texture_uv.v1"
    assert source["metadata"]["manifest"]["frames"] == ["procedural.texture_uv.v1"]
    original_identity = source["evidence_id"]
    source["metadata"]["coordinate_frame"] = workflow.FRAME
    source["metadata"]["manifest"]["frames"] = [workflow.FRAME]
    source["evidence_id"] = evidence_id(source)
    assert source["evidence_id"] != original_identity
    with pytest.raises(ValueError, match="exact declared program"):
        workflow.source_request(source)
