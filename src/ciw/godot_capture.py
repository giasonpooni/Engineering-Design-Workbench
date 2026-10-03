"""Explicit Godot image rendering of retained observations on the original Session.

This launches a separate render-only process with installed code and selected
observation data. It never launches a simulation worker or loads a saved scene.
The native runtime, capture execution and original observation remain distinct.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import file_digest
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import uuid

from .control_contracts import MAX_BYTES, bytes_ref, content_ref, load, save_new
from .operations.registry import Operation
from .simulation_capture import (
    OPERATION, AUTHORITY, MAX_IMAGE, WIDTH, HEIGHT, encode, make_capture, project,
    register_records, render_request, selection, validate_dependencies, validate_native,
    validate_result, validate_runtime, validate_selection,
)
from .simulation_control import completed, open_workspace
from .simulation_records import require

MAX_LOG = 65536
ERROR_LINE = re.compile(r"^(?:SCRIPT ERROR|ERROR):|(?:Parse|Compile) Error:", re.M)
PROJECT = b'''config_version=5
[application]
config/name="NET retained-observation capture"
[display]
window/size/viewport_width=1280
window/size/viewport_height=800
window/size/window_width_override=1280
window/size/window_height_override=800
[rendering]
renderer/rendering_method="gl_compatibility"
environment/defaults/default_clear_color=Color(0.035,0.055,0.085,1)
'''


def read_bounded(path: Path, limit: int = MAX_BYTES) -> bytes:
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Require a regular non-symlink evidence file")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "Evidence file exceeds the read budget")
    return raw


def _process(command: list[str], cwd: Path, timeout: float) -> tuple[int, int, bytes]:
    """One bounded child, bounded combined output, no shell or stdin commands.

    Not an OS sandbox or process-tree manager. The installed worker spawns no
    children. Caller retains diagnostics on failures and successful executions.
    """
    require(type(timeout) in (float, int) and 0 < timeout <= 90, "Capture deadline must be in (0,90] seconds")
    env = os.environ.copy()
    env["GODOT_SILENCE_ROOT_WARNING"] = "1"
    proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
    output = bytearray()
    overflow = threading.Event()
    read_failed = threading.Event()
    def drain():
        try:
            while True:
                part = proc.stdout.read(4096)
                if not part:
                    return
                room = MAX_LOG - len(output)
                output.extend(part[:room])
                if len(part) > room:
                    overflow.set()
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                    return
        except OSError:
            read_failed.set()
    worker = threading.Thread(target=drain, daemon=True)
    worker.start()
    try:
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            proc.wait(timeout=5)
            worker.join(timeout=5)
            error = ValueError("Render deadline exceeded")
            error.native_log = bytes(output)
            raise error from exc
        worker.join(timeout=5)
        require(not worker.is_alive(), "Render output did not close after process exit")
        if overflow.is_set() or read_failed.is_set():
            error = ValueError("Render output exceeded bound or failed to close")
            error.native_log = bytes(output)
            raise error
        return proc.pid, code, bytes(output)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        worker.join(timeout=5)
        proc.stdout.close()


class GodotObservationRenderer:
    """Bound operator-selected binary and installed static render worker."""
    def __init__(self, executable: Path, expected_sha256: str, *, timeout: float = 60):
        content_ref(expected_sha256)
        path = Path(executable).resolve(strict=True)
        require(path.is_file() and path.stat().st_size <= 512 * 1024 * 1024, "Select a bounded Godot executable")
        with path.open("rb") as stream:
            actual = "sha256:" + file_digest(stream, "sha256").hexdigest()
        require(actual == expected_sha256, "Godot render executable digest mismatch")
        require(type(timeout) in (float, int) and 0 < timeout <= 90, "Invalid render deadline")
        self.executable, self.timeout = path, timeout
        self.script = Path(__file__).with_name("godot_runtime").joinpath("observation_capture.gd").read_bytes()
        self.runtime = {"provider": "ciw.godot-observation-renderer", "profile": "godot-4.5.2-gl-compatibility-png.v1",
                        "executable_sha256": actual, "worker_sha256": bytes_ref(self.script),
                        "adapter_sha256": bytes_ref(Path(__file__).read_bytes())}
        self.last_log = b""
        self.last_native = None
        self.last_png = None

    def render(self, view: dict, camera: str) -> tuple[dict, bytes]:
        self.last_log, self.last_native, self.last_png = b"", None, None
        # Recheck a changed operator path; this is not a transitive binary attestation
        # or protection against an adversarial same-user filesystem race.
        with self.executable.open("rb") as stream:
            require("sha256:" + file_digest(stream, "sha256").hexdigest() == self.runtime["executable_sha256"], "Render executable changed after binding")
        request = render_request(view, camera, uuid.uuid4().hex)
        raw = encode(request)
        require(len(raw) <= 65536, "Render projection exceeds request budget")
        with tempfile.TemporaryDirectory(prefix="net-observation-render-") as directory:
            root = Path(directory)
            inputs = {"project.godot": PROJECT, "capture.gd": self.script, "request.json": raw}
            for name, payload in inputs.items():
                (root / name).write_bytes(payload)
            command = [str(self.executable), "--path", str(root), "--script", "res://capture.gd",
                       "--rendering-method", "gl_compatibility", "--audio-driver", "Dummy",
                       "--resolution", f"{WIDTH}x{HEIGHT}"]
            # No --headless or --quiet: a real viewport image is required.
            try:
                pid, code, self.last_log = _process(command, root, self.timeout)
            except Exception as exc:
                self.last_log = getattr(exc, "native_log", b"")
                raise
            require(code == 0 and not ERROR_LINE.search(self.last_log.decode("utf-8", errors="replace")), "Godot rendering failed; inspect render.log")
            from .session import loads_json
            native_raw = read_bounded(root / "observed.json", 65536)
            self.last_native = native_raw
            # Retain bounded native bytes even if their PNG/native contract is
            # refused. Diagnostics are not a completed or admitted image artifact.
            image = read_bounded(root / "image.png", MAX_IMAGE)
            self.last_png = image
            native = loads_json(native_raw.decode("utf-8"))
            validate_native(native, request)
            require(native["pid"] == pid, "Render process identity mismatch")
            require(native["image_sha256"] == bytes_ref(image), "Rendered image hash mismatch")
            for name, payload in inputs.items():
                require(read_bounded(root / name) == payload, "Renderer mutated its selected inputs or installed code")
            return native, image


def bind_renderer(session, renderer, image_dir: Path) -> None:
    """Add an explicitly supplied renderer to the existing OperationRegistry."""
    register_records()
    validate_runtime(renderer.runtime)
    image_dir = Path(image_dir)
    require(not image_dir.exists(), "Choose a new image directory")
    image_dir.mkdir(parents=True, exist_ok=False)
    runtime = deepcopy(renderer.runtime)
    def execute(run: dict, parameters: dict) -> dict:
        validate_selection(parameters)
        require(renderer.runtime == runtime, "Render binding changed")
        source = deepcopy(session.results.get(parameters["source_result_id"]))
        require(source is not None, "Source result is not in the existing Session")
        view = project(source, parameters)
        native, png = renderer.render(view, parameters["camera"])
        data = make_capture(source, parameters, runtime, native, png)
        path = image_dir / (data["image"]["sha256"].split(":", 1)[1] + ".png")
        try:
            with path.open("xb") as out:
                out.write(png)
        except FileExistsError:
            require(read_bounded(path, MAX_IMAGE) == png, "Content-addressed image changed")
        return data
    session.operations.register(Operation(OPERATION, "backend", execute, lambda: deepcopy(runtime)))


def _reopen(raw: bytes, output_dir: Path):
    register_records()
    with tempfile.TemporaryDirectory(prefix="net-capture-preflight-") as temp:
        frozen = Path(temp) / "workspace.json"
        frozen.write_bytes(raw)
        checked = open_workspace(frozen, output_dir=Path(temp) / "check")
        validate_dependencies(checked)
        # Original Session reopening is repeated on the exact frozen bytes only
        # after the extra source-dependency check. No providers are attached.
        return open_workspace(frozen, output_dir=output_dir)


def capture(workspace: Path, *, expected_workspace_sha256: str, result_id: str, entity_id: str,
            sample_index: int | None, camera: str, executable: Path, executable_sha256: str,
            output_dir: Path) -> dict:
    """Validate source and selection before any requested output or native launch."""
    raw = read_bounded(workspace)
    require(bytes_ref(raw) == content_ref(expected_workspace_sha256), "Source workspace digest mismatch")
    with tempfile.TemporaryDirectory(prefix="net-capture-selection-") as temp:
        session = _reopen(raw, Path(temp) / "selection")
        source = session.results.get(result_id)
        require(source is not None, "Selected result is not in the source workspace")
        selected = selection(source, entity_id=entity_id, sample_index=sample_index, camera=camera,
                             source_workspace_sha256=bytes_ref(raw))
        project(source, selected)
    renderer = GodotObservationRenderer(executable, executable_sha256)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    session = _reopen(raw, output_dir)
    (output_dir / "source-workspace.json").write_bytes(raw)
    try:
        bind_renderer(session, renderer, output_dir / "images")
        receipt = session.handle({"protocol_version": 1, "request_id": "capture-" + uuid.uuid4().hex,
            "type": "operation.execute", "payload": {"operation_id": OPERATION, "parameters": selected}})
        save_new(output_dir / "dispatch.json", receipt)
        result = completed(receipt)
        validate_result(result)
        validate_dependencies(session)
    finally:
        session.save_workspace(output_dir / "workspace.json")
        (output_dir / "render.log").write_bytes(renderer.last_log)
        if renderer.last_native is not None:
            (output_dir / "native.json").write_bytes(renderer.last_native)
        if renderer.last_png is not None:
            (output_dir / "native-image.png").write_bytes(renderer.last_png)
    # Completion is last, after the original Session workspace is saved.
    save_new(output_dir / "capture.json", result)
    return result


def inspect_capture(directory: Path, *, expected_capture_sha256: str | None = None) -> dict:
    """Reopen and validate existing evidence without executing a renderer/provider."""
    from .session import loads_json
    directory = Path(directory)
    raw = read_bounded(directory / "capture.json")
    if expected_capture_sha256 is not None:
        require(bytes_ref(raw) == content_ref(expected_capture_sha256), "Capture file digest mismatch")
    result = loads_json(raw.decode("utf-8"))
    validate_result(result)
    image = result["data"]["image"]
    png = read_bounded(directory / "images" / (image["sha256"].split(":", 1)[1] + ".png"), MAX_IMAGE)
    validate_result(result, png)
    with tempfile.TemporaryDirectory(prefix="net-capture-inspect-") as temp:
        session = _reopen(read_bounded(directory / "workspace.json"), Path(temp) / "reader")
        require(session.results.get(result["result_id"]) == result, "Capture result is absent or changed in Session")
        source_raw = read_bounded(directory / "source-workspace.json")
        require(bytes_ref(source_raw) == result["parameters"]["source_workspace_sha256"], "Capture source-workspace byte binding mismatch")
        original = _reopen(source_raw, Path(temp) / "original")
        source = result["data"]["source_result"]
        require(original.results.get(source["result_id"]) == source, "Original workspace/source binding mismatch")
        require(all(session.results.get(k) == v for k, v in original.results.items())
                and all(session.executions.get(k) == v for k, v in original.executions.items())
                and session.run == original.run, "Capture workspace changed its previous evidence")
    return {"status": "retained_capture_checked", "capture_execution_id": result["execution_id"],
            "source_execution_id": source["execution_id"], "image_sha256": image["sha256"],
            "availability": result["data"]["view"]["availability"], "renderer_executed": False,
            "simulation_executed": False, **AUTHORITY}


def demo(executable: Path, executable_sha256: str, output_dir: Path) -> dict:
    """Actual native source followed by three separately executed image captures."""
    from .godot_simulation import DEFAULT, PROVIDER_ID, STEP, GodotProjectile
    from .instruments import make_demo_run
    from .session import Session
    from .simulation_control import SimulationControl
    from .simulation_records import observer
    from .simulation_capture import CHANNELS
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    session = Session(make_demo_run(), output_dir / "source")
    config = {**deepcopy(DEFAULT), "p0_m": [1, 2, -3], "v0_m_s": [2, 3, 1]}
    try:
        with GodotProjectile(executable, expected_sha256=executable_sha256, configuration=config) as native:
            control = SimulationControl(session)
            instance = control.attach(native, provider_id=PROVIDER_ID, experiment_id="native-observation-images")
            player = observer("delayed-position", kind="embodied_agent", channels=CHANNELS)
            debugger = observer("current-position", kind="debugger", channels=CHANNELS)
            empty = completed(instance.command("observe", observer=player))
            completed(instance.command("start"))
            for _ in range(10):
                completed(instance.command("step", dt=STEP))
            current = completed(instance.command("observe", observer=debugger))
            delayed = completed(instance.command("observe", observer=player))
            completed(instance.command("stop"))
        require(native.diagnostics()["returncode"] == 0, "Source native process did not close cleanly")
    finally:
        session.save_workspace(output_dir / "source" / "workspace.json")
    source = output_dir / "source" / "workspace.json"
    source_hash = bytes_ref(source.read_bytes())
    outputs = []
    for name, selected, index in (("current", current, 10), ("delayed", delayed, 8), ("unavailable", empty, None)):
        result = capture(source, expected_workspace_sha256=source_hash, result_id=selected["result_id"],
            entity_id="projectile", sample_index=index, camera="oblique", executable=executable,
            executable_sha256=executable_sha256, output_dir=output_dir / name)
        outputs.append({"name": name, "capture_result_id": result["result_id"],
                        "capture_execution_id": result["execution_id"],
                        "source_execution_id": selected["execution_id"],
                        "image_sha256": result["data"]["image"]["sha256"],
                        "image_file": name + "/images/" + result["data"]["image"]["sha256"].split(":")[1] + ".png"})
    require(bytes_ref(source.read_bytes()) == source_hash, "Rendering changed source workspace")
    summary = {"status": "completed", "source_workspace_sha256": source_hash,
               "source_execution_count": len(session.executions), "capture_count": len(outputs),
               "source_process": native.diagnostics(), "captures": outputs, **AUTHORITY}
    save_new(output_dir / "summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="net simulation godot capture", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("demo")
    p.add_argument("--godot", type=Path, required=True)
    p.add_argument("--godot-sha256", required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p = sub.add_parser("create")
    p.add_argument("workspace", type=Path)
    p.add_argument("--expected-workspace-sha256", required=True)
    p.add_argument("--result-id", required=True)
    p.add_argument("--entity-id", required=True)
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument("--sample-index", type=int)
    choice.add_argument("--unavailable", action="store_true")
    p.add_argument("--camera", choices=["oblique", "front"], default="oblique")
    p.add_argument("--godot", type=Path, required=True)
    p.add_argument("--godot-sha256", required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p = sub.add_parser("inspect")
    p.add_argument("directory", type=Path)
    p.add_argument("--expected-capture-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = demo(args.godot, args.godot_sha256, args.output_dir)
        elif args.command == "inspect":
            result = inspect_capture(args.directory, expected_capture_sha256=args.expected_capture_sha256)
        else:
            result = capture(args.workspace, expected_workspace_sha256=args.expected_workspace_sha256,
                result_id=args.result_id, entity_id=args.entity_id, sample_index=args.sample_index,
                camera=args.camera, executable=args.godot, executable_sha256=args.godot_sha256, output_dir=args.output_dir)
            result = {"status": "completed", "capture_result_id": result["result_id"],
                      "capture_execution_id": result["execution_id"], "image": result["data"]["image"], **AUTHORITY}
        print(encode(result).decode("utf-8"), end="")
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, subprocess.SubprocessError) as exc:
        print(encode({"status": "refused", "reason": str(exc)}).decode(), file=sys.stderr, end="")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
