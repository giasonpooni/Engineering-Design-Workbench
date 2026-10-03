"""Independent geometry checks and the static/fresh authority boundary."""
from copy import deepcopy
import math

import pytest

from ciw.operations.runner import digest, seal
from ciw.procedural_compiler import generate
from ciw.procedural_contract import CLAIMS, example_request, validate_result
from ciw.procedural_verification import validate_report, verify


def request(expression="x", closed=False, resolution=8):
    result = example_request("sphere")
    result["definition"] = {"expression": expression, "parameters": {}}
    result["domain"]["resolution"] = resolution
    result["verification"] = {"field_tolerance": 0.05, "require_closed": closed}
    return result


def artifact(q, points, faces):
    n = q["domain"]["resolution"]
    side = n + 1
    sources = []
    for point in points:
        i, j, k = (round((coordinate + 1) * n / 2) for coordinate in point)
        node = (i * side + j) * side + k
        sources.append([node, node, 0.0])
    return seal({"schema": "ciw.procedural-mesh.v1", "request_digest": digest(q),
                 "mesh": {"vertices": points, "triangles": faces, "edge_sources": sources,
                          "units": q["domain"]["units"], "frame": q["domain"]["frame"]},
                 "appearance": deepcopy(q["appearance"]), "claims": deepcopy(CLAIMS)})


def reseal(record):
    return seal({name: value for name, value in record.items() if name != "record_digest"})


def checks(report):
    return {row["name"]: row for row in report["checks"]}


@pytest.fixture(scope="module")
def sphere():
    q = example_request("sphere")
    return q, generate(q)


def test_analytic_open_triangle_has_explicit_boundary():
    q = request()
    m = artifact(q, [[0, -1, -1], [0, 0, -1], [0, -1, 0]], [[0, 1, 2]])
    report = verify(q, m)
    assert report["status"] == "PASS"
    assert report["metrics"]["boundary_edge_count"] == 3
    assert report["metrics"]["surface_area"] == 0.5
    assert report["metrics"]["component_count"] == 1
    assert report["metrics"]["max_field_residual"] == 0
    assert report["claims"]["self_intersections"] == "not_checked"
    assert validate_report(q, m, report) == report


@pytest.mark.parametrize("amplitude", [1.0, 1e-12])
def test_winding_is_invariant_under_positive_field_rescaling(amplitude):
    q = request(f"{amplitude}*x")
    points = [[0, -1, -1], [0, 0, -1], [0, -1, 0]]
    assert verify(q, artifact(q, points, [[0, 1, 2]]))["status"] == "PASS"
    report = verify(q, artifact(q, points, [[0, 2, 1]]))
    assert checks(report)["increasing_field_winding"]["status"] == "FAIL"


def test_zero_gradient_does_not_establish_increasing_field_winding():
    q = request("x*x")
    m = artifact(q, [[0, -1, -1], [0, 0, -1], [0, -1, 0]], [[0, 1, 2]])
    report = verify(q, m)
    assert checks(report)["increasing_field_winding"]["status"] == "FAIL"


@pytest.mark.parametrize("profile", ["wave", "gyroid"])
def test_qualified_open_examples_pass_with_retained_boundary_counts(profile):
    q = example_request(profile)
    report = verify(q, generate(q))
    assert report["status"] == "PASS"
    assert report["metrics"]["boundary_edge_count"] > 0


def test_declared_binary64_lattice_is_used_at_resolution_24():
    q = example_request("sphere")
    q["domain"]["resolution"] = 24
    q["domain"]["bounds"] = [[-0.96, 1.01], [-0.91, 1.08], [-0.94, 1.02]]
    report = verify(q, generate(q))
    assert report["status"] == "PASS"


def test_closed_requirement_fails_for_clipped_surface():
    q = request(closed=True)
    m = artifact(q, [[0, -1, -1], [0, 0, -1], [0, -1, 0]], [[0, 1, 2]])
    report = verify(q, m)
    assert report["status"] == "FAIL"
    assert checks(report)["required_closed_surface"]["value"] == 3


def test_analytic_sphere_topology_area_and_sampling(sphere):
    q, m = sphere
    report = verify(q, m)
    assert report["status"] == "PASS"
    metrics = report["metrics"]
    assert metrics["boundary_edge_count"] == 0
    assert metrics["component_count"] == 1
    assert metrics["orientation_conflict_count"] == 0
    assert metrics["nonmanifold_edge_count"] == metrics["nonmanifold_vertex_count"] == 0
    assert 0.98 * 4 * math.pi * 0.7**2 < metrics["surface_area"] < 4 * math.pi * 0.7**2
    assert 0 < metrics["max_field_residual"] < q["verification"]["field_tolerance"]
    assert validate_report(q, m, report)["status"] == "PASS"


def test_sphere_refinement_reduces_sampled_residual_and_area_error():
    errors = []
    for resolution in (8, 16):
        q = example_request("sphere")
        q["domain"]["resolution"] = resolution
        report = verify(q, generate(q))
        errors.append((report["metrics"]["max_field_residual"],
                       abs(report["metrics"]["surface_area"] - 4 * math.pi * 0.7**2)))
    assert errors[1][0] < errors[0][0]
    assert errors[1][1] < errors[0][1]


def test_checker_never_invokes_extractor(sphere, monkeypatch):
    q, m = sphere
    def blocked(*args, **kwargs):
        raise AssertionError("extractor must not be used by verifier")
    monkeypatch.setattr("ciw.procedural_compiler.generate", blocked)
    assert verify(q, m)["status"] == "PASS"


def test_static_validator_does_not_evaluate_field_or_fresh_verify(sphere, monkeypatch):
    q, m = sphere
    report = verify(q, m)
    def blocked(*args, **kwargs):
        raise AssertionError("static validation activated a provider or expression")
    monkeypatch.setattr("ciw.procedural_verification.evaluate_field", blocked)
    monkeypatch.setattr("ciw.procedural_contract.evaluate_field", blocked)
    monkeypatch.setattr("ciw.procedural_compiler.generate", blocked)
    monkeypatch.setattr("ciw.procedural_verification.verify", blocked)
    assert validate_report(q, m, report) == report


def test_static_validator_returns_detached_record(sphere):
    q, m = sphere
    report = verify(q, m)
    detached = validate_report(q, m, report)
    detached["metrics"]["surface_area"] = 0
    assert report["metrics"]["surface_area"] > 0


@pytest.mark.parametrize("mutation,expected", [
    ("duplicate", "duplicate_triangles"),
    ("degenerate", "degenerate_triangles"),
    ("reverse_one", "orientation_conflicts"),
    ("reverse_all", "increasing_field_winding"),
    ("unused", "unused_vertices"),
    ("coincident", "coincident_vertices"),
    ("lineage_node", "lineage_grid_edges"),
    ("lineage_alpha", "lineage_root_interpolation"),
    ("coordinate", "lineage_coordinates"),
    ("outside", "vertices_in_domain"),
])
def test_coherently_sealed_candidate_forgery_is_detected(sphere, mutation, expected):
    q, original = sphere
    m = deepcopy(original)
    mesh = m["mesh"]
    if mutation == "duplicate":
        mesh["triangles"].append(mesh["triangles"][0][:])
    elif mutation == "degenerate":
        mesh["triangles"][0] = [0, 0, 0]
    elif mutation == "reverse_one":
        mesh["triangles"][0].reverse()
    elif mutation == "reverse_all":
        for triangle in mesh["triangles"]:
            triangle.reverse()
    elif mutation in {"unused", "coincident"}:
        mesh["vertices"].append(mesh["vertices"][0][:])
        mesh["edge_sources"].append(mesh["edge_sources"][0][:])
    elif mutation == "lineage_node":
        mesh["edge_sources"][0] = [0, (q["domain"]["resolution"] + 1)**3 - 1, 0.5]
    elif mutation == "lineage_alpha":
        source = next(source for source in mesh["edge_sources"] if source[0] != source[1])
        source[2] += 0.001 if source[2] < 0.99 else -0.001
    elif mutation == "coordinate":
        mesh["vertices"][0][0] += 0.001
    elif mutation == "outside":
        mesh["vertices"][0][0] = 1.01
    m = reseal(m)
    validate_result(q, m)
    report = verify(q, m)
    assert report["status"] == "FAIL"
    assert checks(report)[expected]["status"] == "FAIL"
    assert validate_report(q, m, report) == report


def test_field_residual_detects_vertices_off_the_declared_surface(sphere):
    q, m = sphere
    q = deepcopy(q)
    q["verification"]["field_tolerance"] = 0.001
    m = deepcopy(m)
    m["request_digest"] = digest(q)
    report = verify(q, reseal(m))
    assert checks(report)["sampled_field_residual"]["status"] == "FAIL"


def test_zero_node_source_needs_zero_field():
    q = request()
    m = artifact(q, [[0, -1, -1], [0, 0, -1], [0, -1, 0]], [[0, 1, 2]])
    m["mesh"]["edge_sources"][0] = [0, 0, 0.0]
    report = verify(q, reseal(m))
    assert checks(report)["lineage_root_interpolation"]["status"] == "FAIL"


def test_zero_node_source_requires_zero_alpha():
    q = request()
    m = artifact(q, [[0, -1, -1], [0, 0, -1], [0, -1, 0]], [[0, 1, 2]])
    m["mesh"]["edge_sources"][0][2] = 0.1
    report = verify(q, reseal(m))
    assert checks(report)["lineage_root_interpolation"]["status"] == "FAIL"


def test_nonmanifold_edge_and_vertex_links_are_checked():
    q = request()
    m = artifact(q, [[0, -1, -1], [0, 0, -1], [0, -1, 0], [0, 0, 0], [0, 1, 0]],
                 [[0, 1, 2], [1, 0, 3], [0, 1, 4]])
    report = verify(q, m)
    assert report["metrics"]["nonmanifold_edge_count"] == 1
    assert report["metrics"]["nonmanifold_vertex_count"] >= 2
    assert report["status"] == "FAIL"


def test_bowtie_vertex_detected_even_without_nonmanifold_edges():
    q = request()
    m = artifact(q, [[0, 0, 0], [0, 1, 0], [0, 0, 1], [0, -1, 0], [0, 0, -1]],
                 [[0, 1, 2], [0, 3, 4]])
    report = verify(q, m)
    assert report["metrics"]["nonmanifold_edge_count"] == 0
    assert report["metrics"]["nonmanifold_vertex_count"] == 1
    assert checks(report)["nonmanifold_vertices"]["status"] == "FAIL"


def test_disconnected_manifold_components_are_retained_not_falsely_joined():
    q = request()
    m = artifact(q, [[0, -1, -1], [0, -0.5, -1], [0, -1, -0.5],
                     [0, 0, 0], [0, 0.5, 0], [0, 0, 0.5]], [[0, 1, 2], [3, 4, 5]])
    report = verify(q, m)
    assert report["status"] == "PASS"
    assert report["metrics"]["component_count"] == 2


def test_coherent_report_forgery_needs_fresh_verification(sphere):
    q, m = sphere
    report = verify(q, m)
    forged = deepcopy(report)
    forged["metrics"]["max_field_residual"] = 0
    checks(forged)["sampled_field_residual"]["value"] = 0
    forged = reseal(forged)
    assert validate_report(q, m, forged) == forged
    assert verify(q, m)["record_digest"] != forged["record_digest"]


@pytest.mark.parametrize("name", ["physical_validation", "manufacturing", "continuous_fidelity", "self_intersections"])
def test_report_cannot_escalate_authority(sphere, name):
    q, m = sphere
    report = verify(q, m)
    report["claims"][name] = "established"
    with pytest.raises(ValueError):
        validate_report(q, m, reseal(report))


@pytest.mark.parametrize("mutation", ["candidate", "request", "seal", "status", "tolerance", "bbox", "count",
                                    "check_missing", "check_duplicate", "nan", "boolean", "metric_binding"])
def test_static_report_rejects_broken_declarations(sphere, mutation):
    q, m = sphere
    report = verify(q, m)
    if mutation in {"candidate", "request"}:
        report[mutation + "_digest"] = "sha256:" + "0" * 64
    elif mutation == "seal":
        report["record_digest"] = "sha256:" + "0" * 64
    elif mutation == "status":
        report["status"] = "FAIL"
    elif mutation == "tolerance":
        report["checks"][0]["tolerance"] = 1
    elif mutation == "bbox":
        report["metrics"]["bounding_box"][0][0] -= 0.001
    elif mutation == "count":
        report["metrics"]["vertex_count"] -= 1
    elif mutation == "check_missing":
        report["checks"].pop()
    elif mutation == "check_duplicate":
        report["checks"][-1] = deepcopy(report["checks"][0])
    elif mutation == "nan":
        report["metrics"]["surface_area"] = float("nan")
    elif mutation == "boolean":
        report["metrics"]["component_count"] = True
    elif mutation == "metric_binding":
        report["metrics"]["duplicate_triangle_count"] = 1
    if mutation != "seal" and mutation != "nan":
        report = reseal(report)
    with pytest.raises(ValueError):
        validate_report(q, m, report)
