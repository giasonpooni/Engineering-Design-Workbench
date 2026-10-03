"""Finite instantaneous particle-to-bin observables, never a constitutive arrow.

The reduction preserves extensive mass and momentum. It resolves only each
bin's mean-motion kinetic energy and separately records subcell kinetic energy.
Particle identities, forces, correlations, pressure and transport information
are not reconstructed. A retained source report is content evidence, not fresh
physics, empirical validation, uncertainty calibration or state admission.
"""
from __future__ import annotations

from copy import deepcopy
import math
import sys

from .control_contracts import json_tree, keys, number
from .operations.runner import check_seal, digest, seal

SNAPSHOT_SCHEMA = "ciw.fluid-particle-snapshot.v1"
MAP_SCHEMA = "ciw.fluid-scale-map.v1"
REPORT_SCHEMA = "ciw.fluid-scale-map-verification.v1"
SEMANTICS = {"molecular": "structureless_atomistic_interaction_site",
             "sph": "equal_mass_sph_continuum_parcel"}
MAX_PARTICLES = 256
MAX_BINS = 4096
ROUND_OFF = 512.0 * sys.float_info.epsilon
CLAIMS = {
    "instantaneous_declared_observable_map_only": True,
    "source_report_interpretation": "retained_numerical_report_only",
    "source_fresh_physics_replayed": False,
    "constitutive_model_supplied": False,
    "transport_parameters_supplied": False,
    "physical_validation_established": False,
    "si_parameter_calibration_established": False,
    "state_admission_performed": False,
    "execution_authority": False,
}
LOSSES = ["individual_particle_identity", "within_bin_positions", "pair_correlations",
          "interaction_forces", "potential_energy", "pressure_tensor", "transport_coefficients",
          "chemical_identity", "molecular_to_water_equivalence", "temporal_evolution"]


def _digest_ref(value):
    if (type(value) is not str or not value.startswith("sha256:") or len(value) != 71
            or any(char not in "0123456789abcdef" for char in value[7:])):
        raise ValueError("Require an exact SHA256 content reference")


def validate_snapshot(snapshot: dict) -> dict:
    """Validate a sealed typed declaration; never run its source provider."""
    json_tree(snapshot)
    keys(snapshot, {"schema", "profile", "particle_semantics", "source_refs", "sample",
                    "unit_system", "units", "frame", "dimension", "periodic_lengths",
                    "cross_section_area", "particle_masses", "positions", "velocities", "record_digest"})
    if (snapshot["schema"] != SNAPSHOT_SCHEMA or type(snapshot["profile"]) is not str
            or snapshot["profile"] not in SEMANTICS):
        raise ValueError("Require a supported typed particle snapshot")
    profile = snapshot["profile"]
    if snapshot["particle_semantics"] != SEMANTICS[profile]:
        raise ValueError("Atomic interaction sites and SPH parcels must remain distinct")
    dimension = snapshot["dimension"]
    if type(dimension) is not int or dimension != (3 if profile == "molecular" else 1):
        raise ValueError("Particle snapshot dimension differs from its fixed profile")
    if snapshot["frame"] != "source_periodic_cartesian_frame":
        raise ValueError("No implicit coordinate-frame conversion is supplied")
    unit_system = snapshot["unit_system"]
    units = ({"length": "m", "mass": "kg", "velocity": "m/s", "time": "s",
              "volume": "m^3", "momentum": "kg*m/s", "energy": "J", "density": "kg/m^3"}
             if unit_system == "SI" else
             {"length": "sigma", "mass": "site_mass", "velocity": "sqrt(epsilon/site_mass)",
              "time": "sigma*sqrt(site_mass/epsilon)", "volume": "sigma^3",
              "momentum": "sqrt(site_mass*epsilon)", "energy": "epsilon", "density": "site_mass/sigma^3"}
             if unit_system == "reduced_lj" else None)
    if units is None or snapshot["units"] != units or profile == "sph" and unit_system != "SI":
        raise ValueError("Require exact declared SI or reduced-LJ units, without implicit conversion")
    keys(snapshot["units"], set(units))
    keys(snapshot["source_refs"], {"request_digest", "result_digest", "verification_digest"})
    for value in snapshot["source_refs"].values():
        _digest_ref(value)
    sample = snapshot["sample"]
    keys(sample, {"trace", "index", "time"})
    if type(sample["trace"]) is not str or len(sample["trace"]) > 40 or not sample["trace"]:
        raise ValueError("Require a bounded exact source trace name")
    if type(sample["index"]) is not int or not 0 <= sample["index"] <= 4096 or number(sample["time"]) < 0:
        raise ValueError("Require a bounded exact retained sample index and time")
    lengths = snapshot["periodic_lengths"]
    if type(lengths) is not list or len(lengths) != dimension:
        raise ValueError("Require one declared periodic length per axis")
    for length in lengths:
        if not 1e-20 <= number(length) <= 1e6:
            raise ValueError("Periodic length is outside the finite map domain")
    if dimension == 3:
        if snapshot["cross_section_area"] is not None:
            raise ValueError("Three-dimensional maps use the declared box volume")
    elif not 1e-20 <= number(snapshot["cross_section_area"]) <= 1e6:
        raise ValueError("One-dimensional parcel maps require explicit cross-section area")
    masses = snapshot["particle_masses"]
    if type(masses) is not list or not 2 <= len(masses) <= MAX_PARTICLES:
        raise ValueError("Require 2..256 finite declared particles")
    for mass in masses:
        if not 1e-30 <= number(mass) <= 1e6:
            raise ValueError("Particle mass is outside the finite map domain")
    if any(mass != masses[0] for mass in masses):
        raise ValueError("Current atomic-site and SPH profiles require equal declared particle masses")
    for field in ("positions", "velocities"):
        rows = snapshot[field]
        if type(rows) is not list or len(rows) != len(masses):
            raise ValueError("Particle fields must cover every declared mass")
        for row in rows:
            if type(row) is not list or len(row) != dimension:
                raise ValueError("Particle field dimension differs")
            for value in row:
                if abs(number(value)) > 1e9:
                    raise ValueError("Particle field exceeds the finite map domain")
    check_seal(snapshot)
    return deepcopy(snapshot)


def _bins(snapshot, bins_per_axis):
    if type(bins_per_axis) is not list or len(bins_per_axis) != snapshot["dimension"]:
        raise ValueError("Require one explicit bin count per represented axis")
    if any(type(value) is not int or not 1 <= value <= 32 for value in bins_per_axis) or math.prod(bins_per_axis) > MAX_BINS:
        raise ValueError("Bin partition exceeds the bounded allocation")
    return list(bins_per_axis)


def reduce(snapshot: dict, *, bins_per_axis: list[int]) -> dict:
    """Reduce one declared snapshot to periodic bins; no future dynamics implied."""
    snapshot = validate_snapshot(snapshot)
    counts = _bins(snapshot, bins_per_axis)
    dimension, lengths = snapshot["dimension"], snapshot["periodic_lengths"]
    bin_volume = math.prod(length / count for length, count in zip(lengths, counts))
    if dimension == 1:
        bin_volume *= snapshot["cross_section_area"]
    groups = [[] for _ in range(math.prod(counts))]
    for index, position in enumerate(snapshot["positions"]):
        coordinate = [min(count - 1, int((value % length) / length * count))
                      for value, length, count in zip(position, lengths, counts)]
        flat = 0
        for value, count in zip(coordinate, counts):
            flat = flat * count + value
        groups[flat].append(index)
    cells = []
    for flat, members in enumerate(groups):
        index, remainder = [0] * dimension, flat
        for axis in range(dimension - 1, -1, -1):
            index[axis] = remainder % counts[axis]
            remainder //= counts[axis]
        mass = math.fsum(snapshot["particle_masses"][i] for i in members)
        momentum = [math.fsum(snapshot["particle_masses"][i] * snapshot["velocities"][i][axis]
                              for i in members) for axis in range(dimension)]
        mean = [value / mass for value in momentum] if mass else None
        kinetic = math.fsum(0.5 * snapshot["particle_masses"][i] * math.fsum(value * value for value in snapshot["velocities"][i])
                            for i in members)
        resolved = 0.5 * math.fsum(value * speed for value, speed in zip(momentum, mean)) if mean is not None else 0.0
        # Weighted variance is nonnegative. Evaluate directly to avoid losing
        # subcell energy when mean motion dominates fluctuation velocity.
        subcell = (math.fsum(0.5 * snapshot["particle_masses"][i] * math.fsum(
            (value - speed)**2 for value, speed in zip(snapshot["velocities"][i], mean)) for i in members)
                   if mean is not None else 0.0)
        cells.append({"index": index, "particle_count": len(members), "volume": bin_volume,
                      "mass": mass, "mass_density": mass / bin_volume, "momentum": momentum,
                      "mean_velocity": mean, "particle_kinetic_energy": kinetic,
                      "resolved_kinetic_energy": resolved, "subcell_kinetic_energy": subcell})
    return seal({"schema": MAP_SCHEMA, "source_snapshot_digest": snapshot["record_digest"],
                 "source_refs": deepcopy(snapshot["source_refs"]), "particle_semantics": snapshot["particle_semantics"],
                 "sample": deepcopy(snapshot["sample"]), "unit_system": snapshot["unit_system"],
                 "units": deepcopy(snapshot["units"]), "frame": snapshot["frame"],
                 "bins_per_axis": counts, "periodic_lengths": list(lengths), "cells": cells,
                 "claims": deepcopy(CLAIMS), "discarded_information": list(LOSSES)})


def verify(snapshot: dict, mapped: dict) -> dict:
    """Explicit finite observable verification; does not verify source physics."""
    snapshot = validate_snapshot(snapshot)
    json_tree(mapped)
    check_seal(mapped)
    if type(mapped.get("bins_per_axis")) is not list:
        raise ValueError("Require a declared particle-bin partition")
    expected = reduce(snapshot, bins_per_axis=mapped["bins_per_axis"])
    if mapped != expected:
        raise ValueError("Particle-bin result differs from its exact declared instantaneous reduction")
    source_mass = math.fsum(snapshot["particle_masses"])
    mapped_mass = math.fsum(cell["mass"] for cell in mapped["cells"])
    source_momentum = [math.fsum(mass * velocity[axis] for mass, velocity in zip(snapshot["particle_masses"], snapshot["velocities"]))
                       for axis in range(snapshot["dimension"])]
    mapped_momentum = [math.fsum(cell["momentum"][axis] for cell in mapped["cells"]) for axis in range(snapshot["dimension"])]
    momentum_scale = math.fsum(mass * math.sqrt(math.fsum(value * value for value in velocity))
                               for mass, velocity in zip(snapshot["particle_masses"], snapshot["velocities"]))
    source_kinetic = math.fsum(0.5 * mass * math.fsum(value * value for value in velocity)
                              for mass, velocity in zip(snapshot["particle_masses"], snapshot["velocities"]))
    kinetic_split = math.fsum(cell["resolved_kinetic_energy"] + cell["subcell_kinetic_energy"] for cell in mapped["cells"])
    residuals = {"mass_relative": abs(mapped_mass - source_mass) / source_mass,
                 "momentum_normalized": max(abs(a - b) for a, b in zip(source_momentum, mapped_momentum)) / max(momentum_scale, 1e-300),
                 "kinetic_split_relative": abs(source_kinetic - kinetic_split) / max(source_kinetic, 1e-300)}
    passed = all(value <= ROUND_OFF for value in residuals.values())
    return seal({"schema": REPORT_SCHEMA, "snapshot_digest": snapshot["record_digest"],
                 "map_digest": mapped["record_digest"], "status": "PASS" if passed else "FAIL",
                 "qualification": {"action": "LOCAL" if passed else "REFUSE",
                     "scope": "finite_instantaneous_mass_momentum_and_kinetic_split_only"},
                 "residuals": residuals, "tolerance": ROUND_OFF, "claims": deepcopy(CLAIMS),
                 "discarded_information": list(LOSSES)})


def molecular_snapshot(request: dict, result: dict, report: dict, *, sample_index: int,
                       trace: str = "time_fine") -> dict:
    """Bind one retained LJ sample, optionally using explicit unvalidated SI scales."""
    from .fluid_molecular_contract import validate_request, validate_result
    from .fluid_molecular_verification import validate_report
    request = validate_request(request)
    result = validate_result(request, result)
    validate_report(request, result, report)
    if report["status"] != "PASS" or report["qualification"]["action"] != "LOCAL":
        raise ValueError("Require a retained LOCAL numerical source report")
    if trace not in ("primary", "time_refined", "time_fine") or type(sample_index) is not int or not 0 <= sample_index < len(result[trace]["time_reduced"]):
        raise ValueError("Require one exact retained molecular sample")
    scaling, source = request["si_scaling"], result[trace]
    length = scaling["sigma_m"] if scaling else 1.0
    mass = scaling["site_mass_kg"] if scaling else 1.0
    velocity_scale = math.sqrt(scaling["epsilon_j"] / mass) if scaling else 1.0
    time_scale = length / velocity_scale
    unit_system = "SI" if scaling else "reduced_lj"
    units = ({"length": "m", "mass": "kg", "velocity": "m/s", "time": "s", "volume": "m^3",
              "momentum": "kg*m/s", "energy": "J", "density": "kg/m^3"} if scaling else
             {"length": "sigma", "mass": "site_mass", "velocity": "sqrt(epsilon/site_mass)",
              "time": "sigma*sqrt(site_mass/epsilon)", "volume": "sigma^3",
              "momentum": "sqrt(site_mass*epsilon)", "energy": "epsilon", "density": "site_mass/sigma^3"})
    snapshot = seal({"schema": SNAPSHOT_SCHEMA, "profile": "molecular", "particle_semantics": SEMANTICS["molecular"],
        "source_refs": {"request_digest": digest(request), "result_digest": result["record_digest"], "verification_digest": report["record_digest"]},
        "sample": {"trace": trace, "index": sample_index, "time": time_scale * source["time_reduced"][sample_index]},
        "unit_system": unit_system, "units": units, "frame": "source_periodic_cartesian_frame", "dimension": 3,
        "periodic_lengths": [length * request["model"]["box_length_reduced"]] * 3, "cross_section_area": None,
        "particle_masses": [mass] * len(request["model"]["positions_reduced"]),
        "positions": [[length * value for value in row] for row in source["positions_reduced"][sample_index]],
        "velocities": [[velocity_scale * value for value in row] for row in source["velocities_reduced"][sample_index]]})
    return validate_snapshot(snapshot)


def sph_snapshot(request: dict, result: dict, report: dict, *, sample_index: int,
                 trace: str = "time_fine") -> dict:
    """Bind one retained moving parcel sample with its declared SI cross section."""
    from .fluid_sph_contract import validate_request, validate_result
    from .fluid_sph_verification import validate_report
    request = validate_request(request)
    result = validate_result(request, result)
    validate_report(request, result, report)
    if report["status"] != "PASS" or report["qualification"]["action"] != "LOCAL":
        raise ValueError("Require a retained LOCAL numerical source report")
    if type(trace) is not str or trace not in result["resolutions"] or type(sample_index) is not int or not 0 <= sample_index < len(result["resolutions"][trace]["time_s"]):
        raise ValueError("Require one exact retained SPH sample")
    source = result["resolutions"][trace]
    snapshot = seal({"schema": SNAPSHOT_SCHEMA, "profile": "sph", "particle_semantics": SEMANTICS["sph"],
        "source_refs": {"request_digest": digest(request), "result_digest": result["record_digest"], "verification_digest": report["record_digest"]},
        "sample": {"trace": trace, "index": sample_index, "time": source["time_s"][sample_index]},
        "unit_system": "SI", "units": {"length": "m", "mass": "kg", "velocity": "m/s", "time": "s",
            "volume": "m^3", "momentum": "kg*m/s", "energy": "J", "density": "kg/m^3"},
        "frame": "source_periodic_cartesian_frame", "dimension": 1,
        "periodic_lengths": [request["model"]["length_m"]], "cross_section_area": request["model"]["area_m2"],
        "particle_masses": [source["parcel_mass_kg"]] * source["particles"],
        "positions": [[value] for value in source["unwrapped_position_m"][sample_index]],
        "velocities": [[value] for value in source["velocity_m_per_s"][sample_index]]})
    return validate_snapshot(snapshot)


def particle_snapshot(profile: str, request: dict, result: dict, report: dict, *, sample_index: int,
                      trace: str = "time_fine") -> dict:
    """Fixed trusted snapshot dispatch; no saved provider path is imported."""
    if profile == "molecular":
        return molecular_snapshot(request, result, report, sample_index=sample_index, trace=trace)
    if profile == "sph":
        return sph_snapshot(request, result, report, sample_index=sample_index, trace=trace)
    raise ValueError("Only atomistic interaction sites and SPH parcels have particle-bin maps")
