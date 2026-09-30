"""Create trusted representation-realization adapter registries and records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load, save_new
from .control_plane import builtin_registry
from .representation_realizations import (
    adapter_registry_from_specs,
    bind_recovery_realization,
    realize,
)
from .semantic_capabilities import builtin_semantic_registry


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net realization", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-registry")
    create.add_argument("morphism_registry", type=Path)
    create.add_argument("spec", type=Path)
    create.add_argument("--output", type=Path, required=True)

    realize_cmd = commands.add_parser("realize")
    realize_cmd.add_argument("adapter_registry", type=Path)
    realize_cmd.add_argument("morphism_registry", type=Path)
    realize_cmd.add_argument("artifact", type=Path)
    realize_cmd.add_argument("spec", type=Path)
    realize_cmd.add_argument("--output", type=Path, required=True)

    bind = commands.add_parser("bind-recovery")
    bind.add_argument("adapter_registry", type=Path)
    bind.add_argument("morphism_registry", type=Path)
    bind.add_argument("gate", type=Path)
    bind.add_argument("realization", type=Path)
    bind.add_argument("artifact", type=Path)
    bind.add_argument("binding_id")
    bind.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        semantic = builtin_semantic_registry(builtin_registry(bind=True))
        morphism_registry = load(args.morphism_registry)
        if args.command == "create-registry":
            spec = load(args.spec)
            if type(spec) is not dict or set(spec) != {"adapters"}:
                raise ValueError("Realization registry spec requires adapters only")
            value = adapter_registry_from_specs(
                morphism_registry, semantic, spec["adapters"])
        elif args.command == "realize":
            value = realize(
                load(args.adapter_registry), morphism_registry, semantic,
                load(args.artifact), load(args.spec))
        else:
            value = bind_recovery_realization(
                load(args.adapter_registry), morphism_registry, semantic,
                load(args.gate), load(args.realization), load(args.artifact),
                args.binding_id)
        save_new(args.output, value)
        print(json.dumps({
            "status": "created",
            "schema": value["schema"],
            "record_digest": value["record_digest"],
            "provider_execution": False,
            "state_admission": False,
            "execution_authority": False,
            "output": str(args.output),
        }))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
