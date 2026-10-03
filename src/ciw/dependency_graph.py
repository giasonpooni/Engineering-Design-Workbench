"""Read-only dependency projection over existing retained artifact identities.

Edges come from retained catalog links and explicit operation inputs. They do
not authenticate observations, establish a physical claim, or grant authority.
Unresolved native input references are reported rather than guessed.
"""
from __future__ import annotations

from copy import deepcopy


def artifact_graph(run: dict, results: dict, executions: dict, workbench) -> dict:
    """Return nodes keyed by their existing identity, without invoking providers."""
    nodes = {run["evidence_id"]: {
        "kind": "evidence", "dependencies": [], "run_id": run["run_id"],
    }}

    def add(identity, kind, dependencies=(), **metadata):
        node = {"kind": kind, "dependencies": sorted(set(dependencies)), **metadata}
        if identity in nodes and nodes[identity] != node:
            raise ValueError("Dependency projection contains conflicting artifact identities")
        nodes[identity] = node

    # Capture the Workbench in one lock, not separately changing read surfaces.
    retained = workbench.dependency_artifacts()
    sources = {source["source_id"]: source for source in retained["sources"]}
    bundles = {bundle["bundle_id"]: bundle for bundle in retained["bundles"]}
    for source in sources.values():
        nodes.setdefault(source["evidence_id"], {"kind": "evidence", "dependencies": []})
        add(source["source_id"], "source", [source["evidence_id"]],
            source_kind=source["kind"], evidence_id=source["evidence_id"], label=source["label"])
    for execution in executions.values():
        deps = [execution["evidence_id"]]
        upstream = execution.get("parameters", {}).get("source_result_id")
        if upstream is not None:
            deps.append(upstream)
        add(execution["execution_id"], "execution", deps,
            operation_id=execution["operation_id"], outcome=execution["status"])
    for result in results.values():
        deps = [result["evidence_id"]]
        upstream = result.get("parameters", {}).get("source_result_id")
        if upstream is not None:
            deps.append(upstream)
        if result["execution_id"] in executions:
            deps.append(result["execution_id"])
        else:
            # Flat legacy analyses retain the occurrence inside the result.
            add(result["execution_id"], "execution", deps,
                operation_id=result["operation_id"], outcome="completed")
            deps = [result["execution_id"]]
        add(result["result_id"], "result", deps, operation_id=result["operation_id"])
    # Native step inputs can refer to another native result, bundle or evidence.
    # Allocate all outputs before resolving the explicit references.
    for execution in retained["executions"]:
        deps = [execution["source_id"]]
        bundle = bundles[execution["bundle_id"]]
        deps.extend(bundle.get("upstream_bundle_ids", []))
        if bundle["upstream_bundle_id"] is not None:
            deps.append(bundle["upstream_bundle_id"])
        add(execution["execution_id"], "execution", deps,
            operation_id=execution["operation_id"], outcome=execution["status"])
        add(execution["result_id"], "result", [execution["execution_id"]],
            operation_id=execution["operation_id"])
    for bundle in bundles.values():
        deps = [bundle["source_id"], *bundle["result_ids"], *bundle.get("upstream_bundle_ids", [])]
        if bundle["upstream_bundle_id"] is not None:
            deps.append(bundle["upstream_bundle_id"])
        add(bundle["bundle_id"], "bundle", deps, source_kind=bundle["kind"])
    for execution in retained["executions"]:
        node = nodes[execution["execution_id"]]
        refs = execution["input_refs"]
        node["dependencies"] = sorted(set(node["dependencies"]) | {ref for ref in refs if ref in nodes})
        unresolved = sorted({ref for ref in refs if ref not in nodes})
        if unresolved:
            node["unresolved_input_refs"] = unresolved
    return deepcopy(nodes)
