"""Export an exact retained FSRT occurrence, without importing or running FSRT.

Uses the existing workspace reader, including source, payload, covariance and
execution/result validation. The view is not a new execution, verification or
state-admission record. A digest binds bytes, not publisher authenticity.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tempfile

from .session import Session

OPERATIONS = frozenset({"fsrt.tank-reconstruct.v1", "fsrt.tank-reconstruct.v2"})
MAX_WORKSPACE_BYTES = 8 * 1024 * 1024
MAX_ENVELOPE_BYTES = 256 * 1024
SCHEMA = "ciw.fsrt-view.v1"
ENVELOPE = "ciw.fsrt-view-envelope.v1"


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def export_view(workspace: Path, execution_id: str, *, expected_workspace_sha256: str) -> dict:
    """Inspect a frozen workspace and return a detached exact-byte view envelope.

    Select an execution explicitly, including a refused occurrence. The expected
    workspace digest must come from the operator's retained-artifact selection.
    Reopening occurs in a temporary directory: the caller's workspace and result
    files are never written. No provider is registered, imported or invoked.
    """
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
    # The same frozen bytes are hashed and parsed; source mutation cannot swap
    # the file between checking it and reopening it. All writes stay in scratch.
    with tempfile.TemporaryDirectory(prefix="ciw-fsrt-view-") as directory:
        frozen = Path(directory) / "workspace.json"
        frozen.write_bytes(raw)
        session = Session.from_workspace(frozen, Path(directory) / "inspect")
        if execution_id not in session.executions:
            raise ValueError("Selected execution is not retained in this workspace")
        execution = session.executions[execution_id]
        if execution["operation_id"] not in OPERATIONS:
            raise ValueError("Selected execution is not a supported FSRT snapshot")
        result = session.results.get(execution["result_id"]) if execution["status"] == "completed" else None
        metadata = session.run["metadata"]
        sensors = metadata.get("rci_source", {}).get("sensors")
        if not isinstance(sensors, list) or len(sensors) != 2:
            raise ValueError("View requires the supported retained two-reservoir source")
        provenance = metadata["provenance"]
        payload = {
            "schema": SCHEMA,
            "workspace_sha256": expected_workspace_sha256,
            "source": {
                "run_id": session.run["run_id"], "evidence_id": session.run["evidence_id"],
                "coordinate_frame": metadata["coordinate_frame"],
                "description": provenance["source"], "time_reference": provenance["time_reference"],
                "source_order": [sensor["name"] for sensor in sensors],
                "observed_at": [sensor["measurement"]["records"][0]["observed_at"] for sensor in sensors],
            },
            "execution": deepcopy(execution), "result": deepcopy(result),
            "authority": {"read_only": True, "numerical_replay": "not_performed_by_inspection",
                          "state_admission": "not_performed"},
        }
    text = _json(payload)
    envelope = {"schema": ENVELOPE, "payload": text, "sha256": sha256(text.encode("utf-8"))}
    if len(_json(envelope).encode("utf-8")) > MAX_ENVELOPE_BYTES:
        raise ValueError("View exceeds the 256 KiB envelope budget")
    return envelope


def write_view(envelope: dict, output: Path) -> str:
    """Create a new artifact exclusively; never replace an existing source/file."""
    raw = _json(envelope).encode("utf-8")
    if len(raw) > MAX_ENVELOPE_BYTES:
        raise ValueError("View exceeds the 256 KiB envelope budget")
    with Path(output).open("xb") as stream:
        stream.write(raw)
    return envelope["sha256"]


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
        parser.exit(2, f"FSRT view refused: {exc}\n")
    print(json.dumps({"view_sha256": digest, "execution_id": args.execution,
                      "output": str(args.output), "provider_execution": "not_performed"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
