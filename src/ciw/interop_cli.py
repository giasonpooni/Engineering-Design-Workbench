"""Executable interoperability ingress over external standards and proprietary schemas."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .control_contracts import load, save_new
from .control_plane import builtin_registry
from .interop_ingress import (
    identity_reference_from_qualification,
    ingress_from_spec,
    profile_from_spec,
    qualify_ingress,
    validate_ingress,
    validate_profile,
    validate_qualification,
    validate_verification,
    verification_from_spec,
)
from .semantic_capabilities import builtin_semantic_registry


def _semantic():
    return builtin_semantic_registry(builtin_registry(bind=True))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="net interop", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    execute_ifc = commands.add_parser("execute-ifc", help="Execute exact IFC/observation bytes through pinned CSE and existing NET review boundaries")
    execute_ifc.add_argument("ifc", type=Path)
    execute_ifc.add_argument("observation", type=Path)
    execute_ifc.add_argument("spec", type=Path)
    execute_ifc.add_argument("--cse", type=Path, required=True)
    execute_ifc.add_argument("--output", type=Path, required=True)

    verify_ifc = commands.add_parser("verify-ifc", help="Independently recompute an IFC transition run from retained bytes")
    verify_ifc.add_argument("record", type=Path)
    verify_ifc.add_argument("--cse", type=Path)

    profile = commands.add_parser("create-profile")
    profile.add_argument("registry", type=Path)
    profile.add_argument("preservation_contract", type=Path)
    profile.add_argument("spec", type=Path)
    profile.add_argument("--output", type=Path, required=True)

    ingress = commands.add_parser("retain")
    ingress.add_argument("profile", type=Path)
    ingress.add_argument("spec", type=Path)
    ingress.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("profile", type=Path)
    verify.add_argument("ingress", type=Path)
    verify.add_argument("spec", type=Path)
    verify.add_argument("--output", type=Path, required=True)

    qualify = commands.add_parser("qualify")
    qualify.add_argument("registry", type=Path)
    qualify.add_argument("preservation_contract", type=Path)
    qualify.add_argument("profile", type=Path)
    qualify.add_argument("ingress", type=Path)
    qualify.add_argument("verification", type=Path)
    qualify.add_argument("--output", type=Path, required=True)

    project = commands.add_parser("identity-reference")
    project.add_argument("registry", type=Path)
    project.add_argument("preservation_contract", type=Path)
    project.add_argument("profile", type=Path)
    project.add_argument("ingress", type=Path)
    project.add_argument("verification", type=Path)
    project.add_argument("qualification", type=Path)
    project.add_argument("--output", type=Path, required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("record", type=Path)
    inspect.add_argument("--registry", type=Path)
    inspect.add_argument("--preservation-contract", type=Path)
    inspect.add_argument("--profile", type=Path)
    inspect.add_argument("--ingress", type=Path)
    inspect.add_argument("--verification", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command in {"execute-ifc", "verify-ifc"}:
            from .ifc_transition import execute_ifc as execute, verify_ifc as verify
            from .adapters.subprocess import _json
            if args.command == "execute-ifc":
                with args.ifc.open("rb") as stream:
                    ifc = stream.read(65537)
                with args.observation.open("rb") as stream:
                    observation = stream.read(4097)
                value = execute(ifc, observation, load(args.spec), {"cse": args.cse})
                save_new(args.output, value)
                result = verify(value)
                result["output"] = str(args.output)
            else:
                with args.record.open("rb") as stream:
                    raw = stream.read(4 * 1024 * 1024 + 1)
                if not raw or len(raw) > 4 * 1024 * 1024:
                    raise ValueError("IFC transition record exceeds byte budget")
                result = verify(_json(raw), None if args.cse is None else {"cse": args.cse})
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0 if result["qualification"] == "QUALIFIED" and result["transition_readiness"] == "READY_FOR_AUTHORITY_REVIEW" else 2

        semantic = _semantic()

        if args.command == "create-profile":
            value = profile_from_spec(
                load(args.registry),
                semantic,
                load(args.preservation_contract),
                load(args.spec),
            )
            save_new(args.output, value)
            print(json.dumps({
                "status": "created",
                "profile_id": value["profile_id"],
                "source_family": value["source_family"],
                "source_profile_id": value["source_profile_id"],
                "morphism_id": value["morphism_id"],
                "standard_or_schema_conformance_established": False,
                "semantic_preservation_established": False,
                "output": str(args.output),
            }))
            return 0

        if args.command == "retain":
            value = ingress_from_spec(load(args.profile), load(args.spec))
            save_new(args.output, value)
            print(json.dumps({
                "status": "retained",
                "ingress_id": value["ingress_id"],
                "payload_ref": value["payload_ref"],
                "mapping_executed": False,
                "profile_conformance_established": False,
                "output": str(args.output),
            }))
            return 0

        if args.command == "verify":
            value = verification_from_spec(
                load(args.profile), load(args.ingress), load(args.spec)
            )
            save_new(args.output, value)
            print(json.dumps({
                "status": value["status"],
                "verification_id": value["verification_id"],
                "verification_is_not_physical_validation": True,
                "mapping_executed": False,
                "output": str(args.output),
            }, indent=2))
            return 0 if value["status"] == "VERIFIED" else 2

        if args.command == "qualify":
            value = qualify_ingress(
                load(args.registry),
                semantic,
                load(args.preservation_contract),
                load(args.profile),
                load(args.ingress),
                load(args.verification),
            )
            save_new(args.output, value)
            print(json.dumps({
                "status": value["status"],
                "source_system_id": value["source_system_id"],
                "source_representation_id": value["source_representation_id"],
                "target_representation_id": value["target_representation_id"],
                "mapping_executed": False,
                "state_admission_performed": False,
                "output": str(args.output),
            }, indent=2))
            return 0 if value["status"] == "QUALIFIED" else 2

        if args.command == "identity-reference":
            value = identity_reference_from_qualification(
                load(args.qualification),
                load(args.registry),
                semantic,
                load(args.preservation_contract),
                load(args.profile),
                load(args.ingress),
                load(args.verification),
            )
            save_new(args.output, value)
            print(json.dumps({
                "status": "projected",
                "reference_id": value["reference_id"],
                "system_id": value["system_id"],
                "evidence_ref": value["evidence_ref"],
                "identity_admission_performed": False,
                "output": str(args.output),
            }))
            return 0

        value = load(args.record)
        schema = value.get("schema") if type(value) is dict else None
        if schema == "ciw.interoperability-profile.v1":
            if args.registry is None or args.preservation_contract is None:
                raise ValueError("Profile inspection requires --registry and --preservation-contract")
            checked = validate_profile(
                value, load(args.registry), semantic, load(args.preservation_contract)
            )
            result = {
                "schema": "ciw.interoperability-profile-inspection.v1",
                "record_digest": checked["record_digest"],
                "profile_id": checked["profile_id"],
                "source_family": checked["source_family"],
                "standard_id": checked["standard_id"],
                "source_profile_id": checked["source_profile_id"],
                "source_representation_id": checked["source_representation_id"],
                "target_representation_id": checked["target_representation_id"],
                "declared_loss_properties": checked["declared_loss_properties"],
                "semantic_preservation_established": False,
            }
        elif schema == "ciw.external-ingress.v1":
            if args.profile is None:
                raise ValueError("Ingress inspection requires --profile")
            checked = validate_ingress(value, load(args.profile))
            result = {
                "schema": "ciw.external-ingress-inspection.v1",
                "record_digest": checked["record_digest"],
                "ingress_id": checked["ingress_id"],
                "payload_ref": checked["payload_ref"],
                "source_identity": checked["source_identity"],
                "mapping_executed": False,
            }
        elif schema == "ciw.external-ingress-verification.v1":
            if args.profile is None or args.ingress is None:
                raise ValueError("Ingress verification inspection requires --profile and --ingress")
            checked = validate_verification(value, load(args.profile), load(args.ingress))
            result = {
                "schema": "ciw.external-ingress-verification-inspection.v1",
                "record_digest": checked["record_digest"],
                "status": checked["status"],
                "checks": checked["checks"],
                "verification_is_not_physical_validation": True,
            }
        elif schema == "ciw.external-ingress-qualification.v1":
            required = {
                "registry": args.registry,
                "preservation_contract": args.preservation_contract,
                "profile": args.profile,
                "ingress": args.ingress,
                "verification": args.verification,
            }
            missing = [name for name, path in required.items() if path is None]
            if missing:
                raise ValueError(
                    "Qualification inspection requires dependencies: " + ", ".join(missing)
                )
            checked = validate_qualification(
                value,
                load(args.registry),
                semantic,
                load(args.preservation_contract),
                load(args.profile),
                load(args.ingress),
                load(args.verification),
            )
            result = {
                "schema": "ciw.external-ingress-qualification-inspection.v1",
                "record_digest": checked["record_digest"],
                "status": checked["status"],
                "source_system_id": checked["source_system_id"],
                "source_identity": checked["source_identity"],
                "source_representation_id": checked["source_representation_id"],
                "target_representation_id": checked["target_representation_id"],
                "state_admission_performed": False,
                "physical_validity_established": False,
            }
        else:
            raise ValueError("Unsupported interoperability record schema")

        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
