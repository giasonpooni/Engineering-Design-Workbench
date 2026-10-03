"""Checked-stage algebra lowered into the ORIGINAL production work-order plan.

Unlike dataflow series, stage series is a completion/acceptance barrier. Cross-job
artifact transport remains provider-owned; this compiler never invents a port
wire between jobs. Fixed Gate policies and bounded declared retries are reused.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .control_contracts import _base, bytes_ref, content_ref, detached, keys, text
from .control_plane import _plan_contracts
from .core.identities import content_identity
from .production import _gate_bindings, plan, run_production
from .operations.runner import seal
from .workflow_algebra import (AUTHORITY, _check_independence, _effects, _grant,
                               _topology, _validate_expression, effects, grant)


def stage(name):
    """Exactly the first attempt of one operator-declared, checked stage."""
    return {"kind": "stage", "name": text(name)}


def bounded_retry(name, *, max_attempts):
    """FAIL-only selection of a bounded prefix of PREDECLARED parameter variants.

    This is not a categorical trace, a fixed point, adaptive source rewriting or
    retry-on-refusal. Original production behavior for held/refused work remains.
    """
    return {"kind": "bounded_retry", "name": text(name), "max_attempts": max_attempts}


def declare_stage(job, *, effect=None, permissions=(), qualifications=None):
    return {"template_digest": content_identity(detached(job)),
            "effects": effects(unknown=True) if effect is None else _effects(effect),
            **grant(permissions=permissions, qualifications=qualifications)}


def _stage_graph(expr):
    kind = expr["kind"]
    if kind in ("stage", "bounded_retry"):
        name = expr["name"]
        return {name: expr.get("max_attempts", 1)}, {name: set()}, {name}, {name}
    if kind == "identity":
        return {}, {}, set(), set()
    counts, deps, roots, ends = {}, {}, set(), set()
    for item in expr["items"]:
        c, d, r, e = _stage_graph(item)
        if not c:
            continue
        if not counts:
            counts, deps, roots, ends = c, d, r, e
            continue
        if kind == "sequence":
            for name in r:
                d[name].update(ends)
            ends = e
        else:
            roots.update(r); ends.update(e)
        counts.update(c); deps.update(d)
    return counts, deps, roots, ends


def _lower(expr, templates, declarations, contracts, gate_runtimes, authorization, *, plan_id, project_id, source_evidence_id):
    counts, deps, _, _ = _stage_graph(expr)
    if not counts:
        raise ValueError("Structural production identity has no executable jobs")
    keys(templates, set(counts)); keys(declarations, set(counts))
    order = _topology(counts, deps)
    ancestors = {}
    for name in order:
        ancestors[name] = set(deps[name])
        for dep in deps[name]:
            ancestors[name].update(ancestors[dep])
    job_effects, jobs = {}, []
    used_ops, used_gates = set(), set()
    for name in order:
        template = templates[name]
        keys(template, {"job_id", "worker_id", "requires", "depends_on", "attempts", "checks"})
        if template["job_id"] != name or type(template["depends_on"]) is not list:
            raise ValueError("Stage template identity mismatch")
        mandatory = template["depends_on"]
        if any(type(dep) is not str for dep in mandatory) or len(set(mandatory)) != len(mandatory):
            raise ValueError("Invalid mandatory acceptance dependencies")
        if set(mandatory) - ancestors[name]:
            raise ValueError(f"Required acceptance predecessor missing or unordered: {name}")
        declaration = declarations[name]
        keys(declaration, {"template_digest", "effects", "permissions", "qualifications"})
        if declaration["template_digest"] != content_identity(template):
            raise ValueError("Stage template drift")
        job_effects[name] = _effects(declaration["effects"])
        required = _grant({key: declaration[key] for key in ("permissions", "qualifications")})
        if set(required["permissions"]) - set(authorization["permissions"]):
            raise ValueError("Missing exact stage permission")
        if any(authorization["qualifications"].get(scope) != ref for scope, ref in required["qualifications"].items()):
            raise ValueError("Missing or mismatched stage qualification reference")
        attempts = template["attempts"]
        if type(attempts) is not list or not 1 <= len(attempts) <= 3 or counts[name] > len(attempts):
            raise ValueError("Retry exceeds the predeclared attempt set")
        # Validate ALL declared variants, including unselected variants. No hidden
        # code/route/check changes can hide in a later 'retry'. Original validator
        # checks node shapes; strengthen this front end to fix global parameters.
        for graph in attempts:
            if content_identity(graph["parameters"]) != content_identity(attempts[0]["parameters"]):
                raise ValueError("Repairs may not change experiment-global parameters")
            operations = {node["operation_id"] for node in graph["nodes"]}
            _plan_contracts(graph, {op: contracts[op] for op in operations})
            if set(template["requires"]) - {cap for op in operations for cap in contracts[op]["capabilities"]}:
                raise ValueError("Stage requires unavailable capability")
            used_ops.update(operations)
        for check in template["checks"]:
            used_gates.add(check["gate_id"])
        jobs.append({**deepcopy(template), "depends_on": sorted(deps[name]),
                     "attempts": deepcopy(attempts[:counts[name]])})
    keys(contracts, used_ops); keys(gate_runtimes, used_gates)
    for name, runtime in gate_runtimes.items():
        text(name)
        if type(runtime) is not dict or not runtime:
            raise ValueError("Acceptance gate needs an explicit runtime identity")
    _check_independence(order, deps, job_effects)
    # The original validator also checks unselected variant shape, policies and
    # total 256-node worst case. Reject rather than expanding old runtime limits.
    plan(plan_id, project_id=project_id, source_evidence_id=source_evidence_id,
         jobs=[{**deepcopy(templates[name]), "depends_on": sorted(deps[name])} for name in order])
    compiled = plan(plan_id, project_id=project_id, source_evidence_id=source_evidence_id, jobs=jobs)
    return seal({"schema": "ciw.workflow-production-compilation.v1", "expression": detached(expr),
        "templates": detached(templates), "declarations": detached(declarations),
        "contracts": detached(contracts), "gate_runtimes": detached(gate_runtimes),
        "grant_snapshot": authorization, "plan": compiled,
        "compiler_sha256": bytes_ref(Path(__file__).read_bytes()),
        "algebra_sha256": bytes_ref(Path(__file__).with_name("workflow_algebra.py").read_bytes()),
        "authority": deepcopy(AUTHORITY)})


def compile_plan(expr, templates, registry, declarations, gates, authorization, *, plan_id, project_id, source_evidence_id):
    _, names = _validate_expression(expr, production=True)
    selected = {name: detached(templates[name]) for name in sorted(names)}
    annotated = {name: detached(declarations[name]) for name in sorted(names)}
    operations = {n["operation_id"] for t in selected.values() for g in t["attempts"] for n in g["nodes"]}
    gate_names = {c["gate_id"] for t in selected.values() for c in t["checks"]}
    runtime = _gate_bindings({name: gates[name] for name in sorted(gate_names)}) if gate_names else {}
    return _lower(expr, selected, annotated, {op: registry.contract(op) for op in sorted(operations)}, runtime,
                  _grant(authorization), plan_id=plan_id, project_id=project_id, source_evidence_id=source_evidence_id)


def inspect_compilation(value):
    value = detached(value)
    _base(value, "workflow-production-compilation", {"expression", "templates", "declarations", "contracts",
          "gate_runtimes", "grant_snapshot", "plan", "compiler_sha256", "algebra_sha256", "authority"})
    _validate_expression(value["expression"], production=True)
    fields = {key: value["plan"][key] for key in ("plan_id", "project_id", "source_evidence_id")}
    expected = _lower(value["expression"], value["templates"], value["declarations"], value["contracts"],
                      value["gate_runtimes"], _grant(value["grant_snapshot"]), **fields)
    if content_identity(expected) != content_identity(value):
        raise ValueError("Compiled production differs from its declarations/compiler")
    return {"integrity": "checked", "fresh_execution": False, **deepcopy(AUTHORITY)}


def check_live(value, registry, templates, declarations, gates, authorization):
    value = detached(value)
    inspect_compilation(value)
    current = compile_plan(value["expression"], templates, registry, declarations, gates, authorization,
        **{key: value["plan"][key] for key in ("plan_id", "project_id", "source_evidence_id")})
    if content_identity(current) != content_identity(value):
        raise ValueError("Live stage/gate/permission binding differs; recompile explicitly")
    return value["plan"]


def run_compiled(source, value, registry, templates, declarations, gates, workers, authorization, output_dir, *, max_operations=128):
    """Live recheck followed by the existing sequential production controller."""
    compiled = check_live(value, registry, templates, declarations, gates, authorization)
    return run_production(source, compiled, registry, workers, gates, output_dir, max_operations=max_operations)


def compile_workcell(stages, jobs, registry, gates, *, candidate_id, recipe_id, source_evidence_id):
    """Existing recipe handoffs stay in CellOperations, not fictitious data wires."""
    from .workflow_algebra import sequence
    content_ref(candidate_id)
    if tuple(stages) not in (("build", "test"), ("build", "test", "package")):
        raise ValueError("Workcell adapter accepts only existing stage routes")
    templates = {job["job_id"]: detached(job) for job in jobs}
    keys(templates, set(stages))
    declarations = {name: declare_stage(templates[name],
        effect=effects(writes=("workcell/" + candidate_id[7:],)), permissions=("workcell." + name,)) for name in stages}
    authorization = grant(permissions=tuple("workcell." + name for name in stages))
    return compile_plan(sequence(*(stage(name) for name in stages)), templates, registry,
        declarations, gates, authorization, plan_id="workcell-build", project_id=recipe_id,
        source_evidence_id=source_evidence_id)
