"""Export one retained simulated-FSRT occurrence; never run the source or solver.

The original observation bytes, engine clock, execution and result stay distinct.
This is a representation, not an execution, verification, admission or publication.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path
import re
import tempfile

from .fsrt_view import MAX_ENVELOPE_BYTES, _json, sha256, write_view
from .session import Session
from .simulated_fsrt import MAX_WORKSPACE_BYTES, OPERATION, validate_source

SCHEMA = "ciw.simulated-fsrt-view.v1"
ENVELOPE = "ciw.simulated-fsrt-view-envelope.v1"
AUTHORITY = {"read_only": True, "numerical_replay": "not_performed_by_inspection",
             "state_admission": "not_performed", "reference_truth_included": False}


def export_view(workspace: Path, execution_id: str, *, expected_workspace_sha256: str) -> dict:
    """Select one occurrence from frozen, validated bytes, including a refusal."""
    if not isinstance(execution_id, str) or not re.fullmatch(r"execution-[0-9a-f]{32}", execution_id):
        raise ValueError("Select a complete execution identity")
    if not isinstance(expected_workspace_sha256, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", expected_workspace_sha256):
        raise ValueError("A complete expected workspace SHA-256 is required")
    with Path(workspace).open("rb") as stream:
        raw = stream.read(MAX_WORKSPACE_BYTES + 1)
    if len(raw) > MAX_WORKSPACE_BYTES:
        raise ValueError("Workspace exceeds the 8 MiB view-export budget")
    if sha256(raw) != expected_workspace_sha256:
        raise ValueError("Workspace bytes differ from the selected digest")
    with tempfile.TemporaryDirectory(prefix="ciw-simulated-view-") as directory:
        frozen = Path(directory) / "workspace.json"
        frozen.write_bytes(raw)
        session = Session.from_workspace(frozen, Path(directory) / "inspect")
        source = validate_source(session.run)
        execution = session.executions.get(execution_id)
        if execution is None or execution["operation_id"] != OPERATION:
            raise ValueError("Selected occurrence is not retained simulated FSRT")
        result = session.results[execution["result_id"]] if execution["status"] == "completed" else None
        retained = session.run["metadata"]["simulation_source"]
        observation_text = base64.b64decode(retained["raw_b64"], validate=True).decode("utf-8")
        payload = {
            "schema": SCHEMA, "workspace_sha256": expected_workspace_sha256,
            "source": {
                "run_id": session.run["run_id"], "evidence_id": session.run["evidence_id"],
                "source_sha256": retained["source_sha256"], "payload": observation_text,
                "channel_evidence_ids": [session.run["channels"][q]["evidence_id"] for q in source["source_ids"]],
            },
            "execution": deepcopy(execution), "result": deepcopy(result),
            "authority": deepcopy(AUTHORITY),
        }
    text = _json(payload)
    envelope = {"schema": ENVELOPE, "payload": text, "sha256": sha256(text.encode("utf-8"))}
    if len(_json(envelope).encode("utf-8")) > MAX_ENVELOPE_BYTES:
        raise ValueError("View exceeds the 256 KiB envelope budget")
    return envelope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--execution", required=True)
    parser.add_argument("--expect-workspace-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        view = export_view(args.workspace, args.execution,
                           expected_workspace_sha256=args.expect_workspace_sha256)
        digest = write_view(view, args.output)
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        parser.exit(2, f"Simulated FSRT view refused: {exc}\n")
    print(json.dumps({"view_sha256": digest, "execution_id": args.execution,
                      "output": str(args.output), "provider_execution": "not_performed",
                      "source_class": "simulated_observation"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
