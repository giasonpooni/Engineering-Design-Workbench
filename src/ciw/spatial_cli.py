"""Author/check GIS/RS requests in the existing workbench; never run GIS locally."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .adapters.protocol import AdapterRefusal
from .control_contracts import keys, load, save_new
from .control_plane import builtin_registry, plan_graph
from .spatial_requests import add_spatial_routes, make_plan, validate_request


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="net spatial", description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("catalog", help="List declared, unbound provider targets; no discovery or execution")
    cmd = subs.add_parser("check", help="Check explicit request metadata; does not admit evidence")
    cmd.add_argument("request", type=Path)
    cmd = subs.add_parser("plan", help="Write an existing CIW experiment for an explicitly selected provider operation")
    cmd.add_argument("request", type=Path)
    cmd.add_argument("--model-id", required=True)
    cmd.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        registry = builtin_registry()
        add_spatial_routes(registry)
        if args.command == "catalog":
            value = registry.catalog("gis_rs")
        else:
            request = load(args.request)
            keys(request, {"operation", "spatial"})
            validate_request(request["operation"], request["spatial"])
            if args.command == "plan":
                declared = make_plan(request["operation"], request["spatial"], model_id=args.model_id)
                plan_graph(declared, registry)
                save_new(args.output, declared)
            value = {"status": "request_metadata_checked", "provider_executed": False,
                     "admission_performed": False, "release_performed": False,
                     "reference_authenticity_checked": False}
        print(json.dumps(value, indent=2, allow_nan=False))
        return 0
    except AdapterRefusal as exc:
        print(json.dumps({"status": "refused", **exc.to_dict()}), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "refused", "code": "invalid_spatial_request", "message": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
