"""Provider-free validators for a bounded local-frame representation profile.

Validation checks shape, source binding and missingness, not numerical accuracy.
It never imports PROJ, resolves an asset, estimates state or executes a provider.
"""
from __future__ import annotations
from copy import deepcopy
import math
import re
from .adapters.protocol import InstrumentManifest
from .core.identities import content_identity, evidence_id, validate_evidence_identity
from .core.records import validate_run_structure

OPERATION = "gsc.local-frame.v1"
INSTRUMENT = "org.notationsystems.recorded-geodetic.v1"
SOURCE_FRAME = "WGS84:lon_deg,lat_deg,ellipsoidal_height_m"
SCHEMA = "ciw.local-frame-projection.v1"
MAX_SAMPLES = 4096
MAX_BYTES = 4 * 1024 * 1024
AUTHORITY = "representation_only"
CHANNELS = {"longitude": "deg", "latitude": "deg", "height": "m"}


def manifest():
    return InstrumentManifest(INSTRUMENT, role="record_only", inputs=("run.v1",),
        units=CHANNELS, frames=(SOURCE_FRAME,), supported_operations=(),
        normalization={"axis_order": "longitude_latitude_height", "height_reference": "WGS84_ellipsoidal"})


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Require finite JSON numbers, not booleans")
    return float(value)


def _position(value):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("Require a three-component coordinate")
    return [_number(v) for v in value]


def geodetic(value):
    lon, lat, height = _position(value)
    if not -180 <= lon <= 180 or not -90 <= lat <= 90 or not -1000 <= height <= 100_000:
        raise ValueError("Coordinates exceed the local-frame source profile")
    return [lon, lat, height]


def source(run):
    validate_run_structure(run)
    validate_evidence_identity(run)
    if (run["instrument"] != INSTRUMENT or run["metadata"]["coordinate_frame"] != SOURCE_FRAME
            or run["metadata"].get("manifest") != manifest().to_dict()
            or set(run["channels"]) != set(CHANNELS)):
        raise ValueError("Require the recorded-geodetic source profile")
    if not 1 <= len(run["time_s"]) <= MAX_SAMPLES:
        raise ValueError("Source exceeds 4096 samples")
    for key, unit in CHANNELS.items():
        if run["channels"][key]["unit"] != unit:
            raise ValueError("Source channel unit mismatch")
    spatial = run["metadata"].get("spatial")
    if not isinstance(spatial, dict) or set(spatial) != {"entity_id", "source_class", "height_reference"}:
        raise ValueError("Require explicit spatial entity, source class and height reference")
    if not isinstance(spatial["entity_id"], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}", spatial["entity_id"]):
        raise ValueError("Invalid stable entity identity")
    if spatial["source_class"] not in {"synthetic", "recorded"} or spatial["height_reference"] != "WGS84_ellipsoidal":
        raise ValueError("Source class and ellipsoidal height must be explicit")
    # Check present coordinates individually even when another coordinate is missing.
    limits = {"longitude": (-180, 180), "latitude": (-90, 90), "height": (-1000, 100_000)}
    for key, (low, high) in limits.items():
        if any(v is not None and not low <= _number(v) <= high for v in run["channels"][key]["values"]):
            raise ValueError("Source coordinate exceeds the declared range")
    return deepcopy(run)


def request(run, parameters, selection=None):
    source(run)
    if not isinstance(parameters, dict) or set(parameters) != {"origin", "interval_s", "channel"}:
        raise ValueError("Require origin and explicit captured selection only")
    origin = geodetic(parameters["origin"])
    interval = parameters["interval_s"]
    if (not isinstance(interval, list) or len(interval) != 2
            or not 0 <= _number(interval[0]) < _number(interval[1]) <= run["metadata"]["duration_s"]
            or parameters["channel"] not in CHANNELS):
        raise ValueError("Invalid projection selection")
    if selection is not None and any(parameters[k] != selection[k] for k in ("channel", "interval_s")):
        raise ValueError("Projection contradicts captured selection")
    indices = [i for i, t in enumerate(run["time_s"]) if interval[0] <= t < interval[1]]
    if not indices:
        raise ValueError("Projection interval contains no samples")
    samples = []
    for i in indices:
        point = [run["channels"][key]["values"][i] for key in CHANNELS]
        samples.append(None if any(v is None for v in point) else geodetic(point))
    return {"origin": origin, "samples": samples}, indices


def pipeline(origin):
    lon, lat, height = map(float, origin)
    return ("+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad "
            "+step +proj=cart +ellps=WGS84 +step +proj=topocentric +ellps=WGS84 "
            f"+lon_0={lon!r} +lat_0={lat!r} +h_0={height!r}")


def validate_payload(operation_id, data, run, parameters, selection):
    inputs, indices = request(run, parameters, selection)
    fields = {"schema", "origin", "positions_enu_m", "axes", "unit", "height_reference", "runtime",
              "uncertainty", "authority", "source_evidence_id", "sample_indices", "time_s", "entity_id", "frame_id"}
    if operation_id != OPERATION or not isinstance(data, dict) or set(data) != fields or data["schema"] != SCHEMA:
        raise ValueError("Invalid local-frame projection schema")
    geodetic(data["origin"])
    expected = {"origin": inputs["origin"], "axes": ["east", "north", "up"], "unit": "m",
        "height_reference": "WGS84_ellipsoidal", "authority": AUTHORITY,
        "uncertainty": {"status": "unavailable", "reason": "not_propagated"},
        "source_evidence_id": run["evidence_id"], "sample_indices": indices,
        "time_s": [run["time_s"][i] for i in indices], "entity_id": run["metadata"]["spatial"]["entity_id"],
        "frame_id": "local-enu:" + content_identity(inputs["origin"])}
    if any(data[key] != value for key, value in expected.items()):
        raise ValueError("Projection source, frame, authority or selection binding mismatch")
    if any(type(i) is not int for i in data["sample_indices"]) or any(type(t) not in (int, float) for t in data["time_s"]):
        raise ValueError("Sample indices and times must be numerical, not booleans")
    runtime = data["runtime"]
    if (not isinstance(runtime, dict) or set(runtime) != {"worker_version", "pyproj", "proj", "pipeline", "network_enabled"}
            or runtime["worker_version"] != "1" or runtime["pyproj"] != "3.7.2"
            or not isinstance(runtime["proj"], str) or not re.fullmatch(r"\d+\.\d+\.\d+", runtime["proj"])
            or runtime["pipeline"] != pipeline(inputs["origin"]) or runtime["network_enabled"] is not False):
        raise ValueError("Invalid declared PROJ runtime identity")
    points = data["positions_enu_m"]
    if not isinstance(points, list) or len(points) != len(indices):
        raise ValueError("Projection sample count mismatch")
    for src, point in zip(inputs["samples"], points):
        if src is None:
            if point is not None:
                raise ValueError("Missing coordinates must remain unavailable")
        elif point is None or math.hypot(*_position(point)) > 20_000:
            raise ValueError("Projected position missing or outside local-frame radius")


def demo_run():
    """Explicit synthetic inputs, including an incomplete position. Not GNSS data."""
    origin = [-79.7, 44.0, 250.0]
    lon, lat, height = origin
    run = {"run_schema": "run.v1", "run_id": "synthetic-geodetic-loop-v1", "instrument": INSTRUMENT,
        "metadata": {"duration_s": 6.0, "sample_count": 6, "coordinate_frame": SOURCE_FRAME,
            "provenance": {"source": "ciw.spatial-demo.v1", "kind": "synthetic", "observed": False},
            "spatial": {"entity_id": "demo:survey-probe", "source_class": "synthetic", "height_reference": "WGS84_ellipsoidal"},
            "manifest": manifest().to_dict()},
        "time_s": [0., 1., 2., 3., 4., 5.],
        "channels": {"longitude": {"unit": "deg", "values": [lon, lon+.0001, lon+.0002, None, lon+.0001, lon]},
                     "latitude": {"unit": "deg", "values": [lat, lat, lat+.0001, lat+.0002, lat+.0001, lat]},
                     "height": {"unit": "m", "values": [height, height+1, height+2, height+3, height+1, height]}},
        "render": {}}
    run["evidence_id"] = evidence_id(run)
    source(run)
    return run, origin
