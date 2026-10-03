"""Public SPH contracts, qualification routes and retained failed evidence."""
from copy import deepcopy
import json

import numpy as np
import pytest

from ciw.fluid_sph_contract import (EXPANSION_OBSERVABLES, REFUSED_OBSERVABLES, example_request,
    length_scale_m, preservation_scope, time_scale_s, validate_request, validate_result)
from ciw.fluid_sph_solver import csv_rows, simulate
from ciw.fluid_sph_verification import validate_report, verify
from ciw.operations.runner import digest, seal


@pytest.fixture(scope="module")
def sph():
    request = example_request()
    result = simulate(request)
    report = verify(request, result)
    return request, result, report


def test_default_qualifies_real_moving_parcels_with_declared_budgets(sph):
    request, result, report = sph
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == "LOCAL"
    validate_report(request, result, report)
    assert len(json.dumps(result).encode()) < 4 * 1024 * 1024
    assert result["representation"]["particle_semantics"] == "equal_mass_sph_continuum_parcel"
    assert result["representation"]["wave_semantics"] == "barotropic_acoustic_pressure_wave"
    assert result["resolutions"]["primary"]["unwrapped_position_m"][0] != result["resolutions"]["primary"]["unwrapped_position_m"][-1]
    assert 1.95 < report["metrics"]["time_convergence"]["order"] < 2.05
    assert 1.9 < report["metrics"]["spatial_convergence"]["order"] < 2.05
    assert report["metrics"]["reference_refinement"] < 1e-7
    assert report["metrics"]["hamiltonian_gradient"] < 1e-6
    header, rows = csv_rows(result)
    assert header[:3] == ["time_s", "parcel_index", "parcel_mass_kg"]
    assert len(rows) == 33 * 32
    assert length_scale_m(request) == 1.0 and time_scale_s(request) == 0.0125
    assert set(preservation_scope(request)) == {"representation", "particle_meaning", "spatial_detail", "vertical_detail",
                                              "clock", "receiver_coupling", "physical_validity", "molecular_scope"}


@pytest.mark.parametrize("section,field,value", [
    ("model", "strain_amplitude", 0.000500001), ("model", "particle_semantics", "molecule"),
    ("model", "eos", "gravity_wave"), ("model", "kernel", "adaptive_cubic"),
    ("model", "boundary", "free_surface"), ("model", "sound_speed_m_per_s", True),
    ("model", "reference_density_kg_per_m3", float("nan")), ("integration", "particles", 32.0),
    ("integration", "steps", True), ("clock", "externally_synchronized", 0), ("clock", "origin_s", False),
])
def test_strict_request_and_hard_physics_constraints(section, field, value):
    request = example_request()
    request[section][field] = value
    request["tolerances"] = {key: 0.1 for key in request["tolerances"]}
    with pytest.raises(ValueError):
        validate_request(request)


def test_hard_acoustic_timestep_and_bounded_allocation():
    request = example_request()
    request["integration"]["particles"] = 64
    with pytest.raises(ValueError, match="timestep"):
        validate_request(request)
    request["integration"]["steps"] = 128
    with pytest.raises(ValueError, match="budget"):
        validate_request(request)


@pytest.mark.parametrize("observable,route", [("free_surface", "EXPAND"), ("experimental_validation", "REFUSE")])
def test_expansion_and_authority_routes(sph, observable, route):
    request, original, _ = sph
    request, result = deepcopy(request), deepcopy(original)
    request["desired_observables"].append(observable)
    result["request_digest"] = digest(request)
    result = seal(result)
    report = verify(request, result)
    assert report["status"] == "PASS"
    assert report["qualification"]["action"] == route
    validate_report(request, result, report)


@pytest.mark.parametrize("mutation", ["units", "molecular", "clock", "shape", "initial", "mass", "boolean", "time"])
def test_result_boundary_rejects_undeclared_semantics_and_structure(sph, mutation):
    request, original, _ = sph
    result = deepcopy(original)
    trace = result["resolutions"]["primary"]
    if mutation == "units":
        result["units"]["pressure_pa"] = "kPa"
    elif mutation == "molecular":
        result["representation"]["molecular_identity"] = 0
    elif mutation == "clock":
        result["clock"]["owner"] = "snapshot_estimator"
    elif mutation == "shape":
        trace["density_kg_per_m3"][-1].pop()
    elif mutation == "initial":
        trace["velocity_m_per_s"][0][0] *= -1.0
    elif mutation == "mass":
        trace["parcel_mass_kg"] *= 2.0
    elif mutation == "boolean":
        trace["pressure_pa"][3][3] = True
    else:
        trace["time_s"][2] *= 2.0
    with pytest.raises(ValueError):
        validate_result(request, seal(result))


@pytest.mark.parametrize("field,scale", [("unwrapped_position_m", 0.005), ("velocity_m_per_s", 1e30),
                                         ("density_kg_per_m3", -1e30), ("pressure_pa", 1e30)])
def test_resealed_physics_corruption_fails_and_failed_report_remains_inspectable(sph, field, scale):
    request, original, _ = sph
    result = deepcopy(original)
    result["resolutions"]["primary"][field][-1][3] += scale
    result = seal(result)
    validate_result(request, result)
    report = verify(request, result)
    assert report["status"] == "FAIL"
    assert report["qualification"]["action"] == "REFUSE"
    validate_report(request, result, report)


def test_static_report_inspection_cannot_activate_force_reference_solver_or_fft(sph, monkeypatch):
    request, result, report = sph

    def forbidden(*args, **kwargs):
        raise AssertionError("static record inspection activated fresh physics")

    monkeypatch.setattr("ciw.fluid_sph_solver.simulate", forbidden)
    monkeypatch.setattr("ciw.fluid_sph_verification.reference", forbidden)
    monkeypatch.setattr("ciw.fluid_sph_verification.quantities", forbidden)
    monkeypatch.setattr("ciw.fluid_sph_verification.analytic_values", forbidden)
    monkeypatch.setattr(np.fft, "rfft", forbidden)
    validate_report(request, result, report)


@pytest.mark.parametrize("mutation", ["threshold", "duplicate", "identity", "metric", "qualification"])
def test_static_report_coherence_and_binding_tampering_rejected(sph, mutation):
    request, result, original = sph
    report = deepcopy(original)
    if mutation == "threshold":
        report["checks"][0]["tolerance"] = 0.1
    elif mutation == "duplicate":
        report["checks"][1] = deepcopy(report["checks"][0])
    elif mutation == "identity":
        report["result_digest"] = "sha256:" + "0" * 64
    elif mutation == "metric":
        report["metrics"]["time_convergence"]["order"] = 2.0
    else:
        report["qualification"]["action"] = "EXPAND"
    with pytest.raises(ValueError):
        validate_report(request, result, seal(report))
