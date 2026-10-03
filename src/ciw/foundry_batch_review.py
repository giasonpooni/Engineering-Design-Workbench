"""Offline batch handoff inspection using the original candidate scope checker."""
from __future__ import annotations

from pathlib import Path

from . import foundry_packets as packets, foundry_pipeline as pipeline
from .control_contracts import _base, content_ref, keys, save_new
from .core.identities import content_identity
from .foundry_queue import queue, ASSIGNABLE
from .operations.runner import seal
from .session import loads_json


def read_batch(project: dict, directory: Path, expected_batch_id: str) -> tuple[dict, list[dict]]:
    """An independently retained batch ID anchors all packet and specification IDs."""
    pipeline.validate_project(project)
    content_ref(expected_batch_id)
    root = packets.root_dir(directory)

    def read(name):
        return loads_json(packets.read_file(root, name).decode("utf-8"))

    batch = read("batch.json")
    _base(batch, "foundry-packet-batch", {"project_digest", "spec_digest", "queue_digest",
          "packets", "conflicts", "executed", "acceptance", "publication"})
    if batch["record_digest"] != expected_batch_id:
        raise ValueError("Batch differs from the independently retained batch identity")
    if (batch["project_digest"] != project["record_digest"] or batch["executed"] is not False
            or batch["acceptance"] != "not_performed" or batch["publication"] != "not_performed"):
        raise ValueError("Batch changed project or authority")
    spec, retained_queue = read("spec.json"), read("queue.json")
    if (content_identity(spec) != batch["spec_digest"]
            or content_identity(retained_queue) != batch["queue_digest"]):
        raise ValueError("Batch specification or retained queue changed")
    keys(spec, {"schema", "assignments"})
    if spec["schema"] != "ciw.foundry-batch-spec.v1" or type(spec["assignments"]) is not list:
        raise ValueError("Invalid batch specification")
    items = batch["packets"]
    if type(items) is not list or not 1 <= len(items) <= 16 or len(items) != len(spec["assignments"]):
        raise ValueError("Invalid batch packet coverage")
    result, seen = [], set()
    for entry, assignment in zip(items, spec["assignments"]):
        keys(entry, {"task_id", "path", "packet_id"})
        keys(assignment, {"task_id", "assignee", "writable", "context", "max_changed_bytes"})
        task = pipeline.task_for(project, entry["task_id"])
        name = task["task_id"]
        if name in seen or entry["path"] != name + "/packet.json":
            raise ValueError("Duplicate task or unexpected packet path")
        seen.add(name)
        packet = read(entry["path"])
        packets.validate_packet(packet, project, task)
        if packet["record_digest"] != entry["packet_id"]:
            raise ValueError("Packet differs from retained batch identity")
        if (assignment["task_id"] != name or assignment["assignee"] != packet["assignee"]
                or sorted(assignment["writable"]) != packet["writable"]
                or set(assignment["context"]) != set(packet["context"])
                or assignment["max_changed_bytes"] != packet["max_changed_bytes"]):
            raise ValueError("Packet differs from batch assignment")
        result.append(packet)
    if packets.compatible_wave(result) != batch["conflicts"]:
        raise ValueError("Batch conflict report differs from actual packets")
    return batch, result


def check_batch(project: dict, source_root: Path, directory: Path, *, expected_batch_id: str,
                candidates: dict[str, Path], evidence=None, destination: Path | None = None) -> dict:
    """Check available returns; retain missing/refused work without calling it accepted."""
    batch, issued = read_batch(project, directory, expected_batch_id)
    names = [p["task_id"] for p in issued]
    if type(candidates) is not dict or set(candidates) - set(names):
        raise ValueError("Candidate bindings name tasks outside this batch")
    current = queue(project, source_root, evidence, targets=names)
    states = {row["task_id"]: row for row in current["tasks"]}
    rows = []
    for packet in issued:
        name = packet["task_id"]
        state = states[name]
        row = {"task_id": name, "packet_id": packet["record_digest"],
               "current_task_status": state["status"], "blocked_by": state["blocked_by"],
               "scope_check": None, "reason": None}
        if name not in candidates:
            row["status"] = "missing_candidate"
        else:
            try:
                row["scope_check"] = packets.check_candidate(packet, project,
                    pipeline.task_for(project, name), candidates[name],
                    expected_packet_id=packet["record_digest"])
                row["status"] = row["scope_check"]["status"]
            except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
                row.update(status="candidate_unreadable", reason=str(exc)[:2048])
        row["ready_for_quality_review"] = (row["status"] == "scope_passed"
            and not current["source_drift"] and state["status"] in ASSIGNABLE
            and not state["blocked_by"])
        rows.append(row)
    if queue(project, source_root, evidence, targets=names) != current:
        raise ValueError("Readiness changed during candidate inspection")
    # Detect mutation of the retained packet batch during the inspection.
    if read_batch(project, directory, expected_batch_id) != (batch, issued):
        raise ValueError("Batch changed during candidate inspection")
    report = seal({"schema": "ciw.foundry-batch-review.v1",
        "project_digest": project["record_digest"], "batch_digest": batch["record_digest"],
        "current_queue": current, "candidates": rows,
        "status": "ready_for_quality_review" if all(r["ready_for_quality_review"] for r in rows) else "incomplete",
        "conflicts": batch["conflicts"], "quality_acceptance": "not_performed",
        "executed": False, "integration": "not_performed", "release_authorized": False})
    if destination is not None:
        destination = Path(destination)
        roots = [Path(source_root).resolve(), Path(directory).resolve(),
                 *(Path(p).resolve() for p in candidates.values())]
        if any(root in (destination.resolve(), *destination.resolve().parents) for root in roots):
            raise ValueError("Review output must be outside source, batch and candidate roots")
        if any(p.is_symlink() for p in (destination, *destination.parents)):
            raise ValueError("Output symlinks are not admitted")
        destination.mkdir(parents=True, exist_ok=False)
        lines = ["# Foundry batch review", "", f"Batch: `{batch['record_digest']}`", "",
                 "Scope inspection only. Quality review and integration remain outstanding.", "",
                 "| Task | Candidate scope | Current task | Ready for quality review |",
                 "|---|---|---|---|"]
        for row in rows:
            lines.append(f"| {row['task_id']} | {row['status']} | {row['current_task_status']} | {row['ready_for_quality_review']} |")
        lines += ["", f"Source changes: {len(current['source_drift'])}.",
                  f"Packet conflicts: {len(batch['conflicts']['conflicts'])}; rebase and requalify at integration.",
                  "See review.json for exact changes, refusal reasons, evidence and packet identities.", ""]
        (destination / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
        save_new(destination / "review.json", report)
    return report
