"""Cross-system identity continuity and industrial state-transition envelopes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load, save_new
from .control_plane import builtin_registry
from .industrial_transition import (
    binding_from_spec,
    identity_verification_from_spec,
    transition_envelope_from_spec,
    validate_binding,
    validate_identity_verification,
    validate_transition_envelope,
)
from .semantic_capabilities import builtin_semantic_registry


def _semantic():
    return builtin_semantic_registry(builtin_registry(bind=True))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net transition", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    bind = commands.add_parser("bind-identity")
    bind.add_argument("spec", type=Path)
    bind.add_argument("--output", type=Path, required=True)

    verify_identity = commands.add_parser("verify-identity")
    verify_identity.add_argument("binding", type=Path)
    verify_identity.add_argument("spec", type=Path)
    verify_identity.add_argument("--output", type=Path, required=True)

    envelope = commands.add_parser("envelope")
    envelope.add_argument("source_state", type=Path)
    envelope.add_argument("candidate_state", type=Path)
    envelope.add_argument("binding", type=Path)
    envelope.add_argument("identity_verification", type=Path)
    envelope.add_argument("registry", type=Path)
    envelope.add_argument("preservation_contract", type=Path)
    envelope.add_argument("preservation_verification", type=Path)
    envelope.add_argument("preservation_gate", type=Path)
    envelope.add_argument("spec", type=Path)
    envelope.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("record", type=Path)
    inspect.add_argument("--binding", type=Path)
    inspect.add_argument("--source-state", type=Path)
    inspect.add_argument("--candidate-state", type=Path)
    inspect.add_argument("--identity-verification", type=Path)
    inspect.add_argument("--registry", type=Path)
    inspect.add_argument("--preservation-contract", type=Path)
    inspect.add_argument("--preservation-verification", type=Path)
    inspect.add_argument("--preservation-gate", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "bind-identity":
            value = binding_from_spec(load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "created",
                "binding_id": value["binding_id"],
                "canonical_entity_id": value["canonical_entity_id"],
                "references": len(value["references"]),
                "identity_admission_performed": False,
                "canonical_state_mutated": False,
                "output": str(args.output),
            }))
            return 0

        if args.command == "verify-identity":
            value = identity_verification_from_spec(load(args.binding), load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": value["status"],
                "verification_id": value["verification_id"],
                "canonical_entity_id": value["canonical_entity_id"],
                "identity_verification_is_not_admission": True,
                "output": str(args.output),
            }, indent=2))
            return 0 if value["status"] == "VERIFIED" else 2

        if args.command == "envelope":
            semantic = _semantic()
            value = transition_envelope_from_spec(
                load(args.source_state),
                load(args.candidate_state),
                load(args.binding),
                load(args.identity_verification),
                load(args.registry),
                semantic,
                load(args.preservation_contract),
                load(args.preservation_verification),
                load(args.preservation_gate),
                load(args.spec),
            )
            save_new(args.output, value)
            print(json.dumps({
                "status": value["readiness"],
                "transition_id": value["transition_id"],
                "canonical_entity_id": value["canonical_entity_id"],
                "required_admission_authority": value["required_admission_authority"],
                "state_admission_performed": False,
                "canonical_state_mutated": False,
                "output": str(args.output),
            }, indent=2))
            return 0 if value["readiness"] == "READY_FOR_AUTHORITY_REVIEW" else 2

        value = load(args.record)
        schema = value.get("schema") if type(value) is dict else None
        if schema == "ciw.entity-binding.v1":
            checked = validate_binding(value)
            result = {
                "schema": "ciw.entity-binding-inspection.v1",
                "record_digest": checked["record_digest"],
                "binding_id": checked["binding_id"],
                "canonical_entity_id": checked["canonical_entity_id"],
                "references": checked["references"],
                "identity_admission_performed": False,
            }
        elif schema == "ciw.entity-binding-verification.v1":
            if args.binding is None:
                raise ValueError("Identity-verification inspection requires --binding")
            checked = validate_identity_verification(value, load(args.binding))
            result = {
                "schema": "ciw.entity-binding-verification-inspection.v1",
                "record_digest": checked["record_digest"],
                "status": checked["status"],
                "checks": checked["checks"],
                "identity_verification_is_not_admission": True,
            }
        elif schema == "ciw.industrial-transition-envelope.v1":
            required = {
                "source_state": args.source_state,
                "candidate_state": args.candidate_state,
                "binding": args.binding,
                "identity_verification": args.identity_verification,
                "registry": args.registry,
                "preservation_contract": args.preservation_contract,
                "preservation_verification": args.preservation_verification,
                "preservation_gate": args.preservation_gate,
            }
            missing = [name for name, path in required.items() if path is None]
            if missing:
                raise ValueError(
                    "Transition-envelope inspection requires dependencies: " + ", ".join(missing)
                )
            semantic = _semantic()
            checked = validate_transition_envelope(
                value,
                load(args.source_state),
                load(args.candidate_state),
                load(args.binding),
                load(args.identity_verification),
                load(args.registry),
                semantic,
                load(args.preservation_contract),
                load(args.preservation_verification),
                load(args.preservation_gate),
            )
            result = {
                "schema": "ciw.industrial-transition-envelope-inspection.v1",
                "record_digest": checked["record_digest"],
                "transition_id": checked["transition_id"],
                "canonical_entity_id": checked["canonical_entity_id"],
                "readiness": checked["readiness"],
                "reasons": checked["reasons"],
                "required_admission_authority": checked["required_admission_authority"],
                "state_admission_performed": False,
                "canonical_state_mutated": False,
            }
        else:
            raise ValueError("Unsupported industrial transition record schema")

        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
