#!/usr/bin/env python3
"""Operator-bound native integration gate; usable with an installed ciw wheel.

Install CIW (or set PYTHONPATH explicitly). This script never alters import paths,
installs packages, compiles a provider, or treats a native-only pass as completion
of the separate SP1 and sanitizer gates.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time
import uuid
from unittest.mock import patch

from ciw import native_interop as ni
from ciw import native_interop_contract as nc
from ciw.adapters.oscillator import make_demo_run
from ciw.session import Session
from ciw.telemetry import byte_digest, canonical


def row(name, status, **details):
    return {"gate": name, "status": status, **details}


def load_fixtures(path):
    raw = path.read_bytes()
    if len(raw) > 1024*1024:
        raise ValueError("Fixture file exceeds the byte budget")
    value = json.loads(raw)
    if value.get("schema") != "ciw.native-interop-reference-fixtures.v1":
        raise ValueError("Unsupported fixture schema")
    if not isinstance(value.get("cases"), list) or not 1 <= len(value["cases"]) <= 32:
        raise ValueError("Expected 1..32 fixed cases")
    if len({case["name"] for case in value["cases"]}) != len(value["cases"]):
        raise ValueError("Fixture names must be unique")
    for case in value["cases"]:
        for provider in case["providers"]:
            nc.make_source(case["profile"], provider, case["payload"], experiment_id=case["name"])
    return value, byte_digest(raw)


def reference_output(bundle):
    return bundle["steps"][0]["result"]["data"]["output"]


def retained_metrics(bundle):
    """Measured process, provider-dispatch, solver, check and retained-byte costs."""
    result = []
    for label, step in (("initial", bundle["steps"][0]),
                        ("fresh_process_reproduction", bundle["verification"]["reproduction"])):
        transport = step["transport"]
        raw = base64.b64decode(transport["response"]["bytes_b64"], validate=True)
        response = json.loads(raw)
        result.append({"execution": label, "execution_id": step["execution_id"],
                       "result_id": step["result_id"], "numerical_result_id": step["numerical_result_id"],
                       "process_seconds": transport["process_seconds"],
                       "host_dispatch_seconds": response["host"].get("elapsed_seconds"),
                       "solver_seconds": response["data"].get("solver", {}).get("solve_seconds"),
                       "independent_check_seconds": step["check_seconds"],
                       "request_bytes": len(base64.b64decode(transport["request"]["bytes_b64"], validate=True)),
                       "response_bytes": len(raw)})
    return result


def execute_source(session, source, destination, index):
    start = time.perf_counter()
    raw = canonical(source)
    serialization_seconds = time.perf_counter()-start
    source_record = session.workbench.add_source({"kind": ni.KIND, "label": source["experiment_id"],
        "bytes_b64": base64.b64encode(raw).decode("ascii")})
    summary = session.workbench.execute({"operation_id": ni.OPERATION, "source_id": source_record["source_id"]})
    bundle = session.workbench.get_bundle(summary["bundle_id"])
    encoded = canonical(bundle)
    path = destination/f"bundle-{index:02d}.json"
    with path.open("xb") as stream:
        stream.write(encoded)
    return summary, bundle, {"bundle_id": summary["bundle_id"], "bundle_file": path.name,
                             "retained_bytes": len(encoded), "source_serialization_seconds": serialization_seconds,
                             "executions": retained_metrics(bundle)}


def persistent_benchmark(binding, destination, anchor):
    """Separate technical A/B/A trace using the same pinned, bounded SCR host."""
    bindings, runtime = ni.NativeInteropWorkflow()._adapters({"runtime": binding})
    _, host_bytes, artifacts = ni._runtime(bindings)
    folder = destination/"persistent-benchmark"
    folder.mkdir()
    executable = folder/("scr-provider-host.exe" if os.name == "nt" else "scr-provider-host")
    executable.write_bytes(host_bytes)
    executable.chmod(0o700)
    for name, raw in artifacts.items():
        path = folder/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    project = folder/"runtimes/native-interop"
    command = [str(executable), "--provider", "julia", "--julia", bindings["julia"],
               "--project", str(project), "--worker", str(project/"worker.jl"), "--timeout-ms", "180000"]
    env = dict(os.environ, JULIA_NUM_THREADS="1", JULIA_LOAD_PATH=os.pathsep.join(("@", "@stdlib")),
               JULIA_PKG_OFFLINE="true", JULIA_DEPOT_PATH=ni._depot(bindings["julia_depot"]))
    source = nc.source(base64.b64decode(anchor["source"]["evidence"][0]["bytes_b64"], validate=True))
    varied = deepcopy(source)
    varied["payload"]["delta_x"][0] *= -1
    hello = {"schema": "ciw.native-interop-handshake-request.v1", "request_id": "handshake-"+uuid.uuid4().hex}
    sources = [source, varied, source]
    requests = [{"schema": ni.REQUEST_SCHEMA, "request_id": "request-"+uuid.uuid4().hex,
                 "parent_execution_id": anchor["steps"][0]["execution_id"],
                 **{key: value[key] for key in ("profile", "arithmetic", "semantics", "payload")}}
                for value in sources]
    started = time.perf_counter()
    serialized = [canonical(value) for value in [hello, *requests]]
    framed = b"".join(ni.frame(value) for value in serialized)
    serialization_seconds = time.perf_counter()-started
    started = time.perf_counter()
    stdout, stderr = ni._run(command, framed, cwd=folder, env=env, timeout=210)
    process_seconds = time.perf_counter()-started
    decoded = [json.loads(raw) for raw in ni.frames(stdout)]
    if len(decoded) != 4 or decoded[0].get("request_id") != hello["request_id"]:
        raise ValueError("Persistent benchmark handshake or response count differs")
    elapsed, checks = [], []
    for submitted, request, response in zip(sources, requests, decoded[1:], strict=True):
        ni._host_check(submitted, request, response)
        ni._runtime_link(runtime, submitted, hello, decoded[0], response)
        started = time.perf_counter()
        nc.check_output(submitted, response["data"])
        checks.append(time.perf_counter()-started)
        elapsed.append(response["host"]["elapsed_seconds"])
    nc.compare(decoded[1]["data"], decoded[3]["data"])
    if ni._runtime(bindings)[0] != runtime:
        raise ValueError("Persistent benchmark runtime changed")
    for name, raw in artifacts.items():
        if (folder/name).read_bytes() != raw:
            raise ValueError("Persistent worker snapshot changed")
    (folder/"request.frames").write_bytes(framed)
    (folder/"response.frames").write_bytes(stdout)
    (folder/"stderr.bin").write_bytes(stderr)
    return {"anchor_bundle_id": anchor["bundle_digest"], "process_seconds": process_seconds,
            "cold_process_first_dispatch_seconds": elapsed[0], "warm_dispatch_seconds": elapsed[1:],
            "startup_and_teardown_overhead_seconds": max(0.0, process_seconds-sum(elapsed)),
            "serialization_seconds": serialization_seconds, "independent_check_seconds": checks,
            "request_sha256": byte_digest(framed), "response_sha256": byte_digest(stdout),
            "retained_transport_bytes": len(framed)+len(stdout)+len(stderr),
            "scope": "Separate persistent technical reproduction; package caches already exist. The overhead includes process/handshake startup, response writes and teardown; compilation is not isolated."}


def check_run(binding, fixture_path, output):
    fixtures, fixture_digest = load_fixtures(fixture_path)
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "ciw.native-interop-gate-report.v1", "mode": "run", "full_completion": False,
              "fixture_sha256": fixture_digest, "rows": [], "measurements": [],
              "authority": deepcopy(nc.AUTHORITY)}
    session = Session(make_demo_run(), output/"session")
    session.workbench.bind_workflow(ni.KIND, {"runtime": binding})
    records = {}
    next_index = 1
    for case in fixtures["cases"]:
        for provider in case["providers"]:
            name = f"{case['name']}:{provider}"
            print(f"native-interop: running {name}", file=sys.stderr, flush=True)
            try:
                source = nc.make_source(case["profile"], provider, case["payload"], experiment_id=name)
                summary, bundle, metrics = execute_source(session, source, output, next_index)
                next_index += 1
                if expected := case.get("expected"):
                    nc.compare(expected, reference_output(bundle), exact=case["profile"] == "affine-d256.v1")
                records[(case["name"], provider)] = (summary, bundle)
                report["measurements"].append({"case": name, **metrics})
                report["rows"].append(row(name, "PASS", bundle_id=summary["bundle_id"],
                    reference_check=bundle["steps"][0]["result"]["data"]["reference_check"]))
            except Exception as exc:
                print(f"native-interop: {name} failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                report["rows"].append(row(name, "FAIL", reason=f"{type(exc).__name__}: {exc}"[:4000]))

    for name, exact in (("affine-binary64", False), ("affine-d256", True)):
        try:
            cpp = reference_output(records[(name, "cpp")][1])
            julia = reference_output(records[(name, "julia")][1])
            error = nc.compare(cpp, julia, exact=exact)
            report["rows"].append(row(f"cross-provider:{name}", "PASS", max_abs_discrepancy=error))
        except KeyError:
            report["rows"].append(row(f"cross-provider:{name}", "BLOCKED", reason="Required retained runs are absent"))
        except Exception as exc:
            report["rows"].append(row(f"cross-provider:{name}", "FAIL", reason=str(exc)))

    try:
        tsit5 = records[("oscillator-tsit5", "julia")][1]
        control = records[("control-oscillator", "julia")][1]
        expected = {key: reference_output(tsit5)[key] for key in ("time_s", "q_m", "v_m_s", "energy_j")}
        discrepancy = nc.compare(expected, reference_output(control))
        report["rows"].append(row("JuliaControl-versus-Tsit5", "PASS", max_abs_discrepancy=discrepancy))
        tsit_source = nc.source(base64.b64decode(tsit5["source"]["evidence"][0]["bytes_b64"], validate=True))
        payload = {"model": tsit_source["payload"]["model"],
                   **{key: reference_output(tsit5)[key] for key in ("time_s", "q_m", "v_m_s")}}
        source = nc.make_source("oscillator-force-energy.v1", "cpp", payload, experiment_id="retained-trajectory-force",
            upstream={"bundle_digest": tsit5["bundle_digest"], "result_id": tsit5["steps"][0]["result_id"]})
        summary, force, metrics = execute_source(session, source, output, next_index)
        next_index += 1
        initial = {key: reference_output(force)[key][0] if isinstance(reference_output(force)[key], list)
                   else reference_output(force)[key] for key in fixtures["force_expected_initial"]}
        nc.compare(fixtures["force_expected_initial"], initial)
        report["rows"].append(row("retained-Julia-trajectory-to-Cpp-force", "PASS", bundle_id=summary["bundle_id"]))
        report["measurements"].append({"case": "retained-trajectory-force", **metrics})
        records[("retained-trajectory-force", "cpp")] = (summary, force)
    except KeyError:
        report["rows"].append(row("retained-Julia-trajectory-to-Cpp-force", "BLOCKED", reason="Required trajectory runs are absent"))
    except Exception as exc:
        report["rows"].append(row("retained-Julia-trajectory-to-Cpp-force", "FAIL", reason=str(exc)))

    workspace = output/"workspace.json"
    try:
        session.save_workspace(workspace)
        def forbidden(*args, **kwargs):
            raise AssertionError("Offline reopening attempted provider or reference execution")
        with patch.object(ni, "_invoke", forbidden), patch.object(ni, "_runtime", forbidden), patch.object(nc, "check_output", forbidden):
            reopened = Session.from_workspace(workspace, output/"reopened")
            if len(reopened.workbench.list_bundles()) != len(session.workbench.list_bundles()):
                raise ValueError("Offline reopening changed the retained bundle count")
            for summary, _ in records.values():
                reopened.workbench.inspect_experiment({"bundle_id": summary["bundle_id"]})
        report["rows"].append(row("save-reopen-inspect-provider-free", "PASS", workspace=workspace.name))
        reopened.workbench.bind_workflow(ni.KIND, {"runtime": binding})
        for key in (("affine-d256", "julia"), ("retained-trajectory-force", "cpp")):
            original_summary, original = records[key]
            replay = reopened.workbench.replay({"bundle_id": original_summary["bundle_id"]})
            fresh = reopened.workbench.get_bundle(replay["bundle"]["bundle_id"])
            if fresh["steps"][0]["execution_id"] == original["steps"][0]["execution_id"]:
                raise ValueError("Replay reused the execution occurrence")
            if fresh["steps"][0]["result_id"] == original["steps"][0]["result_id"]:
                raise ValueError("Replay reused the result occurrence")
            if replay["replay_receipt"]["numerical_match"] is not True:
                raise ValueError("Replay numerical content differs")
            report["rows"].append(row("fresh-replay:"+":".join(key), "PASS", bundle_id=fresh["bundle_digest"],
                                      execution_id=fresh["steps"][0]["execution_id"]))
            report["measurements"].append({"case": "replay:"+":".join(key), "executions": retained_metrics(fresh)})
        reopened.save_workspace(output/"workspace-replayed.json")
    except KeyError:
        report["rows"].append(row("fresh-replay", "BLOCKED", reason="Required retained run is absent"))
    except Exception as exc:
        report["rows"].append(row("save-reopen-replay", "FAIL", reason=f"{type(exc).__name__}: {exc}"[:4000]))

    report["rows"] += [
        row("native-exact-checker", "NOT_RUN", reason="Separate SCR exact-checker invocation is required"),
        row("SP1-proof-and-fresh-verification", "NOT_RUN", reason="This gate creates no proof and invokes no cryptographic verifier"),
        row("UBSan", "NOT_RUN", reason="No sanitizer build/run is attested by this gate"),
        row("legacy-worker-adversarial-protocol", "NOT_RUN", reason="Run the separate genuine Julia pytest gate"),
        row("physical-validation", "NOT_RUN", reason="All inputs are declared simulations or mathematical fixtures"),
    ]
    try:
        metrics = persistent_benchmark(binding, output, records[("affine-binary64", "julia")][1])
        report["measurements"].append({"case": "persistent-host-A-B-A", **metrics})
        report["rows"].append(row("persistent-host-A-B-A", "PASS"))
    except KeyError:
        report["rows"].append(row("persistent-host-A-B-A", "BLOCKED", reason="Julia affine anchor is absent"))
    except Exception as exc:
        report["rows"].append(row("persistent-host-A-B-A", "FAIL", reason=str(exc)))
    report["cost_scope"] = {"persistent_warm_dispatch": "NOT_RUN", "peak_memory": "NOT_RUN",
        "proof_generation": "NOT_RUN", "cryptographic_verification": "NOT_RUN",
        "note": "Shared workflow initial/reproduction timings each include a fresh host and provider process; they are not warm dispatch measurements."}
    if any(item["gate"] == "persistent-host-A-B-A" and item["status"] == "PASS" for item in report["rows"]):
        report["cost_scope"]["persistent_warm_dispatch"] = "PASS"
    report["cost_scope"].update(compilation_isolated="NOT_RUN", pure_julia_calculation_isolated="NOT_RUN", pure_native_kernel_isolated="NOT_RUN")
    report["native_subset_passed"] = not any(item["status"] in {"FAIL", "BLOCKED"} for item in report["rows"])
    with (output/"report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--probe", action="store_true", help="Read configured pins/files; do not execute providers or install anything")
    mode.add_argument("--run", action="store_true", help="Execute the native subset through the shared Session/Workbench API")
    parser.add_argument("--binding", type=Path, required=True, help="Operator-owned native runtime binding JSON")
    parser.add_argument("--fixtures", type=Path, default=Path(__file__).resolve().parents[1]/"examples/native-interop/reference_fixtures.json")
    parser.add_argument("--output", type=Path, help="New result directory; existing paths are refused")
    parser.add_argument("--require-all", action="store_true", help="Exit nonzero unless every mandatory gate, including proof and sanitizer validation, is completed")
    args = parser.parse_args(argv)
    try:
        if args.probe:
            _, runtime = ni.NativeInteropWorkflow()._adapters({"runtime": args.binding.resolve()})
            report = {"schema": "ciw.native-interop-gate-report.v1", "mode": "probe", "full_completion": False,
                "runtime": runtime, "rows": [row("operator-runtime-binding", "PASS", meaning="Pinned files match; execution has not been tested"),
                    row("native-execution", "NOT_RUN"), row("SP1-proof-and-fresh-verification", "NOT_RUN"), row("UBSan", "NOT_RUN")]}
        else:
            if args.output is None:
                parser.error("--run requires --output pointing to a new directory")
            report = check_run(args.binding.resolve(), args.fixtures.resolve(), args.output.resolve())
        print(json.dumps(report, indent=2, allow_nan=False))
        if args.require_all and not report["full_completion"]:
            return 3
        return 0 if args.probe or report["native_subset_passed"] else 1
    except (ValueError, OSError, KeyError) as exc:
        print(f"native-interop gate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
