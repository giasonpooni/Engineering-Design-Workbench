"""Thin GIS/RS requests over NET's existing registry, graphs and Session.

No raster reader, CRS resolver, numerical engine, evidence store or view renderer.
These fields are declarations; specialist adapters validate referenced source,
licence, admission and release records. A content reference is not authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .adapters.protocol import AdapterRefusal, InstrumentManifest
from .control_contracts import content_ref, detached, keys, number, text
from .control_plane import CapabilityRegistry, experiment
from .operations.registry import Operation
from .operations.runner import digest

# Public workbench verbs map to versioned CIW operation identities. These are
# targets, not assertions that a deployment or executable adapter is installed.
ROUTES = {
    "spatial.map": ("GSC", "representation_reference"),
    "spatial.inspect": ("GSV", "read_only_view_reference"),
    "rs.scene.admit": ("PPDA+ESM", "admission_outcome_reference"),
}
ROOMS = frozenset({"PAYLOAD", "TRADEWIND", "LANDSHARK"})
LICENSES = frozenset({"public_official", "licensed", "synthetic"})
AUTHORITY = {"state_admission_by_net": False, "state_release_by_net": False,
             "verification_id": None, "verification_status": "not_verified"}
FIELDS = {"investigation_id", "room", "entity", "aoi", "crs", "geometry_basis_ref",
          "scene", "time_window", "license_posture", "license_ref", "sources",
          "governance", "collection"}
_REGISTERED = False


def refuse(code: str, message: str) -> None:
    raise AdapterRefusal(code, message)


def need(condition: bool, code: str, message: str) -> None:
    if not condition:
        refuse(code, message)


def _time(value) -> datetime:
    text(value)
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
        return stamp
    except ValueError as exc:
        raise AdapterRefusal("unresolved_time", "Declare an ISO timestamp with an explicit offset") from exc


def _window(value) -> None:
    keys(value, {"start", "end"})
    need(_time(value["start"]) <= _time(value["end"]), "invalid_time_window", "Time window is reversed")


def _crs(value) -> None:
    try:
        keys(value, {"id", "definition_ref", "datum_ref", "axis_order", "coordinate_epoch"})
        text(value["id"])
        content_ref(value["definition_ref"])
        content_ref(value["datum_ref"])
        axes = value["axis_order"]
        if type(axes) is not list or not 2 <= len(axes) <= 3:
            raise ValueError
        for axis in axes:
            text(axis)
        if len(set(axes)) != len(axes):
            raise ValueError
        if value["coordinate_epoch"] is not None:
            number(value["coordinate_epoch"])
    except (ValueError, TypeError) as exc:
        raise AdapterRefusal("unresolved_crs", "Declare CRS definition, datum, axis order and epoch (or explicit null)") from exc


def validate_request(operation: str, fields: dict) -> None:
    """Check declared compatibility only; never inspect pixels or infer a datum."""
    need(type(operation) is str and operation in ROUTES, "spatial_operation_unavailable", "Select an installed GIS/RS request route")
    detached(fields)
    if type(fields) is dict and "crs" not in fields:
        refuse("unresolved_crs", "The request must declare its CRS")
    keys(fields, FIELDS)
    text(fields["investigation_id"])
    need(type(fields["room"]) is str and fields["room"] in ROOMS, "unknown_room", "Use PAYLOAD, TRADEWIND or LANDSHARK")
    keys(fields["entity"], {"kind", "id"})
    need(fields["entity"]["kind"] in ("organization", "site", "shipment"), "person_yield", "This route observes organizations, sites and shipments, not people")
    text(fields["entity"]["id"])
    keys(fields["collection"], {"subject", "product"})
    need(fields["collection"]["subject"] in ("infrastructure", "land_cover"), "person_yield", "Declare infrastructure or land-cover yield; unknown/person yield refuses")
    need(fields["collection"]["product"] == "entity_observation", "geofence_product", "AOI selection is permitted; geofence products are not")
    keys(fields["aoi"], {"geometry_ref"})
    content_ref(fields["aoi"]["geometry_ref"])
    _crs(fields["crs"])
    content_ref(fields["geometry_basis_ref"])
    _window(fields["time_window"])
    need(type(fields["license_posture"]) is str and fields["license_posture"] in LICENSES, "license_posture_unresolved", "Declare public_official, licensed or synthetic")
    # A licence reference names the operator's evidence, not a legal conclusion.
    try:
        content_ref(fields["license_ref"])
    except ValueError as exc:
        raise AdapterRefusal("license_posture_unresolved", "Licence posture needs a source reference") from exc
    scene = fields["scene"]
    if scene is not None:
        keys(scene, {"scene_id", "sensor", "product_family"})
        for value in scene.values():
            text(value)
    sources = fields["sources"]
    need(type(sources) is list and 1 <= len(sources) <= 16, "missing_provenance_source", "Select 1..16 explicitly sourced references")
    pixels, grids, seen = set(), set(), set()
    for source in sources:
        if type(source) is not dict or type(source.get("provenance")) is not dict:
            refuse("missing_provenance_source", "Each input needs provenance.source")
        try:
            text(source["provenance"].get("source"))
        except ValueError as exc:
            raise AdapterRefusal("missing_provenance_source", "Each input needs provenance.source") from exc
        if "crs" not in source:
            refuse("unresolved_crs", "Each input must declare its CRS")
        keys(source, {"ref", "kind", "provenance", "knownAt", "valid_time", "crs",
                      "geometry_basis_ref", "pixel_basis", "grid_ref", "yield_class"})
        keys(source["provenance"], {"source"})
        ref = content_ref(source["ref"])
        need(ref not in seen, "duplicate_source", "Select each source reference once")
        seen.add(ref)
        need(source["kind"] in ("scene", "raster", "footprint", "admitted_state", "released_snapshot"), "invalid_source_kind", "Unsupported source kind")
        need(source["yield_class"] in ("infrastructure", "land_cover"), "person_yield", "Person-yield and unclassified inputs are refused")
        _time(source["knownAt"])
        _window(source["valid_time"])
        _crs(source["crs"])
        need(all(source["crs"][key] == fields["crs"][key] for key in ("datum_ref", "coordinate_epoch")),
             "implicit_datum_shift", "Datum/epoch conversion requires a separately declared specialist operation")
        need(source["crs"] == fields["crs"], "mixed_crs_basis", "Resolve CRS and axis differences explicitly; NET does not reproject")
        need(content_ref(source["geometry_basis_ref"]) == fields["geometry_basis_ref"], "mixed_geometry_basis", "Mixed geometry bases require explicit specialist reconciliation")
        pixel = source["pixel_basis"]
        need(pixel in ("area", "point", "not_applicable"), "mixed_pixel_basis", "Pixel basis must be explicit")
        if source["kind"] in ("scene", "raster"):
            need(pixel != "not_applicable", "mixed_pixel_basis", "Raster/scene inputs need a pixel basis")
        if pixel == "not_applicable":
            need(source["grid_ref"] is None, "mixed_pixel_basis", "Non-pixel data cannot silently carry a raster grid")
        else:
            content_ref(source["grid_ref"])
            pixels.add(pixel)
            grids.add(source["grid_ref"])
    need(len(pixels) <= 1, "mixed_pixel_basis", "Area and point pixels cannot be silently combined")
    need(len(grids) <= 1, "mixed_grid_basis", "Different raster grids need a separately declared resampling operation")
    governance = fields["governance"]
    keys(governance, {"esm_admission_ref", "admitted_state_ref", "esm_release_ref", "released_snapshot_ref"})
    for value in governance.values():
        if value is not None:
            content_ref(value)
    if operation == "spatial.map":
        need(governance["esm_admission_ref"] is not None and governance["admitted_state_ref"] is not None,
             "esm_admission_required", "GSC mapping selects ESM-admitted state, not a raw GeoTIFF")
        need(len(sources) == 1 and sources[0]["ref"] == governance["admitted_state_ref"]
             and sources[0]["kind"] == "admitted_state",
             "admission_source_mismatch", "Map one admitted state reference; extra raw inputs need ESM admission first")
    elif operation == "spatial.inspect":
        need(governance["esm_release_ref"] is not None and governance["released_snapshot_ref"] is not None,
             "released_snapshot_required", "GSV projects only an explicitly released snapshot")
        need(len(sources) == 1 and sources[0]["kind"] == "released_snapshot"
             and sources[0]["ref"] == governance["released_snapshot_ref"],
             "release_source_mismatch", "The view receives one released snapshot, not extra unreleased layers")
    else:
        need(scene is not None and all(s["kind"] in ("scene", "raster") for s in sources),
             "scene_required", "Scene admission needs explicit scene/sensor/product metadata and candidate scene references")
        need(all(v is None for v in governance.values()), "candidate_not_canonical", "Submit candidates through PPDA+ESM; NET cannot label them admitted")


def make_plan(operation: str, fields: dict, *, model_id: str) -> dict:
    """Use the existing sealed experiment/DAG record; no new investigation store."""
    validate_request(operation, fields)
    return experiment(fields["investigation_id"], model_id=model_id,
        nodes=[{"node_id": "spatial-request", "operation_id": operation + ".v1",
                "parameters": {}, "inputs": {}, "depends_on": []}],
        parameters={"spatial": detached(fields)})


@dataclass(frozen=True)
class ProviderBinding:
    """Explicit installed adapter; neither a profile nor a saved record loads it.

    invoke returns only output_ref and provider_execution_ref. For GSV the
    callable must implement projection only. Specialist code enforces actual
    ESM/PPDA/source/licence records; metadata checks here do not authenticate them.
    """
    invoke: Callable[[str, dict], dict]
    runtime_identity: Callable[[], dict]


def _payload(operation_id, data, run, parameters, selection):
    alias = operation_id.removesuffix(".v1")
    keys(parameters, {"spatial"})
    validate_request(alias, parameters["spatial"])
    keys(data, {"provider", "output_kind", "request_ref", "output_ref", "provider_execution_ref", *AUTHORITY})
    need(data["provider"] == ROUTES[alias][0] and data["output_kind"] == ROUTES[alias][1], "spatial_output_mismatch", "Result contradicts the provider route")
    need(data["request_ref"] == digest(parameters), "spatial_output_mismatch", "Result is bound to another request")
    for key in ("output_ref", "provider_execution_ref"):
        content_ref(data[key])
    need(all(type(data[k]) is type(v) and data[k] == v for k, v in AUTHORITY.items()),
         "spatial_authority_escalation", "NET references provider outcomes; it cannot grant admission, release or verification")


def register_readers() -> None:
    global _REGISTERED
    if not _REGISTERED:
        from .operations.schemas import register_payload_validator
        for alias in ROUTES:
            register_payload_validator(alias + ".v1", _payload)
        _REGISTERED = True


def add_spatial_routes(registry: CapabilityRegistry, *, bindings: dict[str, ProviderBinding] | None = None) -> None:
    """Add names to the original catalog; no adapters are bound by default."""
    bindings = {} if bindings is None else dict(bindings)
    need(not set(bindings) - set(ROUTES), "spatial_operation_unavailable", "Only the three declared routes can be bound")
    current = registry.catalog()
    need(not {name + ".v1" for name in ROUTES} & set(current["operations"])
         and not {target for target, _ in ROUTES.values()} & set(current["providers"]),
         "spatial_registration_conflict", "Existing provider/operation registrations are never replaced")
    # Resolve all supplied identities before changing the registry.
    prepared = {}
    for alias, binding in bindings.items():
        need(isinstance(binding, ProviderBinding) and callable(binding.invoke) and callable(binding.runtime_identity),
             "invalid_spatial_binding", "Supply a trusted adapter object, not a path or saved executable name")
        runtime = detached(binding.runtime_identity())
        need(type(runtime) is dict and runtime.get("provider") == ROUTES[alias][0]
             and type(runtime.get("implementation_ref")) is str,
             "invalid_spatial_binding", "Bind the declared provider with an explicit implementation reference")
        content_ref(runtime["implementation_ref"])
        prepared[alias] = runtime
    register_readers()
    for alias, (target, output_kind) in ROUTES.items():
        operation_id = alias + ".v1"
        runtime = prepared.get(alias, {"provider": target, "status": "unbound_interface_target", "interface_version": "1"})
        registry.advertise(InstrumentManifest(target, version="request-interface-v1", role="view" if target == "GSV" else "adapter",
            inputs=("ciw.experiment.v1",), outputs=("ciw.operation-result.v1",), supported_operations=(operation_id,),
            normalization={"implicit_crs_conversion": False, "implicit_resampling": False},
            calibration_requirements={"admission_authority": "ESM", "provider_validates_references": True}),
            runtime=runtime, capabilities={operation_id: [alias, "gis_rs", "read_only" if target == "GSV" else "provider_dispatch"]})
        if alias not in bindings:
            continue
        binding = bindings[alias]
        def execute(run, parameters, name=alias, bound=binding, owner=target, kind=output_kind):
            keys(parameters, {"spatial"})
            fields = detached(parameters["spatial"])
            validate_request(name, fields)
            # Never send Session recording arrays as if they were scene pixels.
            result = detached(bound.invoke(name, fields))
            keys(result, {"output_ref", "provider_execution_ref"})
            return {"provider": owner, "output_kind": kind, "request_ref": digest(parameters), **result, **AUTHORITY}
        registry.bind(Operation(operation_id, "backend", execute, binding.runtime_identity))


def open_spatial_workspace(path, *, output_dir):
    """Trusted readers only. No provider bindings are reconstructed from files."""
    register_readers()
    from .session import Session
    session = Session.from_workspace(path, output_dir=output_dir)
    for result in session.results.values():
        if result.get("operation_id") in {alias + ".v1" for alias in ROUTES}:
            need(result["role"] == "backend", "spatial_output_mismatch", "A request result cannot change its operation role")
    return session
