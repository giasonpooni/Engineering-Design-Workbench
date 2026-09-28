"""Bounded, data-only check plans over NET's existing numerical assertions.

A plan cannot bind providers, select code, authorize a machine, or admit state.
Exact input bytes and every requested check are retained for offline rechecking.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

from .control_contracts import (
    _base, bytes_ref, content_ref, detached, json_tree, keys, save_new, text,
)
from .control_checks import SCOPE, _policy, inspect_record, overall, verify
from .core.covariance import validate_covariance_artifact
from .core.identities import content_identity
from .operations.runner import seal
from .session import loads_json

PLAN_SCHEMA = "ciw.check-plan.v1"
REPORT_SCHEMA = "ciw.check-report.v1"
MAX_INPUT_BYTES = 65536
MAX_INPUTS = 8
MAX_CHECKS = 32
MAX_ASSERTIONS = 256
SERIES_SCHEMAS = {"ciw.observation-stream.v1", "ciw.thermal-observation-view.v1"}
COVARIANCE_SCHEMAS = SERIES_SCHEMAS | {"ciw.state.v1", "covariance-artifact.v1"}
AUTHORITY = {
    "claim_scope": SCOPE, "verification_id": None, "new_execution": "not_performed",
    "state_admission": "not_performed", "physical_validation": "not_established",
    "source_authentication": "not_established_by_hashes",
}


def validate_plan(value: dict) -> None:
    """Closed vocabulary. Policies use the original assertion policy validator."""
    json_tree(value)
    keys(value, {"schema", "suite_id", "inputs", "checks"})
    if value["schema"] != PLAN_SCHEMA:
        raise ValueError("Unsupported check plan schema")
    text(value["suite_id"])
    inputs, checks = value["inputs"], value["checks"]
    if type(inputs) is not dict or not 1 <= len(inputs) <= MAX_INPUTS:
        raise ValueError("Declare 1..8 check inputs")
    for alias, item in inputs.items():
        text(alias)
        keys(item, {"schema", "sha256"})
        content_ref(item["sha256"])
        text(item["schema"])
        if item["schema"] not in COVARIANCE_SCHEMAS | {"ciw.comparison.v1"}:
            raise ValueError("Unsupported check input schema")
    if type(checks) is not list or not 1 <= len(checks) <= MAX_CHECKS:
        raise ValueError("Declare 1..32 checks; an empty suite cannot pass")
    names, used = set(), set()
    for check in checks:
        keys(check, {"name", "kind", "input", "policy"})
        name, alias = text(check["name"]), text(check["input"])
        if name in names or alias not in inputs:
            raise ValueError("Duplicate check name or undeclared input")
        names.add(name)
        used.add(alias)
        kind = text(check["kind"])
        _policy(kind, check["policy"])
        supported = ({"ciw.comparison.v1"} if kind == "close_to" else
                     COVARIANCE_SCHEMAS if kind == "covariance_positive_definite" else SERIES_SCHEMAS)
        if inputs[alias]["schema"] not in supported:
            raise ValueError("Check kind and declared input schema do not match")
    if used != set(inputs):
        raise ValueError("Unused input declarations are not permitted")


def plan(suite_id: str, *, inputs: dict, checks: list[dict]) -> dict:
    value = detached({"schema": PLAN_SCHEMA, "suite_id": suite_id, "inputs": inputs, "checks": checks})
    validate_plan(value)
    return value


def _parse(raw: bytes) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_INPUT_BYTES:
        raise ValueError("Require 1..65536 exact UTF-8 JSON bytes per check input/plan")
    value = loads_json(raw.decode("utf-8"))
    json_tree(value)
    if type(value) is not dict:
        raise ValueError("Check documents must be JSON objects")
    return value


def _read(path: Path) -> bytes:
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_INPUT_BYTES + 1)
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise ValueError("Check input/plan exceeds its 64 KiB byte budget or is empty")
    return raw


def _inputs(specification: dict, supplied: dict[str, bytes | None]) -> tuple[dict, dict]:
    if type(supplied) is not dict or set(supplied) - set(specification["inputs"]):
        raise ValueError("Check input bindings must use declared aliases only")
    retained, parsed = {}, {}
    for alias, expected in specification["inputs"].items():
        raw = supplied.get(alias)
        if raw is None:
            retained[alias] = parsed[alias] = None
            continue
        value = _parse(raw)
        if bytes_ref(raw) != expected["sha256"]:
            raise ValueError(f"Exact-byte check input digest mismatch: {alias}")
        if value.get("schema") != expected["schema"]:
            raise ValueError(f"Check input schema mismatch: {alias}")
        if value["schema"] == "covariance-artifact.v1":
            validate_covariance_artifact(value)
        else:
            inspect_record(value)
        retained[alias] = {"sha256": expected["sha256"], "utf8": raw.decode("utf-8")}
        parsed[alias] = value
    return retained, parsed


def _observations(value: dict) -> list:
    if value["schema"] == "ciw.thermal-observation-view.v1":
        return value["stream"]["observations"]
    return value["observations"]


def _cases(check: dict, value: dict | None) -> list[tuple[int | None, Any]]:
    if value is None:
        return [(None, None)]
    if check["kind"] == "close_to":
        return [(None, value)]
    if check["kind"] == "covariance_positive_definite":
        if value["schema"] == "covariance-artifact.v1":
            return [(None, value)]
        if value["schema"] == "ciw.state.v1":
            return [(None, value["uncertainty"])]
        observations = _observations(value)
        return [(i, row["uncertainty"]) for i, row in enumerate(observations)] or [(None, None)]
    return [(None, _observations(value))]


def evaluate(specification: dict, supplied: dict[str, bytes | None]) -> dict:
    """Evaluate every declared check; omitted inputs stay explicit and indeterminate.

    Supplied corruption is an error, not missing evidence. For covariance on a
    series, check every per-tick artifact, never just the first or the diagonal.
    No execution or verification occurrence identity is allocated.
    """
    specification = detached(specification)
    validate_plan(specification)
    retained, parsed = _inputs(specification, supplied)
    prepared = [(check, _cases(check, parsed[check["input"]])) for check in specification["checks"]]
    if sum(len(cases) for _, cases in prepared) > MAX_ASSERTIONS:
        raise ValueError("Check plan exceeds the 256-assertion evaluation budget")
    outcomes, assertions = [], []
    for check, cases in prepared:
        evaluated = [{"sample_index": index, "assertion": verify(check["name"], check["kind"], evidence,
                     **check["policy"])} for index, evidence in cases]
        current = [case["assertion"] for case in evaluated]
        assertions.extend(current)
        outcomes.append({"name": check["name"], "input": check["input"], "kind": check["kind"],
                         "status": overall(current), "cases": evaluated})
    summary = {"status": overall(assertions), "check_count": len(outcomes),
               "assertion_count": len(assertions), "missing_inputs": sorted(k for k, v in parsed.items() if v is None),
               "counts": {status: sum(row["status"] == status for row in outcomes)
                          for status in ("PASS", "FAIL", "INDETERMINATE")}}
    value = {"schema": REPORT_SCHEMA, "plan": specification, "plan_id": content_identity(specification),
             "inputs": retained, "checks": outcomes, "summary": summary, "authority": deepcopy(AUTHORITY)}
    # Preserve the existing bounded-record limits; a large report is refused, not truncated.
    json_tree(value)
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 8 * 1024 * 1024:
        raise ValueError("Check report exceeds its 8 MiB retention budget")
    return seal(value)


def validate_report(value: dict) -> None:
    _base(value, "check-report", {"plan", "plan_id", "inputs", "checks", "summary", "authority"})
    validate_plan(value["plan"])
    keys(value["inputs"], set(value["plan"]["inputs"]))
    supplied = {}
    for alias, item in value["inputs"].items():
        if item is None:
            supplied[alias] = None
        else:
            keys(item, {"sha256", "utf8"})
            if type(item["utf8"]) is not str or item["sha256"] != value["plan"]["inputs"][alias]["sha256"]:
                raise ValueError("Retained input binding differs from check plan")
            supplied[alias] = item["utf8"].encode("utf-8")
    expected = evaluate(value["plan"], supplied)
    if content_identity(expected) != content_identity(value):
        raise ValueError("Check report contradicts its complete plan, evidence or outcomes")


def run_files(plan_path: Path, input_paths: dict[str, Path]) -> dict:
    """Freeze the plan and each bound input once; no automatic file or provider discovery."""
    specification = _parse(_read(plan_path))
    validate_plan(specification)
    if type(input_paths) is not dict or set(input_paths) - set(specification["inputs"]):
        raise ValueError("Unexpected input alias")
    return evaluate(specification, {alias: _read(path) for alias, path in input_paths.items()})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="net check", description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--input", action="append", default=[], metavar="ALIAS=PATH")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        paths = {}
        for binding in args.input:
            alias, separator, path = binding.partition("=")
            if not separator or not alias or not path or alias in paths:
                raise ValueError("Each --input must be a unique ALIAS=PATH")
            paths[alias] = Path(path)
        report = run_files(args.plan, paths)
        save_new(args.output, report)
        if args.json:
            print(json.dumps(report, indent=2, allow_nan=False))
        else:
            print(f"{report['summary']['status']}: {report['plan']['suite_id']}")
            for row in report["checks"]:
                print(f"  {row['status']}: {row['name']} ({row['input']})")
            print(f"Report: {args.output}; no new scientific execution or state admission.")
        return {"PASS": 0, "FAIL": 2, "INDETERMINATE": 3}[report["summary"]["status"]]
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
