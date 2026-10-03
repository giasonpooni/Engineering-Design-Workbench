"""Unit-labelled linear maps through the existing SCR C++/Julia operation.

No provider is launched by compilation or inspection. This adapter evaluates a
supplied local linear model; it does not update its owner's state or covariance.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import math
from pathlib import Path
import re

from .adapters.subprocess import _json
from . import native_interop_contract as native
from .native_interop import NativeInteropWorkflow
from .telemetry import byte_digest, canonical, digest

CASE_SCHEMA = "notation.linear-map.v1"
RUN_SCHEMA = "notation.linear-map-run.v1"
VIEW_SCHEMA = "notation.linear-map-view.v1"
ENVELOPE_SCHEMA = "notation.linear-map-view-envelope.v1"
CLAIM = "first-order-mean-response-only"
MAX_CASE_BYTES = 65536
CASE_KEYS = {"schema", "model", "frame", "inputs", "outputs", "baseline",
             "jacobian_row_major", "delta", "claim_scope", "covariance", "may_authorize"}


def _text(value):
    if type(value) is not str or not 1 <= len(value) <= 256 or not value.isprintable():
        raise ValueError("Require a bounded printable identifier or unit")
    return value


def _finite(value):
    if type(value) not in (int, float):
        raise ValueError("Require a finite number, not a coerced value")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Unrepresentable binary64 number") from exc
    if not math.isfinite(result):
        raise ValueError("Nonfinite linear-map value")
    return result


def _axes(axes):
    if type(axes) is not list or not 1 <= len(axes) <= 8:
        raise ValueError("Require one to eight named axes")
    for axis in axes:
        native.keys(axis, {"id", "unit", "scale"})
        _text(axis["id"]); _text(axis["unit"])
        if not 1e-100 <= _finite(axis["scale"]) <= 1e100:
            raise ValueError("Scale must be positive and within [1e-100, 1e100]")
    if len({a["id"] for a in axes}) != len(axes):
        raise ValueError("Duplicate axis identity")


def validate_case(value):
    """Validate and detach a case. Scales are normalization, not unit conversion."""
    native.keys(value, CASE_KEYS)
    if (value["schema"] != CASE_SCHEMA or value["claim_scope"] != CLAIM
            or value["covariance"] != "not_propagated" or value["may_authorize"] is not False):
        raise ValueError("Unsupported case schema or claim scope")
    native.keys(value["model"], {"owner", "kind", "digest"})
    for key in ("owner", "kind"):
        _text(value["model"][key])
    if type(value["model"]["digest"]) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", value["model"]["digest"]):
        raise ValueError("Require the complete model snapshot digest")
    _text(value["frame"])
    _axes(value["inputs"]); _axes(value["outputs"])
    m, n = len(value["outputs"]), len(value["inputs"])
    for key, size in (("baseline", m), ("delta", n), ("jacobian_row_major", m*n)):
        if type(value[key]) is not list or len(value[key]) != size:
            raise ValueError("Linear-map array shape differs")
        for number in value[key]:
            _finite(number)
    if len(canonical(value)) > MAX_CASE_BYTES:
        raise ValueError("Linear-map case exceeds byte budget")
    return deepcopy(value)


def read_case(raw: bytes):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_CASE_BYTES:
        raise ValueError("Linear-map case exceeds byte budget")
    return validate_case(_json(raw))


def _scaled(value, multiplier, divisor):
    value, multiplier, divisor = map(_finite, (value, multiplier, divisor))
    result = _finite(value * multiplier / divisor)
    if value != 0 and result == 0:
        raise ValueError("Normalization erased a nonzero value")
    return result


def compile_case(case, provider: str):
    """Lower y = y0 + J delta to an approved dimensionless native profile."""
    case = validate_case(case)
    if provider not in ("cpp", "julia"):
        raise ValueError("Select cpp or julia explicitly; no provider fallback")
    inputs, outputs = case["inputs"], case["outputs"]
    m, n = len(outputs), len(inputs)
    payload = {
        "rows": m, "columns": n,
        "a_row_major": [_scaled(case["jacobian_row_major"][i*n+j], inputs[j]["scale"], outputs[i]["scale"])
                        for i in range(m) for j in range(n)],
        "b": [_scaled(v, 1, axis["scale"]) for v, axis in zip(case["baseline"], outputs)],
        "x0": [0.0] * n,
        "delta_x": [_scaled(v, 1, axis["scale"]) for v, axis in zip(case["delta"], inputs)],
    }
    # Binding only the coefficients would allow swapping frames or source models.
    return native.make_source("affine-binary64.v1", provider, payload,
                              experiment_id="linear-map:" + digest(case))


def create_run(case, *, provider: str, bindings: dict):
    """Explicit execution via CIW's registered native workflow, including reproduction."""
    case = validate_case(case)
    source = compile_case(case, provider)
    bundle = NativeInteropWorkflow().create_session(canonical(source), bindings)
    run = {"schema": RUN_SCHEMA, "case": case, "native": bundle}
    inspect_run(run)
    return run


def inspect_run(run):
    """Read retained bytes without provisioning or launching any provider."""
    native.keys(run, {"schema", "case", "native"})
    if run["schema"] != RUN_SCHEMA:
        raise ValueError("Unsupported linear-map run")
    case = validate_case(run["case"])
    bundle = run["native"]
    raw = NativeInteropWorkflow()._validate(bundle)
    source = native.source(raw)
    if raw != canonical(compile_case(case, source["provider"])):
        raise ValueError("Native result is not bound to this complete model case")
    step = bundle["steps"][0]
    data = step["result"]["data"]["output"]
    outputs = []
    for i, axis in enumerate(case["outputs"]):
        outputs.append({"id": axis["id"], "unit": axis["unit"],
                        "baseline": _scaled(data["baseline_output"][i], axis["scale"], 1),
                        "delta": _scaled(data["predicted_delta"][i], axis["scale"], 1),
                        "value": _scaled(data["model_output"][i], axis["scale"], 1)})
    return {"schema": VIEW_SCHEMA, "case_digest": digest(case),
            "model": deepcopy(case["model"]), "frame": case["frame"],
            "provider": source["provider"], "native_profile": source["profile"],
            "bundle_digest": bundle["bundle_digest"], "result_id": step["result_id"],
            "numerical_result_id": step["numerical_result_id"], "execution_id": step["execution_id"],
            "verification_id": bundle["verification"]["verification_id"],
            "runtime_digest": digest(bundle["runtimes"]), "outputs": outputs,
            "claim_scope": CLAIM, "covariance": "not_propagated", "may_authorize": False,
            "physical_validation": "not_established", "sp1_verification": "not_performed",
            "state_admission": "not_performed"}


def export_view(run):
    """Hash exact UTF-8 payload bytes; JavaScript must not reserialize to verify."""
    payload = canonical(inspect_run(run))
    if len(payload) > MAX_CASE_BYTES:
        raise ValueError("View exceeds byte budget")
    return {"schema": ENVELOPE_SCHEMA, "payload": payload.decode("utf-8"),
            "sha256": byte_digest(payload)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    execute = commands.add_parser("run")
    execute.add_argument("case", type=Path)
    execute.add_argument("--provider", required=True, choices=("cpp", "julia"))
    execute.add_argument("--binding", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    view = commands.add_parser("view")
    view.add_argument("run", type=Path)
    view.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new artifact path")
    if args.command == "run":
        with args.case.open("rb") as handle:
            case = read_case(handle.read(MAX_CASE_BYTES + 1))
        result = create_run(case, provider=args.provider, bindings={"runtime": str(args.binding.resolve())})
    else:
        with args.run.open("rb") as handle:
            raw = handle.read(9*1024*1024 + 1)
        if len(raw) > 9*1024*1024:
            raise ValueError("Retained run exceeds byte budget")
        result = export_view(_json(raw))
    with args.output.open("xb") as handle:
        handle.write(canonical(result))


if __name__ == "__main__":
    main()
