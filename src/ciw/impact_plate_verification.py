"""Independent all-history audit of bounded elastic plate/striker impact.

Retained inspection checks declarations and bindings without propagating the
spectral reference or repeating this numerical audit. Content seals establish
content identity, not producer authentication or physical qualification.
"""
from __future__ import annotations

import math

from .control_contracts import json_tree, keys, number
from .impact_plate_contract import (
    CLAIM_SCOPE, EXPANSION_OBSERVABLES, REPORT_SCHEMA, STATE_FIELDS,
    nominal_contact_duration_s, nominal_scales, validate_request, validate_result,
)
from .impact_plate_reference import reference, reference_values
from .operations.runner import check_seal, digest, seal

LIMITATIONS = [
    "Numerical verification of a finite-mode simply supported Kirchhoff-Love elastic plate with a unilateral linear spring patch and point striker only.",
    "Support reactions exchange momentum; only striker contact impulse and striker momentum balance are checked.",
    "Deflection qualification uses a conservative modal L1 spatial bound at retained times, with fixed small-deflection and slope limits.",
    "One timestep comparison and one modal truncation comparison do not establish convergence order, continuum convergence or experimental validation.",
    "Single contact is required within the declared observation window; repeated contact, plasticity, damage, fracture, rate, thermal, molecular and scale response remain unqualified.",
    "Elastic modulus, density and Poisson ratio are declared model inputs, not identified or calibrated polymer properties.",
    "Qualification recommendations do not perform canonical state admission.",
]
DEFLECTION_INTERPRETATION = "maximum retained-time sum of absolute modal displacements; conservative spatial deflection bound, not actual global peak"
REFINEMENT_INTERPRETATIONS = {
    "time_refinement": "one timestep halving at fixed modal basis; no convergence-order claim",
    "spatial_refinement": "one modes-per-axis increase by two at the refined timestep; no continuum-convergence claim",
}
RESIDUAL_FIELDS = {
    "initial_state", "force_law", "compression_only_force", "gap_projection",
    "patch_displacement_projection", "patch_velocity_projection", "integrator_equations",
}
MODAL_FIELDS = ("modal_displacement_m", "modal_velocity_m_per_s")
METRIC_FIELDS = {
    "analytic_maximum_normalized_errors", "numerical_residuals",
    "integrated_striker_impulse_n_s", "maximum_striker_momentum_balance_relative_error",
    "maximum_energy_relative_drift", "initial_energy_j", "final_energy_j",
    "terminal_striker_energy_j", "terminal_plate_energy_j", "terminal_spring_energy_j",
    "restitution", "separation_time_s", "separation_bracket_s", "contact_duration_s",
    "maximum_compression_m", "peak_force_n", "plate_peak_deflection_m",
    "plate_contact_peak_deflection_m", "max_deflection_over_thickness", "slope_bound",
    "single_contact_error", "deflection_interpretation",
}
REFERENCE_FIELDS = {
    "contact_duration_s", "release_time_s", "first_recontact_time_s", "single_contact_supported",
    "initial_energy_j", "maximum_compression_m", "peak_force_n",
    "maximum_plate_contact_displacement_m", "maximum_plate_l1_displacement_m",
    "striker_impulse_n_s", "restitution", "modes", "modal_mass_kg",
    "modal_stiffness_n_per_m", "patch_coupling", "nominal_contact_duration_s",
    "observation_duration_s",
    "nominal_contact_time_s", "nominal_compression_m", "nominal_force_n",
    "nominal_impulse_n_s", "nominal_speed_m_per_s",
}
OBSERVABLE_CHANGE_FIELDS = {
    "striker_impulse", "restitution", "peak_force", "maximum_compression",
    "plate_deflection", "terminal_energy", "separation_time",
}
REFINEMENT_STATE_FIELDS = set(STATE_FIELDS) | set(MODAL_FIELDS) | {"displacement_field_bound"}


def _scales(request):
    model = request["model"]
    mass, stiffness, speed = (model[name] for name in
        ("mass_kg", "stiffness_n_per_m", "initial_speed_m_per_s"))
    displacement = speed * math.sqrt(mass / stiffness)
    return {"time_s": nominal_contact_duration_s(model), "displacement_m": displacement,
            "velocity_m_per_s": speed, "force_n": stiffness * displacement,
            "energy_j": 0.5 * mass * speed * speed, "impulse_n_s": mass * speed}


def _state_scales(scales, basis):
    values = {name: scales["force_n"] if name == "force_n" else
            scales["velocity_m_per_s"] if "velocity" in name else scales["displacement_m"]
            for name in tuple(STATE_FIELDS) + MODAL_FIELDS}
    values["modal_velocity_m_per_s"] = math.sqrt(2.0 * scales["energy_j"] / min(basis["modal_mass_kg"]))
    # Cauchy--Schwarz with the modal kinetic-energy norm gives an attainable
    # patch velocity bound. Plate response has a different energy scale from
    # striker velocity; no eigenvalues or retained numerical errors enter it.
    values["plate_contact_velocity_m_per_s"] = math.sqrt(2.0 * scales["energy_j"] * sum(
        weight * weight / mass for weight, mass in zip(basis["patch_coupling"], basis["modal_mass_kg"])))
    return values


def _energy(model, trace, index):
    striker = 0.5 * model["mass_kg"] * trace["velocity_m_per_s"][index] ** 2
    plate = sum(0.5 * mass * velocities[index] ** 2 + 0.5 * stiffness * positions[index] ** 2
        for mass, stiffness, positions, velocities in zip(trace["modal_mass_kg"],
        trace["modal_stiffness_n_per_m"], trace["modal_displacement_m"], trace["modal_velocity_m_per_s"]))
    spring = 0.5 * model["stiffness_n_per_m"] * max(trace["compression_m"][index], 0.0) ** 2
    return striker, plate, spring


def _deflection_bounds(model, trace):
    modal_q = trace["modal_displacement_m"]
    length, width = model["length_x_m"], model["length_y_m"]
    l1 = max(sum(abs(values[index]) for values in modal_q) for index in range(len(trace["time_s"])))
    slope = max(sum((m * math.pi / length + n * math.pi / width) * abs(values[index])
        for (m, n), values in zip(trace["modes"], modal_q)) for index in range(len(trace["time_s"])))
    return l1, l1 / model["thickness_m"], slope


def _separation(trace):
    gap, times = trace["compression_m"], trace["time_s"]
    crossings = [i for i in range(1, len(gap)) if gap[i - 1] > 0 and gap[i] <= 0]
    if not crossings:
        return None, None, 1.0
    index = crossings[0]
    crossing = times[index - 1] + trace["dt_s"] * gap[index - 1] / (gap[index - 1] - gap[index])
    single = len(crossings) == 1 and all(value <= 0 for value in gap[index:])
    single = single and all(force == 0 for force in trace["force_n"][index:])
    return crossing, [times[index - 1], times[index]], 0.0 if single else 1.0


def _metrics(request, trace, ref, scales):
    model, dt = request["model"], trace["dt_s"]
    mass, stiffness, speed = (model[name] for name in
        ("mass_kg", "stiffness_n_per_m", "initial_speed_m_per_s"))
    times, striker_q, gap, velocity, force, patch_q, patch_v = (trace[name] for name in
        ("time_s", "striker_displacement_m", "compression_m", "velocity_m_per_s", "force_n",
         "plate_contact_displacement_m", "plate_contact_velocity_m_per_s"))
    q, v = trace["modal_displacement_m"], trace["modal_velocity_m_per_s"]
    masses, springs, coupling = (trace[name] for name in
        ("modal_mass_kg", "modal_stiffness_n_per_m", "patch_coupling"))
    expected = reference_values(request, times, modes_per_axis=trace["modes_per_axis"])
    state_scales = _state_scales(scales, trace)
    errors = {name: max(abs(a - b) for a, b in zip(trace[name], expected[name])) / state_scales[name]
              for name in STATE_FIELDS}
    for name in MODAL_FIELDS:
        errors[name] = max(abs(a - b) for observed, exact in zip(trace[name], expected[name])
                          for a, b in zip(observed, exact)) / state_scales[name]
    residuals = {name: 0.0 for name in RESIDUAL_FIELDS}
    residuals["initial_state"] = max(abs(striker_q[0]), abs(gap[0]), abs(patch_q[0]),
        *(abs(values[0]) for values in q)) / scales["displacement_m"]
    residuals["initial_state"] = max(residuals["initial_state"], abs(velocity[0] - speed) / speed,
        abs(patch_v[0]) / speed, *(abs(values[0]) / speed for values in v), abs(force[0]) / scales["force_n"])
    residuals["force_law"] = max(abs(f - stiffness * max(delta, 0.0)) for f, delta in zip(force, gap)) / scales["force_n"]
    residuals["compression_only_force"] = max(0.0, -min(force)) / scales["force_n"]
    residuals["gap_projection"] = max(abs(delta - (position - patch)) for delta, position, patch in
        zip(gap, striker_q, patch_q)) / scales["displacement_m"]
    impulse, momentum_error, energy_drift = 0.0, 0.0, 0.0
    energies = []
    for index in range(len(times)):
        projected_q = sum(weight * values[index] for weight, values in zip(coupling, q))
        projected_v = sum(weight * values[index] for weight, values in zip(coupling, v))
        residuals["patch_displacement_projection"] = max(residuals["patch_displacement_projection"],
            abs(patch_q[index] - projected_q) / scales["displacement_m"])
        residuals["patch_velocity_projection"] = max(residuals["patch_velocity_projection"],
            abs(patch_v[index] - projected_v) / speed)
        energy = sum(_energy(model, trace, index))
        energies.append(energy)
        energy_drift = max(energy_drift, abs(energy - scales["energy_j"]) / scales["energy_j"])
        if not index:
            continue
        impulse += 0.5 * (force[index - 1] + force[index]) * dt
        momentum_error = max(momentum_error, abs(mass * (speed - velocity[index]) - impulse) / scales["impulse_n_s"])
        predicted_q = striker_q[index - 1] + velocity[index - 1] * dt - 0.5 * force[index - 1] / mass * dt * dt
        predicted_v = velocity[index - 1] - 0.5 * (force[index - 1] + force[index]) / mass * dt
        recurrence = max(abs(striker_q[index] - predicted_q) / scales["displacement_m"], abs(velocity[index] - predicted_v) / speed)
        for mode_mass, mode_k, weight, positions, velocities in zip(masses, springs, coupling, q, v):
            previous_a = (weight * force[index - 1] - mode_k * positions[index - 1]) / mode_mass
            current_a = (weight * force[index] - mode_k * positions[index]) / mode_mass
            modal_q = positions[index - 1] + velocities[index - 1] * dt + 0.5 * previous_a * dt * dt
            modal_v = velocities[index - 1] + 0.5 * (previous_a + current_a) * dt
            recurrence = max(recurrence, abs(positions[index] - modal_q) / scales["displacement_m"], abs(velocities[index] - modal_v) / speed)
        residuals["integrator_equations"] = max(residuals["integrator_equations"], recurrence)
    separation, bracket, single_error = _separation(trace)
    if not ref["single_contact_supported"]:
        single_error = 1.0
    l1, ratio, slope = _deflection_bounds(model, trace)
    striker_energy, plate_energy, spring_energy = _energy(model, trace, -1)
    return {"analytic_maximum_normalized_errors": errors, "numerical_residuals": residuals,
        "integrated_striker_impulse_n_s": impulse, "maximum_striker_momentum_balance_relative_error": momentum_error,
        "maximum_energy_relative_drift": energy_drift, "initial_energy_j": energies[0], "final_energy_j": energies[-1],
        "terminal_striker_energy_j": striker_energy, "terminal_plate_energy_j": plate_energy, "terminal_spring_energy_j": spring_energy,
        "restitution": -velocity[-1] / speed, "separation_time_s": separation, "separation_bracket_s": bracket,
        "contact_duration_s": separation, "maximum_compression_m": max(gap), "peak_force_n": max(force),
        "plate_peak_deflection_m": l1, "plate_contact_peak_deflection_m": max(abs(value) for value in patch_q),
        "max_deflection_over_thickness": ratio, "slope_bound": slope, "single_contact_error": single_error,
        "deflection_interpretation": DEFLECTION_INTERPRETATION}


def _observable_changes(left, right, scales):
    mapping = {"striker_impulse": ("integrated_striker_impulse_n_s", scales["impulse_n_s"]),
        "restitution": ("restitution", 1.0), "peak_force": ("peak_force_n", scales["force_n"]),
        "maximum_compression": ("maximum_compression_m", scales["displacement_m"]),
        "plate_deflection": ("plate_peak_deflection_m", scales["displacement_m"]),
        "terminal_energy": ("final_energy_j", scales["energy_j"])}
    values = {name: abs(left[field] - right[field]) / scale for name, (field, scale) in mapping.items()}
    values["separation_time"] = (abs(left["separation_time_s"] - right["separation_time_s"]) / scales["time_s"]
        if left["separation_time_s"] is not None and right["separation_time_s"] is not None else 1.0)
    return values


def _refinement_metrics(left_trace, right_trace, left_metrics, right_metrics, scales, *, stride, name):
    left_scales, right_scales = _state_scales(scales, left_trace), _state_scales(scales, right_trace)
    state_scales = {field: max(left_scales[field], right_scales[field]) for field in left_scales}
    aligned = {field: max(abs(a - b) for a, b in zip(left_trace[field], right_trace[field][::stride])) / state_scales[field]
               for field in STATE_FIELDS}
    left_modes = {tuple(mode): index for index, mode in enumerate(left_trace["modes"])}
    right_modes = {tuple(mode): index for index, mode in enumerate(right_trace["modes"])}
    common = sorted(set(left_modes) & set(right_modes))
    added = sorted(set(right_modes) - set(left_modes))
    removed = sorted(set(left_modes) - set(right_modes))
    for field in MODAL_FIELDS:
        aligned[field] = max(abs(a - b) for mode in common
            for a, b in zip(left_trace[field][left_modes[mode]], right_trace[field][right_modes[mode]][::stride])) / state_scales[field]
    # Since every sine product has absolute value <=1, this L1 coefficient
    # difference bounds the difference of the two finite fields everywhere in
    # the plate at each aligned retained time. Added modes must contribute even
    # if their patch projections cancel. This is a truncation comparison, not
    # an error bound against the continuum field.
    aligned["displacement_field_bound"] = max(
        sum(abs(left_trace["modal_displacement_m"][left_modes[mode]][index]
                - right_trace["modal_displacement_m"][right_modes[mode]][index * stride]) for mode in common)
        + sum(abs(right_trace["modal_displacement_m"][right_modes[mode]][index * stride]) for mode in added)
        + sum(abs(left_trace["modal_displacement_m"][left_modes[mode]][index]) for mode in removed)
        for index in range(len(left_trace["time_s"]))) / scales["displacement_m"]
    resolution_key = "resolution_factor" if name == "time_refinement" else "modes_per_axis_increment"
    return {"aligned_state_changes_normalized": aligned,
            "observable_changes_normalized": _observable_changes(left_metrics, right_metrics, scales),
            resolution_key: 2, "interpretation": REFINEMENT_INTERPRETATIONS[name]}


def _check_spec(request):
    tolerance = request["tolerances"]
    spec = {"schema_integrity": 0.0}
    for label in ("primary", "refined", "spatial"):
        for name in RESIDUAL_FIELDS:
            spec[label + "." + name] = 0.0 if name in {"initial_state", "compression_only_force"} else 1e-12
        spec.update({label + ".analytic." + field: tolerance["analytic_normalized"]
            for field in tuple(STATE_FIELDS) + MODAL_FIELDS})
        spec.update({label + ".striker_impulse": tolerance["impulse_relative"],
            label + ".all_history_striker_momentum_balance": tolerance["momentum_relative"],
            label + ".maximum_energy_drift": tolerance["energy_relative"],
            label + ".restitution": tolerance["restitution_absolute"],
            label + ".separation_event": 0.0, label + ".separation_time": tolerance["separation_relative"],
            label + ".single_contact": 0.0, label + ".small_deflection_ratio": 0.1,
            label + ".small_slope_bound": 0.1})
    for name, tolerance_key in (("time_refinement", "refinement_normalized"), ("spatial_refinement", "spatial_refinement_normalized")):
        for field in REFINEMENT_STATE_FIELDS | OBSERVABLE_CHANGE_FIELDS:
            spec[name + "." + field] = tolerance[tolerance_key]
    return spec


def _check_values(metrics, refs):
    values, scales = {"schema_integrity": 0.0}, refs["scales"]
    for label in ("primary", "refined", "spatial"):
        observed = metrics[label]
        ref = refs["spatial" if label == "spatial" else "primary"]
        values.update({label + "." + name: value for name, value in observed["numerical_residuals"].items()})
        values.update({label + ".analytic." + name: value for name, value in observed["analytic_maximum_normalized_errors"].items()})
        values.update({label + ".striker_impulse": abs(observed["integrated_striker_impulse_n_s"] - ref["striker_impulse_n_s"]) / scales["impulse_n_s"] if ref["striker_impulse_n_s"] is not None else 1.0,
            label + ".all_history_striker_momentum_balance": observed["maximum_striker_momentum_balance_relative_error"],
            label + ".maximum_energy_drift": observed["maximum_energy_relative_drift"],
            label + ".restitution": abs(observed["restitution"] - ref["restitution"]) if ref["restitution"] is not None else 1.0,
            label + ".separation_event": 0.0 if observed["separation_time_s"] is not None else 1.0,
            label + ".separation_time": abs(observed["separation_time_s"] - ref["contact_duration_s"]) / scales["time_s"]
                if observed["separation_time_s"] is not None and ref["contact_duration_s"] is not None else 1.0,
            label + ".single_contact": observed["single_contact_error"],
            label + ".small_deflection_ratio": observed["max_deflection_over_thickness"],
            label + ".small_slope_bound": observed["slope_bound"]})
    for name in REFINEMENT_INTERPRETATIONS:
        for change in (metrics[name]["aligned_state_changes_normalized"], metrics[name]["observable_changes_normalized"]):
            values.update({name + "." + field: value for field, value in change.items()})
    return values


def _qualification(passed, unsupported, checks, integrity_failure=None):
    if not passed:
        return {"action": "REFUSE", "reasons": [integrity_failure] if integrity_failure else
                ["Numerical or model-domain acceptance failed (" + str(sum(check["status"] == "FAIL" for check in checks)) + " checks); see the failed check records."],
                "unsupported_observables": unsupported}
    if unsupported:
        return {"action": "EXPAND", "reasons": ["The bounded numerical plate benchmark passed; requested observables need additional qualified models or evidence: " + ", ".join(unsupported)],
                "unsupported_observables": unsupported}
    return {"action": "LOCAL", "reasons": ["All declared numerical and fixed model-domain checks passed for the exact elastic plate/contact scope."], "unsupported_observables": []}


def verify(request: dict, result: dict) -> dict:
    """Recompute trajectories, recurrence, energy and qualification independently."""
    checks, metrics, refs, unsupported = [], {}, {}, []
    request_ref, result_ref, integrity_failure = None, None, None
    try:
        request = validate_request(request)
        request_ref = digest(request)
        unsupported = sorted(set(request["desired_observables"]) & EXPANSION_OBSERVABLES)
        validate_result(request, result)
        result_ref = result["record_digest"]
        scales = _scales(request)
        refs = {"scales": scales, "primary": reference(request, modes_per_axis=result["primary"]["modes_per_axis"]),
                "spatial": reference(request, modes_per_axis=result["spatial"]["modes_per_axis"])}
        refs["state_normalizations"] = {label: _state_scales(scales, result[label]) for label in ("primary", "spatial")}
        for label in ("primary", "refined", "spatial"):
            metrics[label] = _metrics(request, result[label], refs["spatial" if label == "spatial" else "primary"], scales)
        metrics["time_refinement"] = _refinement_metrics(result["primary"], result["refined"], metrics["primary"], metrics["refined"], scales, stride=2, name="time_refinement")
        metrics["spatial_refinement"] = _refinement_metrics(result["refined"], result["spatial"], metrics["refined"], metrics["spatial"], scales, stride=1, name="spatial_refinement")
        values, spec = _check_values(metrics, refs), _check_spec(request)
        checks = [{"name": name, "status": "PASS" if math.isfinite(values[name]) and values[name] <= tolerance else "FAIL", "value": values[name], "tolerance": tolerance}
                  for name, tolerance in sorted(spec.items())]
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        integrity_failure = str(exc) or type(exc).__name__
        checks = [{"name": "schema_integrity", "status": "FAIL", "reason": integrity_failure}]
    passed = integrity_failure is None and all(check["status"] == "PASS" for check in checks)
    return seal({"schema": REPORT_SCHEMA, "request_digest": request_ref, "result_digest": result_ref,
        "claim_scope": CLAIM_SCOPE, "status": "PASS" if passed else "FAIL",
        "qualification": _qualification(passed, unsupported, checks, integrity_failure), "checks": checks,
        "reference": refs, "metrics": metrics, "limitations": list(LIMITATIONS)})


def _validate_reference(request, result, refs):
    """Check retained reference declarations without eigenanalysis or propagation."""
    keys(refs, {"primary", "spatial", "scales", "state_normalizations"})
    scales = _scales(request)
    keys(refs["scales"], set(scales))
    if any(number(value) <= 0 for value in refs["scales"].values()) or refs["scales"] != scales:
        raise ValueError("Stored nominal normalization scales differ from the request")
    keys(refs["state_normalizations"], {"primary", "spatial"})
    for label in ("primary", "spatial"):
        normalizations = refs["state_normalizations"][label]
        keys(normalizations, set(STATE_FIELDS) | set(MODAL_FIELDS))
        if any(number(value) <= 0 for value in normalizations.values()) or normalizations != _state_scales(scales, result[label]):
            raise ValueError("Stored state normalization scales differ from the declared basis and initial energy")
    for label in ("primary", "spatial"):
        ref, trace = refs[label], result[label]
        keys(ref, REFERENCE_FIELDS)
        if (type(ref["modes"]) is not list or len(ref["modes"]) != len(trace["modes"])
                or any(type(mode) is not list or len(mode) != 2
                       or any(type(index) is not int for index in mode) for mode in ref["modes"])):
            raise ValueError("Stored spectral modes require strict integer index pairs")
        for field in ("modes", "modal_mass_kg", "modal_stiffness_n_per_m", "patch_coupling"):
            if ref[field] != trace[field]:
                raise ValueError("Stored spectral basis differs from the retained trace")
            if field != "modes":
                for value in ref[field]:
                    number(value)
        if type(ref["single_contact_supported"]) is not bool:
            raise ValueError("Stored single-contact reference flag must be a boolean")
        for field in REFERENCE_FIELDS - {"modes", "modal_mass_kg", "modal_stiffness_n_per_m", "patch_coupling", "single_contact_supported"}:
            if field in {"contact_duration_s", "release_time_s", "first_recontact_time_s", "striker_impulse_n_s", "restitution"} and ref[field] is None:
                continue
            number(ref[field])
        declared_nominal = nominal_scales(request["model"])
        if any(ref[field] != value for field, value in declared_nominal.items()):
            raise ValueError("Stored nominal reference declaration differs from the request")
        if ref["nominal_contact_duration_s"] != scales["time_s"] or ref["initial_energy_j"] != scales["energy_j"] or not math.isclose(ref["observation_duration_s"], result["primary"]["time_s"][-1], rel_tol=2e-14, abs_tol=0.0):
            raise ValueError("Stored reference time or energy declaration differs from the retained request/grid")
        release = ref["release_time_s"]
        if release != ref["contact_duration_s"] or (release is not None and not 0 < release <= ref["observation_duration_s"]):
            raise ValueError("Stored reference release is outside the declared observation window")
        recontact = ref["first_recontact_time_s"]
        if recontact is not None and (release is None or not release < recontact <= ref["observation_duration_s"]):
            raise ValueError("Stored reference recontact is inconsistent with its release/window")
        if ref["single_contact_supported"] != (release is not None and recontact is None):
            raise ValueError("Stored single-contact qualification contradicts retained event declarations")
        if (ref["striker_impulse_n_s"] is None) != (release is None) or (ref["restitution"] is None) != (release is None):
            raise ValueError("Stored release observables contradict its event declaration")
        for field in ("maximum_compression_m", "peak_force_n", "maximum_plate_contact_displacement_m", "maximum_plate_l1_displacement_m", "striker_impulse_n_s"):
            if ref[field] is not None and ref[field] < 0:
                raise ValueError("Stored reference magnitudes must be nonnegative")
        # A declared recontact lies outside the free-after-release reference's
        # physical scope. Its later free gap must remain retainable as failed
        # evidence rather than be mistaken for active spring compression.
        if recontact is None and (ref["maximum_compression_m"] > scales["displacement_m"] * (1.0 + 1e-10) or ref["peak_force_n"] > scales["force_n"] * (1.0 + 1e-10)):
            raise ValueError("Stored reference spring extrema exceed the initial-energy profile")
        if ref["maximum_plate_contact_displacement_m"] > ref["maximum_plate_l1_displacement_m"] * (1.0 + 1e-10):
            raise ValueError("Stored patch deflection exceeds its declared spatial L1 bound")
        if release is not None:
            if abs(ref["restitution"]) > 1.0 + 1e-10 or not math.isclose(ref["striker_impulse_n_s"], scales["impulse_n_s"] * (1.0 + ref["restitution"]), rel_tol=1e-12, abs_tol=1e-12 * scales["impulse_n_s"]):
                raise ValueError("Stored reference rebound and striker impulse declarations disagree")


def validate_report(request: dict, result: dict, report: dict) -> None:
    """Validate exact retained declarations; do not simulate or repeat verify.

    Scientific errors declared in retained metrics are reproduced only by a
    separate call to verify. A structurally coherent counterfeit can pass this
    declaration check; the content seal does not authenticate its producer.
    """
    request = validate_request(request)
    validate_result(request, result)
    json_tree(report)
    keys(report, {"schema", "request_digest", "result_digest", "claim_scope", "status", "qualification", "checks", "reference", "metrics", "limitations", "record_digest"})
    if report["schema"] != REPORT_SCHEMA or report["request_digest"] != digest(request) or report["result_digest"] != result["record_digest"] or report["claim_scope"] != CLAIM_SCOPE or report["limitations"] != LIMITATIONS or report["status"] not in {"PASS", "FAIL"}:
        raise ValueError("Stored plate report identity, scope or limitations differ")
    _validate_reference(request, result, report["reference"])
    refs, scales, metrics, model = report["reference"], report["reference"]["scales"], report["metrics"], request["model"]
    keys(metrics, {"primary", "refined", "spatial", "time_refinement", "spatial_refinement"})
    for label in ("primary", "refined", "spatial"):
        observed, trace = metrics[label], result[label]
        keys(observed, METRIC_FIELDS)
        keys(observed["analytic_maximum_normalized_errors"], set(STATE_FIELDS) | set(MODAL_FIELDS))
        keys(observed["numerical_residuals"], RESIDUAL_FIELDS)
        for errors in (observed["analytic_maximum_normalized_errors"], observed["numerical_residuals"]):
            if any(number(value) < 0 for value in errors.values()):
                raise ValueError("Stored numerical errors must be nonnegative")
        for field in METRIC_FIELDS - {"analytic_maximum_normalized_errors", "numerical_residuals", "separation_time_s", "separation_bracket_s", "contact_duration_s", "deflection_interpretation"}:
            number(observed[field])
            # Signed counterfeit force histories can produce negative impulse;
            # preserve the failed audit rather than reject its correct signed
            # measurement. Successful checks still require unilateral force.
            if field not in {"restitution", "integrated_striker_impulse_n_s"} and observed[field] < 0:
                raise ValueError("Stored energies, magnitudes and errors must be nonnegative")
        for field in ("separation_time_s", "contact_duration_s"):
            if observed[field] is not None and number(observed[field]) <= 0:
                raise ValueError("Stored release times require positive finite numbers")
        l1, ratio, slope = _deflection_bounds(model, trace)
        energy_parts = _energy(model, trace, -1)
        bindings = {"initial_energy_j": sum(_energy(model, trace, 0)), "final_energy_j": sum(energy_parts),
            "terminal_striker_energy_j": energy_parts[0], "terminal_plate_energy_j": energy_parts[1], "terminal_spring_energy_j": energy_parts[2],
            "restitution": -trace["velocity_m_per_s"][-1] / model["initial_speed_m_per_s"],
            "maximum_compression_m": max(trace["compression_m"]), "peak_force_n": max(trace["force_n"]),
            "plate_peak_deflection_m": l1, "plate_contact_peak_deflection_m": max(abs(value) for value in trace["plate_contact_displacement_m"]),
            "max_deflection_over_thickness": ratio, "slope_bound": slope, "deflection_interpretation": DEFLECTION_INTERPRETATION}
        if any(observed[name] != value for name, value in bindings.items()):
            raise ValueError("Stored measurements differ from retained terminal state or extrema")
        crossing, bracket, single_error = _separation(trace)
        if not refs["spatial" if label == "spatial" else "primary"]["single_contact_supported"]:
            single_error = 1.0
        if observed["single_contact_error"] != single_error or observed["separation_time_s"] != crossing or observed["contact_duration_s"] != crossing or observed["separation_bracket_s"] != bracket:
            raise ValueError("Stored release or single-contact declaration differs from retained gap history")
        if crossing is not None:
            number(crossing)
            for value in bracket:
                number(value)
    for name, left_label, right_label in (("time_refinement", "primary", "refined"), ("spatial_refinement", "refined", "spatial")):
        refinement = metrics[name]
        resolution_key = "resolution_factor" if name == "time_refinement" else "modes_per_axis_increment"
        keys(refinement, {"aligned_state_changes_normalized", "observable_changes_normalized", resolution_key, "interpretation"})
        keys(refinement["aligned_state_changes_normalized"], REFINEMENT_STATE_FIELDS)
        keys(refinement["observable_changes_normalized"], OBSERVABLE_CHANGE_FIELDS)
        expected_changes = _observable_changes(metrics[left_label], metrics[right_label], scales)
        if refinement["observable_changes_normalized"] != expected_changes or type(refinement[resolution_key]) is not int or refinement[resolution_key] != 2 or refinement["interpretation"] != REFINEMENT_INTERPRETATIONS[name]:
            raise ValueError("Stored refinement declaration differs from retained measurements")
        for changes in (refinement["aligned_state_changes_normalized"], refinement["observable_changes_normalized"]):
            if any(number(value) < 0 for value in changes.values()):
                raise ValueError("Stored refinement errors must be nonnegative")
    checks, spec, values = report["checks"], _check_spec(request), _check_values(metrics, refs)
    if type(checks) is not list or len(checks) != len(spec):
        raise ValueError("Stored report is missing or duplicates declared checks")
    names = []
    for check in checks:
        keys(check, {"name", "status", "value", "tolerance"})
        name = check["name"]
        if type(name) is not str or name not in spec or number(check["value"]) != values[name] or number(check["tolerance"]) != spec[name] or check["status"] != ("PASS" if values[name] <= spec[name] else "FAIL"):
            raise ValueError("Stored numerical check contradicts its metric or threshold")
        names.append(name)
    if len(set(names)) != len(names) or set(names) != set(spec):
        raise ValueError("Stored report is missing or duplicates declared checks")
    passed = all(check["status"] == "PASS" for check in checks)
    unsupported = sorted(set(request["desired_observables"]) & EXPANSION_OBSERVABLES)
    if report["status"] != ("PASS" if passed else "FAIL") or report["qualification"] != _qualification(passed, unsupported, checks):
        raise ValueError("Stored qualification contradicts numerical checks or requested observables")
    check_seal(report)
