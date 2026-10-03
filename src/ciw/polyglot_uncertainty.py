"""Compose existing native affine calls to propagate full input covariance.

This is fixed-Jacobian propagation, not a new estimator or a proof. Inspection
checks retained bindings; only explicit execution runs providers/references.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

from . import native_interop_contract as native
from . import polyglot_linear_map as linear
from .adapters.subprocess import _json
from .core.covariance import create_covariance_artifact, validate_covariance_artifact
from .native_interop import NativeInteropWorkflow
from .telemetry import canonical, digest, byte_digest

SCHEMA = "notation.linear-uncertainty.v1"
RUN_SCHEMA = "notation.linear-uncertainty-run.v1"
SCOPE = "fixed-jacobian-input-covariance-only"
POLICY = {"relative": 1e-10, "roundoff_factor": 256, "repair": "forbidden"}
MAX_BYTES = 64 * 1024 * 1024


def bind_covariance(case, matrix, *, provider, evidence_ids=(), covariance_ids=(), assumptions=()):
    """Bind a supplied covariance of delta coordinates, never infer independence."""
    case = linear.validate_case(case)
    return create_covariance_artifact(
        matrix=matrix, quantity_ids=[a["id"] for a in case["inputs"]],
        units=[a["unit"] for a in case["inputs"]], frame=case["frame"],
        reference_values=case["delta"], method="declared-input-perturbation-covariance",
        basis={"kind": "parameter", "id": digest(case)},
        provenance={"provider": provider, "source_evidence_ids": list(evidence_ids),
                    "source_covariance_ids": list(covariance_ids)},
        assumptions=list(assumptions))


def problem(case, covariance):
    case = linear.validate_case(case)
    if len(canonical(covariance)) > 65536:
        raise ValueError("Input covariance exceeds byte budget")
    validate_covariance_artifact(covariance,
        expected_quantity_ids=[a["id"] for a in case["inputs"]],
        expected_units=[a["unit"] for a in case["inputs"]], expected_frame=case["frame"])
    if (covariance["basis"] != {"kind": "parameter", "id": digest(case)}
            or covariance["reference_values"] != case["delta"]):
        raise ValueError("Covariance must bind this case and its delta reference")
    return {"schema": SCHEMA, "case": case, "input_covariance": deepcopy(covariance),
            "scope": SCOPE, "may_authorize": False}


def from_domain(value):
    """Consume an explicit domain export without importing its provider package."""
    native.keys(value, {"schema", "case", "covariance_matrix", "source_evidence_ids",
                        "source_covariance_ids", "assumptions"})
    if value["schema"] != "notation.domain-uncertainty-inputs.v1":
        raise ValueError("Unsupported domain uncertainty export")
    case = linear.validate_case(value["case"])
    covariance = bind_covariance(case, value["covariance_matrix"], provider=case["model"]["owner"],
        evidence_ids=value["source_evidence_ids"], covariance_ids=value["source_covariance_ids"],
        assumptions=value["assumptions"])
    return problem(case, covariance)


def validate_problem(value):
    native.keys(value, {"schema", "case", "input_covariance", "scope", "may_authorize"})
    expected = problem(value["case"], value["input_covariance"])
    if canonical(value) != canonical(expected):
        raise ValueError("Unsupported uncertainty declaration")
    return expected


def _normalized(p, provider):
    source = linear.compile_case(p["case"], provider)
    a = source["payload"]["a_row_major"]
    sx = [x["scale"] for x in p["case"]["inputs"]]
    c = [[linear._scaled(linear._scaled(x, 1, sx[i]), 1, sx[j])
          for j, x in enumerate(row)] for i, row in enumerate(p["input_covariance"]["matrix"])]
    return a, c, source


def _column_source(p, provider, label, a, x):
    m, n = len(p["case"]["outputs"]), len(p["case"]["inputs"])
    return native.make_source("affine-binary64.v1", provider,
        {"rows": m, "columns": n, "a_row_major": list(a), "b": [0.0]*m,
         "x0": [0.0]*n, "delta_x": list(x)},
        experiment_id="uncertainty:" + digest(p) + ":" + label)


def _output(bundle, expected):
    raw = NativeInteropWorkflow()._validate(bundle)
    if raw != canonical(expected):
        raise ValueError("Covariance stage source/ordering binding differs")
    return bundle["steps"][0]["result"]["data"]["output"]["model_output"]


def reference_check(p, matrix):
    """Independent rational J C J^T over the supplied binary64 values.

    Roundoff allowance scales with the absolute terms, not a dimensionful floor.
    Exact nonzero uncertainty may never silently become zero.
    """
    p = validate_problem(p)
    m, n = len(p["case"]["outputs"]), len(p["case"]["inputs"])
    if len(matrix) != m or any(len(row) != m for row in matrix):
        raise ValueError("Covariance output shape differs")
    f = lambda x: Fraction.from_float(float(x))
    j, c = p["case"]["jacobian_row_major"], p["input_covariance"]["matrix"]
    max_ratio = 0.0
    for r in range(m):
        for s in range(m):
            terms = [f(j[r*n+k])*f(c[k][l])*f(j[s*n+l]) for k in range(n) for l in range(n)]
            exact = sum(terms, Fraction())
            observed = f(linear._finite(matrix[r][s]))
            if exact and not observed:
                raise ValueError("Propagation erased nonzero covariance")
            budget = f(POLICY["relative"])*abs(exact) + Fraction(256, 2**52)*sum(map(abs, terms), Fraction())
            error = abs(observed-exact)
            if error > budget:
                raise ValueError("Native covariance differs from independent rational reference")
            if budget:
                max_ratio = max(max_ratio, float(error/budget))
    return {"schema": "notation.linear-uncertainty-check.v1", "subject": digest(p),
            "matrix_digest": digest(matrix), "method": "python-exact-rational-congruence",
            "outcome": "passed", "max_budget_fraction": max_ratio, "policy": deepcopy(POLICY),
            "physical_validation": "not_established", "sp1_verification": "not_performed"}


def _collect(p, provider, stages):
    m, n = len(p["case"]["outputs"]), len(p["case"]["inputs"])
    if type(stages) is not list or len(stages) != 1+n+m:
        raise ValueError("Missing or extra native covariance stages")
    a, c, mean = _normalized(p, provider)
    _output(stages[0], mean)
    left = [[0.0]*n for _ in range(m)]
    for k in range(n):
        values = _output(stages[1+k], _column_source(p, provider, f"left/{k}", a, [row[k] for row in c]))
        for r in range(m):
            left[r][k] = values[r]
    sy = [x["scale"] for x in p["case"]["outputs"]]
    matrix = [[0.0]*m for _ in range(m)]
    for k in range(m):
        values = _output(stages[1+n+k], _column_source(p, provider, f"right/{k}",
                          [x for row in left for x in row], a[k*n:(k+1)*n]))
        for r in range(m):
            matrix[r][k] = linear._scaled(linear._scaled(values[r], sy[r], 1), sy[k], 1)
    runtime = stages[0]["runtimes"]
    occurrences = []
    for stage in stages:
        if stage["runtimes"] != runtime:
            raise ValueError("Native runtime changed within uncertainty execution")
        occurrences.extend([stage["steps"][0]["execution_id"], stage["verification"]["reproduction"]["execution_id"]])
    if len(occurrences) != len(set(occurrences)):
        raise ValueError("Native execution occurrences must be distinct")
    view = linear.inspect_run({"schema": linear.RUN_SCHEMA, "case": p["case"], "native": stages[0]})
    artifact = create_covariance_artifact(matrix=matrix,
        quantity_ids=[x["id"] for x in p["case"]["outputs"]],
        units=[x["unit"] for x in p["case"]["outputs"]], frame=p["case"]["frame"],
        reference_values=[x["value"] for x in view["outputs"]],
        method="native-affine-composition-J-C-JT", basis={"kind": "coordinate", "id": digest(p)},
        provenance={"provider": "SCR/"+provider, "source_evidence_ids": [],
                    "source_covariance_ids": [p["input_covariance"]["covariance_id"]],
                    "metadata": {"native_bundle_digests": [s["bundle_digest"] for s in stages]}},
        assumptions=["Fixed supplied Jacobian; covariance belongs to declared delta coordinates.",
                     "No model error, observation noise or coefficient uncertainty is inferred.",
                     "No Gaussian distribution, confidence interval, calibration or physical validity is established."])
    return artifact


def execute(value, *, provider, bindings):
    p = validate_problem(value)
    a, c, mean = _normalized(p, provider)
    m, n = len(p["case"]["outputs"]), len(p["case"]["inputs"])
    workflow = NativeInteropWorkflow()
    stages = []
    def run(source):
        bundle = workflow.create_session(canonical(source), bindings)
        if stages and bundle["runtimes"] != stages[0]["runtimes"]:
            raise ValueError("Runtime changed within covariance computation")
        stages.append(bundle)
        return _output(bundle, source)
    # Refuse predictable input/budget violations before any provider starts.
    first_sources = [_column_source(p, provider, f"left/{k}", a, [row[k] for row in c]) for k in range(n)]
    run(mean)
    left = [[0.0]*n for _ in range(m)]
    for k in range(n):
        values = run(first_sources[k])
        for r in range(m):
            left[r][k] = values[r]
    for k in range(m):
        run(_column_source(p, provider, f"right/{k}", [x for row in left for x in row], a[k*n:(k+1)*n]))
    artifact = _collect(p, provider, stages)
    check = reference_check(p, artifact["matrix"])
    check["native_bundle_digests"] = [s["bundle_digest"] for s in stages]
    check["verification_id"] = digest(check)
    result = {"schema": RUN_SCHEMA, "problem": p, "provider": provider, "stages": stages,
              "output_covariance": artifact, "check": check}
    result["calculation_id"] = digest(result)
    inspect(result)
    return result


def inspect(run):
    """No solver, native process, or independent rational reference is executed."""
    native.keys(run, {"schema", "problem", "provider", "stages", "output_covariance", "check", "calculation_id"})
    if len(canonical(run)) > MAX_BYTES or run["schema"] != RUN_SCHEMA:
        raise ValueError("Unsupported or oversized uncertainty run")
    if run["calculation_id"] != digest({k:v for k,v in run.items() if k != "calculation_id"}):
        raise ValueError("Uncertainty calculation binding differs")
    p = validate_problem(run["problem"])
    artifact = _collect(p, run["provider"], run["stages"])
    if canonical(artifact) != canonical(run["output_covariance"]):
        raise ValueError("Covariance does not match retained native columns")
    check = run["check"]
    native.keys(check, {"schema", "subject", "matrix_digest", "method", "outcome", "max_budget_fraction",
                        "policy", "physical_validation", "sp1_verification", "native_bundle_digests", "verification_id"})
    if (check["schema"] != "notation.linear-uncertainty-check.v1" or check["subject"] != digest(p)
            or check["matrix_digest"] != digest(artifact["matrix"])
            or check["native_bundle_digests"] != [s["bundle_digest"] for s in run["stages"]]
            or check["method"] != "python-exact-rational-congruence" or check["outcome"] != "passed"
            or canonical(check["policy"]) != canonical(POLICY)
            or check["physical_validation"] != "not_established" or check["sp1_verification"] != "not_performed"
            or check["verification_id"] != digest({k:v for k,v in check.items() if k != "verification_id"})):
        raise ValueError("Retained uncertainty check binding differs")
    native.number(check["max_budget_fraction"], 0, 1)
    return deepcopy(artifact)


def replay(run, *, bindings):
    """Re-execute under the original runtime, retaining distinct occurrences."""
    inspect(run)
    NativeInteropWorkflow()._adapters(bindings, run["stages"][0]["runtimes"])
    fresh = execute(run["problem"], provider=run["provider"], bindings=bindings)
    if fresh["stages"][0]["runtimes"] != run["stages"][0]["runtimes"]:
        raise ValueError("Replay runtime differs")
    old_ids = {s["steps"][0]["execution_id"] for s in run["stages"]}
    new_ids = {s["steps"][0]["execution_id"] for s in fresh["stages"]}
    if old_ids & new_ids:
        raise ValueError("Replay reused a native execution occurrence")
    receipt = {"schema": "notation.linear-uncertainty-replay.v1",
        "source_calculation_id": run["calculation_id"], "replayed_calculation_id": fresh["calculation_id"],
        "comparison": "both-pass-the-same-independent-rational-reference-policy",
        "bit_identity_claimed": False, "may_authorize": False}
    receipt["replay_id"] = digest(receipt)
    return {"run": fresh, "receipt": receipt}


def export_view(run):
    artifact = inspect(run)
    mean = linear.export_view({"schema": linear.RUN_SCHEMA, "case": run["problem"]["case"], "native": run["stages"][0]})
    view = {"schema": "notation.linear-uncertainty-view.v1", "mean": mean,
            "quantity_ids": artifact["quantity_ids"], "units": artifact["units"], "frame": artifact["frame"],
            "matrix": artifact["matrix"], "covariance_id": artifact["covariance_id"],
            "input_covariance_id": run["problem"]["input_covariance"]["covariance_id"],
            "calculation_id": run["calculation_id"], "verification_id": run["check"]["verification_id"],
            "native_stage_count": len(run["stages"]), "scope": SCOPE, "may_authorize": False}
    raw = canonical(view)
    return {"schema": "notation.linear-uncertainty-view-envelope.v1", "payload": raw.decode(), "sha256": byte_digest(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "view", "replay"))
    parser.add_argument("source", type=Path)
    parser.add_argument("--provider", choices=("cpp", "julia"))
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; select a new artifact path")
    with args.source.open("rb") as handle:
        raw = handle.read(MAX_BYTES+1)
    if len(raw) > MAX_BYTES:
        parser.error("Source exceeds byte budget")
    source = _json(raw)
    if args.command == "run":
        if args.provider is None or args.binding is None:
            parser.error("run requires --provider and --binding")
        result = execute(source, provider=args.provider, bindings={"runtime": str(args.binding.resolve())})
    elif args.command == "replay":
        if args.binding is None:
            parser.error("replay requires --binding")
        result = replay(source, bindings={"runtime": str(args.binding.resolve())})
    else:
        result = export_view(source)
    with args.output.open("xb") as handle:
        handle.write(canonical(result))


if __name__ == "__main__":
    main()
