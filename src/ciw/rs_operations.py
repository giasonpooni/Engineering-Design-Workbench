"""Thin, opt-in GSC raster operations on the existing NET registry and Session.

No GDAL/Rasterio imports, raster IO, NDVI implementation, ESM admission or globe.
The operator binds a pinned specialist checkout and an independently selected
scene-manifest digest; saved records never restore executable bindings.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
import re

from .adapters.protocol import AdapterRefusal, InstrumentManifest
from .adapters.subprocess import PinnedSubprocessAdapter
from .control_contracts import content_ref, detached, keys, number, text, observation, record
from .control_plane import CapabilityRegistry, experiment
from .operations.registry import Operation
from .operations.runner import check_seal, digest
from .spatial_requests import AUTHORITY, register_readers as spatial_readers

PROVIDER = "GSC.RS"
OPERATIONS = ("rs.scene.inspect.v1", "rs.index.ndvi.v1")
_REGISTERED = False
SPECIALIST_AUTHORITY = {"state_admission": "not_performed", "state_release": "not_performed",
                       "verification_id": None, "verification_status": "not_verified"}


def need(value: bool, code: str, message: str) -> None:
    if not value:
        raise AdapterRefusal(code, message)


def validate_request(operation_id: str, parameters: dict) -> None:
    need(operation_id in OPERATIONS, "rs_operation_unavailable", "Select a declared specialist operation")
    keys(parameters, {"bundle_ref", "request"}); content_ref(parameters["bundle_ref"])
    q = parameters["request"]; detached(q)
    keys(q, {"investigation_id", "room", "entity", "aoi_ref", "window", "quality"})
    text(q["investigation_id"]); content_ref(q["aoi_ref"])
    need(q["room"] in ("PAYLOAD", "TRADEWIND", "LANDSHARK"), "unknown_room", "Select an established room")
    keys(q["entity"], {"kind", "id"}); text(q["entity"]["id"])
    need(q["entity"]["kind"] in ("organization", "site", "shipment"), "person_yield", "Only industrial entities are supported")
    w = q["window"]
    need(type(w) is list and len(w) == 4 and all(type(v) is int and 0 <= v <= 40000 for v in w)
         and w[2] > 0 and w[3] > 0 and w[2]*w[3] <= 4096,
         "invalid_pixel_window", "Declare one bounded integer pixel window; no implicit clipping or resampling")
    need(q["quality"] in ("declared_mask", "none"), "unknown_mask_policy", "Select declared mask or explicit no masking")


def _payload(operation_id, data, run, parameters, selection):
    validate_request(operation_id, parameters)
    detached(data)
    keys(data, {"provider", "request_ref", "specialist_result", *AUTHORITY})
    need(data["provider"] == PROVIDER and data["request_ref"] == digest(parameters), "rs_binding_mismatch", "Result belongs to another request")
    need(all(type(data[k]) is type(v) and data[k] == v for k,v in AUTHORITY.items()), "rs_authority_escalation", "An RS result grants no NET admission or release")
    r = data["specialist_result"]
    keys(r, {"schema", "operation_id", "provider_execution_id", "runtime", "bundle_sha256", "item_sha256",
             "request_ref", "source", "scene", "grid", "grid_ref", "selection", "assets", "index", *SPECIALIST_AUTHORITY})
    need(r["schema"] == "gsc.rs-result.v1" and r["operation_id"] == operation_id
         and r["bundle_sha256"] == parameters["bundle_ref"] and r["request_ref"] == digest(parameters["request"]),
         "rs_binding_mismatch", "Specialist request/source mismatch")
    need(all(type(r[k]) is type(v) and r[k] == v for k,v in SPECIALIST_AUTHORITY.items()), "rs_authority_escalation", "Candidate computation is not ESM admission")
    need(re.fullmatch(r"gsc-rs-[0-9a-f]{32}", str(r["provider_execution_id"])) is not None,
         "rs_binding_mismatch", "Require a separate specialist occurrence")
    for k in ("item_sha256", "grid_ref"): content_ref(r[k])
    keys(r["runtime"], {"provider", "worker_sha256", "python", "numpy", "rasterio", "gdal", "proj"})
    need(r["runtime"]["provider"] == PROVIDER, "rs_binding_mismatch", "Wrong specialist")
    content_ref(r["runtime"]["worker_sha256"])
    for k in ("python", "numpy", "rasterio", "gdal", "proj"): text(r["runtime"][k])
    s = r["source"]
    keys(s, {"id", "knownAt", "license_posture", "license_ref", "lineage_refs", "collection_policy_ref",
             "radiometry_ref", "yield_class", "product_family"})
    text(s["id"]); text(s["knownAt"]); text(s["product_family"])
    need(s["yield_class"] in ("infrastructure", "land_cover"), "person_yield", "Source yield must stay industrial")
    need(s["license_posture"] in ("public_official", "licensed", "synthetic"), "license_posture_unresolved", "Missing license posture")
    for k in ("license_ref", "collection_policy_ref", "radiometry_ref"): content_ref(s[k])
    need(type(s["lineage_refs"]) is list and 1 <= len(s["lineage_refs"]) <= 16, "missing_provenance_source", "Missing lineage")
    for ref in s["lineage_refs"]: content_ref(ref)
    scene = r["scene"]
    keys(scene, {"scene_id", "collection", "platform", "instruments", "valid_time", "footprint", "footprint_crs",
                 "footprint_status", "scene_cloud_cover_percent", "cloud_cover_scope"})
    for k in ("scene_id", "collection", "platform"): text(scene[k])
    need(type(scene["instruments"]) is list and 1 <= len(scene["instruments"]) <= 256, "rs_output_invalid", "Missing sensor metadata")
    for instrument in scene["instruments"]: text(instrument)
    keys(scene["footprint"], {"type", "coordinates"})
    rings = scene["footprint"]["coordinates"]
    need(scene["footprint"]["type"] == "Polygon" and type(rings) is list and len(rings) == 1
         and type(rings[0]) is list and 4 <= len(rings[0]) <= 512, "rs_output_invalid", "Unsupported declared footprint")
    for xy in rings[0]:
        need(type(xy) is list and len(xy) == 2 and -180 <= number(xy[0]) <= 180 and -90 <= number(xy[1]) <= 90,
             "rs_output_invalid", "Malformed footprint coordinates")
    need(rings[0][0] == rings[0][-1], "rs_output_invalid", "Unclosed footprint")
    keys(scene["valid_time"], {"start", "end"})
    for t in (s["knownAt"], *scene["valid_time"].values()):
        stamp = datetime.fromisoformat(t.replace("Z", "+00:00"))
        need(stamp.utcoffset() is not None, "unresolved_time", "Provider timestamps require offsets")
    need(scene["footprint_crs"] == "OGC:CRS84" and scene["footprint_status"] == "declared_not_geometrically_verified"
         and scene["cloud_cover_scope"] == "scene_metadata_not_window_measurement", "rs_binding_mismatch", "Unsupported footprint/cloud interpretation")
    if scene["scene_cloud_cover_percent"] is not None:
        need(0 <= number(scene["scene_cloud_cover_percent"]) <= 100, "rs_output_invalid", "Cloud percentage outside range")
    keys(r["grid"], {"crs", "axis_order", "coordinate_epoch", "shape", "transform", "pixel_basis"})
    grid = r["grid"]
    need(type(grid["crs"]) is str and re.fullmatch(r"EPSG:32[67](?:0[1-9]|[1-5][0-9]|60)", grid["crs"]) is not None
         and grid["axis_order"] == ["easting", "northing"] and grid["coordinate_epoch"] is None
         and grid["pixel_basis"] in ("area", "point"), "rs_output_invalid", "Unsupported declared grid basis")
    need(type(grid["shape"]) is list and len(grid["shape"]) == 2 and all(type(v) is int and 0 < v <= 40000 for v in grid["shape"]),
         "rs_output_invalid", "Malformed raster shape")
    need(type(grid["transform"]) is list and len(grid["transform"]) == 6, "rs_output_invalid", "Malformed affine metadata")
    for v in grid["transform"]: number(v)
    need(r["grid_ref"] == digest(r["grid"]), "rs_binding_mismatch", "Grid reference mismatch")
    keys(r["selection"], {"window", "bounds_xy", "transform", "aoi_ref", "aoi_relation"})
    need(r["selection"]["window"] == parameters["request"]["window"] and r["selection"]["aoi_ref"] == parameters["request"]["aoi_ref"]
         and r["selection"]["aoi_relation"] == "operator_declared_pixel_window_not_polygon_intersection",
         "rs_binding_mismatch", "A pixel window does not assert polygon intersection")
    need(type(r["selection"]["bounds_xy"]) is list and len(r["selection"]["bounds_xy"]) == 4
         and type(r["selection"]["transform"]) is list and len(r["selection"]["transform"]) == 6,
         "rs_output_invalid", "Malformed selected grid metadata")
    for v in r["selection"]["bounds_xy"] + r["selection"]["transform"]: number(v)
    need(type(r["assets"]) is dict and 2 <= len(r["assets"]) <= 3, "rs_output_invalid", "Unexpected asset set")
    for asset in r["assets"].values():
        fields = {"dtype", "nodata", "tiff_scale", "tiff_offset", "cog_layout_marker", "cog_conformance", "block_shapes", "sha256"}
        if "radiometry_basis" in asset:
            fields |= {"scale", "offset", "unit", "radiometry_basis"}
            need(asset["radiometry_basis"] == "explicit_stac_raster_band" and asset["unit"] == "1",
                 "rs_output_invalid", "Unsupported radiometric basis")
            need(number(asset["scale"]) > 0, "rs_output_invalid", "Invalid scale")
            number(asset["offset"])
        keys(asset, fields)
        content_ref(asset["sha256"])
        need(asset.get("cog_conformance") == "not_certified" and type(asset.get("cog_layout_marker")) is bool,
             "rs_output_invalid", "A layout marker is not COG certification")
    index = r["index"]
    if operation_id == "rs.scene.inspect.v1":
        need(index is None, "rs_output_invalid", "Inspection cannot claim numerical NDVI execution")
        return
    keys(index, {"status", "quantity", "unit", "shape", "order", "values", "valid_count", "total_count", "excluded_counts",
                 "mean", "minimum", "maximum", "outside_unit_interval_count", "quality_mask", "formula", "clamped"})
    w = parameters["request"]["window"]
    need(type(index["total_count"]) is int and type(index["shape"]) is list
         and all(type(v) is int for v in index["shape"]) and index["shape"] == [w[3], w[2]] and index["total_count"] == w[2]*w[3] and index["order"] == "row_major"
         and index["quantity"] == "ndvi" and index["unit"] == "1" and index["clamped"] is False
         and index["formula"] == "(scaled_nir-scaled_red)/(scaled_nir+scaled_red)", "rs_output_invalid", "Unknown numerical representation")
    need(type(index["values"]) is list and len(index["values"]) == index["total_count"], "rs_output_invalid", "Incorrect window shape")
    for value in index["values"]:
        if value is not None: number(value)
    count = sum(v is not None for v in index["values"])
    need(type(index["valid_count"]) is int and index["valid_count"] == count and index["status"] == ("computed" if count else "insufficient_data"),
         "rs_output_invalid", "Missingness and status disagree")
    keys(index["excluded_counts"], {"nodata", "quality_mask", "nonfinite_input", "zero_denominator", "nonfinite_result"})
    need(all(type(v) is int and v >= 0 for v in index["excluded_counts"].values())
         and sum(index["excluded_counts"].values()) + count == index["total_count"], "rs_output_invalid", "Coverage accounting mismatch")
    need(type(index["outside_unit_interval_count"]) is int and 0 <= index["outside_unit_interval_count"] <= count,
         "rs_output_invalid", "Invalid out-of-range count")
    for k in ("mean", "minimum", "maximum"):
        if count: number(index[k])
        else: need(index[k] is None, "rs_output_invalid", "No-data summaries must remain null")
    if index["quality_mask"] is not None:
        keys(index["quality_mask"], {"keep_codes", "policy_ref"})
        content_ref(index["quality_mask"]["policy_ref"])
        need(type(index["quality_mask"]["keep_codes"]) is list and 1 <= len(index["quality_mask"]["keep_codes"]) <= 32
             and all(type(v) is int and 0 <= v <= 65535 for v in index["quality_mask"]["keep_codes"]), "rs_output_invalid", "Invalid mask policy")
    need((index["quality_mask"] is None) == (parameters["request"]["quality"] == "none"), "rs_binding_mismatch", "Mask policy changed")


def register_readers():
    global _REGISTERED
    if not _REGISTERED:
        from .operations.schemas import register_payload_validator
        for op in OPERATIONS: register_payload_validator(op, _payload)
        _REGISTERED = True


class RasterBinding:
    """Operator setup only: fixed source module, pinned checkout, pinned local bundle."""
    def __init__(self, repository_root: Path, revision: str, bundle: Path, bundle_sha256: str, *, python_executable=None):
        import sys
        self._bundle = str(Path(bundle).expanduser().absolute())
        self.bundle_ref = content_ref(bundle_sha256)
        self.adapter = PinnedSubprocessAdapter(repository_root, revision, "worker", source_root="tools/ciw-rs",
            python_executable=python_executable or sys.executable, timeout_seconds=30, max_output_bytes=1024*1024)
        self._specialist = detached(self.adapter.invoke("rs.runtime.v1", {}))
        need(self._specialist.get("provider") == PROVIDER, "rs_binding_mismatch", "Wrong bound runtime")

    def runtime_identity(self):
        return {"provider": PROVIDER, "adapter": self.adapter.runtime_identity(), "specialist": deepcopy(self._specialist), "bundle_ref": self.bundle_ref}

    def execute(self, operation_id, run, parameters):
        validate_request(operation_id, parameters)
        need(parameters["bundle_ref"] == self.bundle_ref, "rs_binding_mismatch", "Saved parameters cannot select a different input bundle")
        # The Session recording is deliberately NOT sent to the RS provider.
        output = self.adapter.invoke(operation_id, {"bundle_path": self._bundle, "bundle_sha256": self.bundle_ref,
                                                   "request": detached(parameters["request"])})
        need(output.get("runtime") == self._specialist, "rs_runtime_drift", "Specialist dependency or worker identity changed")
        return {"provider": PROVIDER, "request_ref": digest(parameters), "specialist_result": output, **AUTHORITY}


def add_rs_routes(registry: CapabilityRegistry, *, binding: RasterBinding | None = None):
    need(not set(OPERATIONS) & set(registry.catalog()["operations"]) and PROVIDER not in registry.catalog()["providers"],
         "rs_registration_conflict", "Existing routes cannot be replaced")
    register_readers()
    runtime = binding.runtime_identity() if binding else {"provider": PROVIDER, "status": "unbound_interface_target"}
    registry.advertise(InstrumentManifest(PROVIDER, version="local-scene-v1", role="adapter", inputs=("gsc.rs-scene.v1",),
        outputs=("ciw.operation-result.v1",), supported_operations=OPERATIONS,
        normalization={"implicit_reprojection": False, "implicit_resampling": False},
        calibration_requirements={"state_admission": "ESM_only"}), runtime=runtime,
        capabilities={op: ["gis_rs", "specialist_raster", "candidate_observation"] for op in OPERATIONS})
    if binding:
        for op in OPERATIONS:
            registry.bind(Operation(op, "backend", lambda run,p,op=op: binding.execute(op,run,p), binding.runtime_identity))


def make_plan(operation_id, parameters):
    validate_request(operation_id, parameters)
    return experiment(parameters["request"]["investigation_id"], model_id="gsc.rs-scene.v1",
        parameters=parameters, nodes=[{"node_id":"rs-request", "operation_id":operation_id,"parameters":{},"inputs":{},"depends_on":[]}])


def validate_result(result):
    check_seal(result)
    need(result.get("schema") == "ciw.operation-result.v1" and result.get("operation_id") in OPERATIONS
         and result.get("role") == "backend" and result.get("verification_id") is None and result.get("verification_status") == "not_verified",
         "rs_output_invalid", "Not an ordinary retained specialist result")
    _payload(result["operation_id"],result["data"],None,result["parameters"],None)
    need(result["runtime"]["specialist"] == result["data"]["specialist_result"]["runtime"]
         and result["runtime"]["bundle_ref"] == result["parameters"]["bundle_ref"], "rs_runtime_drift", "Retained runtime binding differs")


def open_workspace(path, *, output_dir):
    register_readers(); spatial_readers()
    from .session import Session
    session = Session.from_workspace(path,output_dir=output_dir)
    for r in session.results.values():
        if r.get("operation_id") in OPERATIONS: validate_result(r)
    return session


def mean_observations(result):
    """Structural projection only. No band arithmetic or invented time alignment."""
    validate_result(result)
    r = result["data"]["specialist_result"]
    need(r["index"] is not None, "rs_output_invalid", "Select an NDVI result, not metadata inspection")
    valid = r["scene"]["valid_time"]
    need(valid["start"] == valid["end"], "interval_observation", "An interval scene has no single instant; select a specialist temporal comparison")
    q = result["parameters"]["request"]; index=r["index"]
    frame = digest({"grid":r["grid_ref"], "window":q["window"], "aoi":q["aoi_ref"],
        "valid_support":[v is not None for v in index["values"]], "quality_policy":index["quality_mask"],
        "radiometry_ref":r["source"]["radiometry_ref"]})
    refs = [result["record_digest"],r["bundle_sha256"],r["item_sha256"],*[a["sha256"] for a in r["assets"].values()]]
    sample = observation(identity={"model_id":"gsc.ndvi.scaled.v1","entity_id":q["entity"]["id"],"execution_id":result["execution_id"]},
        clock={"id":"utc-posix-seconds", "time_s":datetime.fromisoformat(valid["start"].replace("Z","+00:00")).timestamp()},
        frame="rs-window:"+frame.split(":")[1], quantity="ndvi.window_mean", value=index["mean"],unit="1",
        provenance={"provider":PROVIDER,"sources":list(dict.fromkeys(refs)),
                    "semantics":"simulated" if r["source"]["license_posture"] == "synthetic" else "estimated"})
    return record("observation-stream",observations=[sample])
