"""Finite SI transfer conservation, rigid motion and uncertainty audits."""
from copy import deepcopy
import numpy as np
import pytest

from ciw import fluid_coupling as coupling
from ciw.operations.runner import seal


def test_default_force_moment_power_and_virtual_work():
    request = coupling.example_request()
    result = coupling.transfer(request)
    report = coupling.verify(request, result)
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == "LOCAL"
    assert report["qualification"]["coupled_model_qualified"] is False
    assert report["qualification"]["physical_validation_established"] is False
    data = result["data"]
    assert np.sum(data["structural_forces_n"], axis=0) == pytest.approx([-0.4, 8.0, 1.3])
    assert data["structural_power_w"] == pytest.approx(1.8)
    assert data["fluid_reaction_power_w"] == pytest.approx(-1.8)
    assert data["structural_virtual_work_j"] == pytest.approx(0.018)
    assert data["face_virtual_work_j"] == pytest.approx(0.018)
    assert coupling.validate_report(request, result, report) == report


def test_translation_and_moment_origin_invariance():
    request = coupling.example_request()
    baseline = coupling.transfer(request)
    shift = np.array([150.0, -20.0, 8.0])
    for field in ("fluid_face_centroids_m", "structural_nodes_m"):
        request["geometry"][field] = (np.asarray(request["geometry"][field]) + shift).tolist()
    request["geometry"]["moment_origin_m"] = shift.tolist()
    translated = coupling.transfer(request)
    assert translated["data"] == baseline["data"]
    assert coupling.verify(request, translated)["status"] == "PASS"
    # Constant rigid translation must map to every face unchanged.
    request["structure"]["displacements_m"] = [[0.03, -0.04, 0.02]] * 3
    request["structure"]["velocities_m_per_s"] = [[1.0, 2.0, 3.0]] * 3
    translated = coupling.transfer(request)
    assert translated["data"]["mapped_face_displacements_m"] == pytest.approx(np.array([[0.03, -0.04, 0.02]] * 2))
    assert translated["data"]["mapped_face_velocities_m_per_s"] == pytest.approx(np.array([[1.0, 2.0, 3.0]] * 2))


def test_rigid_rotation_reproduction_and_rotated_coordinate_covariance():
    request = coupling.example_request()
    omega = np.array([0.1, 0.2, 0.3])
    nodes, faces = np.asarray(request["geometry"]["structural_nodes_m"]), np.asarray(request["geometry"]["fluid_face_centroids_m"])
    request["structure"]["velocities_m_per_s"] = np.cross(omega, nodes).tolist()
    result = coupling.transfer(request)
    assert result["data"]["mapped_face_velocities_m_per_s"] == pytest.approx(np.cross(omega, faces))
    assert coupling.verify(request, result)["status"] == "PASS"
    rotation = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    rotated = deepcopy(request)
    for field in ("fluid_face_centroids_m", "fluid_face_normals", "structural_nodes_m"):
        rotated["geometry"][field] = (np.asarray(rotated["geometry"][field]) @ rotation.T).tolist()
    rotated["fluid"]["traction_pa"] = (np.asarray(rotated["fluid"]["traction_pa"]) @ rotation.T).tolist()
    for field in ("displacements_m", "velocities_m_per_s"):
        rotated["structure"][field] = (np.asarray(rotated["structure"][field]) @ rotation.T).tolist()
    face_rotation = np.kron(np.eye(2), rotation)
    rotated["uncertainty"]["traction_covariance_pa2"] = (face_rotation @ np.asarray(request["uncertainty"]["traction_covariance_pa2"]) @ face_rotation.T).tolist()
    transformed = coupling.transfer(rotated)
    assert transformed["data"]["structural_forces_n"] == pytest.approx(np.asarray(result["data"]["structural_forces_n"]) @ rotation.T)
    node_rotation = np.kron(np.eye(3), rotation)
    expected_covariance = node_rotation @ np.asarray(result["uncertainty"]["structural_force_covariance_n2"]) @ node_rotation.T
    assert transformed["uncertainty"]["structural_force_covariance_n2"] == pytest.approx(expected_covariance)
    assert transformed["data"]["structural_power_w"] == pytest.approx(result["data"]["structural_power_w"])
    assert coupling.verify(rotated, transformed)["status"] == "PASS"


def test_full_correlated_covariance_propagation():
    request = coupling.example_request()
    generator = np.array([[1, 0], [0, 2], [2, 1], [1, 1], [-1, 2], [3, -1]], dtype=float)
    covariance = generator @ generator.T
    request["uncertainty"]["traction_covariance_pa2"] = covariance.tolist()
    result = coupling.transfer(request)
    p = np.array([[0.5, 0.5, 0], [0, 0.5, 0.5]])
    b = np.kron(p.T * np.array([0.2, 0.3]), np.eye(3))
    expected = b @ covariance @ b.T
    assert result["uncertainty"]["structural_force_covariance_n2"] == pytest.approx(expected)
    assert np.min(np.linalg.eigvalsh(expected)) > -1e-14
    assert expected[0, 6] != 0  # Full cross-face correlations are retained.
    assert coupling.verify(request, result)["status"] == "PASS"


@pytest.mark.parametrize("mutation", [
    lambda r: r["mapping"]["face_motion_from_structure"][0].__setitem__(0, 0.4),
    lambda r: r["geometry"]["fluid_face_centroids_m"][0].__setitem__(1, 0.1),
    lambda r: r["geometry"]["fluid_face_normals"][0].__setitem__(1, 0.5),
    lambda r: r["geometry"]["fluid_face_areas_m2"].__setitem__(0, -0.2),
    lambda r: r["clock"].update(structural_time_s=0.2),
    lambda r: r["clock"].update(structural_clock_id="different-clock"),
    lambda r: r["clock"].update(structural_step=11),
    lambda r: r["clock"].update(structural_iteration=3),
    lambda r: r["clock"].update(structural_step=True),
    lambda r: r["fluid"].update(frame_id="different-frame"),
    lambda r: r["orientation"].update(traction_convention="opposite_unsigned_pressure"),
    lambda r: r["structure"]["velocities_m_per_s"].pop(),
    lambda r: r["fluid"]["traction_pa"][0].__setitem__(0, True),
    lambda r: r["uncertainty"]["traction_covariance_pa2"][0].__setitem__(0, -1),
    lambda r: r["uncertainty"]["traction_covariance_pa2"][0].__setitem__(1, 0.1),
    lambda r: r["uncertainty"]["traction_covariance_pa2"].pop(),
])
def test_mismatched_geometry_clocks_shapes_and_covariance_refused(mutation):
    request = coupling.example_request()
    mutation(request)
    with pytest.raises(ValueError):
        coupling.validate_request(request)


def test_indefinite_covariance_with_nonnegative_diagonal_refused():
    request = coupling.example_request()
    request["uncertainty"]["traction_covariance_pa2"][0][1] = 10.0
    request["uncertainty"]["traction_covariance_pa2"][1][0] = 10.0
    with pytest.raises(ValueError, match="positive semidefinite"):
        coupling.transfer(request)


def test_mixed_variance_indefiniteness_cannot_hide_below_global_eigen_tolerance():
    request = coupling.example_request()
    covariance = np.eye(6)
    covariance[0, 0] = 1e-16
    covariance[0, 1] = covariance[1, 0] = 2e-8
    request["uncertainty"]["traction_covariance_pa2"] = covariance.tolist()
    # The normalized 2x2 block [[1,2],[2,1]] is materially indefinite despite
    # the raw negative eigenvalue being tiny compared with the other variances.
    with pytest.raises(ValueError, match="positive semidefinite"):
        coupling.validate_request(request)


def test_zero_variance_axes_require_exactly_zero_cross_covariance():
    request = coupling.example_request()
    covariance = np.eye(6)
    covariance[0, 0] = 0.0
    covariance[0, 1] = covariance[1, 0] = 1e-30
    request["uncertainty"]["traction_covariance_pa2"] = covariance.tolist()
    with pytest.raises(ValueError, match="zero-variance"):
        coupling.validate_request(request)
    covariance[0, 1] = covariance[1, 0] = 0.0
    request["uncertainty"]["traction_covariance_pa2"] = covariance.tolist()
    result = coupling.transfer(request)
    assert coupling.verify(request, result)["status"] == "PASS"


@pytest.mark.parametrize("scale", [1e-14, 1e-50])
def test_zeroed_tiny_loads_motion_and_work_are_rejected_without_unit_floors(scale):
    request = coupling.example_request()
    request["fluid"]["traction_pa"] = (np.asarray(request["fluid"]["traction_pa"]) * scale).tolist()
    for field in ("displacements_m", "velocities_m_per_s"):
        request["structure"][field] = (np.asarray(request["structure"][field]) * scale).tolist()
    result = coupling.transfer(request)
    assert coupling.verify(request, result)["status"] == "PASS"
    for field in coupling.VECTOR_FIELDS:
        result["data"][field] = np.zeros_like(result["data"][field]).tolist()
    for field in coupling.SCALAR_FIELDS:
        result["data"][field] = 0.0
    report = coupling.verify(request, seal(result))
    assert report["status"] == "FAIL"
    failed = {row["name"] for row in report["checks"] if row["status"] == "FAIL"}
    assert {"force_mapping", "motion_mapping", "total_force", "total_moment"} <= failed
    coupling.validate_report(request, seal(result), report)


def test_tiny_displacements_are_audited_separately_from_large_velocities():
    request = coupling.example_request()
    request["structure"]["displacements_m"] = (np.asarray(request["structure"]["displacements_m"]) * 1e-14).tolist()
    result = coupling.transfer(request)
    result["data"]["mapped_face_displacements_m"] = np.zeros((2, 3)).tolist()
    result["data"]["face_virtual_work_j"] = 0.0
    report = coupling.verify(request, seal(result))
    assert report["status"] == "FAIL"
    assert next(row for row in report["checks"] if row["name"] == "motion_mapping")["value"] == pytest.approx(1.0)


def test_tiny_geometry_cannot_hide_a_full_coordinate_reproduction_error():
    request = coupling.example_request()
    for field in ("fluid_face_centroids_m", "structural_nodes_m"):
        request["geometry"][field] = (np.asarray(request["geometry"][field]) * 1e-14).tolist()
    request["geometry"]["fluid_face_centroids_m"][0][1] = 1e-14
    with pytest.raises(ValueError, match="coordinate reproduction"):
        coupling.validate_request(request)
    request["geometry"]["moment_origin_m"] = [100.0, 0.0, 0.0]
    with pytest.raises(ValueError, match="coordinate reproduction"):
        coupling.validate_request(request)


def test_resealed_incorrect_forces_motion_power_and_covariance_fail():
    request = coupling.example_request()
    result = coupling.transfer(request)
    result["data"]["structural_forces_n"][0][1] += 0.3
    result["data"]["mapped_face_velocities_m_per_s"][0][1] += 0.1
    result["uncertainty"]["structural_force_covariance_n2"][0][0] = -1.0
    result = seal(result)
    coupling.validate_result(request, result)
    report = coupling.verify(request, result)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    failed = {row["name"] for row in report["checks"] if row["status"] == "FAIL"}
    assert {"force_mapping", "motion_mapping", "total_force", "interface_power", "covariance_propagation", "covariance_psd_deficit"} <= failed
    coupling.validate_report(request, result, report)


def test_zero_uncertainty_and_absence_do_not_invent_covariance():
    request = coupling.example_request()
    request["uncertainty"]["traction_covariance_pa2"] = None
    result = coupling.transfer(request)
    assert result["uncertainty"]["structural_force_covariance_n2"] is None
    assert coupling.verify(request, result)["status"] == "PASS"
    result["uncertainty"]["structural_force_covariance_n2"] = np.zeros((9, 9)).tolist()
    with pytest.raises(ValueError, match="invent or discard"):
        coupling.validate_result(request, seal(result))
    request["uncertainty"]["traction_covariance_pa2"] = np.zeros((6, 6)).tolist()
    result = coupling.transfer(request)
    assert coupling.verify(request, result)["status"] == "PASS"
    result["uncertainty"]["structural_force_covariance_n2"][0][0] = 1e-30
    assert coupling.verify(request, seal(result))["status"] == "FAIL"


def test_fresh_verifier_does_not_replay_transfer_and_static_report_does_not_verify(monkeypatch):
    request = coupling.example_request()
    result = coupling.transfer(request)
    def forbidden(*args, **kwargs):
        raise AssertionError("Forbidden execution during independent or static validation")
    monkeypatch.setattr(coupling, "transfer", forbidden)
    report = coupling.verify(request, result)
    assert report["status"] == "PASS"
    monkeypatch.setattr(coupling, "_independent_values", forbidden)
    coupling.validate_report(request, result, report)


def test_static_archive_validation_never_factorizes_covariance(monkeypatch):
    request = coupling.example_request()
    result = coupling.transfer(request)
    report = coupling.verify(request, result)
    def forbidden(*args, **kwargs):
        raise AssertionError("Static archive validation refreshed numerical covariance execution")
    for function in ("eigvalsh", "eigh", "cholesky"):
        monkeypatch.setattr(np.linalg, function, forbidden)
    monkeypatch.setattr(coupling, "transfer", forbidden)
    monkeypatch.setattr(coupling, "verify", forbidden)
    coupling.validate_request(request, check_psd=False)
    coupling.validate_result(request, result)
    coupling.validate_report(request, result, report)


def test_static_declaration_does_not_claim_fresh_psd_eligibility():
    request = coupling.example_request()
    covariance = np.eye(6)
    covariance[0, 1] = covariance[1, 0] = 2.0
    request["uncertainty"]["traction_covariance_pa2"] = covariance.tolist()
    assert coupling.validate_request(request, check_psd=False) == request
    with pytest.raises(ValueError, match="positive semidefinite"):
        coupling.transfer(request)


def test_resealed_false_report_qualification_refused():
    request = coupling.example_request()
    result = coupling.transfer(request)
    report = coupling.verify(request, result)
    report["qualification"]["coupled_model_qualified"] = True
    with pytest.raises(ValueError, match="qualification"):
        coupling.validate_report(request, result, seal(report))
