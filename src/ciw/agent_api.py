"""Agent-facing projections over existing NET primitives; no model or engine owner.

Copyright (c) 2026 Giason Pooni, for original contributions.
SPDX-License-Identifier: AGPL-3.0-or-later

Host configuration grants access to explicit, frozen inputs and registered
operations. Agent arguments never choose files, imports, executables or policies.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
import threading
from typing import Any

from .control_contracts import bytes_ref, json_tree, keys, number, save_new, record
from .control_plane import CapabilityRegistry, ParameterSpace, experiment, plan_graph, run_graph
from .control_checks import compare, inspect_record
from .check_suite import evaluate, plan, validate_plan
from .session import Session, loads_json

MAX_DOCUMENT = 8 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_ARTIFACTS = 256
MAX_RESPONSE = 256 * 1024
AUTHORITY = {"baseline_acceptance": "not_permitted", "state_admission": "not_performed",
             "verification_id": None, "verification_status": "not_verified",
             "physical_validation": "not_established"}


def encode(value: Any) -> bytes:
    json_tree(value)
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    if len(raw) > MAX_DOCUMENT:
        raise ValueError("Document exceeds 8 MiB")
    return raw


def parse(raw: bytes) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_DOCUMENT:
        raise ValueError("Require bounded nonempty document bytes")
    value = loads_json(raw.decode("utf-8"))
    json_tree(value)
    if type(value) is not dict:
        raise ValueError("Document must be an object")
    return value


def identifier(value: str) -> str:
    if type(value) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", value) is None:
        raise ValueError("Require an opaque identifier, not a path or URL")
    return value


def _count(value: int, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"Require an integer in 1..{maximum}")
    return value


def _validated(value: dict) -> dict:
    """Reuse trusted offline readers, never an executable chosen by saved data."""
    if "workspace_version" in value:
        with tempfile.TemporaryDirectory(prefix="net-agent-inspect-") as directory:
            root = Path(directory)
            save_new(root / "workspace.json", value)
            session = Session.from_workspace(root / "workspace.json", output_dir=root / "readback")
            snapshot = session.snapshot()
            snapshot.pop("session_id", None)  # The scratch reader is not the original session.
            return {"schema": "ciw.workspace-inspection.v1", "session": snapshot,
                    "session_identity": "original_session_id_not_retained_by_workspace_schema",
                    "executions": deepcopy(session.executions), "results": deepcopy(session.results)}
    if value.get("schema") == "ciw.source-selection.v1":
        from .computational_source import validate_capture
        return validate_capture(value)
    if "run_id" in value and "channels" in value:
        from .instruments import validate_run
        from .core.identities import validate_evidence_identity
        validate_run(value)
        validate_evidence_identity(value)
        return value
    inspect_record(value)
    return value


class AgentHost:
    """Single-process, sequential agent access to a host-owned CapabilityRegistry.

    No source edits, native loads, Git writes, network listener, baseline promotion,
    or arbitrary subprocess API. Registered providers remain trusted host code and
    retain their own process/resource controls. This is NOT an OS sandbox.
    """

    def __init__(self, *, registry: CapabilityRegistry, inputs: dict[str, bytes],
                 output_dir: Path | None = None, allow_operations: tuple[str, ...] = (),
                 candidate_domains: dict | None = None, comparisons: dict | None = None,
                 check_suites: dict | None = None, max_executions: int = 8, max_nodes: int = 8):
        if type(allow_operations) is not tuple or len(allow_operations) > 64 or any(type(x) is not str for x in allow_operations):
            raise ValueError("Execution grants must be an explicit bounded tuple")
        for item in (candidate_domains, comparisons, check_suites):
            if item is not None and (type(item) is not dict or len(item) > 64):
                raise ValueError("Host policies must be bounded objects")
        self._lock = threading.RLock()
        self._registry = registry
        self._catalog = encode(registry.catalog())
        self._allow = frozenset(allow_operations)
        if len(self._allow) != len(allow_operations):
            raise ValueError("Duplicate executable grant")
        if self._allow - set(registry.catalog()["operations"]):
            raise ValueError("Execution grant is not advertised")
        for operation_id in self._allow:
            registry.operations.get(operation_id)  # Declaration is not a binding.
        self._maximum = _count(max_executions, 64)
        self._max_nodes = _count(max_nodes, 64)
        self._attempts: dict[str, dict] = {}
        self._artifacts: dict[str, bytes] = {}
        self._aliases: dict[str, str] = {}
        self._generated: set[str] = set()
        self._bytes = 0
        self._domains = {}
        self._policies = deepcopy(comparisons or {})
        self._suites = deepcopy(check_suites or {})
        self._output: Path | None = None
        for name, policy in self._policies.items():
            identifier(name)
            keys(policy, {"atol", "rtol"})
            if number(policy["atol"]) < 0 or number(policy["rtol"]) < 0:
                raise ValueError("Comparison tolerances must be nonnegative")
        for name, suite in self._suites.items():
            identifier(name)
            keys(suite, {"inputs", "checks"})
            declared = {}
            for alias, item in suite["inputs"].items():
                keys(item, {"schema", "comparison_policy"})
                policy = item["comparison_policy"]
                if item["schema"] == "ciw.comparison.v1":
                    if policy not in self._policies:
                        raise ValueError("Comparison check requires a fixed host policy")
                elif policy is not None:
                    raise ValueError("Non-comparison input cannot select comparison policy")
                declared[alias] = {"schema": item["schema"], "sha256": "sha256:" + "0" * 64}
            validate_plan(plan(name, inputs=declared, checks=suite["checks"]))
        if type(inputs) is not dict or len(inputs) > 64:
            raise ValueError("At most 64 explicit input bindings")
        for alias, raw in inputs.items():
            identifier(alias)
            if alias.startswith("a-"):
                raise ValueError("Input aliases cannot use the reserved artifact-handle prefix")
            value = parse(raw)
            _validated(value)
            self._aliases[alias] = self._put(raw)
        for baseline, domains in (candidate_domains or {}).items():
            handle = self._resolve(baseline)
            graph = self._get(handle)
            plan_graph(graph, registry)
            nodes = {node["node_id"]: node for node in graph["nodes"]}
            if type(domains) is not dict or not domains or set(domains) - set(nodes):
                raise ValueError("Candidate domains must address declared baseline nodes")
            compiled = {}
            for node_id, domain in domains.items():
                space = ParameterSpace.from_dict(domain)
                names = set(space.to_dict()["parameters"])
                if not names <= nodes[node_id]["parameters"].keys():
                    raise ValueError("Candidate domain cannot introduce a parameter")
                space.validate({k: nodes[node_id]["parameters"][k] for k in names})
                compiled[node_id] = space.to_dict()
            self._domains[handle] = compiled
        self._policy_bytes = encode({"catalog": parse(self._catalog),
            "allowed_operations": sorted(self._allow), "candidate_domains": self._domains,
            "comparison_policies": self._policies, "check_suites": self._suites,
            "max_executions": self._maximum, "max_nodes": self._max_nodes})
        self._host_policy = bytes_ref(self._policy_bytes)
        if output_dir is not None:
            # The operator supplies this path before serving; requests supply no paths.
            target = Path(output_dir).expanduser().absolute()
            if any(parent.is_symlink() for parent in (target, *target.parents)):
                raise ValueError("Output path must not traverse symbolic links")
            target.mkdir(parents=False, exist_ok=False)
            self._output = target.resolve(strict=True)
            self._output_stat = (self._output.stat().st_dev, self._output.stat().st_ino)
        if self._allow and self._output is None:
            raise ValueError("Executable access requires a fresh operator-owned output directory")

    def _put(self, raw: bytes, *, generated: bool = False) -> str:
        parse(raw)
        key = "a-" + sha256(raw).hexdigest()
        if key not in self._artifacts:
            if len(self._artifacts) >= MAX_ARTIFACTS or self._bytes + len(raw) > MAX_TOTAL:
                raise ValueError("Artifact budget exhausted; no existing artifact was discarded")
            self._artifacts[key] = raw
            self._bytes += len(raw)
        if generated:
            self._generated.add(key)
        return key

    def _resolve(self, name: str) -> str:
        identifier(name)
        key = self._aliases.get(name, name)
        if key not in self._artifacts:
            raise ValueError("Unknown host-bound artifact")
        return key

    def _get(self, name: str) -> dict:
        return parse(self._artifacts[self._resolve(name)])

    def _binding(self, name: str) -> dict:
        key = self._resolve(name)
        value = self._get(key)
        return {"artifact_id": key, "sha256": bytes_ref(self._artifacts[key]),
                "schema": value.get("schema", "workspace" if "workspace_version" in value else "run.v1"),
                "size_bytes": len(self._artifacts[key])}

    def _check_output(self) -> Path:
        if self._output is None:
            raise ValueError("This host is read-only; output capability was not granted")
        path = self._output
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("Output path changed to a symbolic link")
        current = path.stat()
        if (current.st_dev, current.st_ino) != self._output_stat:
            raise ValueError("Output directory identity changed")
        return path

    def _retain(self, value: dict) -> dict:
        root = self._check_output()
        raw = encode(value)
        key = "a-" + sha256(raw).hexdigest()
        # Same immutable result may be returned without overwriting it.
        path = root / (key + ".json")
        if key not in self._artifacts and (len(self._artifacts) >= MAX_ARTIFACTS or self._bytes + len(raw) > MAX_TOTAL):
            raise ValueError("Artifact budget exhausted before retention")
        if key not in self._generated:
            with path.open("xb") as stream:
                stream.write(raw)
        key = self._put(raw, generated=True)
        return self._binding(key)

    def capabilities(self) -> dict:
        catalog = parse(self._catalog)
        for op, value in catalog["operations"].items():
            value["agent_execution_enabled"] = op in self._allow
        return {"catalog": catalog, "inputs": {k: self._binding(v) for k, v in self._aliases.items()},
            "retained_artifacts": [self._binding(k) for k in sorted(self._generated)],
            "host_policy_sha256": self._host_policy, "host_policy": parse(self._policy_bytes),
            "candidate_domains": deepcopy(self._domains), "comparison_policies": deepcopy(self._policies),
            "check_suites": deepcopy(self._suites), "output_enabled": self._output is not None,
            "execution_budget": {"used": len(self._attempts), "maximum": self._maximum,
                                 "max_nodes_per_graph": self._max_nodes},
            "authority": deepcopy(AUTHORITY)}

    def inspect(self, artifact: str, selector: list | None = None, offset: int = 0, limit: int = 32) -> dict:
        key = self._resolve(artifact)
        value = self._get(key)
        # External workspaces are validated without executing providers.
        if "workspace_version" in value:
            value = _validated(value)
        selector = [] if selector is None else selector
        if type(selector) is not list or len(selector) > 12:
            raise ValueError("Selector must contain at most 12 object keys/array indices")
        for part in selector:
            if type(value) is dict and type(part) is str:
                value = value[part]
            elif type(value) is list and type(part) is int and 0 <= part < len(value):
                value = value[part]
            else:
                raise ValueError("Selector does not address the retained JSON value")
        _count(limit, 128)
        if type(offset) is not int or offset < 0:
            raise ValueError("Offset must be a nonnegative integer")
        next_offset = None
        if type(value) is list:
            total = len(value)
            value = value[offset:offset + limit]
            if offset + limit < total:
                next_offset = offset + limit
        elif offset:
            raise ValueError("Offset applies only to arrays")
        result = {"binding": self._binding(key), "selector": selector, "data": value,
                  "next_offset": next_offset, "source_text_is_untrusted_data": True}
        if len(encode(result)) > MAX_RESPONSE:
            raise ValueError("Selected data exceeds response budget; select a smaller field or page")
        return result

    def extract(self, artifact: str, selector: list) -> dict:
        """Retain one supported nested record, never an inferred telemetry projection."""
        inspected = self.inspect(artifact, selector)
        value = inspected["data"]
        if type(value) is not dict:
            raise ValueError("Extraction requires one complete supported record")
        _validated(value)
        return {"artifact": self._retain(value), "parent": self._binding(artifact),
                "selector": deepcopy(selector), "representation": "explicit_JSON_reserialization",
                "authority": deepcopy(AUTHORITY)}

    def source_context(self, artifact: str) -> dict:
        from .computational_source import source_context
        result = source_context(self._get(artifact))
        if len(encode(result)) > MAX_RESPONSE:
            raise ValueError("Source context exceeds response budget")
        return result

    def check_edit(self, artifact: str, candidate_utf8: str) -> dict:
        from .computational_source import check_edit
        if type(candidate_utf8) is not str:
            raise ValueError("Candidate source must be explicit UTF-8 text")
        return check_edit(self._get(artifact), candidate_utf8.encode("utf-8"))

    def candidate(self, baseline: str, changes: dict) -> dict:
        key = self._resolve(baseline)
        if key not in self._domains:
            raise ValueError("No operator-granted parameter domain for this baseline")
        domains = self._domains[key]
        if type(changes) is not dict or not changes or set(changes) - set(domains):
            raise ValueError("Candidate may change only explicitly permitted nodes")
        graph = self._get(key)
        nodes = deepcopy(graph["nodes"])
        for node in nodes:
            name = node["node_id"]
            if name not in changes:
                continue
            change = changes[name]
            space = ParameterSpace.from_dict(domains[name])
            allowed = set(space.to_dict()["parameters"])
            if type(change) is not dict or not change or set(change) - allowed:
                raise ValueError("Candidate parameter is outside the host edit scope")
            values = {k: node["parameters"][k] for k in allowed}
            values.update(change)
            space.validate(values)
            node["parameters"].update(change)
        proposed = experiment("candidate-" + sha256(encode([key, changes])).hexdigest()[:24],
            model_id=graph["model_id"], nodes=nodes, parameters=graph["parameters"],
            parent_checkpoint=graph["parent_checkpoint"])
        plan_graph(proposed, self._registry)
        binding = self._retain(proposed)
        self._domains[binding["artifact_id"]] = deepcopy(domains)
        return {"candidate": binding, "baseline": self._binding(key), "changes": deepcopy(changes),
                "executed": False, "authority": deepcopy(AUTHORITY)}

    def execute(self, source: str, graph: str, attempt: str) -> dict:
        root = self._check_output()
        identifier(attempt)
        source_key, graph_key = self._resolve(source), self._resolve(graph)
        request = {"source": self._binding(source_key), "experiment": self._binding(graph_key),
                   "host_policy_sha256": self._host_policy}
        if attempt in self._attempts:
            old = self._attempts[attempt]
            if old["request"] != request:
                raise ValueError("Attempt identifier already belongs to a different request")
            return {**deepcopy(old["response"]), "reused_response": True}
        if len(self._attempts) >= self._maximum:
            raise ValueError("Execution budget exhausted")
        value, run = self._get(graph_key), self._get(source_key)
        _validated(run)
        if "run_id" not in run or "channels" not in run:
            raise ValueError("Execution requires an explicitly bound source run, not a view or workspace")
        order = plan_graph(value, self._registry)
        if len(order) > self._max_nodes:
            raise ValueError("Experiment exceeds host node budget")
        for node in value["nodes"]:
            if node["operation_id"] not in self._allow:
                raise ValueError("Operation is not enabled for this agent")
            self._registry.operations.get(node["operation_id"])
        if encode(self._registry.catalog()) != self._catalog:
            raise ValueError("Registry changed after host policy was frozen")
        directory = root / attempt
        directory.mkdir(exist_ok=False)
        response = {"attempt": attempt, "status": "failed", "reused_response": False,
                    "artifacts": {}, "authority": deepcopy(AUTHORITY)}
        self._attempts[attempt] = {"request": request, "response": response}
        session = None
        try:
            save_new(directory / "request.json", request)
            save_new(directory / "experiment.json", value)
            session = Session(run, directory, operations=self._registry.operations)
            report = run_graph(session, value, self._registry)
            save_new(directory / "graph-run.json", report)
            session.save_workspace(directory / "workspace.json")
            for name in ("experiment", "graph-run", "workspace"):
                raw = (directory / (name + ".json")).read_bytes()
                handle = self._put(raw, generated=True)
                response["artifacts"][name] = self._binding(handle)
            response.update(status=report["status"], session_id=session.session_id,
                execution_ids=list(session.executions), result_ids=list(session.results))
        except Exception as exc:
            # The attempt is consumed even on failure. Never rerun it on transport retry.
            response["reason"] = type(exc).__name__ + ": " + str(exc)[:1000]
            if session is not None:
                try:
                    session.save_workspace(directory / "workspace.json")
                except Exception:
                    response["workspace_retention"] = "failed; inspect operator output directory"
        save_new(directory / "response.json", response)
        return deepcopy(response)

    def replay(self, original_attempt: str, new_attempt: str) -> dict:
        identifier(original_attempt)
        identifier(new_attempt)
        if new_attempt == original_attempt:
            raise ValueError("Replay requires a new attempt identifier")
        if original_attempt not in self._attempts:
            raise ValueError("Unknown attempt in this host process")
        source = self._attempts[original_attempt]["request"]
        return self.execute(source["source"]["artifact_id"], source["experiment"]["artifact_id"], new_attempt)

    def observe(self, artifact: str, offset: int = 0, limit: int = 32) -> dict:
        value = self._get(artifact)
        if value.get("schema") == "ciw.thermal-observation-view.v1":
            selector = ["stream", "observations"]
        elif value.get("schema") == "ciw.observation-stream.v1":
            selector = ["observations"]
        else:
            raise ValueError("Observe requires retained typed observations, not an invented projection")
        inspect_record(value)
        return self.inspect(artifact, selector, offset, limit)

    def compare(self, left: str, right: str, policy: str) -> dict:
        identifier(policy)
        if policy not in self._policies:
            raise ValueError("Comparison policy was not granted by the operator")
        values = [self._get(left), self._get(right)]
        streams = []
        for value in values:
            inspect_record(value)
            if value["schema"] == "ciw.thermal-observation-view.v1":
                streams.append(value["stream"]["observations"])
            elif value["schema"] == "ciw.observation-stream.v1":
                streams.append(value["observations"])
            else:
                raise ValueError("Comparison requires typed observation streams")
        result = compare(*streams, **self._policies[policy])
        return {"comparison": self._retain(result), "outcome": result["outcome"],
                "policy": policy, "authority": deepcopy(AUTHORITY)}

    def qualify(self, suite: str, inputs: dict) -> dict:
        identifier(suite)
        if suite not in self._suites:
            raise ValueError("Qualification suite is not an operator-bound policy")
        spec = self._suites[suite]
        if type(inputs) is not dict or set(inputs) - set(spec["inputs"]):
            raise ValueError("Unexpected qualification input alias")
        expected, supplied = {}, {}
        for alias, item in spec["inputs"].items():
            key = self._resolve(inputs[alias]) if alias in inputs else None
            raw = self._artifacts[key] if key else None
            if key:
                value = parse(raw)
                if value.get("schema") != item["schema"]:
                    raise ValueError("Qualification input schema mismatch")
                if item["comparison_policy"] is not None:
                    if value["policy"] != self._policies[item["comparison_policy"]]:
                        raise ValueError("Comparison policy differs from the fixed qualification policy")
            expected[alias] = {"schema": item["schema"], "sha256": bytes_ref(raw) if raw else "sha256:" + "0" * 64}
            supplied[alias] = raw
        result = evaluate(plan(suite, inputs=expected, checks=spec["checks"]), supplied)
        return {"report": self._retain(result), "summary": result["summary"],
                "host_policy_sha256": self._host_policy, "authority": deepcopy(AUTHORITY)}

    def call(self, name: str, arguments: dict) -> dict:
        """One serialized controller call; response values never share live objects."""
        from .agent_tools import TOOLS, validate_arguments
        validate_arguments(name, arguments)
        with self._lock:
            method = TOOLS[name]["method"]
            result = getattr(self, method)(**deepcopy(arguments))
            if len(encode(result)) > MAX_RESPONSE:
                raise ValueError("Response exceeds budget; retained results remain in the output directory")
            return deepcopy(result)
