"""Check the conservative event policy for the migrated CI workflows.

PyYAML is pinned in the dev extra as PyYAML==6.0.3. The workflow-contract job
installs that extra and does not carry a second pin. This does not emulate
GitHub's changed-file matching or establish that a selected scientific gate passed.
"""
from __future__ import annotations

from pathlib import Path
import sys
import yaml

QUALIFICATION = (
    "acquired-stream.yml",
    "calibrated-observable.yml",
    "calibrated-window.yml",
    "ci.yml",
    "declared-workloads.yml",
    "energy-accuracy.yml",
    "exchange.yml",
    "free-energy.yml",
    "geodesic-references.yml",
    "geometry-research.yml",
    "identified-design.yml",
    "integrated-modules.yml",
    "proved-heat.yml",
    "remaining-modules.yml",
    "telemetry.yml",
    "workbench-candidates.yml"
)
ALWAYS = ("test.yml", "workflow-contracts.yml")
CANDIDATE_BRANCH = "codex/qualified-release-baseline"
CANDIDATE_WORKFLOWS = (
    "monorepo.yml",
    "test.yml",
    "workflow-contracts.yml",
    "declared-workloads.yml",
    "calibrated-observable.yml",
    "identified-design.yml",
    "calibrated-window.yml",
    "proved-heat.yml",
)
CANDIDATE_AUXILIARY = ("release-evidence.yml",)


def candidate_branches(name: str) -> list[str]:
    return ["main", CANDIDATE_BRANCH] if name in (*CANDIDATE_WORKFLOWS, *CANDIDATE_AUXILIARY) else ["main"]


def check_candidate_push(name: str, value: dict) -> list[str]:
    """Check exact-candidate routing without changing each workflow's other contracts."""
    events = value.get("on", {})
    push = events.get("push", {}) if isinstance(events, dict) else {}
    if not isinstance(push, dict) or push.get("branches") != candidate_branches(name):
        return [f"{name}: require main and the exact reviewed candidate branch"]
    return []

DOCS_ONLY = (
    "README.md",
    "docs/**/*.md",
    "deploy/**/*.md",
    "godot/**/*.md",
    "examples/**/README.md"
)
GROUP = "${{ github.workflow }}-${{ github.event_name }}-${{ github.event.pull_request.number || (github.event_name == 'push' && github.ref) || github.run_id }}"


def check_workflow(name: str, value: dict, *, qualification: bool) -> list[str]:
    errors = []
    events = value.get("on", {})
    if not isinstance(events, dict) or set(events) != {"push", "pull_request", "workflow_dispatch"}:
        return [f"{name}: require push, pull_request and workflow_dispatch"]
    push = {"branches": candidate_branches(name), "tags": ["**"]}
    pull = {}
    if qualification:
        push["paths-ignore"] = list(DOCS_ONLY)
        pull["paths-ignore"] = list(DOCS_ONLY)
    if events["push"] != push:
        errors.append(f"{name}: reviewed branch/all-tag push scope or documentation filter changed")
    if (events["pull_request"] or {}) != pull:
        errors.append(f"{name}: PRs must include stacked targets with the declared documentation filter")
    if events["workflow_dispatch"] not in (None, "", {}):
        errors.append(f"{name}: manual dispatch must not require inputs")
    if value.get("concurrency") != {"group": GROUP, "cancel-in-progress": "true"}:
        errors.append(f"{name}: isolate workflow/events and cancel superseded branch/PR runs while isolating manual dispatches")
    return errors


def main(root: Path) -> int:
    errors = []
    for name in (*ALWAYS, *QUALIFICATION):
        path = root / ".github" / "workflows" / name
        try:
            value = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
            if not isinstance(value, dict):
                raise ValueError("workflow must be a mapping")
            errors.extend(check_workflow(name, value, qualification=name in QUALIFICATION))
        except (OSError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"{name}: {exc}")
    for name in (*CANDIDATE_WORKFLOWS, *CANDIDATE_AUXILIARY):
        if name in (*ALWAYS, *QUALIFICATION):
            continue
        path = root / ".github" / "workflows" / name
        try:
            value = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
            if not isinstance(value, dict):
                raise ValueError("workflow must be a mapping")
            errors.extend(check_candidate_push(name, value))
        except (OSError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"{name}: {exc}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"PASS: shared event policy for {len(ALWAYS) + len(QUALIFICATION)} workflows and exact candidate routing; qualification is separate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(__file__).resolve().parents[1]))
