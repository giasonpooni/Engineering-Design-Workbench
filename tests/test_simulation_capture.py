"""Image-record and host tests. Named doubles are not native Godot evidence."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import sys
import zlib
from unittest.mock import patch

import pytest

from ciw.control_contracts import bytes_ref, observation, save_new
from ciw.godot_capture import (
    GodotObservationRenderer, _process, bind_renderer, capture, inspect_capture, read_bounded,
)
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.session import Session
from ciw.simulation_capture import (
    CHANNELS, FRAME, MODEL, PROVIDER, OPERATION, WIDTH, HEIGHT, encode, make_capture,
    png_info, project, render_request, selection, validate_capture, validate_dependencies, validate_result,
)
from ciw.simulation_control import SimulationControl, completed
from ciw.simulation_records import observer
from ciw.simulation_reference import ReferenceMotion


class PointContractDouble(ReferenceMotion):
    """Explicit Python fixture for source binding, not the native worker."""
    missing = False
    empty = False
    units = "m"
    frame = FRAME
    def identity(self):
        value = super().identity()
        value["model_id"] = MODEL
        return value
    def observe_for(self, selected):
        stamp = self.identity()["clock"]
        samples = []
        if not self.empty:
            for channel, value in zip(CHANNELS, (1.25, 2.5, -3.75)):
                if channel not in selected["channels"] or (self.missing and channel == "position_z"):
                    continue
                samples.append(observation(identity={"model_id": MODEL, "entity_id": "projectile", "execution_id": None},
                    clock=stamp, frame=self.frame, quantity=channel, value=value, unit=self.units,
                    provenance={"provider": PROVIDER, "sources": [bytes_ref(self.snapshot())], "semantics": "simulated"}))
        return {"observer": deepcopy(selected), "available_at": stamp, "samples": samples}


@pytest.fixture
def lab(tmp_path):
    session = Session(make_demo_run(), tmp_path / "source")
    control = SimulationControl(session)
    provider = PointContractDouble()
    instance = control.attach(provider, provider_id=PROVIDER, experiment_id="capture-contract-fixture")
    selected = observer("position-observer", kind="debugger", channels=CHANNELS)
    result = completed(instance.command("observe", observer=selected))
    source = tmp_path / "source.json"
    session.save_workspace(source)
    return session, provider, instance, result, source


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def test_png(width=WIDTH, height=HEIGHT, *, pixels=None, filter_byte=0):
    # A constructed image checks the container contract, not visual correctness.
    rows = (bytes([filter_byte]) + b"\x14\x22\x30" * WIDTH) * HEIGHT if pixels is None else pixels
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
test_png.__test__ = False
PNG = test_png()
RUNTIME = {"provider": "ciw.godot-observation-renderer", "profile": "godot-4.5.2-gl-compatibility-png.v1",
           "executable_sha256": "sha256:" + "1" * 64, "worker_sha256": "sha256:" + "2" * 64,
           "adapter_sha256": "sha256:" + "3" * 64}


def native_for(request, png=PNG, pid=12345):
    position = request["view"]["position_xyz_m"]
    return {"schema": "ciw.godot-observation-image-native.v1", "request_id": request["request_id"],
        "request_sha256": bytes_ref(encode(request)), "pid": pid, "engine_version": "4.5.2 (CONTRACT DOUBLE)",
        "version": [4, 5, 2, "stable"], "display_server": "X11", "rendering_method": "gl_compatibility",
        "video_adapter": "CONTRACT DOUBLE - not native evidence", "image_sha256": bytes_ref(png),
        "width": WIDTH, "height": HEIGHT, "camera": request["camera"], "marker_count": 0 if position is None else 1,
        "position_xyz_m": None if position is None else [struct.unpack("<f", struct.pack("<f", x))[0] for x in position],
        "input_unchanged": True}


class RendererContractDouble:
    calls = 0
    last_log = b"Contract renderer double; not a Godot execution.\n"
    last_native = None
    last_png = None
    runtime = RUNTIME
    def __init__(self, *args, **kwargs):
        pass
    def render(self, view, camera):
        self.calls += 1
        self.request = render_request(view, camera, "a" * 32)
        value = native_for(self.request)
        self.last_native = encode(value)
        self.last_png = PNG
        return value, PNG


def settings(source, index=0, camera="oblique"):
    return selection(source, entity_id="projectile", sample_index=index, camera=camera)


def image_record(source):
    selected = settings(source)
    request = render_request(project(source, selected), "oblique", "a" * 32)
    return make_capture(source, selected, RUNTIME, native_for(request), PNG)


def call_capture(lab, output_dir, **changes):
    _, _, _, source, path = lab
    kwargs = dict(expected_workspace_sha256=bytes_ref(path.read_bytes()), result_id=source["result_id"],
                  entity_id="projectile", sample_index=0, camera="oblique", executable=Path("unused"),
                  executable_sha256=RUNTIME["executable_sha256"], output_dir=output_dir)
    kwargs.update(changes)
    with patch("ciw.godot_capture.GodotObservationRenderer", RendererContractDouble):
        return capture(path, **kwargs)


def test_projection_contains_selected_samples_and_preserves_identity(lab):
    _, provider, _, source, _ = lab
    snapshot = provider.snapshot()
    with patch.object(provider, "snapshot", side_effect=AssertionError("must not read world")):
        view = project(source, settings(source))
    assert view["position_xyz_m"] == [1.25, 2.5, -3.75]
    assert view["source"]["execution_id"] == source["execution_id"]
    assert [s["record_digest"] for s in view["selected_samples"]] == [s["record_digest"] for s in source["data"]["observations"]["samples"]]
    assert provider.snapshot() == snapshot
    raw = encode(render_request(view, "front", "f" * 32))
    for forbidden in (b"configuration", b"snapshot_b64", b"velocity", b"queued"):
        assert forbidden not in raw


@pytest.mark.parametrize("change", ["index-negative", "index-bool", "index-high", "index-null", "wrong-entity", "wrong-id", "wrong-ref", "camera"])
def test_invalid_selections_refuse_before_output_or_renderer(lab, tmp_path, change):
    options = {"index-negative": {"sample_index": -1}, "index-bool": {"sample_index": True},
        "index-high": {"sample_index": 4}, "index-null": {"sample_index": None}, "wrong-entity": {"entity_id": "hidden"},
        "wrong-id": {"result_id": "result-" + "f" * 32}, "wrong-ref": {"expected_workspace_sha256": "sha256:" + "0" * 64},
        "camera": {"camera": "unknown"}}[change]
    dest = tmp_path / "must-not-exist"
    with pytest.raises(ValueError):
        call_capture(lab, dest, **options)
    assert not dest.exists()


@pytest.mark.parametrize("mode", ["empty", "partial", "narrow", "unit", "frame", "not-observation"])
def test_missingness_and_projection_boundary(lab, mode):
    _, provider, instance, source, _ = lab
    if mode == "not-observation":
        source = completed(instance.command("checkpoint"))
    else:
        provider.empty = mode == "empty"
        provider.missing = mode == "partial"
        provider.units = "cm" if mode == "unit" else "m"
        provider.frame = "different-frame" if mode == "frame" else FRAME
        channels = ["position_x"] if mode == "narrow" else CHANNELS
        source = completed(instance.command("observe", observer=observer("test", kind="debugger", channels=channels)))
    if mode in {"narrow", "unit", "frame", "not-observation"}:
        with pytest.raises(ValueError):
            project(source, settings(source))
    else:
        view = project(source, settings(source, None if mode == "empty" else 0))
        assert view["position_xyz_m"] is None
        assert view["availability"] == ("no_samples" if mode == "empty" else "missing_components")
        assert view["sample_time_s"] is None if mode == "empty" else view["selected_samples"][2] is None


def test_image_capture_uses_existing_artifact_and_distinct_session_execution(lab, tmp_path):
    session, provider, _, source, _ = lab
    renderer = RendererContractDouble()
    before_run = deepcopy(session.run)
    before_state = provider.snapshot()
    bind_renderer(session, renderer, tmp_path / "images")
    receipt = session.handle({"protocol_version": 1, "request_id": "render-test", "type": "operation.execute",
                             "payload": {"operation_id": OPERATION, "parameters": settings(source)}})
    result = completed(receipt)
    validate_result(result, PNG)
    validate_dependencies(session)
    assert result["execution_id"] != source["execution_id"]
    assert result["data"]["image"]["schema"] == "ciw.artifact.v1"
    assert result["data"]["image"]["metadata"]["source_execution_id"] == source["execution_id"]
    assert result["verification_id"] is None and session.run == before_run
    assert provider.snapshot() == before_state and session.results[source["result_id"]] == source
    assert renderer.calls == 1


def test_capture_wrapper_inspects_without_running_any_provider(lab, tmp_path):
    dest = tmp_path / "capture"
    result = call_capture(lab, dest)
    with patch("subprocess.Popen", side_effect=AssertionError("no process")), \
         patch("ciw.simulation_control.SimulationControl", side_effect=AssertionError("no simulation controller")):
        report = inspect_capture(dest, expected_capture_sha256=bytes_ref((dest / "capture.json").read_bytes()))
    assert report["source_execution_id"] == lab[3]["execution_id"] and report["capture_execution_id"] == result["execution_id"]
    assert not report["renderer_executed"] and not report["simulation_executed"]
    assert (dest / "source-workspace.json").read_bytes() == lab[4].read_bytes()


def test_existing_output_not_overwritten(lab, tmp_path):
    dest = tmp_path / "occupied"
    dest.mkdir()
    sentinel = dest / "capture.json"
    sentinel.write_text("keep")
    with pytest.raises(FileExistsError):
        call_capture(lab, dest)
    assert sentinel.read_text() == "keep"


def test_renderer_failure_retains_refusal_without_completion(lab, tmp_path):
    dest = tmp_path / "failed"
    with patch.object(RendererContractDouble, "render", side_effect=ValueError("deliberate renderer failure")):
        with pytest.raises(ValueError, match="did not complete"):
            call_capture(lab, dest)
    assert (dest / "workspace.json").is_file() and (dest / "render.log").is_file()
    assert not (dest / "capture.json").exists()
    data = json.loads((dest / "workspace.json").read_text())
    capture_exec = [e for e in data["executions"] if e["operation_id"] == OPERATION]
    assert len(capture_exec) == 1 and capture_exec[0]["status"] == "refused" and capture_exec[0]["result_id"] is None


def test_workspace_publication_failure_does_not_write_completion(lab, tmp_path):
    with patch.object(Session, "save_workspace", side_effect=OSError("workspace unavailable")):
        with pytest.raises(OSError):
            call_capture(lab, tmp_path / "fail")
    assert not (tmp_path / "fail/capture.json").exists()


@pytest.mark.parametrize("change", ["authority", "image-authority", "projection", "image-binding", "capture-request", "camera", "marker", "display-position", "runtime", "source-binding"])
def test_resealed_capture_changes_rejected(lab, change):
    data = image_record(lab[3])
    if change == "authority": data["verification_status"] = "verified"
    elif change == "image-authority": data["image"]["metadata"]["semantics"] = "observed"; seal(data["image"])
    elif change == "projection": data["view"]["position_xyz_m"][0] = 99; seal(data["view"])
    elif change == "image-binding": data["image"]["sha256"] = "sha256:" + "0" * 64; seal(data["image"])
    elif change == "capture-request": data["native"]["request_id"] = "b" * 32
    elif change == "camera": data["selection"]["camera"] = "front"
    elif change == "marker": data["native"]["marker_count"] = False
    elif change == "display-position": data["native"]["position_xyz_m"][2] = 0
    elif change == "runtime": data["runtime"]["provider"] = "untrusted-alternate"
    else: data["selection"]["source_result_ref"] = "sha256:" + "0" * 64
    seal(data)
    with pytest.raises(ValueError): validate_capture(data, PNG)


def test_removed_source_dependency_is_not_accepted(lab, tmp_path):
    session, _, _, source, _ = lab
    renderer = RendererContractDouble()
    bind_renderer(session, renderer, tmp_path / "images")
    completed(session.handle({"protocol_version": 1, "request_id": "render", "type": "operation.execute",
        "payload": {"operation_id": OPERATION, "parameters": settings(source)}}))
    session.results.pop(source["result_id"])
    with pytest.raises(ValueError, match="not the retained Session"):
        validate_dependencies(session)


@pytest.mark.parametrize("change", ["crc", "dimensions", "trailing", "truncated", "decompression", "filter", "metadata", "signature"])
def test_png_container_validation(change):
    value = PNG
    if change == "crc": value = value[:20] + bytes([value[20] ^ 1]) + value[21:]
    elif change == "dimensions": value = test_png(width=1)
    elif change == "trailing": value += b"hidden"
    elif change == "truncated": value = value[:-1]
    elif change == "decompression": value = test_png(pixels=b"x" * ((WIDTH * 3 + 1) * HEIGHT + 1))
    elif change == "filter": value = test_png(filter_byte=7)
    elif change == "metadata": value = value[:-12] + chunk(b"tEXt", b"not allowed") + value[-12:]
    else: value = b"not-png"
    with pytest.raises(ValueError): png_info(value)


def test_png_complete_scanlines_are_supported():
    assert png_info(PNG) == {"width": WIDTH, "height": HEIGHT, "bit_depth": 8, "channels": 3}


def test_png_payload_corruption_refused_by_bundle_reader(lab, tmp_path):
    dest = tmp_path / "capture"
    result = call_capture(lab, dest)
    path = dest / "images" / (result["data"]["image"]["sha256"].split(":")[1] + ".png")
    path.write_bytes(b"changed")
    with pytest.raises(ValueError): inspect_capture(dest)


def test_external_capture_pin_is_checked(lab, tmp_path):
    dest = tmp_path / "capture"
    call_capture(lab, dest)
    with pytest.raises(ValueError, match="Capture file digest"):
        inspect_capture(dest, expected_capture_sha256="sha256:" + "0" * 64)


def test_native_executable_pin_checked_before_launch(tmp_path):
    executable = tmp_path / "not-godot"
    executable.write_bytes(b"explicit test data")
    with patch("subprocess.Popen", side_effect=AssertionError("no launch")):
        with pytest.raises(ValueError, match="digest mismatch"):
            GodotObservationRenderer(executable, "sha256:" + "0" * 64)


def test_actual_process_output_and_failure_bounds(tmp_path):
    pid, code, log = _process([sys.executable, "-c", "print('process-test')"], tmp_path, 5)
    assert pid > 0 and code == 0 and b"process-test" in log
    with pytest.raises(ValueError, match="deadline"):
        _process([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, .1)
    with pytest.raises(ValueError, match="exceeded bound"):
        _process([sys.executable, "-c", "import sys; sys.stdout.write('x'*100000)"], tmp_path, 5)


def test_render_launcher_consumes_only_selected_data(lab, tmp_path):
    binary = tmp_path / "contract-double-binary"
    binary.write_bytes(b"not an engine")
    renderer = GodotObservationRenderer(binary, bytes_ref(binary.read_bytes()))
    view = project(lab[3], settings(lab[3]))
    def process(command, directory, timeout):
        assert "--headless" not in command and "--quiet" not in command
        assert "gl_compatibility" in command and "--script" in command
        request = json.loads((directory / "request.json").read_text())
        assert request["view"] == view and "source_result" not in request
        (directory / "observed.json").write_bytes(encode(native_for(request)))
        (directory / "image.png").write_bytes(PNG)
        return 12345, 0, b"CONTRACT DOUBLE"
    with patch("ciw.godot_capture._process", process):
        native, png = renderer.render(view, "oblique")
    assert png == PNG and native["pid"] == 12345


def test_input_mutation_in_native_render_is_refused(lab, tmp_path):
    binary = tmp_path / "double"
    binary.write_bytes(b"not engine")
    renderer = GodotObservationRenderer(binary, bytes_ref(binary.read_bytes()))
    def process(command, directory, timeout):
        request = json.loads((directory / "request.json").read_text())
        (directory / "observed.json").write_bytes(encode(native_for(request)))
        (directory / "image.png").write_bytes(PNG)
        (directory / "capture.gd").write_text("changed")
        return 12345, 0, b"CONTRACT DOUBLE"
    with patch("ciw.godot_capture._process", process), pytest.raises(ValueError, match="mutated"):
        renderer.render(project(lab[3], settings(lab[3])), "oblique")


def test_bounded_reader_rejects_symlink(tmp_path):
    target = tmp_path / "source"
    target.write_bytes(b"data")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        # Windows permissions are not needed to test the same explicit symlink guard.
        with patch.object(Path, "is_symlink", return_value=True), pytest.raises(ValueError):
            read_bounded(target)
    else:
        with pytest.raises(ValueError): read_bounded(link)


def test_cli_route_preserves_original_help():
    from ciw.godot_simulation_cli import main
    with patch("ciw.godot_capture.main", return_value=17) as capture_main:
        assert main(["capture", "inspect", "selected-directory"]) == 17
        capture_main.assert_called_once_with(["inspect", "selected-directory"])


@pytest.mark.parametrize("intent", [0, 1, 2, 3])
def test_png_accepts_standard_srgb_declaration(intent):
    image = PNG[:33] + chunk(b"sRGB", bytes([intent])) + PNG[33:]
    assert png_info(image) == png_info(PNG)


@pytest.mark.parametrize("mode", ["duplicate", "invalid-intent", "empty", "too-long", "after-data"])
def test_png_rejects_malformed_srgb(mode):
    declaration = chunk(b"sRGB", b"\0")
    if mode == "duplicate": declaration *= 2
    elif mode == "invalid-intent": declaration = chunk(b"sRGB", b"\4")
    elif mode == "empty": declaration = chunk(b"sRGB", b"")
    elif mode == "too-long": declaration = chunk(b"sRGB", b"\0\0")
    image = PNG[:33] + declaration + PNG[33:]
    if mode == "after-data": image = PNG[:-12] + declaration + PNG[-12:]
    with pytest.raises(ValueError): png_info(image)


def test_rejected_native_image_is_retained_only_as_diagnostic(lab, tmp_path):
    def bad_render(self, view, camera):
        self.request = render_request(view, camera, "c" * 32)
        self.last_png = b"bounded invalid native image bytes"
        native = native_for(self.request, self.last_png)
        self.last_native = encode(native)
        return native, self.last_png
    dest = tmp_path / "invalid-native-image"
    with patch.object(RendererContractDouble, "render", bad_render), pytest.raises(ValueError):
        call_capture(lab, dest)
    assert (dest / "native-image.png").read_bytes() == b"bounded invalid native image bytes"
    assert not (dest / "capture.json").exists()
    retained = json.loads((dest / "workspace.json").read_text())
    attempts = [e for e in retained["executions"] if e["operation_id"] == OPERATION]
    assert len(attempts) == 1 and attempts[0]["status"] == "refused"
