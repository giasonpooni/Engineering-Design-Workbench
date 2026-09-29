"""Backend-neutral Container / Experiment Calculus V1.

A NET container is a typed computational boundary above implementation runtimes.
It describes state partitions, admitted/emitted ports, semantic operators, resource
capacity, evidence policy and telemetry requirements. It does not replace Docker,
workcells, Session, semantic capabilities or execution providers.

Transport byte counts are never silently treated as Shannon information. Likewise,
this contract does not assert a Free Energy Principle interpretation or a new
physical theory.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math
import re
from typing import Any

from .control_contracts import content_ref, detached, keys, record, text
from .operations.runner import check_seal

CAPABILITY = re.compile(r"[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*$")
BEHAVIORS = {"SINK", "SOURCE", "BUFFER", "FILTER", "TRANSFORMER", "CONTROLLER", "OBSERVER", "BOUNDARY"}
RELATIONS = {"FLOW", "NESTED"}
BACKENDS = {"LOCAL", "CONTAINER", "HPC", "CLOUD", "EXTERNAL"}
OUTCOMES = {"COMPLETED", "FAILED", "TIMEOUT", "REFUSED"}
PROVENANCE = {"MEASURED", "PROVIDER_REPORTED", "HUMAN_LOGGED", "DECLARED", "UNKNOWN"}
UNCERTAINTY_KINDS = {
    "SHANNON_ENTROPY",
    "POSTERIOR_ENTROPY",
    "HYPOTHESIS_COUNT",
    "FEASIBLE_VOLUME",
    "CUSTOM",
}
RESOURCE_METRICS = {
    "wall_seconds": "seconds",
    "cpu_seconds": "seconds",
    "gpu_seconds": "seconds",
    "peak_ram_bytes": "bytes",
    "storage_read_bytes": "bytes",
    "storage_write_bytes": "bytes",
    "network_in_bytes": "bytes",
    "network_out_bytes": "bytes",
    "energy_joules": "joules",
    "cost_usd": "usd",
    "human_active_seconds": "seconds",
    "operation_calls": "count",
    "model_calls": "count",
}
MAX_LIST = 128


def _time(value: Any, label: str) -> str:
    value = text(value)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


def _nonnegative(value: Any, label: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise ValueError(f"{label} must be a finite nonnegative number")
    result = float(value)
    if not math.isfinite(result) or result < 0 or result > 1e18:
        raise ValueError(f"{label} must be a finite nonnegative number")
    return result


def _bounded_int(value: Any, label: str, maximum: int = 10**15) -> int:
    if type(value) is not int or isinstance(value, bool) or not 0 <= value <= maximum:
        raise ValueError(f"{label} must be a bounded nonnegative integer")
    return value


def _optional_limit(value: Any, label: str, *, integer: bool = False):
    if value is None:
        return None
    return _bounded_int(value, label) if integer else _nonnegative(value, label)


def _unique_text(values: Any, label: str, *, maximum: int = MAX_LIST) -> list[str]:
    if type(values) is not list or len(values) > maximum:
        raise ValueError(f"{label} must be a bounded list")
    result = [text(item) for item in values]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def _refs(values: Any, label: str) -> list[str]:
    if type(values) is not list or len(values) > MAX_LIST:
        raise ValueError(f"{label} must be a bounded list")
    result = [content_ref(item) for item in values]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result


def _capabilities(values: Any) -> list[str]:
    if type(values) is not list or len(values) > MAX_LIST:
        raise ValueError("operators must be a bounded list")
    result = []
    for value in values:
        if type(value) is not str or CAPABILITY.fullmatch(value) is None or len(value) > 160:
            raise ValueError("container operators must be versioned semantic capabilities")
        result.append(value)
    if len(result) != len(set(result)):
        raise ValueError("duplicate semantic operator")
    return result


def _port(value: Any) -> dict:
    keys(value, {"port_id", "schema", "unit", "frame", "required"})
    unit = value["unit"]
    frame = value["frame"]
    if unit is not None:
        unit = text(unit)
    if frame is not None:
        frame = text(frame)
    if type(value["required"]) is not bool:
        raise ValueError("port required must be boolean")
    return {
        "port_id": text(value["port_id"]),
        "schema": text(value["schema"]),
        "unit": unit,
        "frame": frame,
        "required": value["required"],
    }


def _ports(values: Any, label: str) -> list[dict]:
    if type(values) is not list or len(values) > MAX_LIST:
        raise ValueError(f"{label} must be a bounded list")
    result = [_port(item) for item in values]
    ids = [item["port_id"] for item in result]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} contains duplicate port IDs")
    return result


def _authority(value: Any) -> dict:
    keys(value, {"effects", "network", "hardware_actuation", "state_admission", "release"})
    result = {"effects": _unique_text(value["effects"], "authority effects")}
    for name in ("network", "hardware_actuation", "state_admission", "release"):
        if type(value[name]) is not bool:
            raise ValueError(f"authority.{name} must be boolean")
        result[name] = value[name]
    return result


def _state_partition(value: Any) -> dict:
    keys(value, {"internal_state_schemas", "boundary_state_schemas", "external_context_refs"})
    return {
        "internal_state_schemas": _unique_text(value["internal_state_schemas"], "internal state schemas"),
        "boundary_state_schemas": _unique_text(value["boundary_state_schemas"], "boundary state schemas"),
        "external_context_refs": _refs(value["external_context_refs"], "external context refs"),
    }


def _resource_envelope(value: Any) -> dict:
    keys(value, {
        "cpu_cores_max", "gpu_devices_max", "ram_bytes_max",
        "storage_bytes_max", "wall_seconds_max",
    })
    return {
        "cpu_cores_max": _optional_limit(value["cpu_cores_max"], "cpu_cores_max"),
        "gpu_devices_max": _optional_limit(value["gpu_devices_max"], "gpu_devices_max", integer=True),
        "ram_bytes_max": _optional_limit(value["ram_bytes_max"], "ram_bytes_max", integer=True),
        "storage_bytes_max": _optional_limit(value["storage_bytes_max"], "storage_bytes_max", integer=True),
        "wall_seconds_max": _optional_limit(value["wall_seconds_max"], "wall_seconds_max"),
    }


def _evidence_policy(value: Any) -> dict:
    keys(value, {"retain_inputs", "retain_outputs", "retain_telemetry", "required_evidence_refs"})
    for name in ("retain_inputs", "retain_outputs", "retain_telemetry"):
        if type(value[name]) is not bool:
            raise ValueError(f"evidence_policy.{name} must be boolean")
    return {
        "retain_inputs": value["retain_inputs"],
        "retain_outputs": value["retain_outputs"],
        "retain_telemetry": value["retain_telemetry"],
        "required_evidence_refs": _refs(value["required_evidence_refs"], "required evidence refs"),
    }


def _telemetry_policy(value: Any) -> dict:
    keys(value, {
        "required_resource_metrics",
        "required_uncertainty_proxies",
        "require_verified_output_refs",
    })
    metrics = _unique_text(value["required_resource_metrics"], "required resource metrics")
    if any(name not in RESOURCE_METRICS for name in metrics):
        raise ValueError("telemetry policy names an unknown resource metric")
    proxies = _unique_text(value["required_uncertainty_proxies"], "required uncertainty proxies")
    if type(value["require_verified_output_refs"]) is not bool:
        raise ValueError("require_verified_output_refs must be boolean")
    return {
        "required_resource_metrics": metrics,
        "required_uncertainty_proxies": proxies,
        "require_verified_output_refs": value["require_verified_output_refs"],
    }


def container_from_spec(spec: dict) -> dict:
    keys(spec, {
        "container_id", "purpose", "declared_behaviors", "state_partition",
        "boundary", "operators", "resource_envelope", "evidence_policy",
        "telemetry_policy",
    })
    boundary = spec["boundary"]
    keys(boundary, {"inputs", "outputs", "authority"})
    behaviors = _unique_text(spec["declared_behaviors"], "declared behaviors")
    if any(item not in BEHAVIORS for item in behaviors):
        raise ValueError("unknown declared container behavior")
    value = record(
        "container-spec",
        container_id=text(spec["container_id"]),
        purpose=text(spec["purpose"]),
        declared_behaviors=behaviors,
        state_partition=_state_partition(spec["state_partition"]),
        boundary={
            "inputs": _ports(boundary["inputs"], "boundary inputs"),
            "outputs": _ports(boundary["outputs"], "boundary outputs"),
            "authority": _authority(boundary["authority"]),
        },
        operators=_capabilities(spec["operators"]),
        resource_envelope=_resource_envelope(spec["resource_envelope"]),
        evidence_policy=_evidence_policy(spec["evidence_policy"]),
        telemetry_policy=_telemetry_policy(spec["telemetry_policy"]),
        claims={
            "data_level_container_definition": True,
            "executable_binding": False,
            "runtime_selected": False,
            "physical_theory_established": False,
            "fep_interpretation": False,
            "execution_authority": False,
        },
    )
    validate_container(value)
    return value


def validate_container(value: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "container_id", "purpose",
        "declared_behaviors", "state_partition", "boundary", "operators",
        "resource_envelope", "evidence_policy", "telemetry_policy", "claims",
    })
    if value["schema"] != "ciw.container-spec.v1":
        raise ValueError("Wrong container-spec schema")
    check_seal(value)
    text(value["container_id"]); text(value["purpose"])
    behaviors = _unique_text(value["declared_behaviors"], "declared behaviors")
    if any(item not in BEHAVIORS for item in behaviors):
        raise ValueError("unknown declared container behavior")
    _state_partition(value["state_partition"])
    keys(value["boundary"], {"inputs", "outputs", "authority"})
    _ports(value["boundary"]["inputs"], "boundary inputs")
    _ports(value["boundary"]["outputs"], "boundary outputs")
    _authority(value["boundary"]["authority"])
    _capabilities(value["operators"])
    _resource_envelope(value["resource_envelope"])
    _evidence_policy(value["evidence_policy"])
    _telemetry_policy(value["telemetry_policy"])
    expected_claims = {
        "data_level_container_definition": True,
        "executable_binding": False,
        "runtime_selected": False,
        "physical_theory_established": False,
        "fep_interpretation": False,
        "execution_authority": False,
    }
    if value["claims"] != expected_claims:
        raise ValueError("Container spec claims exceed descriptive authority")
    return detached(value)


def _port_map(values: list[dict]) -> dict[str, dict]:
    return {item["port_id"]: item for item in values}


def composition_from_spec(spec: dict) -> dict:
    keys(spec, {"composition_id", "containers", "relations"})
    if type(spec["containers"]) is not list or not 1 <= len(spec["containers"]) <= 256:
        raise ValueError("Composition requires 1..256 container specs")
    containers = [validate_container(item) for item in spec["containers"]]
    ids = [item["container_id"] for item in containers]
    if len(ids) != len(set(ids)):
        raise ValueError("Composition contains duplicate container IDs")
    nodes = [{
        "container_id": item["container_id"],
        "container_spec_ref": item["record_digest"],
        "inputs": deepcopy(item["boundary"]["inputs"]),
        "outputs": deepcopy(item["boundary"]["outputs"]),
    } for item in containers]
    container_map = {item["container_id"]: item for item in containers}

    if type(spec["relations"]) is not list or len(spec["relations"]) > 2048:
        raise ValueError("Composition relation count exceeds bound")
    relations = []
    seen = set()
    parent: dict[str, str] = {}
    for raw in spec["relations"]:
        keys(raw, {
            "relation_id", "kind", "source_container_id", "target_container_id",
            "source_port", "target_port",
        })
        relation_id = text(raw["relation_id"])
        if relation_id in seen:
            raise ValueError("Duplicate composition relation")
        seen.add(relation_id)
        if raw["kind"] not in RELATIONS:
            raise ValueError("Unknown composition relation")
        source = text(raw["source_container_id"])
        target = text(raw["target_container_id"])
        if source == target or source not in container_map or target not in container_map:
            raise ValueError("Composition relation has invalid endpoint")
        if raw["kind"] == "NESTED":
            if raw["source_port"] is not None or raw["target_port"] is not None:
                raise ValueError("Nested relation cannot name ports")
            if source in parent:
                raise ValueError("A child container can have only one direct parent in V1")
            parent[source] = target
        else:
            if raw["source_port"] is None or raw["target_port"] is None:
                raise ValueError("Flow relation requires source/target ports")
            source_port = text(raw["source_port"])
            target_port = text(raw["target_port"])
            outputs = _port_map(container_map[source]["boundary"]["outputs"])
            inputs = _port_map(container_map[target]["boundary"]["inputs"])
            if source_port not in outputs or target_port not in inputs:
                raise ValueError("Flow relation names an undeclared boundary port")
            out = outputs[source_port]
            inn = inputs[target_port]
            if (out["schema"], out["unit"], out["frame"]) != (inn["schema"], inn["unit"], inn["frame"]):
                raise ValueError("Flow relation requires exact schema/unit/frame compatibility")
        relations.append({
            "relation_id": relation_id,
            "kind": raw["kind"],
            "source_container_id": source,
            "target_container_id": target,
            "source_port": raw["source_port"],
            "target_port": raw["target_port"],
        })

    for child in parent:
        visited = set()
        current = child
        while current in parent:
            if current in visited:
                raise ValueError("Nested container hierarchy contains a cycle")
            visited.add(current)
            current = parent[current]

    value = record(
        "container-composition",
        composition_id=text(spec["composition_id"]),
        containers=nodes,
        relations=sorted(relations, key=lambda row: row["relation_id"]),
        claims={
            "composition_definition": True,
            "provider_execution": False,
            "state_admission": False,
            "physical_theory_established": False,
        },
    )
    validate_composition(value)
    return value


def validate_composition(value: dict) -> dict:
    keys(value, {"schema", "record_digest", "composition_id", "containers", "relations", "claims"})
    if value["schema"] != "ciw.container-composition.v1":
        raise ValueError("Wrong container-composition schema")
    check_seal(value)
    text(value["composition_id"])
    if type(value["containers"]) is not list or not 1 <= len(value["containers"]) <= 256:
        raise ValueError("Invalid composition container list")
    ids = []
    snapshots = {}
    for node in value["containers"]:
        keys(node, {"container_id", "container_spec_ref", "inputs", "outputs"})
        container_id = text(node["container_id"])
        ids.append(container_id)
        content_ref(node["container_spec_ref"])
        snapshots[container_id] = {
            "inputs": _ports(node["inputs"], "composition inputs"),
            "outputs": _ports(node["outputs"], "composition outputs"),
        }
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate composition container ID")
    if type(value["relations"]) is not list or len(value["relations"]) > 2048:
        raise ValueError("Invalid composition relation list")
    parent = {}
    relation_ids = set()
    for row in value["relations"]:
        keys(row, {
            "relation_id", "kind", "source_container_id", "target_container_id",
            "source_port", "target_port",
        })
        relation_id = text(row["relation_id"])
        if relation_id in relation_ids:
            raise ValueError("Duplicate composition relation")
        relation_ids.add(relation_id)
        if row["kind"] not in RELATIONS:
            raise ValueError("Unknown composition relation")
        source = text(row["source_container_id"]); target = text(row["target_container_id"])
        if source == target or source not in snapshots or target not in snapshots:
            raise ValueError("Invalid composition endpoint")
        if row["kind"] == "NESTED":
            if row["source_port"] is not None or row["target_port"] is not None:
                raise ValueError("Nested relation cannot name ports")
            if source in parent:
                raise ValueError("Multiple nested parents are not allowed")
            parent[source] = target
        else:
            if row["source_port"] is None or row["target_port"] is None:
                raise ValueError("Flow requires ports")
            out = _port_map(snapshots[source]["outputs"]).get(row["source_port"])
            inn = _port_map(snapshots[target]["inputs"]).get(row["target_port"])
            if out is None or inn is None:
                raise ValueError("Flow names missing port")
            if (out["schema"], out["unit"], out["frame"]) != (inn["schema"], inn["unit"], inn["frame"]):
                raise ValueError("Flow port contracts are incompatible")
    for child in parent:
        visited = set()
        current = child
        while current in parent:
            if current in visited:
                raise ValueError("Nested hierarchy contains a cycle")
            visited.add(current)
            current = parent[current]
    if value["claims"] != {
        "composition_definition": True,
        "provider_execution": False,
        "state_admission": False,
        "physical_theory_established": False,
    }:
        raise ValueError("Composition claims exceed descriptive authority")
    return detached(value)


def _measurement(value: Any, expected_unit: str) -> dict:
    keys(value, {"value", "unit", "provenance", "source_ref"})
    if value["unit"] != expected_unit:
        raise ValueError("Resource metric unit mismatch")
    if value["provenance"] not in PROVENANCE:
        raise ValueError("Unknown telemetry provenance")
    if value["provenance"] == "UNKNOWN":
        if value["value"] is not None or value["source_ref"] is not None:
            raise ValueError("Unknown telemetry metric must not carry value/source")
        return deepcopy(value)
    numeric = _nonnegative(value["value"], "resource metric")
    if expected_unit in {"bytes", "count"} and numeric != int(numeric):
        raise ValueError("Discrete resource metric must be an integer")
    if value["source_ref"] is None:
        raise ValueError("Known telemetry metric requires source reference")
    content_ref(value["source_ref"])
    return {
        "value": int(numeric) if expected_unit in {"bytes", "count"} else numeric,
        "unit": expected_unit,
        "provenance": value["provenance"],
        "source_ref": value["source_ref"],
    }


def _resource_metrics(value: Any) -> dict:
    if type(value) is not dict or set(value) != set(RESOURCE_METRICS):
        raise ValueError("Telemetry requires the complete V1 resource metric set")
    return {name: _measurement(value[name], unit) for name, unit in RESOURCE_METRICS.items()}


def _transport(value: Any) -> dict:
    keys(value, {
        "admitted_items", "admitted_bytes", "emitted_items", "emitted_bytes",
        "discarded_items", "discarded_bytes", "retained_state_bytes",
    })
    return {name: _bounded_int(value[name], f"transport.{name}") for name in value}


def _residuals(values: Any) -> list[dict]:
    if type(values) is not list or len(values) > MAX_LIST:
        raise ValueError("residuals must be a bounded list")
    result = []
    seen = set()
    for value in values:
        keys(value, {"name", "value", "unit", "source_ref"})
        name = text(value["name"])
        if name in seen:
            raise ValueError("Duplicate residual metric")
        seen.add(name)
        raw = value["value"]
        if type(raw) not in (int, float) or isinstance(raw, bool) or not math.isfinite(float(raw)) or abs(float(raw)) > 1e150:
            raise ValueError("Residual must be a finite bounded number")
        result.append({
            "name": name,
            "value": float(raw),
            "unit": text(value["unit"]),
            "source_ref": content_ref(value["source_ref"]),
        })
    return result


def _uncertainty(values: Any) -> list[dict]:
    if type(values) is not list or len(values) > MAX_LIST:
        raise ValueError("uncertainty_proxies must be a bounded list")
    result = []
    seen = set()
    for value in values:
        keys(value, {"proxy_id", "kind", "before", "after", "unit", "method_id", "source_ref"})
        proxy_id = text(value["proxy_id"])
        if proxy_id in seen:
            raise ValueError("Duplicate uncertainty proxy")
        seen.add(proxy_id)
        if value["kind"] not in UNCERTAINTY_KINDS:
            raise ValueError("Unknown uncertainty proxy kind")
        before = _nonnegative(value["before"], "uncertainty before")
        after = _nonnegative(value["after"], "uncertainty after")
        unit = text(value["unit"])
        if value["kind"] in {"SHANNON_ENTROPY", "POSTERIOR_ENTROPY"} and unit not in {"bits", "nats"}:
            raise ValueError("Entropy proxies must declare bits or nats")
        if value["kind"] == "HYPOTHESIS_COUNT" and (
            unit != "count" or before != int(before) or after != int(after)
        ):
            raise ValueError("Hypothesis-count proxy must use integer count units")
        result.append({
            "proxy_id": proxy_id,
            "kind": value["kind"],
            "before": int(before) if value["kind"] == "HYPOTHESIS_COUNT" else before,
            "after": int(after) if value["kind"] == "HYPOTHESIS_COUNT" else after,
            "unit": unit,
            "method_id": text(value["method_id"]),
            "source_ref": content_ref(value["source_ref"]),
        })
    return result


def _backend(value: Any) -> dict:
    keys(value, {"class", "id"})
    if value["class"] not in BACKENDS:
        raise ValueError("Unknown execution backend class")
    return {"class": value["class"], "id": text(value["id"])}


def telemetry_from_spec(spec: dict) -> dict:
    keys(spec, {
        "container_spec", "execution_ref", "occurrence_id", "parent_occurrence_ref",
        "backend", "started_at", "ended_at", "outcome", "transport",
        "resource_metrics", "residuals", "uncertainty_proxies",
        "retained_state_refs", "verified_output_refs", "notes",
    })
    container = validate_container(spec["container_spec"])
    started = _time(spec["started_at"], "started_at")
    ended = _time(spec["ended_at"], "ended_at")
    if datetime.fromisoformat(ended.replace("Z", "+00:00")) < datetime.fromisoformat(started.replace("Z", "+00:00")):
        raise ValueError("ended_at cannot precede started_at")
    if spec["outcome"] not in OUTCOMES:
        raise ValueError("Unknown container occurrence outcome")
    metrics = _resource_metrics(spec["resource_metrics"])
    uncertainty = _uncertainty(spec["uncertainty_proxies"])
    verified = _refs(spec["verified_output_refs"], "verified output refs")
    policy = container["telemetry_policy"]
    for required in policy["required_resource_metrics"]:
        if metrics[required]["value"] is None:
            raise ValueError(f"Required resource metric is unknown: {required}")
    proxy_ids = {item["proxy_id"] for item in uncertainty}
    if any(required not in proxy_ids for required in policy["required_uncertainty_proxies"]):
        raise ValueError("Required uncertainty proxy is missing")
    if policy["require_verified_output_refs"] and spec["outcome"] == "COMPLETED" and not verified:
        raise ValueError("Completed occurrence requires verified output refs by container policy")
    parent = spec["parent_occurrence_ref"]
    if parent is not None:
        parent = content_ref(parent)
    notes = spec["notes"]
    if type(notes) is not str or len(notes) > 4096:
        raise ValueError("notes must be bounded text")
    value = record(
        "container-telemetry",
        container_id=container["container_id"],
        container_spec_ref=container["record_digest"],
        execution_ref=content_ref(spec["execution_ref"]),
        occurrence_id=text(spec["occurrence_id"]),
        parent_occurrence_ref=parent,
        backend=_backend(spec["backend"]),
        started_at=started,
        ended_at=ended,
        outcome=spec["outcome"],
        transport=_transport(spec["transport"]),
        resource_metrics=metrics,
        residuals=_residuals(spec["residuals"]),
        uncertainty_proxies=uncertainty,
        retained_state_refs=_refs(spec["retained_state_refs"], "retained state refs"),
        verified_output_refs=verified,
        telemetry_policy_snapshot=deepcopy(policy),
        notes=notes,
        claims={
            "measured_container_occurrence": True,
            "shannon_information_inferred_from_bytes": False,
            "free_energy_interpretation": False,
            "physical_theory_established": False,
            "execution_authority": False,
        },
    )
    validate_telemetry(value)
    return value


def validate_telemetry(value: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "container_id", "container_spec_ref",
        "execution_ref", "occurrence_id", "parent_occurrence_ref", "backend",
        "started_at", "ended_at", "outcome", "transport", "resource_metrics",
        "residuals", "uncertainty_proxies", "retained_state_refs",
        "verified_output_refs", "telemetry_policy_snapshot", "notes", "claims",
    })
    if value["schema"] != "ciw.container-telemetry.v1":
        raise ValueError("Wrong container-telemetry schema")
    check_seal(value)
    text(value["container_id"]); content_ref(value["container_spec_ref"])
    content_ref(value["execution_ref"]); text(value["occurrence_id"])
    if value["parent_occurrence_ref"] is not None:
        content_ref(value["parent_occurrence_ref"])
    _backend(value["backend"])
    started = _time(value["started_at"], "started_at")
    ended = _time(value["ended_at"], "ended_at")
    if datetime.fromisoformat(ended.replace("Z", "+00:00")) < datetime.fromisoformat(started.replace("Z", "+00:00")):
        raise ValueError("ended_at cannot precede started_at")
    if value["outcome"] not in OUTCOMES:
        raise ValueError("Unknown occurrence outcome")
    _transport(value["transport"])
    metrics = _resource_metrics(value["resource_metrics"])
    _residuals(value["residuals"])
    uncertainty = _uncertainty(value["uncertainty_proxies"])
    _refs(value["retained_state_refs"], "retained state refs")
    verified = _refs(value["verified_output_refs"], "verified output refs")
    policy = _telemetry_policy(value["telemetry_policy_snapshot"])
    for required in policy["required_resource_metrics"]:
        if metrics[required]["value"] is None:
            raise ValueError("Required resource metric is unknown")
    proxy_ids = {item["proxy_id"] for item in uncertainty}
    if any(required not in proxy_ids for required in policy["required_uncertainty_proxies"]):
        raise ValueError("Required uncertainty proxy is missing")
    if policy["require_verified_output_refs"] and value["outcome"] == "COMPLETED" and not verified:
        raise ValueError("Completed occurrence requires verified outputs")
    if type(value["notes"]) is not str or len(value["notes"]) > 4096:
        raise ValueError("notes must be bounded text")
    if value["claims"] != {
        "measured_container_occurrence": True,
        "shannon_information_inferred_from_bytes": False,
        "free_energy_interpretation": False,
        "physical_theory_established": False,
        "execution_authority": False,
    }:
        raise ValueError("Container telemetry claims exceed measured occurrence scope")
    return detached(value)


def summarize_telemetry(value: dict) -> dict:
    value = validate_telemetry(value)
    transport = value["transport"]
    admitted = transport["admitted_bytes"]
    metrics = value["resource_metrics"]
    wall = metrics["wall_seconds"]["value"]
    cost = metrics["cost_usd"]["value"]
    verified_count = len(value["verified_output_refs"])
    reductions = [{
        "proxy_id": item["proxy_id"],
        "kind": item["kind"],
        "unit": item["unit"],
        "method_id": item["method_id"],
        "before": item["before"],
        "after": item["after"],
        "reduction": item["before"] - item["after"],
        "relative_reduction": None if item["before"] == 0 else (item["before"] - item["after"]) / item["before"],
    } for item in value["uncertainty_proxies"]]
    return {
        "schema": "ciw.container-telemetry-summary.v1",
        "record_digest": value["record_digest"],
        "container_id": value["container_id"],
        "backend": deepcopy(value["backend"]),
        "outcome": value["outcome"],
        "transport": {
            **deepcopy(transport),
            "emitted_over_admitted_bytes": None if admitted == 0 else transport["emitted_bytes"] / admitted,
            "discarded_over_admitted_bytes": None if admitted == 0 else transport["discarded_bytes"] / admitted,
            "retained_state_over_admitted_bytes": None if admitted == 0 else transport["retained_state_bytes"] / admitted,
            "interpretation": "byte accounting only; not Shannon information",
        },
        "uncertainty_reductions": reductions,
        "verified_output_count": verified_count,
        "verified_outputs_per_wall_second": None if wall in (None, 0) else verified_count / wall,
        "verified_outputs_per_cost_usd": None if cost in (None, 0) else verified_count / cost,
        "unknown_resource_metrics": sorted(
            name for name, row in metrics.items() if row["value"] is None),
        "claims": deepcopy(value["claims"]),
    }
