"""Bounded deterministic contact scenarios over the original impact Session.

An enumerated design requirement is separate from numerical qualification. No
sampling weights, failure probabilities or physical validation are inferred.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

from .control_contracts import bytes_ref, json_tree, keys, load, number, save_new
from .control_plane import Choice, ParameterSpace
from .operations.runner import check_seal, digest, seal
from . import impact_workflow as workflow

REQUEST_SCHEMA = "ciw.impact-sweep-request.v1"
SUMMARY_SCHEMA = "ciw.impact-sweep-summary.v1"
MAX_CASES = 24
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_WORKSPACE_BYTES = 64 * 1024 * 1024
AXIS_UNITS = {"mass_kg": "kg", "stiffness_n_per_m": "N/m",
              "initial_speed_m_per_s": "m/s", "yield_force_n": "N"}
QUANTITY_UNITS = {"peak_force_n": "N", "restitution": "1",
                  "residual_compression_m": "m", "plastic_work_j": "J"}
CLAIMS = {"deterministic_full_declared_grid": True, "stochastic_sampling_performed": False,
          "failure_probability_estimated": False, "global_robustness_established": False,
          "physical_validation": "not_established", "state_admission": "not_performed",
          "hardware_actuation": "not_performed"}


def _contract(request):
    if type(request) is not dict:
        raise ValueError("Impact base request must be an object")
    if request.get("schema") == "ciw.impact-request.v1":
        from . import impact_contract
        return impact_contract
    if request.get("schema") == "ciw.impact-crush-request.v1":
        from . import impact_crush_contract
        return impact_crush_contract
    raise ValueError("Unsupported impact scenario profile")


def validate_manifest(manifest: dict) -> dict:
    """Validate the complete Cartesian grid before creating any destination."""
    json_tree(manifest)
    keys(manifest, {"schema", "base_request", "axes", "requirements"})
    if manifest["schema"] != REQUEST_SCHEMA:
        raise ValueError("Wrong impact scenario manifest schema")
    contract = _contract(manifest["base_request"])
    base = contract.validate_request(manifest["base_request"])
    crush = workflow._crush(base)
    axes = manifest["axes"]
    allowed = set(AXIS_UNITS) if crush else set(AXIS_UNITS) - {"yield_force_n"}
    if type(axes) is not dict or not 1 <= len(axes) <= 3 or not set(axes) <= allowed:
        raise ValueError("Require 1..3 supported impact scalar axes")
    for name, values in axes.items():
        if type(values) is not list or not 1 <= len(values) <= 6:
            raise ValueError("Each scenario axis requires 1..6 explicit values")
        checked = [number(value) for value in values]
        if len(set(checked)) != len(checked):
            raise ValueError("Scenario axis contains duplicate numerical values")
    requirements = manifest["requirements"]
    if type(requirements) is not list or not 1 <= len(requirements) <= 4:
        raise ValueError("Require 1..4 explicit scenario requirements")
    for row in requirements:
        keys(row, {"quantity", "unit", "operator", "limit"})
        quantity = row["quantity"]
        if type(quantity) is not str or quantity not in QUANTITY_UNITS:
            raise ValueError("Unsupported scenario requirement quantity")
        if not crush and quantity in {"residual_compression_m", "plastic_work_j"}:
            raise ValueError("Plastic requirements require the crush contact profile")
        if (row["unit"] != QUANTITY_UNITS[quantity] or type(row["operator"]) is not str
                or row["operator"] not in {"<=", ">="}):
            raise ValueError("Requirement needs the exact declared SI unit and <= or >= operator")
        number(row["limit"])
    checked = deepcopy(manifest)
    # Sorting dimensions makes ordering independent of JSON object serialization.
    space = ParameterSpace({name: Choice(tuple(axes[name]), AXIS_UNITS[name])
                            for name in sorted(axes)})
    for coordinate in space.grid({}, max_cases=MAX_CASES):
        candidate = deepcopy(base)
        candidate["model"].update(coordinate)
        contract.validate_request(candidate)
    return checked


def _grid(manifest: dict):
    axes = manifest["axes"]
    space = ParameterSpace({name: Choice(tuple(axes[name]), AXIS_UNITS[name])
                            for name in sorted(axes)})
    return space.to_dict(), space.grid({}, max_cases=MAX_CASES)


def _request(manifest: dict, coordinate: dict) -> dict:
    candidate = deepcopy(manifest["base_request"])
    candidate["model"].update(coordinate)
    return _contract(candidate).validate_request(candidate)


def _case_path(destination: Path, index: int) -> Path:
    # Paths never come from the retained summary or other untrusted data.
    return destination / f"case-{index:03d}"


def _file_ref(path: Path, *, maximum: int = MAX_DOCUMENT_BYTES) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Scenario artifacts must be retained regular files")
    if not 0 < path.stat().st_size <= maximum:
        raise ValueError("Scenario artifact exceeds the bounded file profile")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if not raw or len(raw) > maximum:
        raise ValueError("Scenario artifact exceeds the bounded file profile")
    return bytes_ref(raw)


def _preflight_case(directory: Path) -> None:
    """Bound files and reject symlinks before the retained Session is opened."""
    for name in ("request.json", "workspace.json", "verification.json", "preservation.json"):
        path = directory / name
        if name in {"request.json", "workspace.json"} or path.exists() or path.is_symlink():
            _file_ref(path, maximum=MAX_WORKSPACE_BYTES if name == "workspace.json" else MAX_DOCUMENT_BYTES)


def _artifacts(directory: Path, inspected: dict) -> dict:
    names = ["request.json", "workspace.json"]
    if "verification_id" in inspected:
        names.extend(["verification.json", "preservation.json"])
    elif (directory / "verification.json").exists() or (directory / "preservation.json").exists():
        raise ValueError("An unresolved provider attempt cannot retain completed verification artifacts")
    return {name: _file_ref(directory / name, maximum=MAX_WORKSPACE_BYTES if name == "workspace.json"
                           else MAX_DOCUMENT_BYTES) for name in names}


def _requirements(requirements: list, inspected: dict) -> tuple[list, str]:
    evaluated = []
    qualified = inspected["status"] == "LOCAL"
    metrics = inspected.get("metrics", {}).get("primary", {})
    for index, requirement in enumerate(requirements):
        value = None
        status = "UNRESOLVED"
        if qualified:
            if requirement["quantity"] not in metrics:
                raise ValueError("Qualified impact inspection lacks a requested scalar metric")
            value = number(metrics[requirement["quantity"]])
            passed = (value <= requirement["limit"] if requirement["operator"] == "<="
                      else value >= requirement["limit"])
            status = "PASS" if passed else "FAIL"
        evaluated.append({"index": index, **deepcopy(requirement), "value": value, "status": status})
    statuses = {row["status"] for row in evaluated}
    return evaluated, "FAIL" if "FAIL" in statuses else "UNRESOLVED" if "UNRESOLVED" in statuses else "PASS"


def _aggregate(manifest: dict, destination: Path, inspections: list[dict]) -> dict:
    parameter_space, coordinates = _grid(manifest)
    if len(inspections) != len(coordinates):
        raise ValueError("Scenario inspection count differs from the full declared grid")
    cases = []
    for index, (coordinate, inspected) in enumerate(zip(coordinates, inspections)):
        directory = _case_path(destination, index)
        expected = _request(manifest, coordinate)
        if load(directory / "request.json") != expected:
            raise ValueError("Retained scenario request differs from its fixed grid coordinate")
        criteria, design_status = _requirements(manifest["requirements"], inspected)
        cases.append({"index": index, "directory": f"case-{index:03d}",
                      "coordinate": coordinate, "request_ref": digest(expected),
                      "files": _artifacts(directory, inspected), "inspection": deepcopy(inspected),
                      "numerical_status": inspected["status"], "requirements_status": design_status,
                      "requirements": criteria})
    numerical = {row["numerical_status"] for row in cases}
    design = {row["requirements_status"] for row in cases}
    return seal({"schema": SUMMARY_SCHEMA, "manifest_ref": digest(manifest),
                 "manifest_file_ref": _file_ref(destination / "manifest.json"),
                 "parameter_space": parameter_space, "case_count": len(cases), "cases": cases,
                 "status": "REFUSE" if "REFUSE" in numerical else "EXPAND" if "EXPAND" in numerical else "LOCAL",
                 "requirements_status": "FAIL" if "FAIL" in design else "UNRESOLVED" if "UNRESOLVED" in design else "PASS",
                 "requirements_counts": {status: sum(row["requirements_status"] == status for row in cases)
                                         for status in ("PASS", "FAIL", "UNRESOLVED")},
                 "claims": deepcopy(CLAIMS)})


def run_sweep(manifest: dict, destination: Path) -> dict:
    """Execute every valid declared scenario on the existing impact workflow."""
    manifest = validate_manifest(manifest)
    _, coordinates = _grid(manifest)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "manifest.json", manifest)
    inspections = [workflow.run(_request(manifest, coordinate), _case_path(destination, index))
                   for index, coordinate in enumerate(coordinates)]
    summary = _aggregate(manifest, destination, inspections)
    save_new(destination / "summary.json", summary)
    return summary


def inspect_sweep(destination: Path) -> dict:
    """Read, reopen and compare every retained case without numerical replay."""
    destination = Path(destination)
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("Scenario bundle must be a retained directory")
    _file_ref(destination / "manifest.json")
    _file_ref(destination / "summary.json")
    manifest = validate_manifest(load(destination / "manifest.json"))
    _, coordinates = _grid(manifest)
    expected_names = {"manifest.json", "summary.json"} | {f"case-{index:03d}" for index in range(len(coordinates))}
    if {path.name for path in destination.iterdir()} != expected_names:
        raise ValueError("Scenario bundle must retain exactly every declared case")
    inspections = []
    for index in range(len(coordinates)):
        directory = _case_path(destination, index)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Scenario cases must be retained directories")
        _preflight_case(directory)
        inspections.append(workflow.inspect(directory))
    stored = load(destination / "summary.json")
    check_seal(stored)
    rebuilt = _aggregate(manifest, destination, inspections)
    if stored != rebuilt:
        raise ValueError("Retained scenario summary differs from its complete case evidence")
    return rebuilt


def verify_sweep(destination: Path) -> dict:
    """Independently audit retained samples; never rerun numerical solvers."""
    destination = Path(destination)
    summary = inspect_sweep(destination)
    verifications = []
    normalized = []
    for row in summary["cases"]:
        verified = workflow.verify_retained(_case_path(destination, row["index"]))
        verifications.append({"index": row["index"], "fresh_execution": verified["fresh_execution"],
                              "fresh_numerical_verification": verified["fresh_numerical_verification"],
                              "recomputed_report_digest": verified.get("recomputed_report_digest"),
                              "recomputed_with_runtime": verified.get("recomputed_with_runtime")})
        original = deepcopy(verified)
        original["fresh_numerical_verification"] = False
        original.pop("recomputed_report_digest", None)
        original.pop("recomputed_with_runtime", None)
        normalized.append(original)
    manifest = validate_manifest(load(destination / "manifest.json"))
    if _aggregate(manifest, destination, normalized) != summary:
        raise ValueError("Independent case verification differs from the retained scenario aggregate")
    return seal({"schema": "ciw.impact-sweep-verification.v1", "summary_ref": summary["record_digest"],
                 "status": summary["status"], "requirements_status": summary["requirements_status"],
                 "case_count": summary["case_count"], "cases": verifications,
                 "fresh_execution": False, "claims": deepcopy(CLAIMS)})


def example_manifest() -> dict:
    from .impact_crush_contract import example_request
    return {"schema": REQUEST_SCHEMA, "base_request": example_request(),
            "axes": {"initial_speed_m_per_s": [1.0, 2.0, 3.0], "yield_force_n": [80.0, 100.0]},
            "requirements": [{"quantity": "peak_force_n", "unit": "N", "operator": "<=", "limit": 150.0},
                             {"quantity": "residual_compression_m", "unit": "m", "operator": "<=", "limit": 0.045}]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="net impact sweep", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    example = commands.add_parser("example")
    example.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("request", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)
    for name in ("inspect", "verify"):
        commands.add_parser(name).add_argument("directory", type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "example":
            save_new(args.output, validate_manifest(example_manifest()))
            result = {"status": "created", "request": str(args.output)}
        elif args.command == "run":
            result = run_sweep(load(args.request), args.output_dir)
        elif args.command == "inspect":
            result = inspect_sweep(args.directory)
        else:
            result = verify_sweep(args.directory)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result.get("status") in {"REFUSE", "EXPAND"} or result.get("requirements_status") in {"FAIL", "UNRESOLVED"} else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({"status": "REFUSE", "reason": str(exc)}), file=sys.stderr)
        return 1
