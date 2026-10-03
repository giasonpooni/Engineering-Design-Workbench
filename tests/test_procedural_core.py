"""Public bounded-notation and analytic geometry qualification."""
from copy import deepcopy
from collections import Counter
import math

import numpy as np
import pytest

from ciw.operations.runner import digest, seal
from ciw.procedural_compiler import generate
from ciw.procedural_contract import (CLAIMS, evaluate, evaluate_field, example_request,
                                     parse_expression, request_digest, validate_request,
                                     validate_result)


def plane_request(expression="z", resolution=8):
    request = example_request("wave")
    request["definition"] = {"expression": expression, "parameters": {}}
    request["domain"]["resolution"] = resolution
    return request


@pytest.mark.parametrize("expression, expected", [
    ("x+y-z", 0.0), ("-x + +y", 1.0), ("x*y/z", 2.0 / 3.0),
    ("x**0+y**2-z**1", 2.0), ("min(x,y)+max(y,z)", 4.0),
    ("sqrt(y*y)+abs(-z)", 5.0), ("sin(0)+cos(0)", 1.0),
])
def test_scalar_notation_analytic_values(expression, expected):
    assert evaluate(expression, {}, 1.0, 2.0, 3.0) == pytest.approx(expected)


def test_vector_broadcast_and_declared_parameter_values():
    parameters = {"a": {"value": 0.3, "minimum": 0.1, "maximum": 1.0}}
    x = np.array([0.0, math.pi / 2.0, math.pi])
    result = evaluate("a*sin(x)+z", parameters, x, 0.0, 2.0)
    np.testing.assert_allclose(result, [2.0, 2.3, 2.0], atol=1e-15)
    assert result.shape == x.shape
    np.testing.assert_array_equal(evaluate("1", {}, x, 0, 0), np.ones(3))


@pytest.mark.parametrize("coordinates", [
    (np.zeros(200001), 0, 0), (np.zeros((501, 1)), np.zeros((1, 501)), 0),
    (np.zeros(2), np.zeros(3), 0), (10 ** 1000, 0, 0),
])
def test_interpreter_rejects_coordinate_and_broadcast_resource_overruns(coordinates):
    with pytest.raises(ValueError):
        evaluate("x", {}, *coordinates)


@pytest.mark.parametrize("coordinate", [True, "1", np.array([1 + 2j]), np.array(["1"]), np.array([True])])
def test_interpreter_refuses_implicit_boolean_text_or_complex_coordinates(coordinate):
    with pytest.raises(ValueError):
        evaluate("x", {}, coordinate, 0, 0)


@pytest.mark.parametrize("expression", [
    "__import__('os').system('true')", "x.__class__", "x[0]", "[x]", "{x}",
    "(lambda: 1)()", "[i for i in x]", "x if y else z", "x < y", "x and y",
    "x//2", "x%2", "x**y", "x**-1", "x**7", "x**2.0", "sin(x,y)",
    "min(x)", "max(x,y,z)", "sqrt(x=x)", "sin(*x)", "unknown(x)", "unknown",
    "True", "None", "1j", "float('nan')", "1e309", "1000001", "'x'", "",
    "x; y", "(x := 1)", "9" * 1000, "1e-400", "1_0e-400", "1e-99999999999999999999999",
])
def test_unsupported_notation_refused(expression):
    with pytest.raises(ValueError):
        parse_expression(expression)


@pytest.mark.parametrize("expression", ["x" * 1025, "+" * 100 + "x", "+".join(["x"] * 60)])
def test_notation_expression_tree_budgets(expression):
    with pytest.raises(ValueError):
        parse_expression(expression)


@pytest.mark.parametrize("expression", ["1/0", "sqrt(-1)", "x**6", "1/(x-x)", "1000000*1000000"])
def test_nonfinite_undefined_or_overbudget_field_refused(expression):
    with pytest.raises(ValueError):
        evaluate(expression, {}, 100.0, 0.0, 0.0)


def test_undefined_field_at_one_vector_sample_refuses_entire_field():
    with pytest.raises(ValueError):
        evaluate("sqrt(x)", {}, np.array([1.0, -1.0]), 0.0, 0.0)


@pytest.mark.parametrize("profile", ["gyroid", "sphere", "wave"])
def test_examples_are_detached_strict_requests(profile):
    original = example_request(profile)
    detached = validate_request(original)
    detached["domain"]["bounds"][0][0] = -2
    assert original["domain"]["bounds"][0][0] == -1
    assert request_digest(original) == digest(original)


def test_unknown_example_profile_refused():
    with pytest.raises(ValueError):
        example_request("material")


@pytest.mark.parametrize("path, value", [
    (("schema",), "bad"), (("domain", "resolution"), 7), (("domain", "resolution"), 25),
    (("domain", "resolution"), True), (("domain", "resolution"), 8.0),
    (("domain", "units"), "m"), (("domain", "frame"), "world"),
    (("domain", "bounds"), [[0, 0.09], [-1, 1], [-1, 1]]),
    (("domain", "bounds"), [[-11, 1], [-1, 1], [-1, 1]]),
    (("domain", "bounds"), [[1, -1], [-1, 1], [-1, 1]]),
    (("domain", "bounds"), [[-1, 1]]),
    (("surface", "isovalue"), 1), (("surface", "isovalue"), True),
    (("surface", "convention"), "positive_inside"),
    (("appearance", "base_color"), [0, 0]), (("appearance", "base_color"), [0, 0, 1.1]),
    (("appearance", "roughness"), 0.04), (("appearance", "metallic"), -1),
    (("verification", "field_tolerance"), 0.0001),
    (("verification", "field_tolerance"), 2.1), (("verification", "require_closed"), 1),
    (("definition", "expression"), "import os"),
    (("definition", "parameters"), {"x": {"value": 1, "minimum": 0, "maximum": 2}}),
    (("definition", "parameters"), {"sin": {"value": 1, "minimum": 0, "maximum": 2}}),
    (("definition", "parameters"), {"é": {"value": 1, "minimum": 0, "maximum": 2}}),
    (("definition", "parameters"), {"r": {"value": 3, "minimum": 0, "maximum": 2}}),
    (("definition", "parameters"), {"r": {"value": 1, "minimum": 2, "maximum": 0}}),
])
def test_request_boundary_refuses_invalid_declarations(path, value):
    request = example_request("sphere")
    parent = request
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize("group", [None, "definition", "domain", "surface", "appearance", "verification"])
def test_unknown_request_fields_refused(group):
    request = example_request("sphere")
    parent = request if group is None else request[group]
    parent["extra"] = 1
    with pytest.raises(ValueError):
        validate_request(request)


def test_more_than_eight_parameters_refused():
    request = plane_request()
    request["definition"]["parameters"] = {f"p{i}": {"value": 0, "minimum": -1, "maximum": 1} for i in range(9)}
    with pytest.raises(ValueError):
        validate_request(request)


def test_static_request_validation_does_not_evaluate_undefined_fields(monkeypatch):
    request = plane_request("1/0")
    monkeypatch.setattr("ciw.procedural_contract.evaluate", lambda *args: pytest.fail("static validation evaluated"))
    assert validate_request(request) == request


def test_exact_zero_plane_is_welded_oriented_and_analytic():
    request = plane_request("z")
    result = generate(request)
    vertices = np.asarray(result["mesh"]["vertices"])
    faces = np.asarray(result["mesh"]["triangles"])
    assert len(vertices) == 81
    assert len(faces) == 128
    np.testing.assert_array_equal(vertices[:, 2], np.zeros(len(vertices)))
    assert all(source[0] == source[1] and source[2] == 0 for source in result["mesh"]["edge_sources"])
    normals = np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]], vertices[faces[:, 2]] - vertices[faces[:, 0]])
    assert np.all(normals[:, 2] > 0)
    assert np.linalg.norm(normals, axis=1).sum() / 2 == pytest.approx(4.0)
    edges = Counter(tuple(sorted((face[a], face[b]))) for face in faces for a, b in ((0, 1), (1, 2), (2, 0)))
    assert Counter(edges.values()) == {2: 176, 1: 32}


@pytest.mark.parametrize("expression", ["x", "y", "z", "x+y+z", "x+y", "x-y", "-z", "2*x-y+z"])
def test_exact_zero_grid_intersections_have_no_duplicate_or_zero_area_faces(expression):
    result = generate(plane_request(expression))
    vertices = np.asarray(result["mesh"]["vertices"])
    faces = result["mesh"]["triangles"]
    assert len({tuple(vertex) for vertex in vertices}) == len(vertices)
    assert len({tuple(sorted(face)) for face in faces}) == len(faces)
    residuals = evaluate(expression, {}, vertices[:, 0], vertices[:, 1], vertices[:, 2])
    assert np.max(np.abs(residuals)) <= 2e-15
    for face in faces:
        p0, p1, p2 = vertices[face]
        assert np.linalg.norm(np.cross(p1 - p0, p2 - p0)) > 0


def sphere_errors(resolution):
    request = example_request("sphere")
    request["domain"]["resolution"] = resolution
    result = generate(request)
    vertices = np.asarray(result["mesh"]["vertices"])
    faces = np.asarray(result["mesh"]["triangles"])
    radius = request["definition"]["parameters"]["r"]["value"]
    area = np.linalg.norm(np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]], vertices[faces[:, 2]] - vertices[faces[:, 0]]), axis=1).sum() / 2
    return result, float(np.max(np.abs(np.linalg.norm(vertices, axis=1) - radius))), abs(area - 4 * math.pi * radius ** 2)


def test_sphere_analytic_refinement_area_radius_and_closed_topology():
    coarse, coarse_radius, coarse_area = sphere_errors(8)
    fine, fine_radius, fine_area = sphere_errors(16)
    assert fine_radius < coarse_radius / 3
    assert fine_area < coarse_area / 3
    assert fine_radius < 0.01
    assert fine_area < 0.1
    for result in (coarse, fine):
        edges = Counter(tuple(sorted((face[a], face[b]))) for face in result["mesh"]["triangles"] for a, b in ((0, 1), (1, 2), (2, 0)))
        assert set(edges.values()) == {2}
        vertices = np.asarray(result["mesh"]["vertices"])
        for face in result["mesh"]["triangles"]:
            p0, p1, p2 = vertices[face]
            assert np.dot(np.cross(p1 - p0, p2 - p0), (p0 + p1 + p2) / 3) > 0


@pytest.mark.parametrize("profile", ["sphere", "wave", "gyroid"])
def test_generation_deterministic_and_sealed_visual_only(profile):
    request = example_request(profile)
    request["domain"]["resolution"] = 8
    first, second = generate(request), generate(request)
    assert first == second
    assert first["claims"] == CLAIMS
    assert first["request_digest"] == digest(request)
    assert validate_result(request, first) == first
    assert first["record_digest"] == digest({key: value for key, value in first.items() if key != "record_digest"})


@pytest.mark.parametrize("profile", ["sphere", "wave", "gyroid"])
def test_default_examples_pass_the_independent_geometry_verifier(profile):
    from ciw.procedural_verification import verify
    request = example_request(profile)
    report = verify(request, generate(request))
    assert report["status"] == "PASS", report["checks"]


@pytest.mark.parametrize("expression", ["1", "-1", "0", "x*x+y*y+z*z+1", "sqrt(-1)", "1/0"])
def test_empty_or_undefined_surfaces_refused(expression):
    with pytest.raises(ValueError):
        generate(plane_request(expression))


def test_cooperative_extraction_deadline_refuses_without_retained_artifact(monkeypatch):
    clock = iter([0.0, 16.0])
    monkeypatch.setattr("ciw.procedural_compiler.monotonic", lambda: next(clock))
    with pytest.raises(ValueError, match="deadline"):
        generate(plane_request())


def test_static_result_validation_does_not_evaluate_or_generate(monkeypatch):
    request = plane_request()
    result = generate(request)
    monkeypatch.setattr("ciw.procedural_contract.evaluate", lambda *args: pytest.fail("static check evaluated"))
    monkeypatch.setattr("ciw.procedural_compiler.generate", lambda *args: pytest.fail("static check generated"))
    detached = validate_result(request, result)
    detached["mesh"]["vertices"][0][0] = 3
    assert result["mesh"]["vertices"][0][0] != 3


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(schema="bad"), lambda r: r.update(request_digest="sha256:" + "0" * 64),
    lambda r: r["claims"].update(physical_validation="validated"),
    lambda r: r["mesh"].update(units="m"), lambda r: r["mesh"].update(frame="world"),
    lambda r: r["mesh"]["vertices"][0].append(1),
    lambda r: r["mesh"]["vertices"][0].__setitem__(0, float("inf")),
    lambda r: r["mesh"]["triangles"][0].__setitem__(0, -1),
    lambda r: r["mesh"]["triangles"][0].__setitem__(0, True),
    lambda r: r["mesh"]["triangles"][0].__setitem__(0, 999999),
    lambda r: r["mesh"]["edge_sources"][0].__setitem__(0, -1),
    lambda r: r["mesh"]["edge_sources"][0].__setitem__(2, 1.1),
    lambda r: r["mesh"]["edge_sources"].pop(),
])
def test_result_shape_bindings_and_lineage_bounds_refused(mutation):
    request = plane_request()
    result = generate(request)
    mutation(result)
    # Coherently recomputed content seals cannot bless invalid data contracts.
    if not any(math.isinf(coordinate) for vertex in result["mesh"]["vertices"] for coordinate in vertex):
        seal(result)
    with pytest.raises(ValueError):
        validate_result(request, result)


def test_unsealed_result_corruption_refused():
    request = plane_request()
    result = generate(request)
    result["mesh"]["vertices"][0][0] += 0.1
    with pytest.raises(ValueError):
        validate_result(request, result)


def test_retained_boolean_material_parameter_cannot_masquerade_as_one():
    request = plane_request()
    request["appearance"]["metallic"] = 1.0
    result = generate(request)
    result["appearance"]["metallic"] = True
    seal(result)
    with pytest.raises(ValueError):
        validate_result(request, result)


def test_coherent_geometry_mutation_is_deferred_to_independent_verification():
    request = plane_request()
    result = generate(request)
    result["mesh"]["vertices"][0][2] = 0.3
    seal(result)
    assert validate_result(request, result) == result


def test_parameter_and_appearance_changes_bind_generated_artifacts():
    request = example_request("sphere")
    request["domain"]["resolution"] = 8
    first = generate(request)
    request["definition"]["parameters"]["r"]["value"] = 0.6
    second = generate(request)
    assert first["request_digest"] != second["request_digest"]
    assert first["mesh"] != second["mesh"]
    request["appearance"]["metallic"] = 1.0
    third = generate(request)
    assert third["mesh"] == second["mesh"]
    assert third["record_digest"] != second["record_digest"]


def test_field_point_array_budget_and_analytic_values():
    request = example_request("sphere")
    values = evaluate_field(request, [[0, 0, 0], [0.7, 0, 0]])
    np.testing.assert_allclose(values, [-0.49, 0], atol=1e-15)
    with pytest.raises(ValueError):
        evaluate_field(request, [[0, 0]])
    with pytest.raises(ValueError):
        evaluate_field(request, [["0", "0", "0"]])
