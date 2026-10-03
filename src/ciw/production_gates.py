"""Installed, data-only production checks. No dynamic imports selected by plans."""
from pathlib import Path

from .control_contracts import bytes_ref, detached, keys, text
from .core.identities import content_identity
from .production import Gate


def _equals_policy(value: dict) -> None:
    keys(value, {"path", "expected"})
    if type(value["path"]) is not list or not 1 <= len(value["path"]) <= 16:
        raise ValueError("Require a bounded result-data selector")
    for part in value["path"]:
        text(part)
    if type(value["expected"]) not in (str, int, float, bool):
        raise ValueError("Declare a non-null scalar expectation")
    detached(value)


def _equals(result: dict | None, policy: dict) -> dict:
    value = None if result is None else result["data"]
    for part in policy["path"]:
        if type(value) is not dict or part not in value:
            return {"status": "INDETERMINATE", "detail": "missing_result_path"}
        value = value[part]
    if value is None:
        return {"status": "INDETERMINATE", "detail": "missing_value"}
    return {"status": "PASS" if content_identity(value) == content_identity(policy["expected"]) else "FAIL",
            "detail": {"actual": value, "expected": policy["expected"], "comparison": "exact_typed_json"}}


def builtin_gates() -> dict[str, Gate]:
    name = "result.equals.v1"
    return {name: Gate(name, {"provider": "ciw.production-gates", "source_sha256": bytes_ref(Path(__file__).read_bytes()),
        "scope": "installed exact-JSON predicate; not source authentication"}, _equals_policy, _equals)}


def game_gates() -> dict[str, Gate]:
    # This explicit host selection imports only the installed, pure trace checker.
    from . import game_trace, control_checks, control_contracts
    def policy(value):
        keys(value, set())
    def evaluate(result, unused):
        if result is None:
            return {"status": "INDETERMINATE", "detail": "missing_capture"}
        if result["operation_id"] != "game.trace-capture.v1":
            raise ValueError("Authored game checks require the original capture operation")
        audited = game_trace.audit(result["data"], result["execution_id"])
        return {"status": audited["status"], "detail": audited}
    name = "game.authored-rules.v1"
    modules = {"production_gates": Path(__file__), "game_trace": Path(game_trace.__file__),
               "control_checks": Path(control_checks.__file__), "control_contracts": Path(control_contracts.__file__)}
    return {name: Gate(name, {"provider": "ciw.game.trace-checks", "source_files": {k: bytes_ref(p.read_bytes()) for k, p in modules.items()},
        "scope": "installed authored-rule check files; not full dependency attestation"}, policy, evaluate)}
