"""Production planning and evidence joins over the existing Foundry and Session.

The blueprint is authoring data, not another scheduler. Dependency order reuses
NET's experiment validator. Native runs retain the original production receipts;
reviews are explicitly operator attestations, never authenticated proof/release.
"""
from __future__ import annotations
from copy import deepcopy
from fnmatch import fnmatchcase
from pathlib import Path

from . import foundry_catalog as catalog
from . import foundry_packets as packets
from .control_contracts import _base, bytes_ref, content_ref, detached, keys, load, save_new, text
from .control_plane import _experiment, experiment
from .core.identities import content_identity
from .operations.runner import seal

VERSION = "ciw.foundry-pipeline.v1"
SATISFIED = frozenset({"machine_checked", "operator_attested"})


def dependency_order(tasks: list[dict]) -> list[str]:
    graph = experiment("foundry-authoring-order", model_id="foundry-production-blueprint", nodes=[
        {"node_id": t["task_id"], "operation_id": "foundry.authoring.task.v1", "parameters": {},
         "inputs": {}, "depends_on": t["depends_on"]} for t in tasks])
    # Pure DAG validation. The symbolic operation is never registered or dispatched.
    return _experiment(graph)


def create_project(project_id: str, source_root: Path, destination: Path) -> dict:
    text(project_id)
    tasks = catalog.tasks()
    dependency_order(tasks)
    value = seal({"schema": VERSION, "project_id": project_id, "baseline": packets.inventory(source_root),
        "stages": [{"stage_id": i, "title": title} for i, title in catalog.STAGES], "tasks": tasks,
        "template_id": content_identity(tasks), "sources": list(catalog.SOURCES),
        "authority": {"state_admission": "not_performed", "publication": "not_performed"},
        "scope": "authored AAA-style work breakdown; not Ubisoft internal schedule or proof of implementation"})
    destination = Path(destination)
    # Outputs must not contaminate the source tree they lock.
    if Path(source_root).resolve() in (destination.resolve(), *destination.resolve().parents):
        raise ValueError("Project output must be outside the source root")
    destination.mkdir(parents=True, exist_ok=False)
    save_new(destination / "project.json", value)
    return value


def validate_project(value: dict) -> list[str]:
    _base(value, "foundry-pipeline", {"project_id", "baseline", "stages", "tasks", "template_id", "sources", "authority", "scope"})
    text(value["project_id"]); packets.validate_inventory(value["baseline"])
    if (value["tasks"] != catalog.tasks() or value["template_id"] != content_identity(catalog.tasks())
            or value["stages"] != [{"stage_id": i, "title": title} for i, title in catalog.STAGES]
            or value["sources"] != list(catalog.SOURCES)
            or value["authority"] != {"state_admission": "not_performed", "publication": "not_performed"}):
        raise ValueError("Blueprint changes the installed template or authority; explicit implementation revision required")
    return dependency_order(value["tasks"])


def task_for(project: dict, task_id: str) -> dict:
    validate_project(project)
    for task in project["tasks"]:
        if task["task_id"] == task_id:
            return deepcopy(task)
    raise ValueError("Task is not in the installed blueprint")


def impact(project: dict, source_root: Path) -> dict:
    order = validate_project(project)
    current = packets.inventory(source_root)
    diff = packets.changes(project["baseline"], current)
    changed = {item["path"] for item in diff}
    tasks = {t["task_id"]: t for t in project["tasks"]}
    direct = {i for i, t in tasks.items() if any(fnmatchcase(p, pattern) for p in changed for pattern in t["watches"])}
    affected = set(direct)
    for name in order:
        if set(tasks[name]["depends_on"]) & affected:
            affected.add(name)
    return {"schema": "ciw.foundry-change-impact.v1", "baseline_id": project["baseline"]["inventory_id"],
        "current_id": current["inventory_id"], "changes": diff,
        "direct_tasks": [i for i in order if i in direct], "affected_tasks": [i for i in order if i in affected],
        "policy": "conservative all-input watches except exact native recipe inputs; no automatic re-execution"}


def _native_evidence(project: dict, task: dict, directory: Path) -> dict:
    from . import foundry_water as water
    from .foundry_workflow import inspect_order, report_order
    directory = packets.root_dir(directory)
    link = load(directory / "task-run.json")
    _base(link, "foundry-task-run", {"project_digest", "task_id", "task_digest", "source_lock", "production_digest", "scope"})
    if (link["project_digest"] != project["record_digest"] or link["task_id"] != task["task_id"]
            or link["task_digest"] != content_identity(task)):
        raise ValueError("Native evidence belongs to another project or task")
    from .foundry_project import validate_lock
    validate_lock(link["source_lock"])
    if any(project["baseline"]["files"].get(p, {}).get("sha256") != digest for p, digest in link["source_lock"]["files"].items()):
        raise ValueError("Native evidence used different source inputs")
    root = directory / "production"
    packets.root_dir(root)
    report = inspect_order(root)  # independent gate recomputation; no process creation
    original = load(root / "production.json")
    if original["record_digest"] != link["production_digest"]:
        raise ValueError("Original production occurrence was substituted")
    specification = load(root / "plan.json")
    jobs = specification["jobs"]
    if [j["job_id"] for j in jobs] != ["water-round", "water-round-regression"] or jobs[1]["depends_on"] != ["water-round"]:
        raise ValueError("Required primary/regression recipe was altered")
    for job in jobs:
        if job["worker_id"] != water.WORKERS[0].worker_id or job["requires"] != ["game.1792.water-round"]:
            raise ValueError("Unexpected recipe worker")
        expected_checks = [{"check_id": "complete-conserved-water-round", "node_id": "candidate", "gate_id": water.GATE, "policy": water.POLICY}]
        if job["checks"] != expected_checks:
            raise ValueError("Required acceptance checks were changed")
        for graph in job["attempts"]:
            if len(graph["nodes"]) != 1 or graph["nodes"][0]["operation_id"] != water.OP:
                raise ValueError("Recipe selected a different operation")
    bindings = load(root / "bindings.json")
    runtime = bindings["contracts"][water.OP]["runtime"]
    if (runtime.get("provider") != "ciw.foundry.godot-project" or runtime.get("execution_mode") != "native_process"
            or runtime.get("source_lock") != link["source_lock"]):
        raise ValueError("Non-native, mismatched or unrecognized provider is not native evidence")
    # Do not count a primary success without its independent fresh-process regression.
    accepted = report["status"] == "completed" and all(report["jobs"][i]["status"] == "accepted" for i in ("water-round", "water-round-regression"))
    return {"status": "machine_checked" if accepted else "not_accepted", "evidence_id": link["record_digest"],
        "basis": "recomputed_original_foundry_acceptance", "production_id": original["production_id"],
        "session_id": original["session_id"], "counters": report_order(root),
        "scope": "water domain fixture only, not played route, visual quality or release"}


def _review_evidence(project: dict, task: dict, directory: Path, dependencies: dict) -> dict:
    directory = packets.root_dir(directory)
    review = load(directory / "review.json")
    _base(review, "foundry-task-review", {"project_digest", "task_id", "task_digest", "decision", "reviewer", "producer", "review_role", "dependencies", "artifacts", "authority", "scope"})
    if (review["project_digest"] != project["record_digest"] or review["task_id"] != task["task_id"]
            or review["task_digest"] != content_identity(task) or review["review_role"] != task["owner_role"]):
        raise ValueError("Review applies to another work contract")
    text(review["reviewer"]); text(review["producer"])
    if review["reviewer"] == review["producer"] or review["decision"] not in {"approved", "rejected"}:
        raise ValueError("Review needs a distinct declared reviewer and an explicit disposition")
    if review["authority"] != {"authentication": "not_verified", "release_authorized": False}:
        raise ValueError("Review cannot confer authentication or release permission")
    if review["dependencies"] != dependencies:
        return {"status": "stale", "evidence_id": review["record_digest"], "basis": "prerequisite_evidence_changed"}
    packets.validate_inventory(review["artifacts"])
    if packets.inventory(directory / "artifacts") != review["artifacts"]:
        raise ValueError("Reviewed artifacts changed or are missing")
    return {"status": "operator_attested" if review["decision"] == "approved" else "review_rejected",
            "evidence_id": review["record_digest"], "basis": "declared_human_review_not_authenticated",
            "reviewer": review["reviewer"], "scope": "planning disposition, not independent quality proof or release"}


def assess(project: dict, source_root: Path, evidence: dict[str, Path] | None = None) -> dict:
    order = validate_project(project)
    evidence = {} if evidence is None else evidence
    if type(evidence) is not dict or set(evidence) - set(order):
        raise ValueError("Evidence names unknown tasks")
    drift = impact(project, source_root)
    rows, tasks = {}, {t["task_id"]: t for t in project["tasks"]}
    for name in order:
        task = tasks[name]
        dependencies = {i: rows[i].get("evidence_id") for i in task["depends_on"]}
        blocked = [i for i in task["depends_on"] if rows[i]["status"] not in SATISFIED]
        row = {"status": "blocked" if blocked else "awaiting_review" if task["automation"] == "human_led" else "ready_for_packet",
               "blocked_by": blocked, "installed_execution": task["installed_recipe"],
               "supplied_evidence_inspected": False}
        if name in drift["affected_tasks"]:
            row.update(status="stale", basis="source_inputs_changed")
        elif name in evidence and not blocked:
            row["supplied_evidence_inspected"] = True
            row.update(_native_evidence(project, task, evidence[name]) if task["completion"] == "native_foundry"
                       else _review_evidence(project, task, evidence[name], dependencies))
        elif not blocked and task["installed_recipe"]:
            row["status"] = "ready_to_run"
        # Evidence is supplied explicitly. No directory crawling, last-result guessing or
        # silent execution of providers/agents takes place during status inspection.
        rows[name] = row
    stage_status = []
    for stage in project["stages"]:
        names = [t["task_id"] for t in project["tasks"] if t["stage"] == stage["stage_id"]]
        stage_status.append({**stage, "tasks": names, "satisfied_for_planning": sum(rows[n]["status"] in SATISFIED for n in names),
                             "total": len(names), "complete_for_planning": all(rows[n]["status"] in SATISFIED for n in names)})
    machine = sum(r["status"] == "machine_checked" for r in rows.values())
    human = sum(r["status"] == "operator_attested" for r in rows.values())
    native = [r["counters"] for r in rows.values() if "counters" in r]
    return {"schema": "ciw.foundry-pipeline-status.v1", "project_id": project["project_id"], "project_digest": project["record_digest"],
        "tasks": rows, "stages": stage_status, "impact": drift,
        "metrics": {"machine_checked_tasks": machine, "operator_attested_tasks": human,
                    "unresolved_tasks": len(rows)-machine-human,
                    "native_attempts": sum(len(r["attempts"]) for r in native),
                    "rejected_native_attempts": sum(r["rejected_attempts"] for r in native),
                    "captured_native_wall_s": sum(r["captured_native_wall_s"] for r in native),
                    "human_hours": None, "model_cost": None, "accepted_playable_minutes": None},
        "release_authorized": False, "fresh_execution": False,
        "scope": "task-specific evidence and declared reviews; no studio-equivalence, game completion or release claim"}


def review_task(project: dict, task_id: str, source_root: Path, artifact_root: Path, destination: Path,
                *, reviewer: str, producer: str, decision: str, evidence: dict[str, Path] | None = None) -> dict:
    task = task_for(project, task_id)
    if task["completion"] != "operator_review":
        raise ValueError("A human receipt cannot replace the required native acceptance gate")
    text(reviewer); text(producer)
    if reviewer == producer or decision not in {"approved", "rejected"}:
        raise ValueError("Require distinct declared producer/reviewer and approved/rejected decision")
    current = assess(project, source_root, evidence)
    if current["tasks"][task_id]["blocked_by"] or current["tasks"][task_id]["status"] == "stale":
        raise ValueError("Task review is blocked by prerequisites or source drift")
    dependencies = {i: current["tasks"][i]["evidence_id"] for i in task["depends_on"]}
    artifact_root = packets.root_dir(artifact_root)
    manifest = packets.inventory(artifact_root)
    # Snapshot artifacts once, then recheck before retaining. Only ordinary files copied.
    raws = {p: packets.read_file(artifact_root, p) for p in manifest["files"]}
    if any(bytes_ref(raw) != manifest["files"][p]["sha256"] for p, raw in raws.items()):
        raise ValueError("Review artifacts changed during read")
    value = seal({"schema": "ciw.foundry-task-review.v1", "project_digest": project["record_digest"],
        "task_id": task_id, "task_digest": content_identity(task), "decision": decision,
        "reviewer": reviewer, "producer": producer, "review_role": task["owner_role"],
        "dependencies": dependencies, "artifacts": manifest,
        "authority": {"authentication": "not_verified", "release_authorized": False},
        "scope": "operator-entered review; identity strings are not authenticated human judgment"})
    destination = Path(destination)
    if any(root in (destination.resolve(), *destination.resolve().parents) for root in (Path(source_root).resolve(), artifact_root)):
        raise ValueError("Review output must be outside source and input artifacts")
    destination.mkdir(parents=True, exist_ok=False)
    for path, raw in raws.items():
        target = destination / "artifacts" / path; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
        if manifest["files"][path]["executable"]:
            target.chmod(target.stat().st_mode | 0o111)
    save_new(destination / "review.json", value)  # completion marker comes last
    return value


def run_task(project: dict, task_id: str, source_root: Path, executable: Path, expected_sha256: str,
             destination: Path, *, candidate_trips: int = 1, repair: bool = True, max_operations: int = 3) -> dict:
    from . import foundry_water as water
    from .foundry_project import GodotProjectBinding, snapshot
    from .production import preflight, run_production
    task = task_for(project, task_id)
    if task["installed_recipe"] != "1792.water-round.v1":
        raise ValueError("No installed execution binding for this task; a potential automation class is not an executable worker")
    if packets.inventory(source_root) != project["baseline"]:
        raise ValueError("Source drift: refuse dispatch before creating output")
    lock, _ = snapshot(source_root)
    source = water.source(lock)
    specification = water.compile_plan(source, candidate_trips=candidate_trips, repair=repair)
    binding = GodotProjectBinding(executable, source_root, expected_sha256=expected_sha256, source_lock=lock)
    registry = water.registry(binding)
    preflight(specification, registry, water.WORKERS, water.gates(), max_operations=max_operations)
    destination = Path(destination)
    if Path(source_root).resolve() in (destination.resolve(), *destination.resolve().parents):
        raise ValueError("Execution output must be outside locked source")
    destination.mkdir(parents=True, exist_ok=False)
    original = run_production(source, specification, registry, water.WORKERS, water.gates(), destination / "production", max_operations=max_operations)
    link = seal({"schema": "ciw.foundry-task-run.v1", "project_digest": project["record_digest"],
        "task_id": task_id, "task_digest": content_identity(task), "source_lock": lock,
        "production_digest": original["record_digest"],
        "scope": "reference to original production occurrence; no second execution identity"})
    save_new(destination / "task-run.json", link)
    return {"status": original["status"], "task_id": task_id, "production_id": original["production_id"],
            "session_id": original["session_id"], "evidence_id": link["record_digest"], "fresh_execution": True,
            "publication": "not_performed"}


def markdown_report(project: dict, report: dict) -> str:
    lines = [f"# {project['project_id']} · Production pipeline", "",
        "Authored AAA-style task breakdown, not a recovered Ubisoft internal schedule.",
        "Stage labels show a typical progression; dependency edges permit overlapping work.",
        "Only the 1792 water-domain recipe is executable here. Other automation labels describe potential work division.", "",
        "| Stage | Task | Responsibility | Agent potential | Current disposition | Requires |", "|---|---|---|---|---|---|"]
    for t in project["tasks"]:
        lines.append(f"| {t['stage']} | {t['task_id']}: {t['title']} | {t['owner_role']} | {t['automation']} | {report['tasks'][t['task_id']]['status']} | {', '.join(t['depends_on']) or '—'} |")
    lines += ["", "## Acceptance requirements", ""]
    for t in project["tasks"]:
        lines += [f"### {t['task_id']} · {t['title']}", t["acceptance"], ""]
    m = report["metrics"]
    lines += ["## Observed coverage", f"Machine-checked tasks: {m['machine_checked_tasks']}. Operator-attested tasks: {m['operator_attested_tasks']}. Unresolved: {m['unresolved_tasks']}.",
        f"Native attempts: {m['native_attempts']}; rejected: {m['rejected_native_attempts']}.",
        "Human hours, model costs, accepted playable minutes and studio-equivalent productivity are not measured.",
        "Operator review identities are declared, not authenticated. Scope-check success is not acceptance. Release remains unauthorized.", "",
        "## Public references", ""]
    for s in catalog.SOURCES:
        lines += [f"- {s['url']} — {s['supports']}"]
    return "\n".join(lines) + "\n"
