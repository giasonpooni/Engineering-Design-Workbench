"""Execute qualified IFC ingress through the existing pinned CSE workload."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .bim_interop import execute_bim_mapping_bundle, validate_bim_mapping_witness
from .cse_preservation import project_bim_states, verify_bim_preservation
from .control_contracts import load, save_new
from .control_plane import builtin_registry
from .semantic_capabilities import builtin_semantic_registry


def _semantic():
    return builtin_semantic_registry(builtin_registry(bind=True))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net interop-bim", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    execute = commands.add_parser("execute")
    execute.add_argument("registry", type=Path)
    execute.add_argument("preservation_contract", type=Path)
    execute.add_argument("profile", type=Path)
    execute.add_argument("ingress", type=Path)
    execute.add_argument("ingress_verification", type=Path)
    execute.add_argument("qualification", type=Path)
    execute.add_argument("bim_source", type=Path)
    execute.add_argument("spec", type=Path)
    execute.add_argument("--cse-repository", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    execute.add_argument("--bundle-output", type=Path, required=True)

    project = commands.add_parser("project-states")
    project.add_argument("registry", type=Path)
    project.add_argument("preservation_contract", type=Path)
    project.add_argument("profile", type=Path)
    project.add_argument("ingress", type=Path)
    project.add_argument("ingress_verification", type=Path)
    project.add_argument("qualification", type=Path)
    project.add_argument("mapping_witness", type=Path)
    project.add_argument("bundle", type=Path)
    project.add_argument("binding", type=Path)
    project.add_argument("identity_verification", type=Path)
    project.add_argument("--source-output", type=Path, required=True)
    project.add_argument("--candidate-output", type=Path, required=True)

    verify = commands.add_parser("verify-preservation")
    verify.add_argument("registry", type=Path)
    verify.add_argument("preservation_contract", type=Path)
    verify.add_argument("profile", type=Path)
    verify.add_argument("ingress", type=Path)
    verify.add_argument("ingress_verification", type=Path)
    verify.add_argument("qualification", type=Path)
    verify.add_argument("mapping_witness", type=Path)
    verify.add_argument("bundle", type=Path)
    verify.add_argument("--verification-id", required=True)
    verify.add_argument("--notes", default="")
    verify.add_argument("--source-state", type=Path)
    verify.add_argument("--candidate-state", type=Path)
    verify.add_argument("--binding", type=Path)
    verify.add_argument("--identity-verification", type=Path)
    verify.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("witness", type=Path)
    inspect.add_argument("registry", type=Path)
    inspect.add_argument("preservation_contract", type=Path)
    inspect.add_argument("profile", type=Path)
    inspect.add_argument("ingress", type=Path)
    inspect.add_argument("ingress_verification", type=Path)
    inspect.add_argument("qualification", type=Path)
    inspect.add_argument("bundle", type=Path)

    args = parser.parse_args(argv)
    try:
        semantic = _semantic()
        if args.command == "execute":
            value, bundle = execute_bim_mapping_bundle(
                load(args.registry),
                semantic,
                load(args.preservation_contract),
                load(args.profile),
                load(args.ingress),
                load(args.ingress_verification),
                load(args.qualification),
                load(args.bim_source),
                {"cse": args.cse_repository},
                load(args.spec),
            )
            save_new(args.output, value)
            save_new(args.bundle_output, bundle)
            print(json.dumps({
                "status": value["mapping_outcome"],
                "execution_id": value["execution_id"],
                "payload_ref": value["payload_ref"],
                "native_result_ref": value["native_result_ref"],
                "preservation_verification_performed": False,
                "state_admission_performed": False,
                "output": str(args.output),
                "bundle_output": str(args.bundle_output),
            }, indent=2))
            return 0 if value["mapping_outcome"] == "MAPPED" else 2

        if args.command == "project-states":
            source_state, candidate_state = project_bim_states(
                load(args.registry),
                semantic,
                load(args.preservation_contract),
                load(args.profile),
                load(args.ingress),
                load(args.ingress_verification),
                load(args.qualification),
                load(args.mapping_witness),
                load(args.bundle),
                load(args.binding),
                load(args.identity_verification),
            )
            save_new(args.source_output, source_state)
            save_new(args.candidate_output, candidate_state)
            print(json.dumps({
                "status": "projected",
                "source_state_ref": source_state["record_digest"],
                "candidate_state_ref": candidate_state["record_digest"],
                "canonical_entity_id": source_state["identity"]["entity_id"],
                "state_admission_performed": False,
                "source_output": str(args.source_output),
                "candidate_output": str(args.candidate_output),
            }, indent=2))
            return 0

        if args.command == "verify-preservation":
            value = verify_bim_preservation(
                load(args.registry),
                semantic,
                load(args.preservation_contract),
                load(args.profile),
                load(args.ingress),
                load(args.ingress_verification),
                load(args.qualification),
                load(args.mapping_witness),
                load(args.bundle),
                verification_id=args.verification_id,
                notes=args.notes,
                source_state_record=None if args.source_state is None else load(args.source_state),
                candidate_state_record=None if args.candidate_state is None else load(args.candidate_state),
                binding=None if args.binding is None else load(args.binding),
                identity_verification=None if args.identity_verification is None else load(args.identity_verification),
            )
            save_new(args.output, value)
            print(json.dumps({
                "status": value["status"],
                "verification_id": value["verification_id"],
                "source_state_ref": value["source_state_ref"],
                "candidate_state_ref": value["candidate_state_ref"],
                "checks": value["checks"],
                "verification_is_not_admission": True,
                "output": str(args.output),
            }, indent=2))
            return 0 if value["status"] == "VERIFIED" else 2

        checked = validate_bim_mapping_witness(
            load(args.witness),
            load(args.registry),
            semantic,
            load(args.preservation_contract),
            load(args.profile),
            load(args.ingress),
            load(args.ingress_verification),
            load(args.qualification),
            load(args.bundle),
        )
        print(json.dumps({
            "schema": "ciw.interop-mapping-witness-inspection.v1",
            "record_digest": checked["record_digest"],
            "mapping_outcome": checked["mapping_outcome"],
            "native_status": checked["native_status"],
            "native_reason": checked["native_reason"],
            "payload_ref": checked["payload_ref"],
            "target": checked["target"],
            "preservation_verification_performed": False,
            "physical_validity_established": False,
            "state_admission_performed": False,
        }, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
