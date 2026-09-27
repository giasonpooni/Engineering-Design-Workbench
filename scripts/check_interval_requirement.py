#!/usr/bin/env python3
"""Run a bounded interval requirement gate and retain its shared CIW workspace.

Requires installed CIW or an explicitly configured development PYTHONPATH.
An enclosure can pass its exact containment check while its requirement is
inconclusive or fails throughout. No physical validation or actuation is implied.
"""
import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path
import sys
from unittest.mock import patch

from ciw import interval_contract as ic, native_interop as ni, native_interop_contract as nc
from ciw.adapters.oscillator import make_demo_run
from ciw.adapters.subprocess import _json
from ciw.session import Session
from ciw.telemetry import byte_digest, canonical

MAX_FIXTURE_BYTES = 256 * 1024
FIXTURE_SCHEMA = "ciw.interval-requirement-fixtures.v1"
REPORT_SCHEMA = "ciw.interval-requirement-report.v1"


def forbidden(*args, **kwargs):
    raise AssertionError("Read-only interval inspection attempted a provider or oracle")


def inspect_workspace(path, artifacts, expected=None):
    with patch.object(ni, "_runtime", forbidden), patch.object(ni, "_invoke", forbidden), \
         patch.object(nc, "check_output", forbidden), patch.object(ic, "check_output", forbidden), \
         patch.object(ic, "reference", forbidden):
        session = Session.from_workspace(path, artifacts)
        if expected is not None and canonical(session.workbench.serialize()) != canonical(expected):
            raise ValueError("Reopen changed retained identities or content")
        summaries = session.workbench.list_bundles()
        for row in summaries:
            session.workbench.inspect_experiment({"bundle_id": row["bundle_id"]})
    return summaries


def source(case):
    return nc.make_source(ic.PROFILE, "intervals", case["payload"],
                          experiment_id=case["name"] + ":intervals")


def read_fixtures(path):
    """Prevalidate the entire data-only fixture set before output or providers."""
    with path.open("rb") as stream:
        raw = stream.read(MAX_FIXTURE_BYTES + 1)
    if not raw or len(raw) > MAX_FIXTURE_BYTES:
        raise ValueError("Interval fixtures exceed their byte budget")
    spec = _json(raw)
    nc.keys(spec, {"schema", "cases"})
    if (spec["schema"] != FIXTURE_SCHEMA or type(spec["cases"]) is not list
            or not 1 <= len(spec["cases"]) <= 16):
        raise ValueError("Unsupported bounded interval fixture set")
    names = set()
    for case in spec["cases"]:
        nc.keys(case, {"name", "payload"})
        name = case["name"]
        if type(name) is not str or not name or name in names:
            raise ValueError("Interval case names must be nonempty, unique strings")
        names.add(name)
        source(case)
    return raw, spec


def result_row(name, retained, summary, bundle):
    """Project a retained result; requirement status is not the gate outcome."""
    step = bundle["steps"][0]
    data = step["result"]["data"]
    output = data["output"]
    return {"gate": name, "envelope_status": "PASS", "requirement": output["requirement"],
            "source_id": retained["source_id"], "evidence_id": retained["evidence_id"],
            "bundle_id": summary["bundle_id"], "operation_id": step["operation_id"],
            "execution_id": step["execution_id"], "result_id": step["result_id"],
            "numerical_result_id": step["numerical_result_id"],
            "verification_id": bundle["verification"]["verification_id"],
            "enclosure": deepcopy(output["enclosure"]),
            "configuration": deepcopy(output["configuration"]),
            "check": deepcopy(data["reference_check"]),
            "process_seconds": step["transport"]["process_seconds"],
            "check_seconds": step["check_seconds"]}


def run(binding, fixtures, destination):
    raw, spec = read_fixtures(fixtures)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "fixtures.json").write_bytes(raw)
    session = Session(make_demo_run(), destination / "artifacts")
    repositories = {"runtime": binding.resolve()}
    workspace = destination / "workspace.json"
    report = {"schema": REPORT_SCHEMA, "fixture_sha256": byte_digest(raw),
              "fixture_file": "fixtures.json", "workspace_file": "workspace.json",
              "authority": deepcopy(nc.AUTHORITY), "runtime": None, "rows": [],
              "scope": "Declared scalar-square interval requirement; no physical validation, confidence interval or actuation."}
    current_gate = "runtime-binding"
    first = None
    try:
        _, runtime = ni.NativeInteropWorkflow()._adapters(repositories)
        report["runtime"] = deepcopy(runtime)
        session.workbench.bind_workflow(ni.KIND, repositories)
        for case in spec["cases"]:
            current_gate = case["name"]
            print("interval requirement: " + current_gate, file=sys.stderr, flush=True)
            declaration = source(case)
            retained = session.workbench.add_source({"kind": ni.KIND, "label": current_gate,
                "bytes_b64": base64.b64encode(canonical(declaration)).decode("ascii")})
            summary = session.workbench.execute({"operation_id": ni.OPERATION,
                                                 "source_id": retained["source_id"]})
            bundle = session.workbench.get_bundle(summary["bundle_id"])
            report["rows"].append(result_row(current_gate, retained, summary, bundle))
            if first is None:
                first = (retained, summary, bundle)
            session.save_workspace(workspace)

        current_gate = "fresh-replay"
        retained, old_summary, old = first
        replayed = session.workbench.replay({"bundle_id": old_summary["bundle_id"]})
        summary = replayed["bundle"]
        fresh = session.workbench.get_bundle(summary["bundle_id"])
        for key in ("execution_id", "result_id"):
            previous = {old["steps"][0][key], old["verification"]["reproduction"][key]}
            current = {fresh["steps"][0][key], fresh["verification"]["reproduction"][key]}
            if len(previous | current) != 4:
                raise ValueError("Replay reused occurrence identity")
        if fresh["steps"][0]["numerical_result_id"] != old["steps"][0]["numerical_result_id"]:
            raise ValueError("Replay changed the retained interval result")
        row = result_row(current_gate, retained, summary, fresh)
        row.update(source_bundle_id=old_summary["bundle_id"],
                   replay_id=replayed["replay_receipt"]["replay_id"])
        report["rows"].append(row)
        session.save_workspace(workspace)

        current_gate = "provider-free-reopen"
        reopened = inspect_workspace(workspace, destination / "reopened", session.workbench.serialize())
        if len(reopened) != len(spec["cases"]) + 1:
            raise ValueError("Reopen lost retained interval history")
        report["rows"].append({"gate": current_gate, "envelope_status": "PASS",
                               "bundle_count": len(reopened), "retained_content_match": True})
        report["outcome"] = "passed"
    except Exception as exc:
        report["outcome"] = "failed"
        report["rows"].append({"gate": current_gate, "envelope_status": "FAIL", "reason": str(exc)[:4000]})
        session.save_workspace(workspace)
        raise
    finally:
        (destination / "report.json").write_bytes(canonical(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--binding", type=Path, required=True)
    run_parser.add_argument("--fixtures", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("--workspace", type=Path, required=True)
    inspect_parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run":
        result = run(args.binding, args.fixtures, args.output)
    else:
        result = {"mode": "retained-inspection", "fresh_execution": False,
                  "bundles": inspect_workspace(args.workspace, args.artifacts)}
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
