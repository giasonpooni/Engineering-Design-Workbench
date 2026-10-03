"""Historical-perspective authoring operations on the original NET/CIW Session.

No game clock, engine process, external model, evidence admission or release.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys
import tempfile
import uuid

from . import historical_perspective as h
from .adapters.protocol import InstrumentManifest
from .control_contracts import bytes_ref, keys, load, save_new
from .control_plane import CapabilityRegistry
from .core.identities import content_identity, evidence_id
from .operations.registry import Operation

ACTOR_OP = "history.actor-state.v1"
AUDIT_OP = "history.epistemic-audit.v1"
_REGISTERED = False


def _manifest() -> InstrumentManifest:
    return InstrumentManifest(instrument_id="org.notationsystems.historical-perspective", version="1",
        role="operation_provider", inputs=(h.SCHEMA,), outputs=(h.VIEW, h.AUDIT), units={"declaration": "1"},
        frames=("historical-authoring-declaration",), sampling={"mode": "declaration_only"},
        normalization={"state": "unchanged"}, supported_operations=(ACTOR_OP, AUDIT_OP),
        determinism={"claim": "pure_qualitative_policy_for_identical_validated_input"},
        tolerance_policy={"policy": "exact_typed_json"}, calibration_requirements={"status": "not_applicable"})


def _runtime() -> dict:
    return {"provider": "ciw.historical-perspective", "policy": h.POLICY, "python": platform.python_version(),
            "source_files": {"kernel": bytes_ref(Path(h.__file__).read_bytes()),
                             "workflow": bytes_ref(Path(__file__).read_bytes())},
            "scope": "installed authoring policy; not historical authentication or complete dependency attestation"}


def make_run(scenario: dict) -> dict:
    scenario = h.validate(scenario)
    run = {"run_schema": "run.v1", "run_id": "run-" + uuid.uuid4().hex,
           "instrument": _manifest().instrument_id, "time_s": [0.0],
           "channels": {"declaration": {"unit": "1", "kind": "declared_initial_condition", "values": [0.0]}},
           "render": {}, "metadata": {"sample_count": 1, "sample_rate_hz": None, "duration_s": 1.0,
               "coordinate_frame": "historical-authoring-declaration", "manifest": _manifest().to_dict(),
               "provenance": {"origin": "authored_scenario_not_historical_or_gameplay_observation",
                              "duration_s_semantics": "selection_support_only_not_game_time"},
               "historical_perspective": scenario}}
    run["evidence_id"] = evidence_id(run)
    return run


def _compute(operation: str, run: dict, parameters: dict) -> dict:
    source = run["metadata"]["historical_perspective"]
    if operation == ACTOR_OP:
        keys(parameters, {"actor", "at_tick"})
        return h.compile_actor(source, parameters["actor"], parameters["at_tick"])
    h.require(operation == AUDIT_OP, "Unknown perspective operation")
    keys(parameters, set())
    return h.audit(source)


def _validate_payload(operation, data, run, parameters, selection):
    expected = _compute(operation, run, parameters)
    h.require(content_identity(data) == content_identity(expected), "Perspective result contradicts declared source")


def register_schemas() -> None:
    global _REGISTERED
    if not _REGISTERED:
        from .operations.schemas import register_payload_validator
        for operation in (ACTOR_OP, AUDIT_OP):
            register_payload_validator(operation, _validate_payload)
        _REGISTERED = True


def registry(*, bind: bool = False) -> CapabilityRegistry:
    """Saved declarations never choose code, executable paths or a provider."""
    register_schemas()
    result = CapabilityRegistry()
    result.advertise(_manifest(), runtime=_runtime(),
                     capabilities={ACTOR_OP: ["history.actor-perspective"], AUDIT_OP: ["history.epistemic-audit"]})
    if bind:
        for operation in (ACTOR_OP, AUDIT_OP):
            result.bind(Operation(operation, "backend",
                        lambda run, params, op=operation: _compute(op, run, params), _runtime))
    return result


def validate_session(session):
    source = session.run["metadata"]["historical_perspective"]
    h.require(session.run["evidence_id"] == make_run(source)["evidence_id"], "Historical declaration identity mismatch")
    for result in session.results.values():
        h.require(result["operation_id"] in {ACTOR_OP, AUDIT_OP}, "Unexpected result in perspective investigation")
        h.require(result["runtime"].get("provider") == _runtime()["provider"], "Wrong perspective provider")
        h.require(result["runtime"].get("source_files") == _runtime()["source_files"], "Installed perspective policy differs from source binding")
        h.require(result["runtime"].get("policy") == h.POLICY, "Perspective policy mismatch")
        _validate_payload(result["operation_id"], result["data"], session.run, result["parameters"], {})
    return session


def run_case(scenario: dict, output: str | Path, *, at_tick: int):
    from .session import Session
    source = make_run(scenario)
    h.tick(at_tick)
    bound = registry(bind=True)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    session = Session(source, output_dir=output, operations=bound.operations)
    try:
        requests = [(ACTOR_OP, {"actor": actor, "at_tick": at_tick}) for actor in source["metadata"]["historical_perspective"]["actors"]]
        requests.append((AUDIT_OP, {}))
        for operation, parameters in requests:
            response = session.handle({"protocol_version": 1, "request_id": uuid.uuid4().hex,
                "type": "operation.execute", "payload": {"operation_id": operation, "parameters": parameters}})
            session.save_workspace(output / "workspace.json")
            h.require(response["type"] != "error", "Retained perspective operation refusal")
            execution = list(session.executions.values())[-1]
            h.require(execution["status"] == "completed", "Retained perspective execution failure")
        return validate_session(session)
    finally:
        session.save_workspace(output / "workspace.json")


def _open_frozen(path: str | Path, directory: Path):
    from .session import Session
    register_schemas()
    value = load(Path(path))
    frozen = directory / "input.json"
    save_new(frozen, value)
    return validate_session(Session.from_workspace(frozen, directory / "reopened"))


def inspect(path: str | Path) -> dict:
    """Recompute ordinary checks without binding operations or starting providers."""
    with tempfile.TemporaryDirectory(prefix="net-perspective-inspect-") as tmp:
        session = _open_frozen(path, Path(tmp))
        return {"schema": "ciw.perspective-inspection.v1", "source_evidence_id": session.run["evidence_id"],
            "project_id": session.run["metadata"]["historical_perspective"]["project_id"],
            "executions": [{k: e[k] for k in ("execution_id", "operation_id", "status", "result_id")}
                           for e in session.executions.values()],
            "results": [{"result_id": r["result_id"], "execution_id": r["execution_id"],
                         "operation_id": r["operation_id"], "data": r["data"]} for r in session.results.values()],
            "runtime_executed": False, "state_admission": "not_performed", "verification_id": None}


def export_actor(path: str | Path, result_id: str, output: str | Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="net-perspective-export-") as tmp:
        session = _open_frozen(path, Path(tmp))
        result = session.results.get(result_id)
        h.require(result is not None and result["operation_id"] == ACTOR_OP, "Select a retained actor result")
        # The exported data is filtered. The full operator workspace must not be supplied to actors.
        save_new(Path(output), result["data"])
        return {"result_id": result_id, "execution_id": result["execution_id"],
                "output": str(output), "sha256": bytes_ref(Path(output).read_bytes()), "runtime_executed": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog")
    command = commands.add_parser("example"); command.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("inspect"); command.add_argument("workspace", type=Path)
    command = commands.add_parser("export-actor"); command.add_argument("workspace", type=Path)
    command.add_argument("--result-id", required=True); command.add_argument("--output", type=Path, required=True)
    for name in ("demo", "run"):
        command = commands.add_parser(name)
        command.add_argument("--output-dir", type=Path, required=True)
        command.add_argument("--at-tick", type=int, default=4)
        if name == "run":
            command.add_argument("--scenario", type=Path, required=True)
    args = parser.parse_args(argv)
    code = 0
    try:
        if args.command == "catalog":
            result = registry().catalog()
        elif args.command == "example":
            save_new(args.output, h.example()); result = {"output": str(args.output)}
        elif args.command == "inspect":
            result = inspect(args.workspace)
        elif args.command == "export-actor":
            result = export_actor(args.workspace, args.result_id, args.output)
        else:
            scenario = h.example() if args.command == "demo" else load(args.scenario)
            session = run_case(scenario, args.output_dir, at_tick=args.at_tick)
            result = inspect(args.output_dir / "workspace.json")
            audit = next(r["data"] for r in session.results.values() if r["operation_id"] == AUDIT_OP)
            if args.command == "demo":
                expected = ["FAIL", "PASS", "INDETERMINATE", "PASS", "FAIL", "PASS", "PASS"]
                h.require([c["status"] for c in audit["checks"]] == expected, "Demonstration diagnostic changed")
                result["deliberate_failures_match_expected"] = True
            else:
                code = {"PASS": 0, "FAIL": 2, "INDETERMINATE": 3}[audit["status"]]
        print(json.dumps(result, indent=2, allow_nan=False))
        return code
    except (ValueError, OSError, KeyError, TypeError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
