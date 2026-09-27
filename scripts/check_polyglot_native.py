"""Required live C++ AND Julia qualification. Missing runtimes are failures.

This script never substitutes a Python reference or protocol double for a
provider. It retains genuine native runs, explicit replays and inspect views.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path

from ciw import polyglot_linear_map as maps
from ciw.native_interop import NativeInteropWorkflow
from ciw.telemetry import canonical, digest


def fixture():
    model = {"name": "synthetic-rectangular-affine-qualification", "baseline": [2.0, -1.0],
             "jacobian": [3.0, -2.0, -4.0, 6.0], "delta": [0.002, 0.05]}
    return {"schema": maps.CASE_SCHEMA,
            "model": {"owner": "native-qualification", "kind": "synthetic-affine.v1", "digest": digest(model)},
            "frame": "synthetic-quantity-coordinates",
            "inputs": [{"id": "a", "unit": "m", "scale": .001}, {"id": "b", "unit": "m", "scale": .01}],
            "outputs": [{"id": "y", "unit": "m", "scale": .01}, {"id": "z", "unit": "m", "scale": .1}],
            "baseline": model["baseline"], "jacobian_row_major": model["jacobian"], "delta": model["delta"],
            "claim_scope": maps.CLAIM, "covariance": "not_propagated", "may_authorize": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Output directory must be new")
    binding = {"runtime": str(args.binding.resolve())}
    artifacts, results = {}, {}
    for provider in ("cpp", "julia"):
        case = fixture()
        run = maps.create_run(case, provider=provider, bindings=binding)
        # Round-trip and inspect with no binding argument: inspection is not replay.
        loaded = json.loads(canonical(run))
        view = maps.inspect_run(loaded)
        observed = [q["value"] for q in view["outputs"]]
        if not all(math.isclose(a, b, rel_tol=2e-8, abs_tol=2e-10) for a, b in zip(observed, [1.906, -.708])):
            raise ValueError("Independent physical-coordinate reference differs")
        swapped = deepcopy(loaded)
        swapped["case"]["frame"] = "different-frame"
        try:
            maps.inspect_run(swapped)
        except ValueError:
            pass
        else:
            raise ValueError("A changed case was accepted against an old execution")
        replay = NativeInteropWorkflow().replay_session(loaded["native"], binding)
        fresh = {"schema": maps.RUN_SCHEMA, "case": case, "native": replay["session"]}
        fresh_view = maps.inspect_run(fresh)
        if fresh_view["execution_id"] == view["execution_id"]:
            raise ValueError("Replay reused an execution occurrence")
        for suffix, value in (("run", loaded), ("replay", fresh), ("view", maps.export_view(loaded))):
            artifacts[f"{provider}-{suffix}.json"] = value
        results[provider] = {"values": observed, "bundle_digest": view["bundle_digest"],
                             "replay_bundle_digest": fresh_view["bundle_digest"],
                             "runtime_digest": view["runtime_digest"]}
    if not all(math.isclose(a, b, rel_tol=2e-8, abs_tol=2e-10)
               for a, b in zip(results["cpp"]["values"], results["julia"]["values"])):
        raise ValueError("C++ and Julia results disagree")
    report = {"schema": "notation.linear-map-native-qualification.v1", "outcome": "passed",
              "scope": "synthetic-affine-only", "providers": results,
              "source_to_binary_attestation": "not_established", "may_authorize": False}
    artifacts["qualification.json"] = report
    args.output_dir.mkdir(parents=False)
    for name, value in artifacts.items():
        with (args.output_dir / name).open("xb") as handle:
            handle.write(canonical(value))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
