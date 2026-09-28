"""Game-development capture, checks and reproduction in the existing CIW Session.

python -m ciw.game_workflow --help

Only the optional, operator-bound Godot courier reference runs natively in v1.
No saved file can choose a script, executable, import, device or network target.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import platform
import tempfile
import uuid

from . import game_trace as c
from .control_contracts import bytes_ref, content_ref, keys, load, save_new
from .core.identities import content_identity, evidence_id
from .interactive_simulation import file_sha, run_process

CAPTURE_OP = "game.trace-capture.v1"
AUDIT_OP = "game.trace-audit.v1"
COMPARE_OP = "game.trace-compare.v1"
_REGISTERED = False


def courier_scenario() -> dict:
    def channel(entity, quantity, perspective="world"):
        return {"entity_id": entity, "quantity": quantity, "unit": "1", "frame": "courier-discrete-state", "perspective": perspective}
    return {"schema": c.SCENARIO, "project_id": "net-reference", "scenario_id": "courier-delay", "model_id": "courier-message.v1",
            "source_class": "synthetic_fixture", "clock": {"id": "courier-logical-time", "tick_seconds": 0.25, "duration_ticks": 8},
            "entities": ["commander", "courier", "recipient"],
            "channels": {"knowledge": channel("recipient", "knowledge.order_received", "recipient"),
                         "mission": channel("courier", "mission.stage"),
                         "reward": channel("courier", "reward.count"),
                         "cargo": channel("courier", "inventory.manifest")},
            "parameters": {"delivery_tick": 3, "return_tick": 6},
            "checks": [
                {"id": "knowledge_requires_delivery", "kind": "before_event_equals", "channel": "knowledge", "event_kind": "order.received", "value": 0},
                {"id": "reward_not_duplicated", "kind": "bounded", "channel": "reward", "minimum": 0, "maximum": 1},
                {"id": "mission_completes", "kind": "final_equals", "channel": "mission", "value": 3},
                {"id": "cargo_delivered", "kind": "final_equals", "channel": "cargo", "value": 0},
                {"id": "command_lifecycle", "kind": "event_sequence", "kinds": ["order.issued", "order.received", "order.acknowledged", "mission.completed", "report.received"]}]}


def validate_courier(value: dict) -> None:
    c.validate_scenario(value)
    expected = courier_scenario()
    for name in ("model_id", "source_class", "entities", "channels"):
        c.require(value[name] == expected[name], "Native adapter supports the courier reference profile only")
    keys(value["parameters"], {"delivery_tick", "return_tick"})
    delivery = c.integer(value["parameters"]["delivery_tick"], 1, value["clock"]["duration_ticks"])
    c.integer(value["parameters"]["return_tick"], delivery + 1, value["clock"]["duration_ticks"])


class GodotCourierBinding:
    """Snapshot operator-selected adapter bytes; never recover executable paths from data."""
    def __init__(self, executable: str | Path, adapter_root: str | Path, *, expected_sha256: str, expected_runtime: dict | None = None):
        content_ref(expected_sha256)
        self.executable = Path(executable).expanduser().resolve(strict=True)
        c.require(self.executable.is_file(), "Godot executable must be a regular file")
        c.require(file_sha(self.executable) == expected_sha256, "Godot executable digest mismatch")
        root = Path(adapter_root).expanduser().resolve(strict=True)
        self.scripts = {}
        for name in ("recorder.gd", "courier.gd"):
            path = root / name
            c.require(path.is_file() and not path.is_symlink(), "Adapter requires regular declared GDScript files")
            raw = path.read_bytes()
            c.require(0 < len(raw) <= 65536, "Adapter script exceeds byte budget")
            raw.decode("utf-8")
            self.scripts[name] = raw
        self.identity = {"provider": "ciw.game.godot-courier", "execution_mode": "native_process",
                         "executable_sha256": expected_sha256, "adapter_files": {k: bytes_ref(v) for k, v in self.scripts.items()},
                         "platform": platform.platform(), "scope": "operator-selected executable and adapter bytes; not shared-library attestation"}
        c.require(expected_runtime is None or self.identity == expected_runtime, "Reproduction runtime differs from retained execution")

    def runtime_identity(self) -> dict:
        c.require(file_sha(self.executable) == self.identity["executable_sha256"], "Godot executable changed after binding")
        return deepcopy(self.identity)

    def invoke(self, scenario: dict, parameters: dict) -> dict:
        from .adapters.protocol import AdapterRefusal
        validate_courier(scenario)
        self.runtime_identity()
        request = {"scenario": deepcopy(scenario), "scenario_digest": content_identity(scenario), **deepcopy(parameters)}
        try:
            with tempfile.TemporaryDirectory(prefix="net-game-runtime-") as directory:
                root = Path(directory)
                for name, raw in self.scripts.items():
                    (root / name).write_bytes(raw)
                (root / "project.godot").write_text('config_version=5\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
                save_new(root / "request.json", request)
                target = root / "trace.json"
                run_process([str(self.executable), "--headless", "--path", str(root), "--script", "courier.gd", "--",
                             str(root / "request.json"), str(target)], root, [target], timeout=30)
                for name in ("stdout.log", "stderr.log"):
                    with (root / name).open("rb") as stream:
                        raw = stream.read(c.MAX_BYTES + 1)
                    c.require(len(raw) <= c.MAX_BYTES, "Engine log exceeded byte budget")
                    c.require(b"ERROR:" not in raw, "Godot logged an error despite a successful exit")
                with target.open("rb") as stream:
                    raw = stream.read(65537)
                c.require(0 < len(raw) <= 65536, "Trace text exceeds current control-record string budget")
                result = {"schema": c.CAPTURE, "request": request, "trace_utf8": raw.decode("utf-8"), "trace_sha256": bytes_ref(raw)}
                c.validate_capture(result)
                c.require(c.unpack(result)[1]["engine"] == "godot", "Wrong engine response")
                self.runtime_identity()
                return result
        except (OSError, ValueError, RuntimeError) as exc:
            raise AdapterRefusal("game_runtime_failed", str(exc)[:4096]) from exc


def make_run(scenario: dict) -> dict:
    from .adapters.protocol import InstrumentManifest
    c.validate_scenario(scenario)
    instrument = "org.notationsystems.game-scenario"
    manifest = InstrumentManifest(instrument_id=instrument, version="1", role="operation_provider",
        inputs=(c.SCENARIO,), outputs=("run.v1",), units={"declaration": "1"}, frames=("game-scenario-declaration",),
        sampling={"mode": "declared_scenario"}, normalization={"state": "unchanged"}, supported_operations=(),
        determinism={"claim": "none_from_declaration"}, tolerance_policy={"policy": "explicit_operation_parameters"},
        calibration_requirements={"status": "not_applicable_simulated"})
    run = {"run_schema": "run.v1", "run_id": "run-" + uuid.uuid4().hex, "instrument": instrument,
           "time_s": [0.0], "channels": {"declaration": {"unit": "1", "kind": "declared_initial_condition", "values": [0.0]}},
           "render": {}, "metadata": {"sample_count": 1, "sample_rate_hz": None, "duration_s": 1.0,
           "coordinate_frame": "game-scenario-declaration", "manifest": manifest.to_dict(),
           "provenance": {"origin": "scenario_declaration_not_gameplay_observation", "duration_s_semantics": "selection support only"},
           "game_scenario": deepcopy(scenario)}}
    run["evidence_id"] = evidence_id(run)
    return run


def _parameters(operation: str, parameters: dict) -> None:
    fields = {CAPTURE_OP: {"nonce", "diagnostic_fault"}, AUDIT_OP: {"source_result_id", "source_record_digest"},
              COMPARE_OP: {"candidate_result_id", "candidate_record_digest", "reference_result_id", "reference_record_digest", "atol", "rtol"}}
    keys(parameters, fields[operation])
    if operation == CAPTURE_OP:
        c.text(parameters["nonce"])
        c.require(parameters["diagnostic_fault"] in c.FAULTS, "Unknown diagnostic fault")
    else:
        for name, value in parameters.items():
            if name.endswith("_digest"):
                content_ref(value)
            elif name.endswith("_id"):
                c.text(value)
            else:
                c.require(c.number(value) >= 0, "Invalid comparison tolerance")


def _validate_payload(operation, data, run, parameters, selection):
    c.validate_scenario(run["metadata"]["game_scenario"])
    _parameters(operation, parameters)
    c.bounded(data)
    if operation == CAPTURE_OP:
        c.validate_capture(data)
        c.require(data["request"]["scenario"] == run["metadata"]["game_scenario"], "Captured source scenario mismatch")
        for name in parameters:
            c.require(data["request"][name] == parameters[name], "Captured request mismatch")
    else:
        expected = "ciw.game-audit.v1" if operation == AUDIT_OP else "ciw.game-comparison.v1"
        c.require(data.get("schema") == expected and data.get("status") in {"PASS", "FAIL", "INDETERMINATE"}, "Invalid check result")
        c.require(data.get("verification_id", "missing") is None and data.get("state_admission") == "not_performed", "Check cannot claim verification or state admission")


def register_schemas() -> None:
    global _REGISTERED
    if not _REGISTERED:
        from .operations.schemas import register_payload_validator
        for name in (CAPTURE_OP, AUDIT_OP, COMPARE_OP):
            register_payload_validator(name, _validate_payload)
        _REGISTERED = True


def _source(session, parameters: dict, prefix: str) -> dict:
    result = session.results.get(parameters[prefix + "_result_id"])
    c.require(result is not None and result["operation_id"] == CAPTURE_OP, "Missing capture dependency")
    c.require(result["record_digest"] == parameters[prefix + "_record_digest"], "Capture dependency digest mismatch")
    return result


def _derived(session, operation: str, parameters: dict) -> dict:
    if operation == AUDIT_OP:
        source = _source(session, parameters, "source")
        return c.audit(source["data"], source["execution_id"])
    left, right = [_source(session, parameters, side) for side in ("candidate", "reference")]
    return c.comparison(left["data"], right["data"], left["execution_id"], right["execution_id"], atol=parameters["atol"], rtol=parameters["rtol"])


def validate_session(session):
    scenario = session.run["metadata"]["game_scenario"]
    c.require(session.run["evidence_id"] == make_run(scenario)["evidence_id"], "Scenario/run source identity mismatch")
    for result in session.results.values():
        operation, parameters = result["operation_id"], result["parameters"]
        if operation == CAPTURE_OP:
            c.validate_capture(result["data"])
            c.require(result["runtime"]["provider"] == "ciw.game.godot-courier", "Capture/runtime provider mismatch")
        elif operation in (AUDIT_OP, COMPARE_OP):
            # Pure retained-data validation; no native process or gameplay evolution.
            c.require(result["data"] == _derived(session, operation, parameters), "Retained game check contradicts its sources")
    return session


def bind(session, binding=None) -> None:
    from .operations.registry import Operation
    register_schemas()
    if binding is not None:
        def capture(run, parameters):
            _parameters(CAPTURE_OP, parameters)
            return binding.invoke(run["metadata"]["game_scenario"], parameters)
        session.operations.register(Operation(CAPTURE_OP, "backend", capture, binding.runtime_identity))
    def runtime():
        return {"provider": "ciw.game.trace-checks", "source_sha256": file_sha(Path(c.__file__)), "python": platform.python_version(), "scope": "ordinary_authored_rule_checks"}
    for operation in (AUDIT_OP, COMPARE_OP):
        def compute(run, parameters, operation=operation):
            _parameters(operation, parameters)
            return _derived(session, operation, parameters)
        session.operations.register(Operation(operation, "backend", compute, runtime))


def execute(session, operation: str, parameters: dict, output: Path) -> dict:
    response = session.handle({"protocol_version": 1, "request_id": uuid.uuid4().hex, "type": "operation.execute",
                               "payload": {"operation_id": operation, "parameters": parameters}})
    c.require(response["type"] != "error", str(response.get("payload")))
    session.save_workspace(Path(output) / "workspace.json")
    execution = list(session.executions.values())[-1]
    c.require(execution["status"] == "completed", "Retained refusal: " + json.dumps(execution.get("refusal")))
    validate_session(session)
    return session.results[execution["result_id"]]


def audit_result(session, result: dict, output: Path) -> dict:
    return execute(session, AUDIT_OP, {"source_result_id": result["result_id"], "source_record_digest": result["record_digest"]}, output)


def compare_results(session, candidate: dict, reference: dict, output: Path, *, atol: float = 0.0, rtol: float = 0.0) -> dict:
    return execute(session, COMPARE_OP, {"candidate_result_id": candidate["result_id"], "candidate_record_digest": candidate["record_digest"],
        "reference_result_id": reference["result_id"], "reference_record_digest": reference["record_digest"], "atol": atol, "rtol": rtol}, output)


def open_saved(path: str | Path, output: str | Path):
    from .session import Session
    register_schemas()
    value = load(Path(path))
    with tempfile.TemporaryDirectory(prefix="net-game-reopen-") as directory:
        frozen = Path(directory) / "workspace.json"
        save_new(frozen, value)
        session = Session.from_workspace(frozen, Path(output))
    return validate_session(session)


def inspect(path: str | Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="net-game-inspect-") as directory:
        session = open_saved(path, Path(directory) / "reopened")
        scenario = session.run["metadata"]["game_scenario"]
        return {"schema": "ciw.game-inspection.v1", "project_id": scenario["project_id"], "scenario_id": scenario["scenario_id"],
                "source_class": scenario["source_class"], "evidence_id": session.run["evidence_id"],
                "executions": [{"execution_id": e["execution_id"], "operation_id": e["operation_id"], "status": e["status"], "result_id": e["result_id"]} for e in session.executions.values()],
                "results": [{"result_id": r["result_id"], "operation_id": r["operation_id"],
                             "status": r["data"].get("status", "captured"), "diagnostic_fault": r["parameters"].get("diagnostic_fault"),
                             "first_divergence_tick": r["data"].get("first_divergence_tick")} for r in session.results.values()],
                "note": "retained-data consistency checks only; no runtime launch, checkpoint restore or gameplay evolution"}


def run_case(scenario: dict, binding, output: str | Path, *, fault: str = "none"):
    from .session import Session
    c.validate_scenario(scenario)
    c.require(fault in c.FAULTS, "Unknown diagnostic fault")
    register_schemas()
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    session = Session(make_run(scenario), output)
    bind(session, binding)
    result = execute(session, CAPTURE_OP, {"nonce": uuid.uuid4().hex, "diagnostic_fault": fault}, output)
    audit_result(session, result, output)
    return session, result


def extend_case(path: str | Path, binding, output: str | Path, *, source_execution_id: str, reproduce: bool, fault: str = "none"):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    session = open_saved(path, output)
    source = session.executions.get(source_execution_id)
    c.require(source is not None and source["operation_id"] == CAPTURE_OP and source["status"] == "completed", "Select a completed native capture execution")
    reference = session.results[source["result_id"]]
    if reproduce:
        c.require(fault == "none", "Reproduction cannot substitute a diagnostic fault")
        c.require(binding.runtime_identity() == source["runtime"], "Reproduction requires the original runtime identity")
        fault = source["parameters"]["diagnostic_fault"]
    c.require(fault in c.FAULTS, "Unknown diagnostic fault")
    bind(session, binding)
    result = execute(session, CAPTURE_OP, {"nonce": uuid.uuid4().hex, "diagnostic_fault": fault}, output)
    audit_result(session, result, output)
    compare_results(session, result, reference, output)
    return session, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog")
    seed = sub.add_parser("example"); seed.add_argument("--output", type=Path, required=True)
    view = sub.add_parser("inspect"); view.add_argument("workspace", type=Path)
    obs = sub.add_parser("observations"); obs.add_argument("workspace", type=Path); obs.add_argument("--execution-id", required=True); obs.add_argument("--output", type=Path, required=True)
    for name in ("run", "candidate", "reproduce"):
        cmd = sub.add_parser(name)
        if name == "run":
            cmd.add_argument("--scenario", type=Path, required=True)
        else:
            cmd.add_argument("workspace", type=Path); cmd.add_argument("--execution-id", required=True)
        cmd.add_argument("--godot", required=True); cmd.add_argument("--godot-sha256", required=True)
        cmd.add_argument("--adapter-root", type=Path, required=True); cmd.add_argument("--output-dir", type=Path, required=True)
        if name != "reproduce":
            cmd.add_argument("--diagnostic-fault", choices=c.FAULTS, default="none")
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            result = {"schema": "ciw.game-capabilities.v1", "authorizes_execution": False,
                      "implemented": ["godot.courier.capture", "trace.events", "trace.observations", "trace.authored-checks", "trace.compare", "same-runtime.reproduce", "provider-free.inspect"],
                      "not_implemented": ["live-game-attach", "generic-save-restore", "bevy-event-adapter", "gameplay-ai", "historical-claim-validation"],
                      "games_connected": [], "profile": "synthetic courier reference; real game adapters are separate increments"}
        elif args.command == "example":
            save_new(args.output, courier_scenario()); result = {"scenario": str(args.output)}
        elif args.command == "inspect":
            result = inspect(args.workspace)
        elif args.command == "observations":
            with tempfile.TemporaryDirectory() as directory:
                session = open_saved(args.workspace, directory)
                execution = session.executions.get(args.execution_id)
                c.require(execution is not None and execution["operation_id"] == CAPTURE_OP and execution["status"] == "completed", "Select a completed capture")
                record = session.results[execution["result_id"]]
                save_new(args.output, c.observations(record["data"], execution["execution_id"]))
            result = {"observations": str(args.output), "runtime_executed": False}
        else:
            binding = GodotCourierBinding(args.godot, args.adapter_root, expected_sha256=args.godot_sha256)
            if args.command == "run":
                session, _ = run_case(load(args.scenario), binding, args.output_dir, fault=args.diagnostic_fault)
            else:
                session, _ = extend_case(args.workspace, binding, args.output_dir, source_execution_id=args.execution_id,
                    reproduce=args.command == "reproduce", fault=getattr(args, "diagnostic_fault", "none"))
            result = inspect(args.output_dir / "workspace.json")
            print(json.dumps(result, indent=2, allow_nan=False))
            statuses = [r["data"]["status"] for r in session.results.values() if r["operation_id"] in (AUDIT_OP, COMPARE_OP)]
            # Scope the exit to the latest added audit and comparison, not inherited failures.
            recent = statuses[-(1 if args.command == "run" else 2):]
            return 2 if "FAIL" in recent else 3 if "INDETERMINATE" in recent else 0
        print(json.dumps(result, indent=2, allow_nan=False)); return 0
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)})); return 1


if __name__ == "__main__":
    raise SystemExit(main())
