"""Independent UV geometry and decoded PNG/pixel audits."""
import base64
from copy import deepcopy
from hashlib import sha256
import math
import struct
import zlib

import pytest

from ciw.operations.runner import seal
from ciw.procedural_representation_verification import decode_texture_png, validate_report, verify
from ciw.procedural_surface import example_surface, generate_surface, validate_surface_result
from ciw.procedural_texture import example_texture, generate_texture, validate_texture_result


def reseal(record):
    return seal({key: value for key, value in record.items() if key != "record_digest"})


def checks(record):
    return {row["name"]: row for row in record["checks"]}


def chunk(name, data):
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)


def png(width, height, rgba, *, filter_type=0, color_type=6, suffix=b"", raw_override=None):
    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    rows = (b"".join(bytes([filter_type]) + rgba[row * width * 4:(row + 1) * width * 4]
                     for row in range(height)) if raw_override is None else raw_override)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows))
            + chunk(b"IEND", b"") + suffix)


def replace_png(result, image_bytes):
    result["image"]["png_base64"] = base64.b64encode(image_bytes).decode("ascii")
    result["image"]["png_sha256"] = "sha256:" + sha256(image_bytes).hexdigest()
    return reseal(result)


@pytest.fixture(scope="module")
def surface():
    q = example_surface()
    return q, generate_surface(q)


@pytest.fixture(scope="module")
def texture():
    q = example_texture()
    q["domain"]["resolution"] = [24, 16]
    return q, generate_texture(q)


def test_periodic_torus_geometry_and_area(surface):
    q, m = surface
    r = verify(q, m)
    assert r["status"] == "PASS"
    assert r["metrics"]["vertex_count"] == 24 * 16
    assert r["metrics"]["triangle_count"] == 2 * 24 * 16
    assert r["metrics"]["boundary_edge_count"] == 0
    assert r["metrics"]["component_count"] == 1
    assert r["metrics"]["max_field_residual"] == 0
    exact_area = 4 * math.pi**2 * 0.65 * 0.22
    assert 0.97 * exact_area < r["metrics"]["surface_area"] < exact_area
    assert validate_report(q, m, r) == r


def test_open_parametric_plane_has_analytic_area():
    q = example_surface()
    q["definition"] = {"expressions": ["u", "v", "0"], "parameters": {}}
    q["domain"]["bounds"] = [[-1, 1], [-1, 1]]
    q["domain"]["resolution"] = [8, 12]
    q["domain"]["periodic"] = [False, False]
    q["verification"]["require_closed"] = False
    r = verify(q, generate_surface(q))
    assert r["status"] == "PASS"
    assert r["metrics"]["surface_area"] == 4
    assert r["metrics"]["boundary_edge_count"] == 2 * (8 + 12)


def test_periodic_flag_does_not_establish_endpoint_agreement():
    q = example_surface()
    q["definition"] = {"expressions": ["u", "v", "0"], "parameters": {}}
    q["domain"]["bounds"] = [[-1, 1], [-1, 1]]
    r = verify(q, generate_surface(q))
    assert checks(r)["periodic_seam_residual"]["value"] == 2
    assert checks(r)["periodic_seam_residual"]["status"] == "FAIL"


@pytest.mark.parametrize("change,check", [("uv", "parameter_coordinates"), ("position", "sampled_position_residual"),
                                        ("connectivity", "tessellation_connectivity"), ("winding", "parameter_winding"),
                                        ("hole", "required_closed_surface"), ("duplicate", "duplicate_triangles")])
def test_coherent_surface_forgery_fails_fresh_check(surface, change, check):
    q, original = surface
    m = deepcopy(original)
    if change == "uv":
        m["mesh"]["parameter_coordinates"][1][1] += 0.0001
    elif change == "position":
        m["mesh"]["vertices"][0][0] += 0.01
    elif change == "connectivity":
        m["mesh"]["triangles"][0], m["mesh"]["triangles"][1] = m["mesh"]["triangles"][1], m["mesh"]["triangles"][0]
    elif change == "winding":
        for triangle in m["mesh"]["triangles"]:
            triangle.reverse()
    elif change == "hole":
        m["mesh"]["triangles"].pop()
    elif change == "duplicate":
        m["mesh"]["triangles"].append(m["mesh"]["triangles"][0][:])
    m = reseal(m)
    validate_surface_result(q, m)
    r = verify(q, m)
    assert r["status"] == "FAIL"
    assert checks(r)[check]["status"] == "FAIL"
    assert validate_report(q, m, r) == r


def test_texture_png_and_pixel_centers_are_independently_verified(texture):
    q, m = texture
    r = verify(q, m)
    assert r["status"] == "PASS"
    assert r["metrics"]["pixel_count"] == 24 * 16
    assert r["metrics"]["max_channel_byte_error"] == 0
    rgba = base64.b64decode(m["image"]["rgba_base64"])
    assert decode_texture_png(base64.b64decode(m["image"]["png_base64"]), 24, 16) == rgba
    assert validate_report(q, m, r) == r


def test_constant_channels_clip_and_use_half_up_rounding():
    q = example_texture()
    q["domain"]["resolution"] = [16, 16]
    q["definition"] = {"expressions": ["-0.1", "0.5", "1.1"], "parameters": {}}
    m = generate_texture(q)
    assert base64.b64decode(m["image"]["rgba_base64"]) == bytes([0, 128, 255, 255]) * (16 * 16)
    assert verify(q, m)["status"] == "PASS"


def test_coherent_texture_pixels_and_png_forgery_fails_field_sampling(texture):
    q, original = texture
    m = deepcopy(original)
    raw = bytearray(base64.b64decode(m["image"]["rgba_base64"]))
    raw[0] += 1
    m["image"]["rgba_base64"] = base64.b64encode(raw).decode("ascii")
    m = replace_png(m, png(24, 16, bytes(raw)))
    validate_texture_result(q, m)
    r = verify(q, m)
    assert checks(r)["png_structure"]["status"] == "PASS"
    assert checks(r)["png_rgba_binding"]["status"] == "PASS"
    assert checks(r)["sampled_channel_bytes"]["value"] == 1
    assert r["status"] == "FAIL"
    assert validate_report(q, m, r) == r


def test_png_and_retained_raw_pixel_binding_is_checked(texture):
    q, original = texture
    m = deepcopy(original)
    raw = bytearray(base64.b64decode(m["image"]["rgba_base64"]))
    raw[0] += 1
    m = replace_png(m, png(24, 16, bytes(raw)))
    r = verify(q, m)
    assert checks(r)["sampled_channel_bytes"]["value"] == 0
    assert checks(r)["png_rgba_binding"]["value"] == 1
    assert r["status"] == "FAIL"


def test_maximum_declared_png_byte_budget_still_produces_valid_failure_report(texture):
    q, original = texture
    m = replace_png(deepcopy(original), b"X" * (1024 * 1024))
    validate_texture_result(q, m)
    r = verify(q, m)
    assert r["status"] == "FAIL"
    assert r["metrics"]["png_bytes"] == 1024 * 1024
    assert validate_report(q, m, r) == r


@pytest.mark.parametrize("kind", ["surface", "texture"])
def test_fractional_error_counts_are_rejected(surface, texture, kind):
    q, m = surface if kind == "surface" else texture
    r = verify(q, m)
    name = "parameter_coordinates" if kind == "surface" else "png_structure"
    checks(r)[name].update(value=0.5, status="FAIL")
    r["status"] = "FAIL"
    with pytest.raises(ValueError):
        validate_report(q, m, reseal(r))


@pytest.mark.parametrize("fault", ["signature", "crc", "chunk_truncated", "missing_iend", "extra_chunk", "dimensions",
                                  "color_type", "filter", "inflate_length", "inflate_bomb", "deflate_suffix"])
def test_hostile_png_is_rejected_after_coherent_hash_and_seal(texture, fault):
    q, original = texture
    m = deepcopy(original)
    rgba = base64.b64decode(m["image"]["rgba_base64"])
    raw = base64.b64decode(m["image"]["png_base64"])
    if fault == "signature":
        raw = b"bad" + raw[3:]
    elif fault == "crc":
        raw = raw[:29] + bytes([raw[29] ^ 1]) + raw[30:]
    elif fault == "chunk_truncated":
        raw = raw[:-1]
    elif fault == "missing_iend":
        raw = raw[:-12]
    elif fault == "extra_chunk":
        raw = raw[:-12] + chunk(b"tEXt", b"declared") + raw[-12:]
    elif fault == "dimensions":
        raw = png(16, 24, rgba)
    elif fault == "color_type":
        raw = png(24, 16, rgba, color_type=2)
    elif fault == "filter":
        raw = png(24, 16, rgba, filter_type=1)
    elif fault == "inflate_length":
        raw = png(24, 16, rgba, raw_override=b"\0" * 10)
    elif fault == "inflate_bomb":
        raw = png(24, 16, rgba, raw_override=b"\0" * 1_000_000)
    elif fault == "deflate_suffix":
        rows = b"".join(b"\0" + rgba[row * 96:(row + 1) * 96] for row in range(16))
        header = struct.pack(">IIBBBBB", 24, 16, 8, 6, 0, 0, 0)
        raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows) + b"suffix") + chunk(b"IEND", b"")
    m = replace_png(m, raw)
    validate_texture_result(q, m)
    r = verify(q, m)
    assert r["status"] == "FAIL"
    assert checks(r)["png_structure"]["status"] == "FAIL"
    assert validate_report(q, m, r) == r
    with pytest.raises(ValueError):
        decode_texture_png(raw, 24, 16)


@pytest.mark.parametrize("dims", [(True, 16), (16, True), (15, 16), (16, 257), (16.0, 16)])
def test_decoder_requires_bounded_integer_dimensions(texture, dims):
    with pytest.raises(ValueError):
        decode_texture_png(base64.b64decode(texture[1]["image"]["png_base64"]), *dims)


@pytest.mark.parametrize("kind", ["surface", "texture"])
def test_fresh_verifier_never_calls_generators(surface, texture, monkeypatch, kind):
    q, m = surface if kind == "surface" else texture
    def blocked(*args, **kwargs):
        raise AssertionError("generator activated during independent audit")
    monkeypatch.setattr("ciw.procedural_surface.generate_surface", blocked)
    monkeypatch.setattr("ciw.procedural_texture.generate_texture", blocked)
    assert verify(q, m)["status"] == "PASS"


@pytest.mark.parametrize("kind", ["surface", "texture"])
def test_static_validator_does_not_evaluate_or_decode(surface, texture, monkeypatch, kind):
    q, m = surface if kind == "surface" else texture
    r = verify(q, m)
    def blocked(*args, **kwargs):
        raise AssertionError("static report activated numerical checks")
    monkeypatch.setattr("ciw.graphics_notation.evaluate_uv", blocked)
    monkeypatch.setattr("ciw.procedural_representation_verification._decode_png", blocked)
    monkeypatch.setattr("ciw.procedural_representation_verification.verify", blocked)
    monkeypatch.setattr("ciw.procedural_surface.generate_surface", blocked)
    monkeypatch.setattr("ciw.procedural_texture.generate_texture", blocked)
    assert validate_report(q, m, r) == r


@pytest.mark.parametrize("kind", ["surface", "texture"])
def test_coherent_report_forgery_still_needs_fresh_audit(surface, texture, kind):
    q, m = surface if kind == "surface" else texture
    r = verify(q, m)
    forged = deepcopy(r)
    if kind == "surface":
        forged["metrics"]["max_field_residual"] = 0.0001
        checks(forged)["sampled_position_residual"]["value"] = 0.0001
    else:
        forged["metrics"]["max_channel_byte_error"] = 1
        checks(forged)["sampled_channel_bytes"].update(value=1, status="FAIL")
        forged["status"] = "FAIL"
    forged = reseal(forged)
    assert validate_report(q, m, forged) == forged
    assert verify(q, m)["record_digest"] != forged["record_digest"]


@pytest.mark.parametrize("kind", ["surface", "texture"])
@pytest.mark.parametrize("fault", ["candidate", "request", "status", "count", "authority", "missing_check", "duplicate_check", "boolean"])
def test_static_report_rejects_invalid_bindings(surface, texture, kind, fault):
    q, m = surface if kind == "surface" else texture
    r = verify(q, m)
    if fault in {"candidate", "request"}:
        r[fault + "_digest"] = "sha256:" + "0" * 64
    elif fault == "status":
        r["status"] = "FAIL"
    elif fault == "count":
        r["metrics"]["vertex_count" if kind == "surface" else "width"] += 1
    elif fault == "authority":
        r["claims"]["manufacturing"] = "validated"
    elif fault == "missing_check":
        r["checks"].pop()
    elif fault == "duplicate_check":
        r["checks"][-1] = deepcopy(r["checks"][0])
    elif fault == "boolean":
        r["metrics"]["component_count" if kind == "surface" else "width"] = True
    with pytest.raises(ValueError):
        validate_report(q, m, reseal(r))
