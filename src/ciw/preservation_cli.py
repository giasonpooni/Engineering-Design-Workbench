"""Typed preservation contracts, composition, verification and admission eligibility."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load, save_new
from .control_plane import builtin_registry
from .preservation_contracts import (
    admission_gate_from_spec,
    compose_contracts,
    contract_from_spec,
    validate_admission_gate,
    validate_composition,
    validate_contract,
    validate_verification,
    verification_from_spec,
)
from .semantic_capabilities import builtin_semantic_registry


def _semantic():
    return builtin_semantic_registry(builtin_registry(bind=True))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net preservation", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("registry", type=Path)
    create.add_argument("spec", type=Path)
    create.add_argument("--output", type=Path, required=True)

    compose = commands.add_parser("compose")
    compose.add_argument("registry", type=Path)
    compose.add_argument("left", type=Path)
    compose.add_argument("right", type=Path)
    compose.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("registry", type=Path)
    verify.add_argument("contract", type=Path)
    verify.add_argument("spec", type=Path)
    verify.add_argument("--output", type=Path, required=True)

    gate = commands.add_parser("gate")
    gate.add_argument("registry", type=Path)
    gate.add_argument("contract", type=Path)
    gate.add_argument("verification", type=Path)
    gate.add_argument("policy", type=Path)
    gate.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("registry", type=Path)
    inspect.add_argument("record", type=Path)
    inspect.add_argument("--left", type=Path)
    inspect.add_argument("--right", type=Path)
    inspect.add_argument("--contract", type=Path)
    inspect.add_argument("--verification", type=Path)

    args = parser.parse_args(argv)
    try:
        semantic = _semantic()
        registry = load(args.registry)

        if args.command == "create":
            value = contract_from_spec(registry, semantic, load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "created",
                "contract_id": value["contract_id"],
                "morphism_id": value["morphism_id"],
                "effects": len(value["effects"]),
                "execution_authority": False,
                "state_admission_authority": False,
                "output": str(args.output),
            }))
            return 0

        if args.command == "compose":
            value = compose_contracts(registry, semantic, load(args.left), load(args.right))
            save_new(args.output, value)
            print(json.dumps({
                "status": value["status"],
                "requirement_checks": value["requirement_checks"],
                "unknown_lineages": sum(row["effect"] == "UNKNOWN" for row in value["lineages"]),
                "execution_authority": False,
                "state_admission_authority": False,
                "output": str(args.output),
            }, indent=2))
            return 0 if value["status"] == "COMPOSABLE" else 2

        if args.command == "verify":
            value = verification_from_spec(
                registry, semantic, load(args.contract), load(args.spec)
            )
            save_new(args.output, value)
            print(json.dumps({
                "status": value["status"],
                "verification_id": value["verification_id"],
                "verification_is_not_admission": True,
                "output": str(args.output),
            }, indent=2))
            return 0 if value["status"] == "VERIFIED" else 2

        if args.command == "gate":
            value = admission_gate_from_spec(
                registry,
                semantic,
                load(args.contract),
                load(args.verification),
                load(args.policy),
            )
            save_new(args.output, value)
            print(json.dumps({
                "status": value["decision"],
                "policy_violations": value["policy_violations"],
                "state_admission_performed": False,
                "canonical_state_mutated": False,
                "output": str(args.output),
            }, indent=2))
            return 0 if value["decision"] == "ELIGIBLE" else 2

        value = load(args.record)
        schema = value.get("schema") if type(value) is dict else None
        if schema == "ciw.preservation-contract.v1":
            checked = validate_contract(value, registry, semantic)
            result = {
                "schema": "ciw.preservation-contract-inspection.v1",
                "record_digest": checked["record_digest"],
                "contract_id": checked["contract_id"],
                "morphism_id": checked["morphism_id"],
                "requires": checked["requires"],
                "effects": {
                    kind: sum(row["effect"] == kind for row in checked["effects"])
                    for kind in ("PRESERVE", "TRANSFORM", "BOUND", "FORGET")
                },
                "state_admission_authority": False,
            }
        elif schema == "ciw.preservation-composition.v1":
            if args.left is None or args.right is None:
                raise ValueError("Composition inspection requires --left and --right contracts")
            checked = validate_composition(
                value, registry, semantic, load(args.left), load(args.right)
            )
            result = {
                "schema": "ciw.preservation-composition-inspection.v1",
                "record_digest": checked["record_digest"],
                "status": checked["status"],
                "requirement_checks": checked["requirement_checks"],
                "lineages": checked["lineages"],
                "state_admission_authority": False,
            }
        elif schema == "ciw.preservation-verification.v1":
            if args.contract is None:
                raise ValueError("Verification inspection requires --contract")
            checked = validate_verification(
                value, registry, semantic, load(args.contract)
            )
            result = {
                "schema": "ciw.preservation-verification-inspection.v1",
                "record_digest": checked["record_digest"],
                "status": checked["status"],
                "checks": checked["checks"],
                "verification_is_not_admission": True,
            }
        elif schema == "ciw.preservation-admission-gate.v1":
            if args.contract is None or args.verification is None:
                raise ValueError("Admission-gate inspection requires --contract and --verification")
            checked = validate_admission_gate(
                value,
                registry,
                semantic,
                load(args.contract),
                load(args.verification),
            )
            result = {
                "schema": "ciw.preservation-admission-gate-inspection.v1",
                "record_digest": checked["record_digest"],
                "decision": checked["decision"],
                "policy_violations": checked["policy_violations"],
                "state_admission_performed": False,
            }
        else:
            raise ValueError("Unsupported preservation record schema")

        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
