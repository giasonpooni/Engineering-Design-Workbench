"""Independent public-contract audits for bounded notation and retained graphics.

Analytic geometry and hostile inputs exercise promises independent of extractor
implementation. A coherent false saved report is intentionally distinguishable
from fresh numerical verification.
"""
from contextlib import ExitStack
from copy import deepcopy
import base64
from hashlib import sha256
import http.client
import json
import math
from pathlib import Path
import shutil
import struct
import threading
import zlib
from unittest.mock import patch

import numpy as np
import pytest

from ciw import procedural_compiler as compiler, procedural_contract as contract
from ciw import procedural_verification as verification, procedural_workflow as workflow
from ciw.operations.runner import check_seal, digest, seal
from ciw import procedural_surface as surface, procedural_texture as texture
from ciw import procedural_representation_verification as representation_verification
from ciw import graphics_notation
from ciw.procedural_server import GraphicsServer
from ciw.session import Session, read_json, write_json


def _request(profile="sphere", resolution=8):
    request = contract.example_request(profile)
    request["domain"]["resolution"] = resolution
    return request


def _bytes(directory):
    return {path.relative_to(directory): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


@pytest.fixture(scope="module")
def sphere_bundle(tmp_path_factory):
    directory = tmp_path_factory.mktemp("procedural-independent") / "sphere"
    summary = workflow.run(_request(), directory)
    assert summary["status"] == "LOCAL"
    return directory, summary


@pytest.mark.parametrize("notation", [
    "x.__class__", "x[0]", "__import__('os')", "(lambda: 1)()", "[x for x in [1]]",
    "{'x':x}", "x if y else z", "x < y", "x and y", "(a:=x)", "sin(x, y)",
    "sin(value=x)", "min(x)", "max(x,y,z)", "x**y", "x**7", "x**-1", "x//2",
    "x%2", "True", "1j", "'1'", "float('nan')", "unknown", "1e309", "9" * 1000,
])
def test_notation_never_admits_executable_or_unbounded_syntax(notation):
    request = _request()
    request["definition"]["expression"] = notation
    with pytest.raises(ValueError):
        contract.validate_request(request)


@pytest.mark.parametrize("notation", ["1/(x-x)", "sqrt(-1)", "1000000*1000000", "x**6"])
def test_accepted_grammar_still_refuses_invalid_finite_arithmetic(notation):
    x = 100.0 if notation == "x**6" else 0.1
    with pytest.raises(ValueError):
        contract.evaluate(notation, {}, x, 0.0, 0.0)


def test_analytic_sphere_refinement_improves_area_volume_and_radial_accuracy():
    radius = 0.7
    exact_area = 4 * math.pi * radius**2
    exact_volume = 4 * math.pi * radius**3 / 3
    errors = []
    for resolution in (8, 16):
        artifact = compiler.generate(_request(resolution=resolution))
        vertices = np.asarray(artifact["mesh"]["vertices"])
        triangles = np.asarray(artifact["mesh"]["triangles"])
        points = vertices[triangles]
        cross = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
        area = float(np.linalg.norm(cross, axis=1).sum() / 2)
        volume = float((points[:, 0] * np.cross(points[:, 1], points[:, 2])).sum() / 6)
        radial_error = float(np.abs(np.linalg.norm(vertices, axis=1) - radius).max())
        edges = {tuple(sorted((face[i], face[(i + 1) % 3]))) for face in triangles for i in range(3)}
        assert len(vertices) - len(edges) + len(triangles) == 2
        assert 0 < area < exact_area
        assert 0 < volume < exact_volume
        errors.append((exact_area - area, exact_volume - volume, radial_error))
    assert all(fine < coarse / 2 for coarse, fine in zip(errors[0], errors[1]))
    assert errors[1][0] / exact_area < 0.02
    assert errors[1][1] / exact_volume < 0.03


def test_appearance_changes_source_identity_without_changing_numerical_geometry():
    request = _request()
    changed = deepcopy(request)
    changed["appearance"]["metallic"] = 0.9
    first, second = compiler.generate(request), compiler.generate(changed)
    assert first["mesh"] == second["mesh"]
    assert first["record_digest"] != second["record_digest"]
    assert workflow.make_source(request)["evidence_id"] != workflow.make_source(changed)["evidence_id"]
    assert first["claims"] == second["claims"] == contract.CLAIMS


def test_declared_graphics_source_is_configuration_support_not_acquired_measurement():
    source = workflow.make_source(_request())
    sampling = source["metadata"]["manifest"]["sampling"]
    assert sampling["time_semantics"] == "selection_support_not_physical_time"
    assert source["metadata"]["manifest"]["role"] == "declared_procedural_program"
    assert source["time_s"] == [0.0]
    assert all(len(channel["values"]) == 1 for channel in source["channels"].values())
    assert "not acquired" in source["metadata"]["provenance"]["source"]


def _no_providers():
    stack = ExitStack()
    for target in ("ciw.procedural_compiler.generate", "ciw.procedural_contract.evaluate",
                   "ciw.procedural_verification.verify", "ciw.session.execute_operation",
                   "ciw.procedural_surface.generate_surface", "ciw.procedural_texture.generate_texture",
                   "ciw.graphics_notation.evaluate_uv", "ciw.procedural_representation_verification.verify",
                   "ciw.procedural_representation_verification.decode_texture_png"):
        stack.enter_context(patch(target, side_effect=AssertionError("provider activation during static read")))
    return stack


def test_inspection_read_bundle_and_generic_restore_are_static_and_immutable(tmp_path, sphere_bundle):
    directory, _ = sphere_bundle
    before = _bytes(directory)
    with _no_providers():
        summary = workflow.inspect(directory)
        bundle = workflow.read_bundle(directory)
        session = Session.from_workspace(directory / "workspace.json", tmp_path / "restored")
    assert summary == bundle["summary"]
    assert summary["fresh_execution"] is False
    assert summary["fresh_numerical_verification"] is False
    assert len(session.results) == len(session.executions) == 2
    bundle["request"]["definition"]["expression"] = "fabricated"
    bundle["artifact"]["mesh"]["vertices"][0][0] = 9.0
    assert _bytes(directory) == before
    assert workflow.read_bundle(directory)["request"] == _request()


def test_fresh_verification_and_replay_preserve_original_bytes_and_separate_occurrences(tmp_path, sphere_bundle):
    directory, original = sphere_bundle
    before = _bytes(directory)
    with patch("ciw.procedural_compiler.generate", side_effect=AssertionError("verifier called extraction")):
        checked = workflow.verify_retained(directory)
    assert checked["status"] == "LOCAL" and checked["fresh_numerical_verification"] is True
    assert checked["execution_id"] == original["execution_id"]
    assert checked["verification_id"] == original["verification_id"]
    repeated = workflow.replay(directory, tmp_path / "replay")
    assert repeated["replay"]["status"] == "PASS"
    assert repeated["mesh_digest"] == original["mesh_digest"]
    assert repeated["artifact_digest"] == original["artifact_digest"]
    assert repeated["evidence_id"] == original["evidence_id"]
    for name in ("execution_id", "result_id", "verification_id", "verification_execution_id"):
        assert repeated[name] != original[name]
    assert _bytes(directory) == before


def test_obj_roundtrip_and_sidecar_bind_exact_vertices_faces_and_scope(tmp_path, sphere_bundle):
    directory, original = sphere_bundle
    before = _bytes(directory)
    output = tmp_path / "sphere.obj"
    receipt = workflow.export_obj(directory, output)
    sidecar = read_json(Path(str(output) + ".json"))
    vertices, faces = [], []
    for line in output.read_text(encoding="ascii").splitlines():
        words = line.split()
        if words[0] == "v":
            vertices.append([float(value) for value in words[1:]])
        elif words[0] == "f":
            faces.append([int(value) - 1 for value in words[1:]])
    mesh = workflow.read_bundle(directory)["artifact"]["mesh"]
    assert vertices == mesh["vertices"] and faces == mesh["triangles"]
    assert sidecar["output_sha256"] == "sha256:" + sha256(output.read_bytes()).hexdigest()
    assert sidecar["units"] == mesh["units"] == contract.UNITS
    assert sidecar["frame"] == mesh["frame"] == contract.FRAME
    assert sidecar["source_execution_id"] == receipt["source_execution_id"] == original["execution_id"]
    assert sidecar["claims"] == contract.CLAIMS and sidecar["authority"] == workflow.AUTHORITY
    exported_bytes = output.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.export_obj(directory, output)
    assert output.read_bytes() == exported_bytes and _bytes(directory) == before


@pytest.mark.parametrize("existing", ["obj", "sidecar", "sidecar_symlink"])
def test_obj_export_never_overwrites_either_artifact(tmp_path, sphere_bundle, existing):
    directory, _ = sphere_bundle
    output = tmp_path / "mesh.obj"
    sidecar = Path(str(output) + ".json")
    protected = output if existing == "obj" else sidecar
    if existing == "sidecar_symlink":
        outside = tmp_path / "protected.json"
        outside.write_text("protected")
        try:
            sidecar.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"Symlink unavailable: {exc}")
    else:
        protected.write_text("protected")
    with pytest.raises(FileExistsError):
        workflow.export_obj(directory, output)
    assert protected.read_text() == "protected"
    if existing != "obj":
        assert not output.exists()


def _rewrite_occurrences(directory, workspace):
    """Save every redundant envelope, defeating mere duplicate-file/hash checks."""
    write_json(directory / "workspace.json", workspace)
    for records, identity in ((workspace["results"], "result_id"), (workspace["executions"], "execution_id")):
        for record in records:
            write_json(directory / (record[identity] + ".json"), record)
    verifier = next(record for record in workspace["results"] if record["operation_id"] == workflow.VERIFY)
    write_json(directory / "verification.json", verifier["data"])


def test_coherent_false_mesh_passes_static_declarations_but_fails_fresh_checks(tmp_path, sphere_bundle):
    original, _ = sphere_bundle
    directory = tmp_path / "forged"
    shutil.copytree(original, directory)
    workspace = read_json(directory / "workspace.json")
    candidate = next(record for record in workspace["results"] if record["operation_id"] == workflow.GENERATE)
    retained_verifier = next(record for record in workspace["results"] if record["operation_id"] == workflow.VERIFY)
    vertices = candidate["data"]["mesh"]["vertices"]
    index = next(index for index, point in enumerate(vertices) if all(-0.5 < value < 0.5 for value in point))
    vertices[index][0] += 0.03  # Keep global bounds and counts unchanged.
    seal(candidate["data"])
    seal(candidate)
    retained_verifier["parameters"]["candidate"] = deepcopy(candidate)
    payload = retained_verifier["data"]
    payload["candidate_record_digest"] = candidate["record_digest"]
    payload["report"]["candidate_digest"] = candidate["data"]["record_digest"]
    seal(payload["report"])
    seal(retained_verifier)
    execution = next(record for record in workspace["executions"] if record["operation_id"] == workflow.VERIFY)
    execution["parameters"] = deepcopy(retained_verifier["parameters"])
    seal(execution)
    _rewrite_occurrences(directory, workspace)
    before = _bytes(directory)
    with _no_providers():
        assert workflow.inspect(directory)["status"] == "LOCAL"
    with pytest.raises(ValueError, match="Fresh independent"):
        workflow.verify_retained(directory)
    with pytest.raises(ValueError):
        workflow.export_obj(directory, tmp_path / "forged.obj")
    assert not (tmp_path / "forged.obj").exists()
    assert _bytes(directory) == before


@pytest.mark.parametrize("mutation", ["source_unit", "physical_claim", "verification_authority"])
def test_resealed_authority_and_frame_substitution_never_become_verified(mutation):
    request = _request()
    artifact = compiler.generate(request)
    report = verification.verify(request, artifact)
    if mutation == "source_unit":
        artifact["mesh"]["units"] = "m"
        seal(artifact)
        with pytest.raises(ValueError):
            contract.validate_result(request, artifact)
    elif mutation == "physical_claim":
        artifact["claims"]["physical_validation"] = "established"
        seal(artifact)
        with pytest.raises(ValueError):
            contract.validate_result(request, artifact)
    else:
        report["claims"]["manufacturing"] = "established"
        seal(report)
        with pytest.raises(ValueError):
            verification.validate_report(request, artifact, report)


@pytest.fixture
def local_server(tmp_path):
    server = GraphicsServer(tmp_path / "history", port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _http(server, method, path, raw=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    connection.putheader("Host", server.origin.removeprefix("http://"))
    if headers is None:
        headers = [] if raw is None else [("Content-Type", "application/json"), ("Content-Length", str(len(raw)))]
    for name, value in headers:
        connection.putheader(name, value)
    connection.endheaders(raw)
    reply = connection.getresponse()
    content = reply.read()
    result = (reply.status, dict(reply.getheaders()), content)
    connection.close()
    return result


@pytest.mark.parametrize("extra", [
    [("Origin", "http://attacker.invalid")], [("Origin", "null")],
    [("Origin", "http://localhost:8788")], [("Sec-Fetch-Site", "cross-site")],
    [("Host", "attacker.invalid")], [("Origin", "http://attacker.invalid"), ("Origin", "null")],
])
def test_loopback_server_rejects_host_and_browser_origin_substitution_without_writes(local_server, extra):
    raw = json.dumps({"request": _request()}).encode()
    headers = [("Content-Type", "application/json"), ("Content-Length", str(len(raw)))] + extra
    status, _, content = _http(local_server, "POST", "/api/run", raw, headers)
    assert status == 400 and json.loads(content)["status"] == "REFUSE"
    assert list(local_server.root.iterdir()) == []


@pytest.mark.parametrize("headers", [
    [("Content-Type", "text/plain"), ("Content-Length", "2")],
    [("Content-Type", "application/json")],
    [("Content-Type", "application/json"), ("Content-Length", "2"), ("Content-Length", "2")],
    [("Content-Type", "application/json"), ("Content-Length", "65537")],
    [("Content-Type", "application/json"), ("Content-Length", "-2")],
    [("Content-Type", "application/json"), ("Content-Length", "2"), ("Transfer-Encoding", "chunked")],
    [("Content-Type", "application/json"), ("Content-Type", "application/json"), ("Content-Length", "2")],
])
def test_loopback_server_requires_one_bounded_unambiguous_json_body(local_server, headers):
    status, _, _ = _http(local_server, "POST", "/api/run", b"{}", headers)
    assert status == 400 and list(local_server.root.iterdir()) == []


@pytest.mark.parametrize("body", [b'{"request":{},"request":{}}', b'{"request":NaN}', b'[]', b'{}'])
def test_loopback_server_rejects_duplicate_keys_nonfinite_values_and_missing_request(local_server, body):
    status, _, _ = _http(local_server, "POST", "/api/run", body)
    assert status == 400 and list(local_server.root.iterdir()) == []


def test_preview_is_transient_and_remote_output_path_cannot_be_selected(local_server, tmp_path):
    outside = tmp_path / "outside"
    poisoned = json.dumps({"request": _request(), "output_dir": str(outside)}).encode()
    assert _http(local_server, "POST", "/api/run", poisoned)[0] == 400
    assert not outside.exists()
    status, headers, content = _http(local_server, "POST", "/api/preview", json.dumps({"request": _request()}).encode())
    data = json.loads(content)
    assert status == 200 and data["status"] == "preview" and data["transient"] is True
    assert data["report"]["status"] == "PASS"
    assert data["artifact"]["claims"] == contract.CLAIMS
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert list(local_server.root.iterdir()) == []


@pytest.mark.parametrize("path", ["/api/runs/../outside", "/api/runs/%2e%2e/outside", "/api/runs/run-deadbeef",
                                 "/api/runs/run-" + "a"*32 + "/export?format=obj&output=/tmp/outside"])
def test_server_routes_and_export_queries_cannot_name_arbitrary_files(local_server, path):
    status, _, _ = _http(local_server, "GET", path)
    assert status in {400, 404} and list(local_server.root.iterdir()) == []


def test_server_busy_gate_does_not_create_retained_occurrences(local_server):
    raw = json.dumps({"request": _request()}).encode()
    with local_server.operation_lock:
        status, _, content = _http(local_server, "POST", "/api/run", raw)
    assert status == 429 and json.loads(content)["status"] == "REFUSE"
    assert list(local_server.root.iterdir()) == []


def test_browser_run_history_and_replay_keep_numerical_identity_and_fresh_occurrences(local_server):
    raw = json.dumps({"request": _request()}).encode()
    status, _, content = _http(local_server, "POST", "/api/run", raw)
    assert status == 200
    first = json.loads(content)
    assert first["summary"]["status"] == "LOCAL"
    original_path = local_server.root / first["id"]
    before = _bytes(original_path)
    history = json.loads(_http(local_server, "GET", "/api/history")[2])
    assert history["runs"][0]["id"] == first["id"]
    with _no_providers():
        restored = json.loads(_http(local_server, "GET", "/api/runs/" + first["id"])[2])
    assert restored["artifact"] == first["artifact"]
    status, _, content = _http(local_server, "POST", "/api/runs/" + first["id"] + "/replay", b"{}")
    assert status == 200
    second = json.loads(content)
    assert second["id"] != first["id"]
    assert second["summary"]["mesh_digest"] == first["summary"]["mesh_digest"]
    for name in ("execution_id", "result_id", "verification_id"):
        assert second["summary"][name] != first["summary"][name]
    assert _bytes(original_path) == before


def test_perfect_vertex_residual_does_not_claim_continuous_surface_fidelity():
    # This polynomial vanishes at every x node of the eight-cell dyadic grid,
    # but it is nonzero between nodes. Sampling produces a valid plane although
    # the continuous zero surface bends between samples.
    request = _request("wave")
    request["definition"] = {"expression": "z-200*x*(x*x-0.0625)*(x*x-0.25)*(x*x-0.5625)*(x*x-1)",
                             "parameters": {}}
    request["verification"]["field_tolerance"] = 0.001
    artifact = compiler.generate(request)
    report = verification.verify(request, artifact)
    assert report["status"] == "PASS"
    assert report["metrics"]["max_field_residual"] == 0.0
    assert all(point[2] == 0 for point in artifact["mesh"]["vertices"])
    assert abs(float(contract.evaluate_field(request, [[0.125, 0.0, 0.0]])[0])) > 0.1
    assert report["claims"]["continuous_fidelity"] == "not_established"
    assert report["claims"]["manufacturing"] == "not_established"


def test_viewer_read_uses_retained_request_snapshot_once(tmp_path, sphere_bundle):
    original, _ = sphere_bundle
    directory = tmp_path / "snapshot"
    shutil.copytree(original, directory)
    original_reader = workflow._regular_bytes
    reads = []

    def read_then_replace(path, limit):
        raw = original_reader(path, limit)
        reads.append(path.name)
        if path.name == "request.json":
            path.write_text('{"request":"replaced after retained read"}')
        return raw

    with patch.object(workflow, "_regular_bytes", side_effect=read_then_replace), _no_providers():
        bundle = workflow.read_bundle(directory)
    assert bundle["request"] == _request()
    assert len(reads) == len(set(reads)) == len(list(directory.iterdir()))
    with pytest.raises(ValueError):
        workflow.inspect(directory)


def test_replaced_server_history_root_cannot_redirect_writes(local_server, tmp_path):
    root = local_server.root
    preserved = tmp_path / "preserved-history"
    root.rename(preserved)
    outside = tmp_path / "outside-history"
    outside.mkdir()
    try:
        root.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        preserved.rename(root)
        pytest.skip(f"Symlink unavailable: {exc}")
    try:
        raw = json.dumps({"request": _request()}).encode()
        status, _, content = _http(local_server, "POST", "/api/run", raw)
        assert status == 400 and json.loads(content)["status"] == "REFUSE"
        assert list(outside.iterdir()) == list(preserved.iterdir()) == []
    finally:
        root.unlink()
        preserved.rename(root)


def test_server_rejects_symlinked_run_without_reading_outside_bundle(local_server, sphere_bundle):
    original, _ = sphere_bundle
    linked = local_server.root / ("run-" + "a" * 32)
    try:
        linked.symlink_to(original, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlink unavailable: {exc}")
    try:
        with _no_providers():
            status, _, content = _http(local_server, "GET", "/api/runs/" + linked.name)
        assert status == 400 and json.loads(content)["status"] == "REFUSE"
    finally:
        linked.unlink()


def test_retained_numerical_refusal_remains_inspectable_and_does_not_poison_history(local_server):
    request = _request()
    request["definition"]["expression"] = "1"  # Valid notation, no zero surface.
    status, _, content = _http(local_server, "POST", "/api/run", json.dumps({"request": request}).encode())
    assert status == 200
    refused = json.loads(content)
    assert refused["summary"]["status"] == "REFUSE"
    assert refused["summary"]["verification_status"] == "not_verified"
    assert refused["artifact"] is None and refused["report"] is None
    assert len(refused["summary"]["executions"]) == 1
    assert refused["summary"]["executions"][0]["status"] == "refused"
    with _no_providers():
        opened = json.loads(_http(local_server, "GET", "/api/runs/" + refused["id"])[2])
    assert opened == refused
    assert _http(local_server, "POST", "/api/runs/" + refused["id"] + "/replay", b"{}")[0] == 400
    assert _http(local_server, "GET", "/api/runs/" + refused["id"] + "/export?format=obj")[0] == 400
    assert len(list(local_server.root.iterdir())) == 1
    good_status, _, good_content = _http(local_server, "POST", "/api/run", json.dumps({"request": _request()}).encode())
    assert good_status == 200 and json.loads(good_content)["summary"]["status"] == "LOCAL"
    with _no_providers():
        status, _, history_content = _http(local_server, "GET", "/api/history")
    assert status == 200
    assert {run["summary"]["verification_status"] for run in json.loads(history_content)["runs"]} == {"PASS", "not_verified"}


@pytest.mark.parametrize("literal", ["1e-400", "-1e-400", "1_000e-400", ".01e-400"])
def test_nonzero_notation_literals_cannot_silently_underflow_into_zero(literal):
    request = _request()
    request["definition"]["expression"] = "z+" + literal
    with pytest.raises(ValueError):
        contract.validate_request(request)


def test_declared_zero_literal_with_small_exponent_remains_legitimate():
    request = _request("wave")
    request["definition"] = {"expression": "z+0e-400", "parameters": {}}
    assert contract.validate_request(request) == request
    artifact = compiler.generate(request)
    assert all(point[2] == 0 for point in artifact["mesh"]["vertices"])
    assert verification.verify(request, artifact)["status"] == "PASS"


def _expanded_request(profile):
    if profile == "parametric":
        request = surface.example_surface()
        request["domain"]["resolution"] = [8, 8]
    else:
        request = texture.example_texture()
        request["domain"]["resolution"] = [16, 16]
    return request


@pytest.fixture(scope="module", params=["parametric", "texture"])
def expanded_bundle(request, tmp_path_factory):
    declaration = _expanded_request(request.param)
    directory = tmp_path_factory.mktemp("procedural-representation-audit") / request.param
    summary = workflow.run(declaration, directory)
    assert summary["status"] == "LOCAL"
    return request.param, directory, summary, declaration


def _independent_png(data):
    """A test consumer independent of the production generator/verifier parser."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, payloads = 8, []
    while offset < len(data):
        size = int.from_bytes(data[offset:offset+4], "big")
        kind = data[offset+4:offset+8]
        payload = data[offset+8:offset+8+size]
        observed_crc = int.from_bytes(data[offset+8+size:offset+12+size], "big")
        assert len(payload) == size
        assert observed_crc == zlib.crc32(kind + payload) & 0xffffffff
        payloads.append((kind, payload))
        offset += 12 + size
    assert offset == len(data)
    assert [kind for kind, _ in payloads] == [b"IHDR", b"IDAT", b"IEND"]
    width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payloads[0][1])
    assert (depth, color, compression, filtering, interlace) == (8, 6, 0, 0, 0)
    raw = zlib.decompress(payloads[1][1])
    stride = 1 + 4 * width
    assert len(raw) == height * stride
    assert all(raw[row * stride] == 0 for row in range(height))
    pixels = b"".join(raw[row*stride+1:(row+1)*stride] for row in range(height))
    assert payloads[2][1] == b""
    return width, height, pixels


def test_transformed_torus_has_analytic_embedding_genus_and_refinement_behavior():
    errors = []
    for count in (8, 16):
        request = surface.example_surface()
        request["domain"]["resolution"] = [count, count]
        artifact = surface.generate_surface(request)
        mesh = artifact["mesh"]
        vertices, faces = np.asarray(mesh["vertices"]), np.asarray(mesh["triangles"])
        parameters = request["definition"]["parameters"]
        major, minor, angle = (parameters[name]["value"] for name in ("R", "r", "a"))
        unrotated_x = math.cos(angle) * vertices[:,0] - math.sin(angle) * vertices[:,2]
        unrotated_z = math.sin(angle) * vertices[:,0] + math.cos(angle) * vertices[:,2]
        radial = np.hypot(unrotated_x, vertices[:,1])
        assert float(np.max(np.abs((radial-major)**2 + unrotated_z**2 - minor**2))) < 1e-15
        edges = {tuple(sorted((face[i], face[(i+1)%3]))) for face in faces for i in range(3)}
        assert len(vertices) - len(edges) + len(faces) == 0  # Genus-one closed surface.
        points = vertices[faces]
        area = float(np.linalg.norm(np.cross(points[:,1]-points[:,0], points[:,2]-points[:,0]), axis=1).sum()/2)
        volume = float((points[:,0] * np.cross(points[:,1], points[:,2])).sum()/6)
        exact_area, exact_volume = 4*math.pi**2*major*minor, 2*math.pi**2*major*minor**2
        assert 0 < area < exact_area and 0 < volume < exact_volume
        errors.append((exact_area-area, exact_volume-volume))
    assert all(fine < coarse/2 for coarse, fine in zip(errors[0], errors[1]))


def test_texture_gradient_png_independently_preserves_pixel_centers_channels_and_orientation():
    request = _expanded_request("texture")
    request["definition"] = {"expressions": ["u", "v", "0.5"], "parameters": {}}
    artifact = texture.generate_texture(request)
    png = base64.b64decode(artifact["image"]["png_base64"], validate=True)
    width, height, pixels = _independent_png(png)
    expected = bytes(value for row in range(height) for column in range(width)
                     for value in (int(255*(column+0.5)/width+0.5), int(255*(row+0.5)/height+0.5), 128, 255))
    assert pixels == expected == base64.b64decode(artifact["image"]["rgba_base64"], validate=True)
    assert pixels[:4] == bytes((8,8,128,255))
    assert pixels[-4:] == bytes((247,247,128,255))
    assert artifact["shader"]["compilation"] == "not_performed"
    assert artifact["claims"]["physical_validation"] == "not_established"
    assert representation_verification.verify(request, artifact)["status"] == "PASS"


@pytest.mark.parametrize("profile", ["parametric", "texture"])
@pytest.mark.parametrize("notation", ["u.__class__", "u[0]", "__import__('os')", "x+v", "u**7", "1e-400"])
def test_uv_contract_never_admits_host_code_cartesian_substitution_or_unbounded_syntax(profile, notation):
    request = _expanded_request(profile)
    request["definition"]["expressions"][0] = notation
    validator = surface.validate_surface_request if profile == "parametric" else texture.validate_texture_request
    with pytest.raises(ValueError):
        validator(request)


@pytest.mark.parametrize("profile", ["parametric", "texture"])
def test_resealed_typed_ir_cannot_change_the_program_behind_retained_notation(profile):
    request = _expanded_request(profile)
    generator = surface.generate_surface if profile == "parametric" else texture.generate_texture
    validator = surface.validate_surface_result if profile == "parametric" else texture.validate_texture_result
    artifact = generator(request)
    artifact["ir"][0]["root"] = {"type":"scalar", "op":"constant", "value": 0.0}
    seal(artifact)
    with pytest.raises(ValueError):
        validator(request, artifact)


def test_only_safe_typed_nodes_reach_generated_glsl_source():
    request = _expanded_request("texture")
    request["definition"] = {"expressions": ["u # </script><script>host_attack()</script>", "(v-0.5)**2", "0.5"], "parameters": {}}
    artifact = texture.generate_texture(request)
    source = artifact["shader"]["fragment_source"]
    assert "host_attack" not in source and "</script>" not in source
    assert "netPow2" in source and "pow(" not in source
    forged = deepcopy(artifact)
    forged["shader"]["fragment_source"] += "\nvoid host_attack(){}"
    seal(forged)
    with pytest.raises(ValueError):
        texture.validate_texture_result(request, forged)


def test_expanded_representations_static_read_fresh_verification_and_replay_keep_identity_boundaries(tmp_path, expanded_bundle):
    profile, directory, original, request = expanded_bundle
    before = _bytes(directory)
    with _no_providers():
        bundle = workflow.read_bundle(directory)
        restored = Session.from_workspace(directory / "workspace.json", tmp_path / "restored")
    assert bundle["request"] == request
    assert len(restored.results) == len(restored.executions) == 2
    assert bundle["summary"]["fresh_execution"] is False
    assert bundle["summary"]["fresh_numerical_verification"] is False
    with patch("ciw.procedural_surface.generate_surface", side_effect=AssertionError("fresh verification generated mesh")), \
            patch("ciw.procedural_texture.generate_texture", side_effect=AssertionError("fresh verification baked texture")):
        checked = workflow.verify_retained(directory)
    assert checked["status"] == "LOCAL" and checked["fresh_numerical_verification"] is True
    replay = workflow.replay(directory, tmp_path / "replay")
    assert replay["evidence_id"] == original["evidence_id"]
    assert replay["artifact_digest"] == original["artifact_digest"]
    for name in ("execution_id", "result_id", "verification_id", "verification_execution_id"):
        assert replay[name] != original[name]
    assert _bytes(directory) == before


def test_exported_png_reopens_independently_and_sidecar_binds_exact_bytes(tmp_path):
    request = _expanded_request("texture")
    request["definition"] = {"expressions": ["u", "v", "0.5"], "parameters": {}}
    directory = tmp_path / "texture"
    original = workflow.run(request, directory)
    assert original["status"] == "LOCAL"
    before = _bytes(directory)
    output = tmp_path / "gradient.png"
    result = workflow.export_png(directory, output)
    width, height, pixels = _independent_png(output.read_bytes())
    artifact = workflow.read_bundle(directory)["artifact"]
    assert (width,height) == tuple(request["domain"]["resolution"])
    assert pixels == base64.b64decode(artifact["image"]["rgba_base64"], validate=True)
    manifest = read_json(Path(str(output)+".json"))
    assert manifest["output_sha256"] == "sha256:" + sha256(output.read_bytes()).hexdigest()
    assert manifest["source_execution_id"] == result["source_execution_id"] == original["execution_id"]
    assert manifest["authority"] == original["authority"]
    assert manifest["authority"]["visual_texture"] == "declared_cpu_rgba8_only"
    assert manifest["authority"]["gpu_pixel_equivalence"] == "not_established"
    assert manifest["authority"]["physical_material_validation"] == "not_established"
    assert manifest["authority"]["manufacturing_suitability"] == "not_established"
    assert manifest["authority"]["state_admission"] == "not_performed"
    assert manifest["authority"]["hardware_actuation"] == "not_performed"
    assert manifest["claims"] == contract.CLAIMS
    raw = output.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.export_png(directory, output)
    assert output.read_bytes() == raw and _bytes(directory) == before


@pytest.mark.parametrize("profile", ["parametric", "texture"])
def test_fully_resealed_false_representation_needs_fresh_checks_before_export(tmp_path, profile):
    directory = tmp_path / profile
    assert workflow.run(_expanded_request(profile), directory)["status"] == "LOCAL"
    workspace = read_json(directory / "workspace.json")
    candidate = next(record for record in workspace["results"] if record["operation_id"] == workflow.GENERATE)
    retained_verifier = next(record for record in workspace["results"] if record["operation_id"] == workflow.VERIFY)
    if profile == "parametric":
        face = candidate["data"]["mesh"]["triangles"][0]
        face[1], face[2] = face[2], face[1]
    else:
        image = candidate["data"]["image"]
        png = bytearray(base64.b64decode(image["png_base64"], validate=True))
        png[-5] ^= 1  # Corrupt IEND CRC while retaining its byte count.
        image["png_base64"] = base64.b64encode(png).decode("ascii")
        image["png_sha256"] = "sha256:" + sha256(png).hexdigest()
    seal(candidate["data"])
    seal(candidate)
    retained_verifier["parameters"]["candidate"] = deepcopy(candidate)
    payload = retained_verifier["data"]
    payload["candidate_record_digest"] = candidate["record_digest"]
    payload["report"]["candidate_digest"] = candidate["data"]["record_digest"]
    seal(payload["report"])
    seal(retained_verifier)
    execution = next(record for record in workspace["executions"] if record["operation_id"] == workflow.VERIFY)
    execution["parameters"] = deepcopy(retained_verifier["parameters"])
    seal(execution)
    _rewrite_occurrences(directory, workspace)
    before = _bytes(directory)
    with _no_providers():
        assert workflow.inspect(directory)["status"] == "LOCAL"
    with pytest.raises(ValueError):
        workflow.verify_retained(directory)
    output = tmp_path / ("forged.obj" if profile == "parametric" else "forged.png")
    exporter = workflow.export_obj if profile == "parametric" else workflow.export_png
    with pytest.raises(ValueError):
        exporter(directory, output)
    assert not output.exists() and not Path(str(output)+".json").exists()
    assert _bytes(directory) == before


@pytest.mark.parametrize("profile,export_format", [("parametric","png"),("texture","obj")])
def test_export_representation_cannot_be_silently_coerced_to_an_unqualified_format(tmp_path, profile, export_format):
    directory = tmp_path / profile
    assert workflow.run(_expanded_request(profile), directory)["status"] == "LOCAL"
    output = tmp_path / ("wrong." + export_format)
    exporter = workflow.export_png if export_format == "png" else workflow.export_obj
    with pytest.raises(ValueError):
        exporter(directory, output)
    assert not output.exists()


def test_server_example_catalog_is_a_superset_of_three_representation_types(local_server):
    with _no_providers():
        status, _, content = _http(local_server, "GET", "/api/examples")
    assert status == 200
    examples = {item["id"]: item["request"] for item in json.loads(content)["examples"]}
    assert {"sphere", "gyroid", "wave", "parametric", "texture"} <= examples.keys()
    assert surface.validate_surface_request(examples["parametric"])["schema"] == surface.REQUEST_SCHEMA
    assert texture.validate_texture_request(examples["texture"])["schema"] == texture.REQUEST_SCHEMA
    assert list(local_server.root.iterdir()) == []


@pytest.mark.parametrize("profile", ["parametric", "texture"])
def test_browser_api_preview_retain_and_export_preserve_typed_representation(local_server, profile):
    declaration = _expanded_request(profile)
    raw = json.dumps({"request": declaration}).encode()
    status, _, content = _http(local_server, "POST", "/api/preview", raw)
    preview = json.loads(content)
    assert status == 200 and preview["status"] == "preview" and preview["transient"] is True
    assert preview["request"] == declaration and preview["report"]["status"] == "PASS"
    expected_schema = surface.RESULT_SCHEMA if profile == "parametric" else texture.RESULT_SCHEMA
    assert preview["artifact"]["schema"] == expected_schema
    assert list(local_server.root.iterdir()) == []
    status, _, content = _http(local_server, "POST", "/api/run", raw)
    retained = json.loads(content)
    assert status == 200 and retained["summary"]["status"] == "LOCAL"
    assert retained["artifact"]["schema"] == expected_schema
    assert retained["summary"]["artifact_kind"] == ("mesh" if profile == "parametric" else "texture")
    original = local_server.root / retained["id"]
    before = _bytes(original)
    with _no_providers():
        opened_status, _, opened = _http(local_server, "GET", "/api/runs/" + retained["id"])
    assert opened_status == 200 and json.loads(opened)["artifact"] == retained["artifact"]
    export_format = "obj" if profile == "parametric" else "png"
    status, headers, content = _http(local_server, "GET", "/api/runs/" + retained["id"] + "/export?format=" + export_format)
    assert status == 200
    if profile == "texture":
        width, height, pixels = _independent_png(content)
        assert (width, height) == tuple(declaration["domain"]["resolution"])
        assert pixels == base64.b64decode(retained["artifact"]["image"]["rgba_base64"], validate=True)
        assert headers["Content-Type"] == "image/png"
    else:
        assert b"\nv " in content and b"\nf " in content
    assert _bytes(original) == before
