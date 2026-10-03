"""Bounded RGB notation, deterministic CPU baking and safe GLSL preview source.

RGB is an unqualified display representation. CPU byte checks do not establish
GPU pixel equality, optical material properties, or physical suitability.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
import json
import math
import struct
from time import monotonic
import zlib

import numpy as np

from .control_contracts import MAX_BYTES, keys, number
from .graphics_notation import (GLSL_POWER_HELPERS, compile_uv, evaluate_uv,
                                glsl_expression, validate_parameters)
from .operations.runner import check_seal, digest, seal
from .procedural_contract import CLAIMS
from .procedural_surface import _bounds

REQUEST_SCHEMA = "ciw.procedural-texture-request.v1"
RESULT_SCHEMA = "ciw.procedural-texture.v1"
MAX_GENERATION_SECONDS = 15.0
ENCODING = {"channels": "rgba8", "mapping": "clamp_0_1", "sampling": "pixel_centers",
            "color_interpretation": "unqualified_display_rgb"}
VERTEX_SOURCE = "attribute vec2 a_position;\nattribute vec2 a_uv;\nvarying vec2 v_uv;\nvoid main(){v_uv=a_uv;gl_Position=vec4(a_position,0.0,1.0);}\n"


def _appearance(appearance):
    keys(appearance, {"roughness", "metallic"})
    if not 0.05 <= number(appearance["roughness"]) <= 1 or not 0 <= number(appearance["metallic"]) <= 1:
        raise ValueError("Visual roughness/metallic parameters exceed their bounds")


def _glsl_number(value):
    text = format(number(value), ".17g")
    return text if "." in text or "e" in text.lower() else text + ".0"


def validate_texture_request(request: dict) -> dict:
    keys(request, {"schema", "definition", "domain", "appearance", "encoding", "verification"})
    if request["schema"] != REQUEST_SCHEMA:
        raise ValueError("Unsupported procedural texture schema")
    definition = request["definition"]
    keys(definition, {"expressions", "parameters"})
    validate_parameters(definition["parameters"])
    if type(definition["expressions"]) is not list or len(definition["expressions"]) != 3:
        raise ValueError("Require three scalar RGB channel expressions")
    for expression in definition["expressions"]:
        compile_uv(expression, definition["parameters"])
    domain = request["domain"]
    keys(domain, {"bounds", "resolution", "units", "frame"})
    _bounds(domain["bounds"])
    if (type(domain["resolution"]) is not list or len(domain["resolution"]) != 2
            or any(type(value) is not int or not 16 <= value <= 256 for value in domain["resolution"])):
        raise ValueError("Texture width/height must be integers inside 16..256")
    if domain["units"] != "normalized_coordinates" or domain["frame"] != "procedural.texture_uv.v1":
        raise ValueError("Require the normalized texture UV coordinate declaration")
    _appearance(request["appearance"])
    if type(request["encoding"]) is not dict or request["encoding"] != ENCODING:
        raise ValueError("Require explicit RGBA8 center sampling, clipping and display-color scope")
    keys(request["verification"], {"byte_exact"})
    if request["verification"]["byte_exact"] is not True:
        raise ValueError("CPU texture verification must require byte-exact agreement")
    if len((json.dumps(request, indent=2, allow_nan=False) + "\n").encode()) > 65536:
        raise ValueError("Texture declaration exceeds 64KiB")
    return deepcopy(request)


def shader_sources(request: dict, ir: list[dict] | None = None) -> dict:
    """Data-only safe source emission; no GPU compilation is performed here."""
    request = validate_texture_request(request)
    definition = request["definition"]
    expected_ir = [compile_uv(expression, definition["parameters"]) for expression in definition["expressions"]]
    if ir is not None and digest(ir) != digest(expected_ir):
        raise ValueError("Shader IR differs from its declared channel programs")
    programs = [glsl_expression(channel, definition["parameters"]) for channel in expected_ir]
    (u0, u1), (v0, v1) = request["domain"]["bounds"]
    fragment = ("precision highp float;\nvarying vec2 v_uv;\n" + GLSL_POWER_HELPERS + "\nvoid main(){\n"
                + f"float u={_glsl_number(u0)}+{_glsl_number(u1-u0)}*v_uv.x;\nfloat v={_glsl_number(v0)}+{_glsl_number(v1-v0)}*v_uv.y;\n"
                + "vec3 color=clamp(vec3(" + ",".join(programs) + "),0.0,1.0);\n"
                + "gl_FragColor=vec4(color,1.0);\n}\n")
    return {"language": "glsl_es_1.00", "vertex_source": VERTEX_SOURCE,
            "fragment_source": fragment, "compilation": "not_performed"}


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)


def encode_png(width: int, height: int, rgba: bytes) -> bytes:
    """Encode the fixed RGBA8/filter-0 profile with deterministic zlib settings."""
    if type(width) is not int or type(height) is not int or not 16 <= width <= 256 or not 16 <= height <= 256 or type(rgba) is not bytes or len(rgba) != width * height * 4:
        raise ValueError("PNG dimensions/data differ from the bounded RGBA8 profile")
    stride = width * 4
    scanlines = b"".join(b"\0" + rgba[row * stride:(row + 1) * stride] for row in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(scanlines, level=9)) + _chunk(b"IEND", b"")


def _decode_base64(value, limit):
    if type(value) is not str or len(value) > ((limit + 2) // 3) * 4:
        raise ValueError("Encoded texture bytes exceed the bounded profile")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("Require canonical base64 texture bytes") from exc
    if len(raw) > limit or base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("Require bounded canonical base64 encoding")
    return raw


def validate_texture_result(request: dict, result: dict) -> dict:
    """Static retained byte/identity/source checks; no field or GPU evaluation."""
    request = validate_texture_request(request)
    keys(result, {"schema", "request_digest", "image", "shader", "appearance", "claims", "ir", "record_digest"})
    if result["schema"] != RESULT_SCHEMA or result["request_digest"] != digest(request):
        raise ValueError("Texture result schema or request binding differs")
    _appearance(result["appearance"])
    if result["appearance"] != request["appearance"] or result["claims"] != CLAIMS:
        raise ValueError("Texture visual appearance or authority differs")
    expected_ir = [compile_uv(expression, request["definition"]["parameters"]) for expression in request["definition"]["expressions"]]
    if digest(result["ir"]) != digest(expected_ir) or result["shader"] != shader_sources(request, expected_ir):
        raise ValueError("Texture safe IR or emitted shader source differs")
    image = result["image"]
    keys(image, {"width", "height", "rgba_base64", "png_base64", "png_sha256", "encoding"})
    width, height = request["domain"]["resolution"]
    if type(image["width"]) is not int or type(image["height"]) is not int or (image["width"], image["height"]) != (width, height) or image["encoding"] != ENCODING:
        raise ValueError("Texture image dimensions/encoding differ")
    rgba = _decode_base64(image["rgba_base64"], width * height * 4)
    if len(rgba) != width * height * 4 or any(value != 255 for value in rgba[3::4]):
        raise ValueError("Require a complete opaque RGBA8 image")
    png = _decode_base64(image["png_base64"], 1024 * 1024)
    if not png or image["png_sha256"] != "sha256:" + sha256(png).hexdigest():
        raise ValueError("Retained PNG content identity differs")
    check_seal(result)
    if len((json.dumps(result, indent=2, allow_nan=False) + "\n").encode()) > MAX_BYTES:
        raise ValueError("Texture artifact exceeds 8MiB")
    return deepcopy(result)


def generate_texture(request: dict) -> dict:
    started = monotonic()
    request = validate_texture_request(request)
    width, height = request["domain"]["resolution"]
    (u0, u1), (v0, v1) = request["domain"]["bounds"]
    u = u0 + (np.arange(width, dtype=np.float64) + 0.5) * ((u1 - u0) / width)
    v = v0 + (np.arange(height, dtype=np.float64) + 0.5) * ((v1 - v0) / height)
    grid_u, grid_v = np.meshgrid(u, v, indexing="xy")
    definition = request["definition"]
    channels = []
    for expression in definition["expressions"]:
        channels.append(evaluate_uv(expression, definition["parameters"], grid_u, grid_v))
        if monotonic() - started > MAX_GENERATION_SECONDS:
            raise ValueError("Texture evaluation exceeded its cooperative 15-second deadline")
    rgb = np.floor(255.0 * np.clip(np.stack(channels, axis=-1), 0.0, 1.0) + 0.5).astype(np.uint8)
    rgba = np.concatenate((rgb, np.full((height, width, 1), 255, dtype=np.uint8)), axis=-1).tobytes()
    png = encode_png(width, height, rgba)
    ir = [compile_uv(expression, definition["parameters"]) for expression in definition["expressions"]]
    result = seal({"schema": RESULT_SCHEMA, "request_digest": digest(request),
                   "image": {"width": width, "height": height, "rgba_base64": base64.b64encode(rgba).decode("ascii"),
                             "png_base64": base64.b64encode(png).decode("ascii"), "png_sha256": "sha256:" + sha256(png).hexdigest(),
                             "encoding": deepcopy(ENCODING)}, "shader": shader_sources(request, ir),
                   "appearance": deepcopy(request["appearance"]), "claims": deepcopy(CLAIMS), "ir": ir})
    validated = validate_texture_result(request, result)
    if monotonic() - started > MAX_GENERATION_SECONDS:
        raise ValueError("Texture generation exceeded its cooperative 15-second deadline")
    return validated


def example_texture() -> dict:
    field = "(0.5+0.5*sin(f*u+phase)*sin(f*v+phase))"
    return validate_texture_request({"schema": REQUEST_SCHEMA,
        "definition": {"expressions": ["0.15+0.7*" + field, "0.12+0.3*" + field, "0.25+0.6*" + field],
                       "parameters": {"f": {"value": 8 * math.pi, "minimum": 2.0, "maximum": 80.0},
                                      "phase": {"value": 0.0, "minimum": 0.0, "maximum": 2 * math.pi}}},
        "domain": {"bounds": [[0.0, 1.0], [0.0, 1.0]], "resolution": [128, 128],
                   "units": "normalized_coordinates", "frame": "procedural.texture_uv.v1"},
        "appearance": {"roughness": 0.45, "metallic": 0.15}, "encoding": deepcopy(ENCODING),
        "verification": {"byte_exact": True}})
