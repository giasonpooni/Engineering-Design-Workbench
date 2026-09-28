"""Data-only image evidence for selected retained simulation observations.

The full source result remains privileged evidence. Only its selected XYZ
observations enter the renderer. Image creation is a new execution, never a new
simulation observation, a checkpoint restore or a verification occurrence.
"""
from __future__ import annotations

from copy import deepcopy
import re
import struct
import zlib

from .control_contracts import (
    artifact, bytes_ref, content_ref, detached, keys, number, text, validate_artifact,
)
from .operations.runner import check_seal, digest
from .simulation_records import packed, require, unpack, validate_observation
from .simulation_replay import validate_result as validate_simulation_result

OPERATION = "simulation.observation-capture.v1"
CHANNELS = ["position_x", "position_y", "position_z"]
FRAME = "godot/y-up/metres"
MODEL = "godot-point-projectile.v1"
PROVIDER = "godot.point-projectile"
WIDTH, HEIGHT = 1280, 800
MAX_IMAGE = 4 * 1024 * 1024
VIEW_SCOPE = "derived image of selected observations; not a live camera or world-truth observation"
AUTHORITY = {"verification_id": None, "verification_status": "not_verified", "state_admission": "not_performed"}
_REGISTERED = False


def selection(source: dict, *, entity_id: str, sample_index: int | None, camera: str = "oblique",
              source_workspace_sha256: str | None = None) -> dict:
    value = {"source_result_id": source["result_id"], "source_result_ref": source["record_digest"],
             "entity_id": entity_id, "sample_index": sample_index, "camera": camera,
             "source_workspace_sha256": source_workspace_sha256}
    validate_selection(value)
    return value


def validate_selection(value: dict) -> None:
    keys(value, {"source_result_id", "source_result_ref", "entity_id", "sample_index", "camera", "source_workspace_sha256"})
    require(re.fullmatch(r"result-[0-9a-f]{32}", str(value["source_result_id"])) is not None, "Invalid source result identity")
    content_ref(value["source_result_ref"])
    if value["source_workspace_sha256"] is not None:
        content_ref(value["source_workspace_sha256"])
    text(value["entity_id"])
    index = value["sample_index"]
    require(index is None or (type(index) is int and 0 <= index < 256), "Select a bounded sample index, or null for an empty batch")
    require(value["camera"] in {"oblique", "front"}, "Unknown capture camera")


def project(source: dict, selected: dict) -> dict:
    """Project actual selected observations, never decode native checkpoint bytes.

    A partial triple has no 3D position. No axis is filled with zero and no future
    state is consulted to complete a delayed observer's view.
    """
    source, selected = detached(source), detached(selected)
    validate_selection(selected)
    validate_simulation_result(source)
    require(source["result_id"] == selected["source_result_id"] and source["record_digest"] == selected["source_result_ref"], "Source result selection mismatch")
    event = source["data"]
    batch = event["observations"]
    require(batch is not None, "Select an observation result, not a step or checkpoint")
    instance = event["after"]
    require(instance["provider_id"] == PROVIDER and instance["provider"]["model_id"] == MODEL, "This projection supports the existing Godot point model only")
    require(set(CHANNELS) <= set(batch["observer"]["channels"]), "XYZ capture needs all three position channels; unobserved axes cannot be invented")
    samples = [s for s in batch["samples"] if s["identity"]["entity_id"] == selected["entity_id"] and s["quantity"] in CHANNELS]
    require(samples or not batch["samples"], "Selected entity has no position observations")
    require(selected["entity_id"] == "projectile", "Unknown entity for this bounded point-model projection")
    for sample in samples:
        validate_observation(sample)
        require(sample["frame"] == FRAME and sample["unit"] == "m"
                and sample["clock"]["id"] == batch["available_at"]["id"]
                and sample["identity"]["model_id"] == MODEL
                and sample["provenance"]["semantics"] == "simulated", "Observation frame/unit/model/semantics mismatch")
        require(sample["value"] is None or (type(sample["value"]) in (int, float) and abs(number(sample["value"])) <= 10000), "Position must be a bounded scalar or missing")
    times = sorted({s["clock"]["time_s"] for s in samples})
    index = selected["sample_index"]
    if not times:
        require(index is None, "Empty observations have no sample index; select unavailable explicitly")
        when, triple, availability = None, [], "no_samples"
    else:
        require(type(index) is int and index < len(times), "Selected sample index is unavailable")
        when = times[index]
        at_time = {s["quantity"]: s for s in samples if s["clock"]["time_s"] == when}
        triple = [at_time.get(channel) for channel in CHANNELS]
        availability = "present" if all(s is not None and s["value"] is not None for s in triple) else "missing_components"
    position = [s["value"] for s in triple] if availability == "present" else None
    return packed("ciw.simulation-observation-image-view.v1",
        source={"result_id": source["result_id"], "result_ref": source["record_digest"],
                "execution_id": source["execution_id"], "instance_id": instance["instance_id"],
                "experiment_id": instance["experiment_id"], "model_id": MODEL, "entity_id": selected["entity_id"],
                "workspace_sha256": selected["source_workspace_sha256"]},
        observer={"observer_id": batch["observer"]["observer_id"], "kind": batch["observer"]["kind"]},
        available_at=batch["available_at"], sample_time_s=when, sample_index=index, sample_count=len(times),
        frame=FRAME, unit="m", channels=list(CHANNELS), availability=availability,
        position_xyz_m=position, selected_samples=triple, interpolation="none", claim_scope=VIEW_SCOPE)


def render_request(view: dict, camera: str, nonce: str) -> dict:
    require(re.fullmatch(r"[0-9a-f]{32}", str(nonce)) is not None, "Invalid render request identity")
    require(camera in {"oblique", "front"}, "Unknown capture camera")
    # This is a derived image recipe, not an observation operator or a world save.
    return {"schema": "ciw.godot-observation-image-request.v1", "request_id": nonce,
            "view": deepcopy(view), "camera": camera, "width": WIDTH, "height": HEIGHT,
            "marker": "visual-only radius = orthographic span / 60", "physics": "not_executed"}


def encode(value: dict) -> bytes:
    import json
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def png_info(raw: bytes) -> dict:
    """Validate bounded RGB/RGBA8 non-interlaced PNG, CRCs and complete scanlines.

    Not a general image decoder. The fixed output contract bounds decompression
    before allocating image-sized data; no Pillow dependency is added to NET.
    """
    require(type(raw) is bytes and 0 < len(raw) <= MAX_IMAGE and raw[:8] == b"\x89PNG\r\n\x1a\n", "Invalid or over-budget PNG")
    offset, chunks, compressed, ended = 8, [], bytearray(), False
    width = height = color = None
    idat_ended = False
    while offset < len(raw):
        require(offset + 12 <= len(raw), "Truncated PNG chunk")
        size, kind = struct.unpack(">I4s", raw[offset:offset + 8])
        require(size <= MAX_IMAGE and offset + 12 + size <= len(raw), "Truncated or oversized PNG chunk")
        data = raw[offset + 8:offset + 8 + size]
        crc = struct.unpack(">I", raw[offset + 8 + size:offset + 12 + size])[0]
        require(zlib.crc32(kind + data) & 0xffffffff == crc, "PNG chunk CRC mismatch")
        require(not ended, "Unexpected trailing PNG data")
        if not chunks:
            require(kind == b"IHDR" and size == 13, "PNG must start with IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", data)
            require((width, height) == (WIDTH, HEIGHT) and depth == 8 and color in {2, 6}
                    and (compression, filtering, interlace) == (0, 0, 0), "Unsupported PNG dimensions/format")
        elif kind == b"sRGB":
            # Godot 4.5.2 uses libpng's simplified writer, which emits this
            # standard one-byte colour-space declaration for RGB8 images.
            require(b"sRGB" not in chunks and b"IDAT" not in chunks
                    and size == 1 and data[0] <= 3, "Invalid PNG sRGB declaration")
        elif kind == b"IDAT":
            require(not idat_ended, "Noncontiguous PNG data chunks")
            compressed.extend(data)
        elif kind == b"IEND":
            require(size == 0 and b"IDAT" in chunks, "Invalid PNG ending")
            ended = True
        else:
            # The installed renderer emits plain image PNGs. Do not accept scripts,
            # animation, arbitrary metadata or another image type as this artifact.
            raise ValueError("Unexpected PNG chunk for the capture profile")
        if b"IDAT" in chunks and kind != b"IDAT":
            idat_ended = True
        chunks.append(kind)
        offset += size + 12
    require(ended, "Incomplete PNG")
    stride = WIDTH * (3 if color == 2 else 4)
    expected = HEIGHT * (stride + 1)
    decoder = zlib.decompressobj()
    try:
        scanlines = decoder.decompress(bytes(compressed), expected + 1)
    except zlib.error as exc:
        raise ValueError("Invalid PNG compressed stream") from exc
    require(len(scanlines) == expected and decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data, "PNG decompression length/stream mismatch")
    require(all(scanlines[row * (stride + 1)] <= 4 for row in range(HEIGHT)), "Unsupported PNG row filter")
    return {"width": WIDTH, "height": HEIGHT, "bit_depth": 8, "channels": 3 if color == 2 else 4}


def validate_runtime(runtime: dict) -> None:
    keys(runtime, {"provider", "profile", "executable_sha256", "worker_sha256", "adapter_sha256"})
    require(runtime["provider"] == "ciw.godot-observation-renderer" and runtime["profile"] == "godot-4.5.2-gl-compatibility-png.v1", "Unexpected render runtime")
    for key in ("executable_sha256", "worker_sha256", "adapter_sha256"):
        content_ref(runtime[key])


def validate_native(report: dict, request: dict) -> None:
    keys(report, {"schema", "request_id", "request_sha256", "pid", "engine_version", "version", "display_server",
                  "rendering_method", "video_adapter", "image_sha256", "width", "height", "camera",
                  "marker_count", "position_xyz_m", "input_unchanged"})
    require(report["schema"] == "ciw.godot-observation-image-native.v1" and report["request_id"] == request["request_id"]
            and report["request_sha256"] == bytes_ref(encode(request)), "Native capture request binding mismatch")
    require(type(report["pid"]) is int and report["pid"] > 0, "Invalid render-process identity")
    require(report["version"] == [4, 5, 2, "stable"] and report["rendering_method"] == "gl_compatibility"
            and report["display_server"] != "headless", "Unsupported native render profile")
    for key in ("engine_version", "display_server", "video_adapter"):
        text(report[key])
    require(type(report["width"]) is int and type(report["height"]) is int
            and (report["width"], report["height"]) == (WIDTH, HEIGHT) and report["camera"] == request["camera"], "Capture dimensions/camera mismatch")
    require(report["input_unchanged"] is True, "Renderer changed selected input")
    position = request["view"]["position_xyz_m"]
    require(type(report["marker_count"]) is int and report["marker_count"] == (0 if position is None else 1), "Missingness/marker mismatch")
    expected = None if position is None else [struct.unpack("<f", struct.pack("<f", x))[0] for x in position]
    actual = report["position_xyz_m"]
    require(actual is None if expected is None else type(actual) is list and len(actual) == 3
            and all(type(a) in (float, int) and number(a) == b for a, b in zip(actual, expected)), "Displayed position differs at declared float32 precision")
    content_ref(report["image_sha256"])


def make_capture(source: dict, selected: dict, runtime: dict, native: dict, png: bytes) -> dict:
    view = project(source, selected)
    info = png_info(png)
    request = render_request(view, selected["camera"], native["request_id"])
    validate_runtime(runtime)
    validate_native(native, request)
    require(native["image_sha256"] == bytes_ref(png), "Native image binding mismatch")
    image = artifact(png, media_type="image/png", producer=runtime["provider"],
        experiment_id=view["source"]["experiment_id"], metadata={**info, "modality": "image",
        "semantics": "derived_visualization", "source_execution_id": source["execution_id"],
        "source_result_ref": source["record_digest"], "view_ref": view["record_digest"],
        "render_request_ref": bytes_ref(encode(request))})
    return packed("ciw.simulation-observation-capture.v1", source_result=source, selection=selected,
                  view=view, runtime=runtime, native=native, image=image, claim_scope=VIEW_SCOPE, **AUTHORITY)


def validate_capture(value: dict, png: bytes | None = None) -> None:
    unpack(value, "ciw.simulation-observation-capture.v1", {"source_result", "selection", "view", "runtime", "native", "image", "claim_scope", *AUTHORITY})
    require(all(value[k] == v for k, v in AUTHORITY.items()) and value["claim_scope"] == VIEW_SCOPE, "Capture cannot grant verification or state authority")
    view = project(value["source_result"], value["selection"])
    require(value["view"] == view, "Capture projection differs from selected source")
    request = render_request(view, value["selection"]["camera"], value["native"]["request_id"])
    validate_runtime(value["runtime"])
    validate_native(value["native"], request)
    image = value["image"]
    validate_artifact(image, png)
    meta = image["metadata"]
    info = {"width": WIDTH, "height": HEIGHT, "bit_depth": 8, "channels": meta.get("channels")}
    require(type(info["channels"]) is int and info["channels"] in (3, 4), "Unsupported capture channels")
    require(image["media_type"] == "image/png" and image["producer"] == value["runtime"]["provider"]
            and image["experiment_id"] == view["source"]["experiment_id"]
            and 0 < image["size_bytes"] <= MAX_IMAGE and image["sha256"] == value["native"]["image_sha256"], "Image artifact source/format mismatch")
    expected_meta = {**info, "modality": "image", "semantics": "derived_visualization",
        "source_execution_id": view["source"]["execution_id"], "source_result_ref": view["source"]["result_ref"],
        "view_ref": view["record_digest"], "render_request_ref": bytes_ref(encode(request))}
    require(meta == expected_meta, "Image evidence provenance mismatch")
    if png is not None:
        require(png_info(png) == info, "PNG disagrees with artifact dimensions/channels")


def validate_result(result: dict, png: bytes | None = None) -> None:
    detached(result)
    check_seal(result)
    require(result.get("schema") == "ciw.operation-result.v1" and result.get("operation_id") == OPERATION
            and result.get("role") == "backend" and result.get("verification_id") is None
            and result.get("verification_status") == "not_verified", "Require an ordinary CIW image-capture result")
    for field, prefix in (("execution_id", "execution"), ("result_id", "result")):
        require(re.fullmatch(prefix + r"-[0-9a-f]{32}", str(result.get(field))) is not None, "Invalid capture occurrence identity")
    validate_capture(result["data"], png)
    source = result["data"]["source_result"]
    require(result["parameters"] == result["data"]["selection"] and result["runtime"] == result["data"]["runtime"], "Capture operation binding mismatch")
    require(result["execution_id"] != source["execution_id"] and result["result_id"] != source["result_id"], "Image creation must retain a distinct execution/result")


def _payload(operation_id: str, data: dict, run: dict, parameters: dict, selected: dict) -> None:
    require(operation_id == OPERATION, "Wrong capture operation")
    validate_capture(data)
    require(data["selection"] == parameters, "Image payload differs from operation request")


def register_records() -> None:
    global _REGISTERED
    if not _REGISTERED:
        from .operations.schemas import register_payload_validator
        register_payload_validator(OPERATION, _payload)
        _REGISTERED = True


def validate_dependencies(session) -> None:
    """Resolve image-source references against the original Session ledger."""
    for result in session.results.values():
        if result.get("operation_id") == OPERATION:
            validate_result(result)
            source = result["data"]["source_result"]
            require(session.results.get(source["result_id"]) == source, "Capture source is not the retained Session result")
