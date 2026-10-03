"""Analytic and adversarial checks of UV surfaces, RGB fields and emitted IR."""
import base64
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import math
import struct
import zlib

import numpy as np
import pytest

from ciw.graphics_notation import compile_uv, evaluate_uv, glsl_expression
from ciw.operations.runner import digest, seal
from ciw.procedural_contract import CLAIMS
from ciw.procedural_surface import (example_surface, generate_surface,
                                     validate_surface_request, validate_surface_result)
from ciw.procedural_texture import (example_texture, generate_texture,
                                     validate_texture_request, validate_texture_result)


@pytest.mark.parametrize("expression, expected", [
    ("u+v", 0.75), ("u*v", 0.125), ("(-u)**2", 0.25),
    ("min(u,v)", 0.25), ("max(u,v)", 0.5), ("sqrt(u*u)+abs(-v)", 0.75),
])
def test_uv_scalar_notation_analytic_values_and_typed_ir(expression, expected):
    ir = compile_uv(expression, {})
    assert evaluate_uv(expression, {}, 0.5, 0.25) == pytest.approx(expected)
    assert ir["schema"] == "ciw.graphics-scalar-ir.v1"
    assert ir["expression"] == expression
    assert ir["coordinate_system"] == "uv"
    assert ir["scalar_type"] == "binary64"
    assert "eval" not in glsl_expression(ir, {})


@pytest.mark.parametrize("expression", ["x", "y", "z", "u.__class__", "u[0]", "__import__('os')", "sin(u,v)", "u**7", "u**v", "1e-400", "1e309", "9" * 1000])
def test_uv_rejects_cartesian_syntax_unsafe_calls_and_unrepresentable_numbers(expression):
    with pytest.raises(ValueError):
        compile_uv(expression, {})


def test_eight_declared_uv_parameters_preserve_the_existing_parameter_budget():
    parameters = {f"p{index}": {"value": float(index), "minimum": 0, "maximum": 8} for index in range(8)}
    assert evaluate_uv("u+p7", parameters, 0.5, 0) == 7.5
    for name in ("u", "v", "x", "sin"):
        with pytest.raises(ValueError):
            compile_uv("0", {name: {"value": 0, "minimum": -1, "maximum": 1}})


def test_safe_ir_binding_and_integer_power_glsl_emission():
    ir = compile_uv("((-u)**6)**6", {})
    source = glsl_expression(ir, {})
    assert "netPow6(netPow6(" in source
    assert len(source) < 100
    assert "pow(" not in source
    ir["root"]["op"] = "injected"
    with pytest.raises(ValueError):
        glsl_expression(ir, {})


def sheet_request():
    request = example_surface()
    request["definition"] = {"expressions": ["u", "v", "0"], "parameters": {}}
    request["domain"].update(bounds=[[-1.0, 1.0], [-1.0, 1.0]], resolution=[8, 8], periodic=[False, False])
    request["verification"]["require_closed"] = False
    return request


def test_parametric_plane_analytic_area_grid_and_positive_orientation():
    request = sheet_request()
    result = generate_surface(request)
    vertices = np.asarray(result["mesh"]["vertices"])
    faces = np.asarray(result["mesh"]["triangles"])
    assert len(vertices) == 81 and len(faces) == 128
    np.testing.assert_array_equal(vertices[:, :2], result["mesh"]["parameter_coordinates"])
    np.testing.assert_array_equal(vertices[:, 2], np.zeros(len(vertices)))
    normals = np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]], vertices[faces[:, 2]] - vertices[faces[:, 0]])
    assert np.all(normals[:, 2] > 0)
    assert np.linalg.norm(normals, axis=1).sum() / 2 == pytest.approx(4.0)
    assert result["claims"] == CLAIMS


def test_rotated_parametric_torus_analytic_equation_closed_topology_and_area():
    request = example_surface()
    result = generate_surface(request)
    assert result == generate_surface(request)
    vertices = np.asarray(result["mesh"]["vertices"])
    faces = np.asarray(result["mesh"]["triangles"])
    parameter = request["definition"]["parameters"]
    angle, major, minor = (parameter[name]["value"] for name in ("a", "R", "r"))
    original_x = math.cos(angle) * vertices[:, 0] - math.sin(angle) * vertices[:, 2]
    original_z = math.sin(angle) * vertices[:, 0] + math.cos(angle) * vertices[:, 2]
    residual = (np.hypot(original_x, vertices[:, 1]) - major) ** 2 + original_z ** 2 - minor ** 2
    assert np.max(np.abs(residual)) < 1e-15
    edges = Counter(tuple(sorted((face[a], face[b]))) for face in faces for a, b in ((0, 1), (1, 2), (2, 0)))
    assert set(edges.values()) == {2}
    assert len(vertices) - len(edges) + len(faces) == 0
    area = np.linalg.norm(np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]], vertices[faces[:, 2]] - vertices[faces[:, 0]]), axis=1).sum() / 2
    assert area == pytest.approx(4 * math.pi ** 2 * major * minor, rel=0.025)
    assert max(coordinate[0] for coordinate in result["mesh"]["parameter_coordinates"]) < 2 * math.pi


@pytest.mark.parametrize("group, key, value", [
    ("domain", "resolution", [7, 8]), ("domain", "resolution", [8, 49]),
    ("domain", "resolution", [8, True]), ("domain", "periodic", [True, 1]),
    ("domain", "bounds", [[0, 0.01], [0, 1]]), ("domain", "units", "m"),
    ("definition", "expressions", ["u", "v"]), ("definition", "expressions", ["u", "v", "x"]),
    ("verification", "field_tolerance", 0), ("verification", "require_closed", 1),
    ("appearance", "metallic", True),
])
def test_surface_declaration_profile_refusals(group, key, value):
    request = example_surface()
    request[group][key] = value
    with pytest.raises(ValueError):
        validate_surface_request(request)


def test_surface_static_validation_never_evaluates_or_generates(monkeypatch):
    request = example_surface()
    result = generate_surface(request)
    monkeypatch.setattr("ciw.procedural_surface.evaluate_uv", lambda *a: pytest.fail("static evaluation"))
    monkeypatch.setattr("ciw.procedural_surface.generate_surface", lambda *a: pytest.fail("static generation"))
    assert validate_surface_request(request) == request
    assert validate_surface_result(request, result) == result
    result["mesh"]["vertices"][0][0] += 0.1
    seal(result)
    assert validate_surface_result(request, result) == result


@pytest.mark.parametrize("mutation", [
    lambda r: r["mesh"]["triangles"][0].__setitem__(0, -1),
    lambda r: r["mesh"]["parameter_coordinates"][0].__setitem__(0, 20),
    lambda r: r["claims"].update(physical_validation="validated"),
    lambda r: r["ir"][0]["root"].update(op="unknown"),
    lambda r: r["mesh"].update(units="m"),
])
def test_surface_retained_binding_refusals(mutation):
    request = example_surface()
    result = generate_surface(request)
    mutation(result)
    seal(result)
    with pytest.raises(ValueError):
        validate_surface_result(request, result)


def constant_texture(expressions=("0.5", "-0.1", "1.2")):
    request = example_texture()
    request["definition"] = {"expressions": list(expressions), "parameters": {}}
    request["domain"]["resolution"] = [16, 16]
    return request


def test_cpu_texture_halfup_clipping_opacity_and_png_content_binding():
    request = constant_texture()
    result = generate_texture(request)
    raw = base64.b64decode(result["image"]["rgba_base64"])
    assert raw == bytes([128, 0, 255, 255]) * 256
    png = base64.b64decode(result["image"]["png_base64"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">IIBBBBB", png[16:29]) == (16, 16, 8, 6, 0, 0, 0)
    assert result["image"]["png_sha256"] == "sha256:" + sha256(png).hexdigest()
    length = struct.unpack(">I", png[33:37])[0]
    scanlines = zlib.decompress(png[41:41 + length])
    assert scanlines == (b"\0" + bytes([128, 0, 255, 255]) * 16) * 16
    assert result["claims"] == CLAIMS
    assert result["shader"]["compilation"] == "not_performed"


def test_texture_uv_center_sampling_and_cpu_byte_exact_determinism():
    request = constant_texture(("u", "v", "0.5"))
    result = generate_texture(request)
    assert result == generate_texture(request)
    raw = np.frombuffer(base64.b64decode(result["image"]["rgba_base64"]), dtype=np.uint8).reshape(16, 16, 4)
    assert raw[0, 0].tolist() == [8, 8, 128, 255]
    assert raw[-1, -1].tolist() == [247, 247, 128, 255]
    assert raw[0, -1].tolist() == [247, 8, 128, 255]


def test_shader_source_is_generated_from_safe_ir_and_integer_power_semantics():
    request = constant_texture(("(-u)**2", "v", "max(u,v)"))
    result = generate_texture(request)
    shader = result["shader"]
    assert shader["language"] == "glsl_es_1.00"
    assert "attribute vec2 a_position" in shader["vertex_source"]
    assert "attribute vec2 a_uv" in shader["vertex_source"]
    assert "netPow2((-u))" in shader["fragment_source"]
    assert "precision highp float" in shader["fragment_source"]
    shader["fragment_source"] += "\nvoid injected(){}"
    seal(result)
    with pytest.raises(ValueError):
        validate_texture_result(request, result)


@pytest.mark.parametrize("group, key, value", [
    ("domain", "resolution", [15, 16]), ("domain", "resolution", [16, 257]),
    ("domain", "resolution", [True, 16]), ("domain", "units", "m"),
    ("domain", "frame", "procedural.local_xyz.v1"), ("domain", "bounds", [[-11, 1], [0, 1]]),
    ("definition", "expressions", ["u", "v"]), ("definition", "expressions", ["u", "v", "z"]),
    ("encoding", "channels", "rgb8"), ("encoding", "mapping", "unbounded"),
    ("verification", "byte_exact", 1), ("appearance", "roughness", 0.0),
])
def test_texture_declaration_profile_refusals(group, key, value):
    request = example_texture()
    request[group][key] = value
    with pytest.raises(ValueError):
        validate_texture_request(request)


def test_texture_parameter_changes_bind_bytes_and_typed_ir():
    request = example_texture()
    request["domain"]["resolution"] = [16, 16]
    first = generate_texture(request)
    request["definition"]["parameters"]["phase"]["value"] = 0.5
    second = generate_texture(request)
    assert first["request_digest"] != second["request_digest"]
    assert first["image"]["rgba_base64"] != second["image"]["rgba_base64"]
    assert first["ir"] != second["ir"]
    assert first["shader"]["fragment_source"] != second["shader"]["fragment_source"]


def test_texture_static_validation_evaluates_no_fields_or_gpu(monkeypatch):
    request = example_texture()
    result = generate_texture(request)
    monkeypatch.setattr("ciw.procedural_texture.evaluate_uv", lambda *a: pytest.fail("static evaluation"))
    monkeypatch.setattr("ciw.procedural_texture.generate_texture", lambda *a: pytest.fail("static generation"))
    assert validate_texture_request(request) == request
    assert validate_texture_result(request, result) == result


@pytest.mark.parametrize("mutation", [
    lambda r: r["image"].update(width=True), lambda r: r["image"].update(rgba_base64="bad="),
    lambda r: r["image"].update(png_sha256="sha256:" + "0" * 64),
    lambda r: r["image"]["encoding"].update(mapping="unbounded"),
    lambda r: r["ir"][0]["root"].update(op="unknown"),
    lambda r: r["shader"].update(compilation="performed"),
    lambda r: r["appearance"].update(metallic=True),
])
def test_texture_retained_binding_refusals(mutation):
    request = example_texture()
    result = generate_texture(request)
    mutation(result)
    seal(result)
    with pytest.raises(ValueError):
        validate_texture_result(request, result)


def test_maximum_texture_profile_stays_inside_artifact_budget():
    request = constant_texture()
    request["domain"]["resolution"] = [256, 256]
    result = generate_texture(request)
    assert len(base64.b64decode(result["image"]["rgba_base64"])) == 256 * 256 * 4


def test_maximum_surface_profile_stays_inside_declared_array_budgets():
    request = example_surface()
    request["domain"]["resolution"] = [48, 48]
    result = generate_surface(request)
    assert len(result["mesh"]["vertices"]) == 48 * 48
    assert len(result["mesh"]["triangles"]) == 2 * 48 * 48


@pytest.mark.parametrize("module, generator, example", [
    ("ciw.procedural_surface", generate_surface, example_surface),
    ("ciw.procedural_texture", generate_texture, example_texture),
])
def test_cooperative_representation_deadline_clean_refusal(monkeypatch, module, generator, example):
    clock = iter([0.0, 16.0])
    monkeypatch.setattr(module + ".monotonic", lambda: next(clock))
    with pytest.raises(ValueError, match="deadline"):
        generator(example())
