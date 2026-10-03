"""Read-only union/projection of existing Session evidence, never a new ledger.

Reopen with installed data validators; deduplicate identical occurrences, refuse
conflicts, derive only explicit lineage edges and preserve unknown history gaps.
No native provider, renderer, dynamic import path or operation is bound here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
import heapq
from pathlib import Path
import re
import tempfile

from .control_contracts import MAX_BYTES, bytes_ref, keys
from .godot_capture import inspect_capture, read_bounded
from .operations.runner import check_seal
from .session import loads_json
from .simulation_capture import (
    AUTHORITY, MAX_IMAGE, OPERATION as CAPTURE, encode,
    register_records, validate_dependencies, validate_result as validate_capture,
)
from .simulation_control import open_workspace
from .simulation_records import OPERATION as SIMULATION, packed, require
from .simulation_replay import validate_result, validate_replay
from .simulation_campaign import validate_campaign

MAX_INPUTS = 16
MAX_TOTAL = 96 * 1024 * 1024
MAX_OCCURRENCES = 1024
TIMELINE = "ciw.simulation-timeline.v1"
BUNDLE = "ciw.simulation-timeline-bundle.v1"
SCOPE = "operator evidence index; explicit partial order, not a live world or observer authorization"
_PATH = re.compile(r"evidence/[0-9a-f]{64}\.(?:json|png)\Z")


def _parse(raw: bytes) -> dict:
    value = loads_json(raw.decode("utf-8"))
    require(type(value) is dict, "Evidence JSON must be an object")
    return value


def _store(files: dict[str, bytes], raw: bytes, extension: str = "json") -> str:
    require(type(raw) is bytes and len(raw) <= (MAX_IMAGE if extension == "png" else MAX_BYTES), "Input exceeds per-file budget")
    path = f"evidence/{bytes_ref(raw).split(':', 1)[1]}.{extension}"
    require(path not in files or files[path] == raw, "Conflicting content identity")
    files[path] = raw
    require(sum(map(len, files.values())) <= MAX_TOTAL, "Timeline inputs exceed aggregate byte budget")
    return path


def _inputs(value: dict) -> set[str]:
    keys(value, {"workspaces", "captures", "reports"})
    for group in value.values():
        require(type(group) is list and len(group) <= MAX_INPUTS, "Too many timeline inputs")
    require(value["workspaces"], "Timeline needs at least one source workspace")
    paths = set(value["workspaces"] + value["reports"])
    for item in value["captures"]:
        keys(item, {"capture", "workspace", "source", "image"})
        paths.update(item.values())
        require(item["workspace"] in value["workspaces"] and item["source"] in value["workspaces"], "Capture workspaces must be explicit timeline inputs")
        require(item["image"].endswith(".png"), "Capture needs PNG bytes")
    require(all(type(p) is str and _PATH.fullmatch(p) for p in paths), "Invalid content-addressed evidence path")
    require(all(p.endswith(".json") for p in value["workspaces"] + value["reports"]), "Workspace/report must be JSON")
    require(len(set(value["workspaces"])) == len(value["workspaces"]) and len(set(value["reports"])) == len(value["reports"]), "Duplicate input descriptors")
    return paths


def collect(*, workspaces=(), captures=(), reports=()) -> tuple[dict, dict[str, bytes]]:
    """Freeze caller-selected files before validation or output publication."""
    require(all(len(x) <= MAX_INPUTS for x in (workspaces, captures, reports)), "Too many selected paths")
    files: dict[str, bytes] = {}
    inputs = {"workspaces": [], "captures": [], "reports": []}
    for path in workspaces:
        inputs["workspaces"].append(_store(files, read_bounded(Path(path))))
    for directory in captures:
        directory = Path(directory)
        raw = read_bounded(directory / "capture.json")
        result = _parse(raw)
        validate_capture(result)
        image = result["data"]["image"]
        image_path = directory / "images" / (image["sha256"].split(":", 1)[1] + ".png")
        item = {"capture": _store(files, raw),
                "workspace": _store(files, read_bounded(directory / "workspace.json")),
                "source": _store(files, read_bounded(directory / "source-workspace.json")),
                "image": _store(files, read_bounded(image_path, MAX_IMAGE), "png")}
        inputs["captures"].append(item)
        inputs["workspaces"].extend([item["workspace"], item["source"]])
    for path in reports:
        inputs["reports"].append(_store(files, read_bounded(Path(path))))
    inputs["workspaces"] = sorted(set(inputs["workspaces"]))
    inputs["reports"] = sorted(set(inputs["reports"]))
    # Selecting the same capture twice is harmless; different versions still
    # undergo occurrence conflict detection, not "last file wins" resolution.
    inputs["captures"] = sorted({encode(c): c for c in inputs["captures"]}.values(), key=encode)
    _inputs(inputs)
    return inputs, files


def _union(target: dict, source: dict, label: str) -> None:
    for identity, record in source.items():
        require(identity not in target or target[identity] == record, f"Conflicting retained {label} identity: {identity}")
        target[identity] = record


def _capture_check(item: dict, files: dict, root: Path) -> dict:
    """Use the existing complete capture reader on a frozen scratch bundle."""
    root.mkdir()
    result = _parse(files[item["capture"]])
    validate_capture(result, files[item["image"]])
    (root / "capture.json").write_bytes(files[item["capture"]])
    (root / "workspace.json").write_bytes(files[item["workspace"]])
    (root / "source-workspace.json").write_bytes(files[item["source"]])
    (root / "images").mkdir()
    image = result["data"]["image"]
    (root / "images" / (image["sha256"].split(":", 1)[1] + ".png")).write_bytes(files[item["image"]])
    inspect_capture(root)
    return result


def _entry(execution: dict, result: dict | None) -> dict:
    value = {"execution_id": execution["execution_id"], "execution_ref": execution["record_digest"],
        "operation_id": execution["operation_id"], "created_at": execution["created_at"],
        "status": execution["status"], "result_id": execution["result_id"],
        "result_ref": result["record_digest"] if result else None,
        "kind": "operation", "action": execution["operation_id"], "instance_id": None,
        "experiment_id": None, "owner_id": None, "revision": None, "state_revision": None,
        "world_before": None, "world_after": None, "observer": None, "available_at": None,
        "samples": [], "image": None, "checkpoint_ref": None, "parent": None, "command_id": None,
        "requested_instance_id": None, "refusal": None}
    if execution["status"] == "refused":
        value.update(kind="refusal", refusal=deepcopy(execution["refusal"]))
        request = execution["parameters"]
        # Attempted identity is not observed identity/state/time after failure.
        if execution["operation_id"] == SIMULATION:
            for source, dest in (("instance_id", "requested_instance_id"), ("command_id", "command_id"), ("action", "action")):
                if type(request.get(source)) is str:
                    value[dest] = request[source]
        return value
    if execution["operation_id"] == SIMULATION:
        validate_result(result)
        event = result["data"]
        before, after = event["before"], event["after"]
        action = event["request"]["action"]
        value.update(kind={"observe": "observation", "checkpoint": "checkpoint", "restore": "restore"}.get(action, "command"),
            action=action, instance_id=after["instance_id"], experiment_id=after["experiment_id"],
            owner_id=after["provider"]["owner_id"], revision=after["revision"], state_revision=after["provider"]["state_revision"],
            world_before=deepcopy(before["provider"]["clock"]), world_after=deepcopy(after["provider"]["clock"]),
            parent=deepcopy(after["parent"]), command_id=event["request"]["command_id"])
        if event["checkpoint"] is not None:
            value["checkpoint_ref"] = event["checkpoint"]["record_digest"]
        if event["observations"] is not None:
            batch = event["observations"]
            # These samples are already observer-conditioned. Do not query state
            # or rewrite their time/quantity/uncertainty/occurrence provenance.
            value.update(observer=deepcopy(batch["observer"]), available_at=deepcopy(batch["available_at"]), samples=deepcopy(batch["samples"]))
    elif execution["operation_id"] == CAPTURE:
        validate_capture(result)
        data = result["data"]
        view = data["view"]
        value.update(kind="capture", action="capture", instance_id=view["source"]["instance_id"],
            experiment_id=view["source"]["experiment_id"], observer=deepcopy(view["observer"]), available_at=deepcopy(view["available_at"]),
            image={"sha256": data["image"]["sha256"], "asset": None, "bytes_checked": False,
                "sample_time_s": view["sample_time_s"], "availability": view["availability"],
                "position_xyz_m": deepcopy(view["position_xyz_m"]), "camera": data["selection"]["camera"],
                "source_execution_id": view["source"]["execution_id"], "source_result_ref": view["source"]["result_ref"]})
    return value


def derive(inputs: dict, files: dict[str, bytes]) -> dict:
    """Build a deterministic index from frozen, validated original evidence."""
    require(set(files) == _inputs(inputs), "Unexpected or missing timeline input files")
    require(sum(map(len, files.values())) <= MAX_TOTAL, "Timeline inputs exceed aggregate byte budget")
    for path, raw in files.items():
        require(path.split('/')[-1].split('.')[0] == bytes_ref(raw).split(':')[1], "Input path/content hash mismatch")
        require(len(raw) <= (MAX_IMAGE if path.endswith('.png') else MAX_BYTES), "Input exceeds per-file budget")
    executions, results, source_index, legacy_results = {}, {}, [], set()
    origin = None
    register_records()
    with tempfile.TemporaryDirectory(prefix="net-timeline-read-") as directory:
        root = Path(directory)
        for index, path in enumerate(inputs["workspaces"]):
            raw = files[path]
            saved = _parse(raw)
            # A v3 Workbench can retain other workflow ledgers: this first index
            # refuses rather than claiming it has indexed those unseen histories.
            require(saved.get("workspace_version") in (1, 2), "Timeline v1 indexes recording Session workspaces only, not retained Workbench v3 histories")
            frozen = root / f"source-{index}.json"
            frozen.write_bytes(raw)
            session = open_workspace(frozen, output_dir=root / f"reader-{index}")
            validate_dependencies(session)
            if origin is None:
                origin = session.run
            require(session.run == origin, "Selected workspaces do not share the exact source recording")
            _union(executions, session.executions, "execution")
            _union(results, session.results, "result")
            require(len(executions) <= MAX_OCCURRENCES and len(results) <= MAX_OCCURRENCES, "Merged timeline exceeds occurrence budget")
            legacy_results.update(rid for rid, r in session.results.items() if r.get("schema") != "ciw.operation-result.v1")
            source_index.append({"path": path, "sha256": bytes_ref(raw), "execution_count": len(session.executions), "result_count": len(session.results)})
        images = {}
        for index, item in enumerate(inputs["captures"]):
            capture = _capture_check(item, files, root / f"capture-{index}")
            require(results.get(capture["result_id"]) == capture, "Capture is absent from timeline workspaces")
            images[capture["execution_id"]] = item["image"]
    require(origin is not None, "No retained source recording")
    require(len({r["execution_id"] for r in results.values()}) == len(results), "Distinct results reused an execution identity")
    by_execution = {r["execution_id"]: r for r in results.values()}
    entries = {eid: _entry(e, by_execution.get(eid)) for eid, e in executions.items()}
    for eid, path in images.items():
        entries[eid]["image"].update(asset=path, bytes_checked=True)
    edges, gaps = [], []
    instances = defaultdict(list)
    for r in results.values():
        if r.get("operation_id") == SIMULATION:
            instances[r["data"]["after"]["instance_id"]].append(r)
    def edge(source, target, relation):
        require(source != target, "Self-referencing evidence edge")
        edges.append({"source": source, "target": target, "relation": relation})
    for instance_id, sequence in sorted(instances.items()):
        sequence.sort(key=lambda r: r["data"]["after"]["revision"])
        revisions, command_ids = set(), set()
        previous = None
        binding = sequence[0]["data"]["after"]
        for result in sequence:
            event = result["data"]
            before, after = event["before"], event["after"]
            for key in ("experiment_id", "provider_id", "configuration_ref"):
                require(after[key] == binding[key], "Stable instance binding changed across selected history")
            for key in ("runtime", "model_id", "simulation_id", "owner_id"):
                require(after["provider"][key] == binding["provider"][key], "Provider identity changed across selected history")
            require(after["provider"]["clock"]["id"] == binding["provider"]["clock"]["id"], "Instance clock identity changed")
            require(after["revision"] not in revisions, "Ambiguous instance control revision")
            require(event["request"]["command_id"] not in command_ids, "Accepted commands reused an instance command identity")
            revisions.add(after["revision"])
            command_ids.add(event["request"]["command_id"])
            if previous is not None and before["revision"] == previous["data"]["after"]["revision"]:
                require(before == previous["data"]["after"], "Contradictory adjacent instance state bindings")
                edge(previous["execution_id"], result["execution_id"], "instance_predecessor")
            elif before["revision"] != 0:
                gaps.append({"instance_id": instance_id, "execution_id": result["execution_id"], "missing_predecessor_revision": before["revision"], "reason": "history_gap"})
            if event["request"]["action"] == "restore":
                args = event["request"]["arguments"]
                source = by_execution.get(args["source_execution_id"])
                if source is None:
                    gaps.append({"instance_id": instance_id, "execution_id": result["execution_id"], "source_execution_id": args["source_execution_id"], "reason": "checkpoint_occurrence_not_selected"})
                else:
                    require(source["record_digest"] == args["source_result_ref"] and source.get("operation_id") == SIMULATION
                        and source["data"]["checkpoint"] == args["checkpoint"] and source["data"]["snapshot_b64"] == args["snapshot_b64"]
                        and source["data"]["after"] == args["source"], "Restored checkpoint occurrence contradicts retained source")
                    edge(source["execution_id"], result["execution_id"], "restored_from")
            previous = result
    for eid, r in by_execution.items():
        if r.get("operation_id") == CAPTURE:
            source = r["data"]["source_result"]
            require(results.get(source["result_id"]) == source, "Capture dependency changed across selected sources")
            edge(source["execution_id"], eid, "captured_from")
    edges.sort(key=lambda e: (e["source"], e["target"], e["relation"]))
    # Deterministic topological layout. Timestamp breaks unrelated ties only.
    # Never claim the host's wall clock is simulation/causal order.
    children, degree = defaultdict(list), {eid: 0 for eid in entries}
    for link in edges:
        children[link["source"]].append(link["target"])
        degree[link["target"]] += 1
    stamp = lambda eid: datetime.fromisoformat(executions[eid]["created_at"]).timestamp()
    ready = [(stamp(eid), eid) for eid, n in degree.items() if n == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        _, eid = heapq.heappop(ready)
        ordered.append(entries[eid])
        for child in children[eid]:
            degree[child] -= 1
            if degree[child] == 0:
                heapq.heappush(ready, (stamp(child), child))
    require(len(ordered) == len(entries), "Retained evidence dependencies contain a cycle")
    analyses = []
    for path in inputs["reports"]:
        report = _parse(files[path])
        if report.get("schema") == "ciw.simulation-campaign.v1":
            validate_campaign(report)
            referenced = [report["checkpoint"], *[r for c in report["cases"] for r in c["results"]]]
            outcomes = [{"variant_id": c["variant_id"], "baseline_variant_id": c["baseline_variant_id"], "outcome": deepcopy(c["comparison"]["outcome"])} for c in report["comparisons"]]
            kind, summary = "campaign", deepcopy(report["summary"])
        elif report.get("schema") == "ciw.simulation-replay.v1":
            validate_replay(report)
            referenced = [report["checkpoint"], report["restored"], *report["source"], *report["replayed"]]
            kind, summary, outcomes = "replay", deepcopy(report["outcome"]), []
        else:
            raise ValueError("Unsupported timeline report; select a campaign or replay")
        require(all(results.get(r["result_id"]) == r for r in referenced), "Report references results absent or changed in selected workspaces")
        analyses.append({"kind": kind, "path": path, "record_ref": report["record_digest"], "summary": summary,
            "outcomes": outcomes, "execution_ids": list(dict.fromkeys(r["execution_id"] for r in referenced)), "claim_scope": report["claim_scope"]})
    kinds = dict(sorted(Counter(e["kind"] for e in ordered).items()))
    return packed(TIMELINE, source_recording={"evidence_id": origin["evidence_id"], "run_id": origin["run_id"]},
        sources=source_index, entries=ordered, links=edges, history_gaps=gaps, analyses=analyses,
        summary={"unique_executions": len(executions), "unique_results": len(results), "instance_count": len(instances),
            "deduplicated_execution_copies": sum(s["execution_count"] for s in source_index) - len(executions),
            "kinds": kinds, "checked_images": len(images), "legacy_results_not_indexed": len(legacy_results),
            "history_status": "INDETERMINATE" if gaps else ("selected_history_connected" if instances else "no_indexed_simulation_history"),
            "wall_clock_reversed_links": sum(stamp(e["source"]) > stamp(e["target"]) for e in edges)},
        ordering="explicit dependency partial order; UTC timestamp/identity tie-break is layout only",
        claim_scope=SCOPE, provider_executed=False, **AUTHORITY)


def _artifacts(inputs: dict, files: dict[str, bytes]) -> dict[str, bytes]:
    from .simulation_timeline_view import render
    timeline = derive(inputs, files)
    content = {**files, "timeline.json": encode(timeline), "index.html": render(timeline, files).encode("utf-8")}
    require(len(content["timeline.json"]) <= MAX_BYTES, "Derived timeline exceeds byte budget")
    return content


def build(output_dir: Path, *, workspaces=(), captures=(), reports=()) -> dict:
    inputs, files = collect(workspaces=workspaces, captures=captures, reports=reports)
    artifacts = _artifacts(inputs, files)  # Entire preflight before user output.
    manifest = packed(BUNDLE, inputs=inputs, files={p: bytes_ref(raw) for p, raw in sorted(artifacts.items())},
        claim_scope=SCOPE, provider_executed=False, **AUTHORITY)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    for path, raw in artifacts.items():
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
    # A partially written output has no completed manifest; nothing is overwritten.
    with (output / "manifest.json").open("xb") as stream:
        stream.write(encode(manifest))
    return _parse(artifacts["timeline.json"])["summary"]


def inspect_bundle(directory: Path, *, expected_manifest_sha256: str | None = None) -> dict:
    root = Path(directory)
    raw = read_bounded(root / "manifest.json")
    if expected_manifest_sha256 is not None:
        require(bytes_ref(raw) == expected_manifest_sha256, "Timeline manifest byte digest mismatch")
    manifest = _parse(raw)
    check_seal(manifest)
    keys(manifest, {"schema", "record_digest", "inputs", "files", "claim_scope", "provider_executed", *AUTHORITY})
    require(manifest["schema"] == BUNDLE and manifest["claim_scope"] == SCOPE and manifest["provider_executed"] is False
        and all(manifest[k] == v for k, v in AUTHORITY.items()), "Timeline bundle cannot grant execution or verification authority")
    paths = _inputs(manifest["inputs"])
    require(type(manifest["files"]) is dict and set(manifest["files"]) == paths | {"timeline.json", "index.html"}, "Unexpected bundle inventory")
    content = {}
    for path in sorted(paths):
        content[path] = read_bounded(root / path, MAX_IMAGE if path.endswith(".png") else MAX_BYTES)
        require(sum(map(len, content.values())) <= MAX_TOTAL, "Timeline inputs exceed aggregate byte budget")
    expected = _artifacts(manifest["inputs"], content)
    for path, payload in expected.items():
        require(manifest["files"][path] == bytes_ref(payload), "Bundle differs from its retained source or installed projection")
        actual = content.get(path)
        if actual is None:
            # The HTML embeds bounded image copies; allow only its known size.
            actual = read_bounded(root / path, len(payload))
        require(actual == payload, "Altered derived timeline or view")
    return {"status": "retained_timeline_checked", "summary": _parse(expected["timeline.json"])["summary"],
            "provider_executed": False, **AUTHORITY}
