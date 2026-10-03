"""Optional source-checkout Blender/Godot/Bevy experiments on the existing Session.

Run ``python -m ciw.interactive_simulation --help``. Engine binaries are supplied
by the trusted local operator, never resolved from a saved investigation.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import tempfile
import time
import uuid

from . import interactive_contract as c

AUTHOR_OP = "simulation.projectile-author.v1"
RUN_OP = "simulation.projectile-run.v1"
COMPARE_OP = "simulation.projectile-compare.v1"
ROOT = Path(__file__).resolve().parents[2] / "tools" / "interactive-simulation"
_REGISTERED = False


def write_new(path, value):
    raw = c.canonical(value)
    c.require(len(raw) <= c.MAX_BYTES, "output exceeds byte budget")
    # Private per-investigation directory; no overwrite of an old artifact.
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def run_process(command, cwd, watched=(), timeout=60):
    """Bound actual child runtime and output. This is not an OS sandbox."""
    cwd = Path(cwd)
    logs = [cwd / "stdout.log", cwd / "stderr.log"]
    start = time.monotonic()
    with logs[0].open("wb") as out, logs[1].open("wb") as err:
        process = subprocess.Popen(command, cwd=cwd, stdout=out, stderr=err,
                                   stdin=subprocess.DEVNULL, start_new_session=(os.name == "posix"))
        reason = None
        try:
            while process.poll() is None:
                if time.monotonic()-start > timeout:
                    reason = "runtime timeout"
                    break
                if any(p.exists() and p.stat().st_size > c.MAX_BYTES for p in [*logs, *watched]):
                    reason = "runtime output budget exceeded"
                    break
                time.sleep(.02)
        finally:
            if process.poll() is None:
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
                process.wait(timeout=5)
        if reason is None and process.returncode:
            reason = "runtime exit " + str(process.returncode)
        if reason is None and any(p.exists() and p.stat().st_size > c.MAX_BYTES for p in [*logs, *watched]):
            reason = "runtime output budget exceeded"
    with logs[1].open("rb") as stream:
        stderr_prefix = stream.read(4096).decode("utf-8", "replace")
    diagnostic = {"elapsed_wall_s": time.monotonic()-start, "returncode": process.returncode,
                  "failure": reason, "stderr_prefix": stderr_prefix}
    if reason:
        raise RuntimeError(json.dumps(diagnostic))
    return diagnostic


class Binding:
    """Explicit operator binding; snapshot scripts and check executable drift."""
    def __init__(self, engine, executable, expected=None, *, adapter_root=None):
        c.require(engine in ("blender", "godot", "bevy"), "unsupported runtime")
        self.engine = engine
        self.executable = Path(executable).expanduser().resolve(strict=True)
        c.require(self.executable.is_file(), "runtime is not a file")
        relative = {"blender": "blender/author.py", "godot": "godot/projectile.gd", "bevy": "bevy/src/main.rs"}[engine]
        # Operator-selected adapter sources make the installed wheel usable
        # without assuming that tools/ lives beside site-packages. Saved records
        # never supply this path; reproduction still checks the retained bytes.
        root = ROOT if adapter_root is None else Path(adapter_root).expanduser().resolve(strict=True)
        c.require(root.is_dir(), "adapter root is not a directory")
        script_path = (root / relative).resolve(strict=True)
        c.require(script_path.is_relative_to(root.resolve()), "adapter script escapes selected root")
        with script_path.open("rb") as stream:
            self.script = stream.read(2 * 1024 * 1024 + 1)
        c.require(len(self.script) <= 2 * 1024 * 1024, "adapter source exceeds byte budget")
        self.identity = {"provider": "ciw.interactive."+engine,
                         "executable_sha256": file_sha(self.executable),
                         "adapter_sha256": c.sha(self.script),
                         "platform": platform.platform(),
                         "scope": "operator-selected binary and adapter bytes; shared libraries not attested"}
        if engine == "bevy":
            self.identity["cargo_manifest_sha256"] = file_sha(root / "bevy/Cargo.toml")
            self.identity["cargo_lock_sha256"] = file_sha(root / "bevy/Cargo.lock")
        c.require(expected is None or self.identity == expected, "runtime identity differs from retained execution")

    def runtime_identity(self):
        c.require(file_sha(self.executable) == self.identity["executable_sha256"], "runtime binary changed")
        return copy.deepcopy(self.identity)

    def invoke(self, request=None, asset=None):
        self.runtime_identity()
        with tempfile.TemporaryDirectory(prefix="ciw-interactive-") as directory:
            d = Path(directory)
            if self.engine == "blender":
                (d / "author.py").write_bytes(self.script)
                command = [str(self.executable), "--background", "--factory-startup", "--disable-autoexec",
                           "--python-exit-code", "2", "--python", str(d / "author.py"), "--", str(d / "scene.glb"), str(d / "author.json")]
                run_process(command, d, [d / "scene.glb", d / "author.json"])
                self.runtime_identity()
                with (d / "scene.glb").open("rb") as stream:
                    raw = stream.read(2 * 1024 * 1024 + 1)
                result = {"schema": c.AUTHOR, "format": "glb", "asset_sha256": c.sha(raw),
                          "asset_b64": base64.b64encode(raw).decode(), "generator_sha256": c.sha(self.script),
                          "report": c.read(d / "author.json")}
                c.validate_asset(result)
                return result
            c.validate_request(request)
            c.require(c.sha(asset) == request["asset_sha256"], "runtime asset/request mismatch")
            c.validate_glb(asset)
            (d / "request.json").write_bytes(c.canonical(request))
            (d / "scene.glb").write_bytes(asset)
            args = [str(d / "request.json"), str(d / "scene.glb"), str(d / "trace.json")]
            if self.engine == "godot":
                (d / "projectile.gd").write_bytes(self.script)
                (d / "project.godot").write_text('config_version=5\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
                command = [str(self.executable), "--headless", "--path", str(d), "--script", "projectile.gd", "--", *args]
            else:
                command = [str(self.executable), *args]
            run_process(command, d, [d / "trace.json"])
            self.runtime_identity()
            result = {"schema": c.TRACE, "request": copy.deepcopy(request), "trace": c.read(d / "trace.json")}
            c.validate_trace(result)
            c.require(result["trace"]["engine"] == self.engine, "wrong engine response")
            return result


def make_run(scenario):
    from .adapters.protocol import InstrumentManifest
    from .core.identities import evidence_id
    c.validate_scenario(scenario)
    channels = {axis: {"unit": "m", "kind": "declared_initial_condition", "values": [scenario["p0_m"][i]]}
                for i, axis in enumerate(("x", "y", "z"))}
    manifest = InstrumentManifest(
        instrument_id="org.notationsystems.projectile-scenario", version="1", role="operation_provider",
        inputs=(c.SCENARIO,), outputs=("run.v1",), units={axis: "m" for axis in channels},
        frames=(scenario["frame"],), sampling={"mode": "declared_initial_condition"},
        normalization={"state": "unchanged"}, supported_operations=(),
        determinism={"claim": "none from declaration"}, tolerance_policy={"policy": "operation-specific"},
        calibration_requirements={"status": "not_applicable_synthetic"})
    run = {"run_schema": "run.v1", "run_id": "run-"+uuid.uuid4().hex,
           "instrument": "org.notationsystems.projectile-scenario", "time_s": [0.0],
           "channels": channels, "render": {}, "metadata": {
               "sample_count": 1, "sample_rate_hz": None, "duration_s": 1.0,
               "coordinate_frame": scenario["frame"], "manifest": manifest.to_dict(),
               "provenance": {"origin": "declared_initial_conditions_not_observations",
                              "duration_s_semantics": "selection support only, not simulated duration"},
               "projectile_scenario": copy.deepcopy(scenario)}}
    run["evidence_id"] = evidence_id(run)
    return run


def _validate_payload(operation, data, run, parameters, selection):
    c.validate_scenario(run["metadata"]["projectile_scenario"])
    if operation == AUTHOR_OP:
        c.require(parameters == {}, "author accepts no arbitrary script/configuration")
        c.validate_asset(data)
    elif operation == RUN_OP:
        c.keys(parameters, "asset_result_id asset_record_digest engine scenario fault nonce", "run parameters")
        c.validate_trace(data)
        request = data["request"]
        for field in ("scenario", "fault", "nonce"):
            c.require(request[field] == parameters[field], "captured request mismatch")
        c.require(data["trace"]["engine"] == parameters["engine"], "captured engine mismatch")
    else:
        c.keys(parameters, "left_result_id right_result_id left_record_digest right_record_digest", "comparison parameters")
        c.keys(data, "schema policy left right cross_runtime_max_position_m claim bindings", "comparison result")
        c.require(data["schema"] == c.COMPARE and data["policy"] == c.POLICY and data["bindings"] == parameters, "comparison binding/policy mismatch")
        for side in ("left", "right"):
            c.keys(data[side], "status max_position_error_m max_velocity_error_m_s first_out_of_policy_tick", "metrics")
            status = data[side]["status"]
            c.require(status in ("PASS", "FAIL", "INCOMPLETE"), "comparison status")
            for metric in ("max_position_error_m", "max_velocity_error_m_s"):
                value = data[side][metric]
                c.require(value is None if status == "INCOMPLETE" else c.number(value) >= 0, "invalid metric availability")
            tick = data[side]["first_out_of_policy_tick"]
            c.require((type(tick) is int and 1 <= tick <= 2000) if status == "FAIL" else tick is None, "invalid policy crossing")
            if status != "INCOMPLETE":
                within = (data[side]["max_position_error_m"] <= c.POLICY["position_m"]
                          and data[side]["max_velocity_error_m_s"] <= c.POLICY["velocity_m_s"])
                c.require((status == "PASS") == within, "status contradicts retained error bounds")
        complete = all(data[side]["status"] != "INCOMPLETE" for side in ("left", "right"))
        delta = data["cross_runtime_max_position_m"]
        c.require(c.number(delta) >= 0 if complete else delta is None, "invalid cross-runtime metric availability")
        c.require(data["claim"] == "numerical comparison only; not physical validation or verification", "comparison claim changed")


def register_schemas():
    global _REGISTERED
    if not _REGISTERED:
        from .operations.schemas import register_payload_validator
        for operation in (AUTHOR_OP, RUN_OP, COMPARE_OP):
            register_payload_validator(operation, _validate_payload)
        _REGISTERED = True


def validate_session(session):
    """Check custom dependency bindings, without rerunning engines or references."""
    source = session.run["metadata"]["projectile_scenario"]
    expected = make_run(source)
    c.require(session.run["evidence_id"] == expected["evidence_id"], "declared source/channel mismatch")
    for result in session.results.values():
        op, p, data = result["operation_id"], result.get("parameters", {}), result["data"]
        if op == AUTHOR_OP:
            c.require(data["generator_sha256"] == result["runtime"]["adapter_sha256"], "author source binding")
        elif op == RUN_OP:
            asset = session.results.get(p["asset_result_id"])
            c.require(asset is not None and asset["operation_id"] == AUTHOR_OP, "asset dependency missing")
            c.require(asset["record_digest"] == p["asset_record_digest"] and asset["data"]["asset_sha256"] == data["request"]["asset_sha256"], "asset dependency mismatch")
            c.require(result["runtime"]["provider"] == "ciw.interactive."+p["engine"], "engine/runtime binding")
        elif op == COMPARE_OP:
            for side in ("left", "right"):
                trace = session.results.get(p[side+"_result_id"])
                c.require(trace is not None and trace["operation_id"] == RUN_OP and trace["record_digest"] == p[side+"_record_digest"], "comparison dependency mismatch")
            a, b = [session.results[p[x+"_result_id"]]["data"] for x in ("left", "right")]
            c.require(a["request"]["scenario"] == b["request"]["scenario"], "comparison grid mismatch")
    return session


def _request(session, operation, parameters, path):
    response = session.handle({"protocol_version": 1, "request_id": uuid.uuid4().hex,
                               "type": "operation.execute", "payload": {"operation_id": operation, "parameters": parameters}})
    c.require(response["type"] != "error", str(response.get("payload")))
    validate_session(session)
    session.save_workspace(path)
    execution = list(session.executions.values())[-1]
    c.require(execution["status"] == "completed", "retained refusal: " + json.dumps(execution.get("refusal")))
    return session.results[execution["result_id"]]


def bind(session, bindings):
    from .operations.registry import Operation
    def invoke_bound(binding, *args):
        from .adapters.protocol import AdapterRefusal
        try:
            return binding.invoke(*args)
        except RuntimeError as exc:
            raise AdapterRefusal("runtime_failed", str(exc)) from exc
    def author(run, parameters):
        c.require(parameters == {}, "unsupported author parameters")
        return invoke_bound(bindings["blender"])
    def execute(run, p):
        c.keys(p, "asset_result_id asset_record_digest engine scenario fault nonce", "run parameters")
        c.validate_scenario(p["scenario"])
        asset = session.results[p["asset_result_id"]]
        c.require(asset["operation_id"] == AUTHOR_OP and asset["record_digest"] == p["asset_record_digest"], "invalid selected asset")
        request = {"schema": "ciw.projectile-request.v1", "scenario": p["scenario"], "nonce": p["nonce"],
                   "fault": p["fault"], "asset_sha256": asset["data"]["asset_sha256"]}
        return invoke_bound(bindings[p["engine"]], request, c.validate_asset(asset["data"]))
    def compare(run, p):
        left, right = [session.results[p[x+"_result_id"]] for x in ("left", "right")]
        for side, result in zip(("left", "right"), (left, right)):
            c.require(result["operation_id"] == RUN_OP and result["record_digest"] == p[side+"_record_digest"], "comparison source mismatch")
        data = c.comparison(left["data"], right["data"])
        data["bindings"] = copy.deepcopy(p)
        return data
    # Run binding is selected once per Session binding, never from saved content.
    if "blender" in bindings:
        session.operations.register(Operation(AUTHOR_OP, "backend", author, bindings["blender"].runtime_identity))
    engines = [x for x in ("godot", "bevy") if x in bindings]
    c.require(len(engines) <= 1, "bind one simulation engine per Session instance")
    if engines:
        chosen = engines[0]
        def selected(run, p):
            c.require(p["engine"] == chosen, "engine is not operator-bound")
            return execute(run, p)
        session.operations.register(Operation(RUN_OP, "backend", selected, bindings[chosen].runtime_identity))
    session.operations.register(Operation(COMPARE_OP, "backend", compare,
        lambda: {"provider": "ciw.projectile-analytic-comparison", "source_sha256": file_sha(Path(c.__file__)),
                 "python": platform.python_version(), "claim": "ordinary numerical check, not a verifier"}))


def open_saved(path, output):
    from .session import Session
    register_schemas()
    return validate_session(Session.from_workspace(Path(path), Path(output)))


def inspect(path):
    with tempfile.TemporaryDirectory(prefix="ciw-interactive-inspect-") as directory:
        session = open_saved(path, directory)
        return {"workspace": str(path), "evidence_id": session.run["evidence_id"],
                "executions": [{"execution_id": e["execution_id"], "operation": e["operation_id"], "status": e["status"],
                                "engine": e["parameters"].get("engine"), "result_id": e["result_id"]} for e in session.executions.values()],
                "comparisons": [r["data"] for r in session.results.values() if r["operation_id"] == COMPARE_OP],
                "note": "retained records only; no provider or numerical reference executed"}


def run_case(scenario, blender, runtime, executable, output, *, adapter_root=None):
    from .session import Session
    register_schemas()
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    session = Session(make_run(scenario), output)
    options = {} if adapter_root is None else {"adapter_root": adapter_root}
    bind(session, {"blender": Binding("blender", blender, **options), runtime: Binding(runtime, executable, **options)})
    path = output / "workspace.json"
    asset = _request(session, AUTHOR_OP, {}, path)
    p = {"asset_result_id": asset["result_id"], "asset_record_digest": asset["record_digest"],
         "engine": runtime, "scenario": scenario, "fault": "none", "nonce": uuid.uuid4().hex}
    result = _request(session, RUN_OP, p, path)
    compare_results(session, result, result, path)
    return path, result


def extend_case(path, runtime, executable, output, execution_id=None, scenario=None, fault="none", *, adapter_root=None):
    """Replay exact selected execution, or add an explicitly changed candidate."""
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    session = open_saved(path, output)
    options = {} if adapter_root is None else {"adapter_root": adapter_root}
    prior = session.executions.get(execution_id) if execution_id else None
    if execution_id:
        c.require(prior is not None and prior["operation_id"] == RUN_OP and prior["status"] == "completed", "select a completed simulation execution")
        c.require(prior["parameters"]["engine"] == runtime and scenario is None and fault == "none", "replay cannot change runtime or scenario")
        p = copy.deepcopy(prior["parameters"])
        binding = Binding(runtime, executable, expected=prior["runtime"], **options)
    else:
        assets = [r for r in session.results.values() if r["operation_id"] == AUTHOR_OP]
        c.require(len(assets) == 1, "select a workspace with exactly one authored asset")
        a = assets[0]
        p = {"asset_result_id": a["result_id"], "asset_record_digest": a["record_digest"],
             "engine": runtime, "scenario": scenario or session.run["metadata"]["projectile_scenario"],
             "fault": fault, "nonce": uuid.uuid4().hex}
        binding = Binding(runtime, executable, **options)
    # Fresh request/instance occurrence for replay; parent execution is retained.
    p["nonce"] = uuid.uuid4().hex
    bind(session, {runtime: binding})
    result = _request(session, RUN_OP, p, output / "workspace.json")
    peers = [r for r in session.results.values() if r["operation_id"] == RUN_OP and r["data"]["request"]["scenario"] == p["scenario"]]
    left = session.results[prior["result_id"]] if prior else peers[0]
    compare_results(session, left, result, output / "workspace.json")
    return output / "workspace.json", result


def compare_results(session, left, right, path):
    p = {"left_result_id": left["result_id"], "right_result_id": right["result_id"],
         "left_record_digest": left["record_digest"], "right_record_digest": right["record_digest"]}
    return _request(session, COMPARE_OP, p, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--scenario", required=True); run.add_argument("--blender", required=True)
    run.add_argument("--runtime", choices=("godot", "bevy"), required=True)
    run.add_argument("--executable", required=True); run.add_argument("--output-dir", required=True)
    run.add_argument("--adapter-root", help="Operator-selected tools/interactive-simulation directory")
    view = sub.add_parser("inspect"); view.add_argument("workspace")
    for name in ("replay", "candidate"):
        cmd = sub.add_parser(name); cmd.add_argument("workspace")
        cmd.add_argument("--runtime", choices=("godot", "bevy"), required=True)
        cmd.add_argument("--executable", required=True); cmd.add_argument("--output-dir", required=True)
        cmd.add_argument("--adapter-root", help="Operator-selected adapter sources; never read from workspace")
        if name == "replay":
            cmd.add_argument("--execution-id", required=True)
        else:
            cmd.add_argument("--scenario"); cmd.add_argument("--diagnostic-fault", choices=("none", "double-gravity"), default="none")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect(args.workspace)
        elif args.command == "run":
            path, _ = run_case(c.read(args.scenario), args.blender, args.runtime, args.executable, args.output_dir, adapter_root=args.adapter_root)
            result = inspect(path)
        else:
            path, _ = extend_case(args.workspace, args.runtime, args.executable, args.output_dir,
                                 execution_id=getattr(args, "execution_id", None),
                                 scenario=c.read(args.scenario) if getattr(args, "scenario", None) else None,
                                 fault=getattr(args, "diagnostic_fault", "none"), adapter_root=args.adapter_root)
            result = inspect(path)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        parser.exit(2, str(exc)+"\n")


if __name__ == "__main__":
    raise SystemExit(main())
