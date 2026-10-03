"""Bounded work-conjugate SI interface map for separately qualified solvers.

P maps structural nodal motion to fluid-face motion. Loads use its weighted
transpose: f_s=P.T A traction. Partition of unity conserves total force; linear
coordinate reproduction conserves moment and infinitesimal rigid-body motion.
The transpose relation preserves interface power and virtual work algebraically.
This module supplies no CFD or constitutive model, time interpolation, global
coupling convergence guarantee, experimental validation or state admission.

Primary coupling-library background (consulted 2026-10-03):
https://precice.org/configuration-mapping.html
https://precice.org/doxygen/main/classprecice_1_1mapping_1_1Mapping.html
The explicit transpose and moment checks here are this instrument's finite
algebraic contract; use of those pages does not claim a preCICE runtime binding.
"""
from __future__ import annotations

from copy import deepcopy
import numpy as np

from .control_contracts import json_tree, keys, number, text
from .operations.runner import check_seal, digest, seal

REQUEST_SCHEMA = "ciw.fluid-interface-request.v1"
RESULT_SCHEMA = "ciw.fluid-interface-result.v1"
REPORT_SCHEMA = "ciw.fluid-interface-verification.v1"
CLAIM_SCOPE = "finite_si_work_conjugate_face_traction_structural_motion_transfer"
MAX_POINTS = 32
HARD_GEOMETRY_TOLERANCE = 1e-10
FRAME_AXES = "right_handed_cartesian_xyz"
ORIENTATION = {"normal_convention": "outward_from_fluid_into_structure",
               "traction_convention": "force_of_fluid_on_structure",
               "power_convention": "positive_into_structure"}
UNITS = {"fluid_face_forces_n": "N", "fluid_reaction_forces_n": "N", "structural_forces_n": "N",
         "mapped_face_displacements_m": "m", "mapped_face_velocities_m_per_s": "m/s",
         "structural_power_w": "W", "fluid_reaction_power_w": "W",
         "structural_virtual_work_j": "J", "face_virtual_work_j": "J",
         "structural_force_covariance_n2": "N^2"}
VECTOR_FIELDS = ("fluid_face_forces_n", "fluid_reaction_forces_n", "structural_forces_n",
                 "mapped_face_displacements_m", "mapped_face_velocities_m_per_s")
SCALAR_FIELDS = ("structural_power_w", "fluid_reaction_power_w", "structural_virtual_work_j", "face_virtual_work_j")
CHECK_NAMES = {"partition_unity", "coordinate_reproduction", "clock_skew_s", "force_mapping",
               "motion_mapping", "total_force", "total_moment", "interface_power", "virtual_work",
               "reported_power_work", "covariance_propagation", "covariance_psd_deficit"}
LIMITATIONS = [
    "Only a finite supplied SI interface geometry and mapping are qualified; fluid and structural solvers retain their own physics and must be qualified separately.",
    "Traction is an already signed force-per-area vector exerted by fluid on structure; declared unit normals point outward from fluid into structure. No pressure/stress-to-traction conversion is inferred.",
    "P uses the same fixed geometry for motion and weighted transpose loads; geometry and mapping must be re-declared and re-verified after deformation or remeshing.",
    "Linear reproduction preserves infinitesimal rigid rotation and total moment on this supplied geometry, not an arbitrary finite-rotation or nonlinear structural law.",
    "Clock compatibility is checked against supplied common-clock sample declarations; no acquisition synchronization, interpolation, external clock authentication or lag stability is established.",
    "Virtual work is force dotted with supplied displacement; it is not accumulated physical energy unless a separately qualified temporal/load integration supplies that interpretation.",
    "Only the declared traction covariance is propagated; geometric, map, constitutive and clock uncertainty are absent rather than proven negligible.",
    "No coupled-model convergence, experimental validation, solver activation, hardware operation or canonical state admission occurs.",
]


def _bounded(value, lower, upper, label):
    value = number(value)
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be inside {lower}..{upper}")
    return value


def _matrix(values, rows, columns, bound, label):
    if type(values) is not list or len(values) != rows:
        raise ValueError(f"{label} has an unsupported row count")
    for row in values:
        if type(row) is not list or len(row) != columns:
            raise ValueError(f"{label} has an unsupported column count")
        for value in row:
            _bounded(value, -bound, bound, label)
    return np.asarray(values, dtype=float)


def _covariance(value, dimension, label, *, check_psd=True):
    if value is None:
        return None
    matrix = _matrix(value, dimension, dimension, 1e24, label)
    symmetry, deficit = _correlation_psd_metrics(matrix, check_psd=check_psd)
    if symmetry > 1e-12:
        raise ValueError(f"{label} must be symmetric after diagonal normalization")
    if deficit > 1e-12:
        raise ValueError(f"{label} must be positive semidefinite after diagonal normalization; zero-variance axes require exact zero rows")
    return matrix


def _correlation_psd_metrics(matrix, *, check_psd=True):
    """Variance-scale-independent covariance eligibility, including singular axes.

    A global raw eigenvalue tolerance can hide a materially indefinite tiny-
    variance block. Congruence by positive standard deviations instead tests
    the dimensionless correlation block. Exactly zero variance mathematically
    requires exactly zero cross-covariance; no absolute noise floor admits it.
    """
    diagonal = np.diag(matrix)
    if np.any(diagonal < 0.0):
        return 0.0, 1e100
    zero = diagonal == 0.0
    if np.any(matrix[zero, :] != 0.0) or np.any(matrix[:, zero] != 0.0):
        return 0.0, 1e100
    active = ~zero
    if not np.any(active):
        return 0.0, 0.0
    standard_deviations = np.sqrt(diagonal[active])
    # Divide sequentially rather than multiplying tiny standard deviations,
    # whose product can underflow even when each normalized entry is finite.
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        correlation = matrix[np.ix_(active, active)] / standard_deviations[:, None] / standard_deviations[None, :]
    if not np.all(np.isfinite(correlation)):
        return 0.0, 1e100
    symmetry = float(np.max(np.abs(correlation - correlation.T)))
    scale = max(1.0, float(np.max(np.abs(correlation))))
    if not check_psd:
        # Static inspection checks finite shape, zero-variance constraints,
        # nonnegative variances and symmetry without refreshing the PSD audit.
        return min(1e100, symmetry / scale), 0.0
    eigenvalue = float(np.min(np.linalg.eigvalsh(0.5 * (correlation + correlation.T))))
    return min(1e100, symmetry / scale), min(1e100, max(0.0, -eigenvalue) / scale)


def _normalized(error, scale):
    """Physical-scale error with no arbitrary one-unit floor.

    Zero expected scale admits only an exactly zero error. Bounded saturation
    prevents malformed candidates from overflowing a report, without allowing
    any failing ratio to pass. This function never clips candidate quantities.
    """
    error, scale = float(error), float(scale)
    if scale == 0.0:
        return 0.0 if error == 0.0 else 1e100
    return min(1e100, error / scale)


def _geometry_metrics(request):
    geometry, mapping = request["geometry"], np.asarray(request["mapping"]["face_motion_from_structure"])
    # Local geometric extent must not depend on an arbitrary far-away origin
    # chosen to report moments: such an origin can otherwise hide a complete
    # interpolation mismatch on a tiny interface.
    anchor = np.asarray(geometry["structural_nodes_m"][0])
    nodes = np.asarray(geometry["structural_nodes_m"]) - anchor
    faces = np.asarray(geometry["fluid_face_centroids_m"]) - anchor
    length = max(float(np.max(np.abs(nodes))), float(np.max(np.abs(faces))))
    return float(np.max(np.abs(np.sum(mapping, axis=1) - 1.0))), _normalized(float(np.max(np.abs(mapping @ nodes - faces))), length)


def validate_request(request, *, check_psd=True):
    """Data/geometry checks; optionally perform the active covariance PSD audit.

    Static archive/source validation uses check_psd=False and never factorizes
    covariance. Transfer and fresh verification retain check_psd=True. Neither
    mode propagates a solver, performs remeshing or activates a provider.
    """
    if type(check_psd) is not bool:
        raise ValueError("Covariance PSD audit choice must be a strict boolean")
    json_tree(request)
    keys(request, {"schema", "scope", "frame", "orientation", "geometry", "mapping", "fluid", "structure", "clock", "uncertainty", "tolerances"})
    if request["schema"] != REQUEST_SCHEMA or request["scope"] != CLAIM_SCOPE:
        raise ValueError("Unsupported fluid interface declaration")
    keys(request["frame"], {"frame_id", "axes", "coordinate_unit"})
    text(request["frame"]["frame_id"])
    if request["frame"]["axes"] != FRAME_AXES or request["frame"]["coordinate_unit"] != "m":
        raise ValueError("Interface geometry requires one explicit right-handed Cartesian SI frame")
    if request["orientation"] != ORIENTATION:
        raise ValueError("Interface load/normal/power orientation differs from its explicit convention")
    keys(request["orientation"], set(ORIENTATION))
    geometry = request["geometry"]
    keys(geometry, {"fluid_face_centroids_m", "fluid_face_normals", "fluid_face_areas_m2", "structural_nodes_m", "moment_origin_m"})
    faces, nodes = geometry["fluid_face_centroids_m"], geometry["structural_nodes_m"]
    if type(faces) is not list or type(nodes) is not list or not 1 <= len(faces) <= MAX_POINTS or not 1 <= len(nodes) <= MAX_POINTS:
        raise ValueError("Interface requires 1..32 faces and 1..32 structural nodes")
    face_count, node_count = len(faces), len(nodes)
    _matrix(faces, face_count, 3, 1e6, "face centroids")
    _matrix(nodes, node_count, 3, 1e6, "structural nodes")
    normals = _matrix(geometry["fluid_face_normals"], face_count, 3, 1.0, "face normals")
    if float(np.max(np.abs(np.sum(normals * normals, axis=1) - 1.0))) > 1e-12:
        raise ValueError("Face normals must be unit vectors in the declared frame")
    _matrix([geometry["moment_origin_m"]], 1, 3, 1e6, "moment origin")
    area = geometry["fluid_face_areas_m2"]
    if type(area) is not list or len(area) != face_count:
        raise ValueError("Face area count differs from face geometry")
    for value in area:
        _bounded(value, 1e-12, 1e6, "face area m2")
    keys(request["mapping"], {"kind", "face_motion_from_structure"})
    if request["mapping"]["kind"] != "partition_unity_linear_reproduction":
        raise ValueError("Only a declared partition-unity linear-reproduction map is supported")
    _matrix(request["mapping"]["face_motion_from_structure"], face_count, node_count, 2.0, "motion map")
    partition, coordinates = _geometry_metrics(request)
    if partition > HARD_GEOMETRY_TOLERANCE or coordinates > HARD_GEOMETRY_TOLERANCE:
        raise ValueError("Mapping must preserve partition of unity and linear coordinate reproduction")
    keys(request["fluid"], {"traction_pa", "frame_id", "quantity_semantics"})
    if request["fluid"]["frame_id"] != request["frame"]["frame_id"] or request["fluid"]["quantity_semantics"] != "force_of_fluid_on_structure_per_face_area":
        raise ValueError("Fluid traction frame or force-per-area meaning differs")
    _matrix(request["fluid"]["traction_pa"], face_count, 3, 1e12, "fluid traction Pa")
    keys(request["structure"], {"displacements_m", "velocities_m_per_s", "frame_id"})
    if request["structure"]["frame_id"] != request["frame"]["frame_id"]:
        raise ValueError("Structural motion must use the same declared interface frame")
    _matrix(request["structure"]["displacements_m"], node_count, 3, 1e6, "structural displacement m")
    _matrix(request["structure"]["velocities_m_per_s"], node_count, 3, 1e6, "structural velocity m/s")
    clock = request["clock"]
    keys(clock, {"shared_clock_id", "fluid_clock_id", "structural_clock_id", "time_basis", "fluid_time_s", "structural_time_s",
                 "fluid_step", "structural_step", "fluid_iteration", "structural_iteration", "maximum_skew_s"})
    for field in ("shared_clock_id", "fluid_clock_id", "structural_clock_id"):
        text(clock[field])
    if clock["fluid_clock_id"] != clock["shared_clock_id"] or clock["structural_clock_id"] != clock["shared_clock_id"] or clock["time_basis"] != "elapsed_physical_model_time":
        raise ValueError("Coupled sample clocks must explicitly declare the same physical model clock")
    for field in ("fluid_time_s", "structural_time_s"):
        _bounded(clock[field], 0, 1e9, field)
    skew = _bounded(clock["maximum_skew_s"], 0.0, 1e-9, "maximum clock skew s")
    if abs(clock["fluid_time_s"] - clock["structural_time_s"]) > skew:
        raise ValueError("Interface sample times are not synchronized within the declared hard clock allowance")
    for field in ("fluid_step", "structural_step", "fluid_iteration", "structural_iteration"):
        if type(clock[field]) is not int or not 0 <= clock[field] <= 1000000000:
            raise ValueError("Interface clock step/iteration must be bounded nonnegative integers")
    if clock["fluid_step"] != clock["structural_step"] or clock["fluid_iteration"] != clock["structural_iteration"]:
        raise ValueError("Interface data must belong to the same declared step and coupling iteration")
    keys(request["uncertainty"], {"traction_covariance_pa2", "component_order", "omitted_uncertainty"})
    if request["uncertainty"]["component_order"] != "face_major_xyz" or request["uncertainty"]["omitted_uncertainty"] != ["geometry", "mapping", "clock", "constitutive_models"]:
        raise ValueError("Interface covariance ordering or omissions differ")
    _covariance(request["uncertainty"]["traction_covariance_pa2"], 3 * face_count, "traction covariance Pa2", check_psd=check_psd)
    keys(request["tolerances"], {"algebra_normalized", "covariance_normalized"})
    for field, value in request["tolerances"].items():
        _bounded(value, 1e-13, 1e-8, field)
    return deepcopy(request)


def transfer(request):
    request = validate_request(request)
    p = np.asarray(request["mapping"]["face_motion_from_structure"])
    area = np.asarray(request["geometry"]["fluid_face_areas_m2"])
    traction = np.asarray(request["fluid"]["traction_pa"])
    displacement = np.asarray(request["structure"]["displacements_m"])
    velocity = np.asarray(request["structure"]["velocities_m_per_s"])
    face_force = area[:, None] * traction
    nodal_force = p.T @ face_force
    face_displacement, face_velocity = p @ displacement, p @ velocity
    data = {"fluid_face_forces_n": face_force.tolist(), "fluid_reaction_forces_n": (-face_force).tolist(),
            "structural_forces_n": nodal_force.tolist(), "mapped_face_displacements_m": face_displacement.tolist(),
            "mapped_face_velocities_m_per_s": face_velocity.tolist(),
            "structural_power_w": float(np.sum(nodal_force * velocity)),
            "fluid_reaction_power_w": float(np.sum(-face_force * face_velocity)),
            "structural_virtual_work_j": float(np.sum(nodal_force * displacement)),
            "face_virtual_work_j": float(np.sum(face_force * face_displacement))}
    covariance = request["uncertainty"]["traction_covariance_pa2"]
    if covariance is None:
        mapped_covariance = None
    else:
        b = np.kron(p.T * area[None, :], np.eye(3))
        mapped_covariance = (b @ np.asarray(covariance) @ b.T).tolist()
    return seal({"schema": RESULT_SCHEMA, "request_digest": digest(request), "scope": CLAIM_SCOPE,
                 "frame": deepcopy(request["frame"]), "orientation": deepcopy(ORIENTATION), "clock": deepcopy(request["clock"]),
                 "units": dict(UNITS), "data": data,
                 "uncertainty": {"structural_force_covariance_n2": mapped_covariance,
                                 "component_order": "node_major_xyz", "source_component_order": "face_major_xyz",
                                 "omitted_uncertainty": deepcopy(request["uncertainty"]["omitted_uncertainty"])}})


def validate_result(request, result):
    request = validate_request(request, check_psd=False)
    json_tree(result)
    keys(result, {"schema", "request_digest", "scope", "frame", "orientation", "clock", "units", "data", "uncertainty", "record_digest"})
    expected = {"schema": RESULT_SCHEMA, "request_digest": digest(request), "scope": CLAIM_SCOPE, "frame": request["frame"],
                "orientation": ORIENTATION, "clock": request["clock"], "units": UNITS}
    if any(result[field] != value for field, value in expected.items()):
        raise ValueError("Interface result identity, units, frame, orientation or clock differs")
    json_tree(result["clock"])
    for field in ("fluid_time_s", "structural_time_s", "maximum_skew_s"):
        number(result["clock"][field])
    for field in ("fluid_step", "structural_step", "fluid_iteration", "structural_iteration"):
        if type(result["clock"][field]) is not int:
            raise ValueError("Result clock steps and iterations must remain strict integers")
    data = result["data"]
    keys(data, set(VECTOR_FIELDS) | set(SCALAR_FIELDS))
    faces, nodes = len(request["geometry"]["fluid_face_centroids_m"]), len(request["geometry"]["structural_nodes_m"])
    for field in VECTOR_FIELDS:
        _matrix(data[field], nodes if field == "structural_forces_n" else faces, 3, 1e30, field)
    for field in SCALAR_FIELDS:
        _bounded(data[field], -1e40, 1e40, field)
    uncertainty = result["uncertainty"]
    keys(uncertainty, {"structural_force_covariance_n2", "component_order", "source_component_order", "omitted_uncertainty"})
    if (uncertainty["component_order"] != "node_major_xyz" or uncertainty["source_component_order"] != "face_major_xyz" or
            uncertainty["omitted_uncertainty"] != request["uncertainty"]["omitted_uncertainty"]):
        raise ValueError("Result covariance ordering or omissions differ")
    covariance = uncertainty["structural_force_covariance_n2"]
    if (covariance is None) != (request["uncertainty"]["traction_covariance_pa2"] is None):
        raise ValueError("Result may not invent or discard traction uncertainty")
    if covariance is not None:
        # Candidate PSD is an audit condition, not an eligibility shortcut; a
        # finite indefinite candidate can be retained as a failed verification.
        _matrix(covariance, 3 * nodes, 3 * nodes, 1e40, "candidate force covariance N2")
    check_seal(result)
    return deepcopy(result)


def _independent_values(request, result):
    """Separate scalar summation and tensor contraction, not transfer replay."""
    p = request["mapping"]["face_motion_from_structure"]
    area, traction = request["geometry"]["fluid_face_areas_m2"], request["fluid"]["traction_pa"]
    faces, nodes = len(area), len(p[0])
    face_force = np.array([[area[i] * traction[i][d] for d in range(3)] for i in range(faces)])
    force = np.array([[sum(p[i][j] * face_force[i, d] for i in range(faces)) for d in range(3)] for j in range(nodes)])
    displacement, velocity = request["structure"]["displacements_m"], request["structure"]["velocities_m_per_s"]
    mapped_displacement = np.array([[sum(p[i][j] * displacement[j][d] for j in range(nodes)) for d in range(3)] for i in range(faces)])
    mapped_velocity = np.array([[sum(p[i][j] * velocity[j][d] for j in range(nodes)) for d in range(3)] for i in range(faces)])
    data = result["data"]
    candidate_force = np.asarray(data["structural_forces_n"])
    candidate_face_force = np.asarray(data["fluid_face_forces_n"])
    candidate_reaction = np.asarray(data["fluid_reaction_forces_n"])
    candidate_displacement = np.asarray(data["mapped_face_displacements_m"])
    candidate_velocity = np.asarray(data["mapped_face_velocities_m_per_s"])
    magnitude = lambda values: float(np.max(np.abs(values)))
    force_scale = float(np.sum(np.abs(face_force)))
    displacement_scale, velocity_scale = magnitude(mapped_displacement), magnitude(mapped_velocity)
    origin = np.asarray(request["geometry"]["moment_origin_m"])
    face_coordinates = np.asarray(request["geometry"]["fluid_face_centroids_m"]) - origin
    node_coordinates = np.asarray(request["geometry"]["structural_nodes_m"]) - origin
    length_scale = max(magnitude(face_coordinates), magnitude(node_coordinates))
    fluid_moment = np.sum(np.cross(face_coordinates, face_force), axis=0)
    structural_moment = np.sum(np.cross(node_coordinates, candidate_force), axis=0)
    structural_power = float(np.sum(candidate_force * np.asarray(velocity)))
    fluid_power = float(np.sum(candidate_reaction * candidate_velocity))
    structural_work = float(np.sum(candidate_force * np.asarray(displacement)))
    face_work = float(np.sum(candidate_face_force * candidate_displacement))
    power_scale = max(float(np.sum(np.abs(force * np.asarray(velocity)))), float(np.sum(np.abs(face_force * mapped_velocity))))
    work_scale = max(float(np.sum(np.abs(force * np.asarray(displacement)))), float(np.sum(np.abs(face_force * mapped_displacement))))
    partition, coordinates = _geometry_metrics(request)
    covariance = request["uncertainty"]["traction_covariance_pa2"]
    covariance_residual, psd_deficit = 0.0, 0.0
    if covariance is not None:
        weights = np.asarray(p).T * np.asarray(area)[None, :]
        tensor = np.asarray(covariance).reshape(faces, 3, faces, 3)
        expected = np.einsum("ia,acbd,jb->icjd", weights, tensor, weights).reshape(3 * nodes, 3 * nodes)
        candidate = np.asarray(result["uncertainty"]["structural_force_covariance_n2"])
        scale = float(np.max(np.abs(expected)))
        covariance_residual = _normalized(magnitude(candidate - expected), scale)
        covariance_symmetry, covariance_indefiniteness = _correlation_psd_metrics(candidate)
        psd_deficit = max(covariance_symmetry, covariance_indefiniteness)
    return {"partition_unity": partition, "coordinate_reproduction": coordinates,
            "clock_skew_s": abs(request["clock"]["fluid_time_s"] - request["clock"]["structural_time_s"]),
            "force_mapping": _normalized(max(magnitude(candidate_force - force), magnitude(candidate_face_force - face_force), magnitude(candidate_reaction + face_force)), force_scale),
            "motion_mapping": max(_normalized(magnitude(candidate_displacement - mapped_displacement), displacement_scale),
                                   _normalized(magnitude(candidate_velocity - mapped_velocity), velocity_scale)),
            "total_force": _normalized(magnitude(np.sum(candidate_force, axis=0) - np.sum(face_force, axis=0)), force_scale),
            "total_moment": _normalized(magnitude(structural_moment - fluid_moment), force_scale * length_scale),
            "interface_power": _normalized(abs(structural_power + fluid_power), power_scale),
            "virtual_work": _normalized(abs(structural_work - face_work), work_scale),
            "reported_power_work": max(_normalized(abs(data["structural_power_w"] - structural_power), power_scale),
                _normalized(abs(data["fluid_reaction_power_w"] - fluid_power), power_scale),
                _normalized(abs(data["structural_virtual_work_j"] - structural_work), work_scale),
                _normalized(abs(data["face_virtual_work_j"] - face_work), work_scale)),
            "covariance_propagation": covariance_residual, "covariance_psd_deficit": psd_deficit}


def _spec(request):
    spec = {name: request["tolerances"]["algebra_normalized"] for name in CHECK_NAMES}
    spec.update(partition_unity=HARD_GEOMETRY_TOLERANCE, coordinate_reproduction=HARD_GEOMETRY_TOLERANCE,
                clock_skew_s=request["clock"]["maximum_skew_s"],
                covariance_propagation=request["tolerances"]["covariance_normalized"], covariance_psd_deficit=1e-12)
    return spec


def _qualification(passed):
    return {"action": "LOCAL" if passed else "REFUSE", "qualified_scope": CLAIM_SCOPE if passed else None,
            "coupled_model_qualified": False, "receiving_solver_qualification": "required_separately",
            "physical_validation_established": False, "state_admission_performed": False,
            "reason": "Finite supplied interface algebra passed all declared checks." if passed else "Finite supplied interface algebra failed independent checks."}


def verify(request, result):
    request, result = validate_request(request), validate_result(request, result)
    values, spec = _independent_values(request, result), _spec(request)
    checks = [{"name": name, "value": values[name], "tolerance": spec[name], "status": "PASS" if values[name] <= spec[name] else "FAIL"} for name in sorted(spec)]
    passed = all(row["status"] == "PASS" for row in checks)
    return seal({"schema": REPORT_SCHEMA, "request_digest": digest(request), "result_digest": result["record_digest"],
                 "scope": CLAIM_SCOPE, "verification_method": "independent_scalar_load_motion_tensor_covariance_and_force_moment_work_audit.v1",
                 "status": "PASS" if passed else "FAIL", "checks": checks, "qualification": _qualification(passed), "limitations": list(LIMITATIONS)})


def validate_report(request, result, report):
    """Static retained declarations; call verify for fresh interface algebra."""
    request, result = validate_request(request, check_psd=False), validate_result(request, result)
    json_tree(report)
    keys(report, {"schema", "request_digest", "result_digest", "scope", "verification_method", "status", "checks", "qualification", "limitations", "record_digest"})
    if (report["schema"] != REPORT_SCHEMA or report["request_digest"] != digest(request) or report["result_digest"] != result["record_digest"] or
            report["scope"] != CLAIM_SCOPE or report["verification_method"] != "independent_scalar_load_motion_tensor_covariance_and_force_moment_work_audit.v1" or
            report["status"] not in ("PASS", "FAIL") or report["limitations"] != LIMITATIONS):
        raise ValueError("Interface report identity, scope, method or limitations differ")
    spec = _spec(request)
    if type(report["checks"]) is not list or len(report["checks"]) != len(spec):
        raise ValueError("Interface report must retain exactly the fixed checks")
    for row, name in zip(report["checks"], sorted(spec)):
        keys(row, {"name", "value", "tolerance", "status"})
        if row["name"] != name or number(row["tolerance"]) != spec[name] or not 0 <= number(row["value"]) <= 1e100:
            raise ValueError("Interface report check name, tolerance or value differs")
        if row["status"] != ("PASS" if row["value"] <= row["tolerance"] else "FAIL"):
            raise ValueError("Interface report status contradicts retained arithmetic")
    passed = all(row["status"] == "PASS" for row in report["checks"])
    if report["status"] != ("PASS" if passed else "FAIL") or report["qualification"] != _qualification(passed):
        raise ValueError("Interface report qualification contradicts retained checks")
    check_seal(report)
    return deepcopy(report)


def example_request():
    frame_id = "fluid-structure.interface.reference.v1"
    return {"schema": REQUEST_SCHEMA, "scope": CLAIM_SCOPE,
            "frame": {"frame_id": frame_id, "axes": FRAME_AXES, "coordinate_unit": "m"}, "orientation": deepcopy(ORIENTATION),
            "geometry": {"fluid_face_centroids_m": [[0.5, 0.0, 0.0], [1.5, 0.0, 0.0]],
                         "fluid_face_normals": [[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
                         "fluid_face_areas_m2": [0.2, 0.3], "structural_nodes_m": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                         "moment_origin_m": [0.0, 0.0, 0.0]},
            "mapping": {"kind": "partition_unity_linear_reproduction", "face_motion_from_structure": [[0.5, 0.5, 0.0], [0.0, 0.5, 0.5]]},
            "fluid": {"traction_pa": [[1.0, 10.0, 2.0], [-2.0, 20.0, 3.0]], "frame_id": frame_id,
                      "quantity_semantics": "force_of_fluid_on_structure_per_face_area"},
            "structure": {"displacements_m": [[0.0, 0.001, 0.0], [0.0, 0.002, 0.0], [0.0, 0.003, 0.0]],
                          "velocities_m_per_s": [[0.0, 0.1, 0.0], [0.0, 0.2, 0.0], [0.0, 0.3, 0.0]], "frame_id": frame_id},
            "clock": {"shared_clock_id": "fsi.interface.clock.v1", "fluid_clock_id": "fsi.interface.clock.v1", "structural_clock_id": "fsi.interface.clock.v1",
                      "time_basis": "elapsed_physical_model_time", "fluid_time_s": 0.1, "structural_time_s": 0.1,
                      "fluid_step": 10, "structural_step": 10, "fluid_iteration": 2, "structural_iteration": 2, "maximum_skew_s": 0.0},
            "uncertainty": {"traction_covariance_pa2": np.diag([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]).tolist(),
                            "component_order": "face_major_xyz", "omitted_uncertainty": ["geometry", "mapping", "clock", "constitutive_models"]},
            "tolerances": {"algebra_normalized": 1e-11, "covariance_normalized": 1e-11}}
