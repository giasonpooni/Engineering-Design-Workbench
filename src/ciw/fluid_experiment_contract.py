"""Data-only contracts for bounded held-out fluid observations.

No numerical model, covariance factorization or statistical test is replayed by
these validators. A declaration of measurement is not authentication of a sensor.
"""
from __future__ import annotations
from copy import deepcopy
import csv
from datetime import datetime
from hashlib import sha256
import io
import math
import re

from .control_contracts import keys, text, number, content_ref, json_tree
from .operations.runner import digest, seal, check_seal
from .fluid_reservoir_contract import CLOCK_ID, example_request

METADATA_SCHEMA = "ciw.fluid-experiment-metadata.v1"
RESULT_SCHEMA = "ciw.fluid-experiment-comparison.v1"
REPORT_SCHEMA = "ciw.fluid-experiment-verification.v1"
COMPARE_OPERATION = "fluid.experiment.compare.v1"
VERIFY_OPERATION = "fluid.experiment.verify.v1"
INSTRUMENT = "fluid-experiment-observations.v1"
FRAME = "two_reservoir_vertical_head_and_outward_piston"
BASELINE = "hydrostatic_pressure_deviation_from_preloaded_equilibrium"
MAX_ROWS = 16
MAX_CHANNELS = 2
MAX_AXES = MAX_ROWS * MAX_CHANNELS
MAX_INPUT_BYTES = 65536
UNITS = {"head1_m": "m", "head2_m": "m", "pressure1_deviation_pa": "Pa", "pressure2_deviation_pa": "Pa",
         "flow_m3_per_s": "m^3/s", "connector_velocity_m_per_s": "m/s", "piston_displacement_m": "m", "piston_velocity_m_per_s": "m/s"}
TERMS = ("measurement", "parameter_prediction", "model_discrepancy", "numerical_interpolation")
OUTCOMES = {"EMPIRICALLY_COMPATIBLE", "INCOMPATIBLE", "INCONCLUSIVE"}
AUTHORITY = {"measurement_authenticity": "operator_declaration_only", "calibration_authenticity": "not_authenticated",
             "physical_validation": "not_established", "causal_inference": "not_established",
             "state_admission": "not_performed", "hardware_actuation": "not_performed"}


def refs(value):
    if type(value) is not list or not 1 <= len(value) <= 16 or len(set(value)) != len(value):
        raise ValueError("Require bounded distinct content references")
    for item in value:
        content_ref(item)


def labels(value, *, empty=True):
    if type(value) is not list or len(value) > 32 or (not empty and not value) or len(set(value)) != len(value):
        raise ValueError("Require distinct bounded labels")
    for item in value:
        text(item)


def matrix(value, size):
    """Structural covariance check only; positive semidefiniteness is executable."""
    if value is None:
        return
    if type(value) is not list or len(value) != size or any(type(row) is not list or len(row) != size for row in value):
        raise ValueError("Covariance must use all declared stacked axes")
    for i, row in enumerate(value):
        for j, item in enumerate(row):
            number(item)
            if item != value[j][i]:
                raise ValueError("Covariance must be exactly symmetric; no repair is performed")
        if row[i] < 0 or (row[i] == 0 and any(item != 0 for item in row)):
            raise ValueError("Covariance diagonal or zero-variance row is invalid")


def validate_metadata(value):
    json_tree(value)
    keys(value, {"schema", "profile", "csv_sha256", "target_request_digest", "coordinate_frame", "baseline",
                 "provenance", "observation_operator", "clock", "split", "uncertainty"})
    if value["schema"] != METADATA_SCHEMA or value["profile"] != "reservoir":
        raise ValueError("EXPAND: only the qualified reservoir observation operator is available")
    content_ref(value["csv_sha256"])
    content_ref(value["target_request_digest"])
    if value["coordinate_frame"] != FRAME or value["baseline"] != BASELINE:
        raise ValueError("Exact coordinate frame and preloaded equilibrium baseline are required")
    provenance = value["provenance"]
    keys(provenance, {"source_kind", "acquisition_id", "operator_id", "sensor_id", "acquired_at_utc", "declaration"})
    if provenance["source_kind"] not in {"synthetic_fixture", "declared_measured"} or provenance["declaration"] != "operator_declaration_only_not_authenticated":
        raise ValueError("Source semantics must distinguish synthetic fixtures and declared measurements")
    for key in ("acquisition_id", "operator_id", "sensor_id", "acquired_at_utc"):
        text(provenance[key])
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", provenance["acquired_at_utc"]) is None:
        raise ValueError("Acquisition timestamp must declare UTC seconds")
    try:
        datetime.strptime(provenance["acquired_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError("Acquisition timestamp must be a valid UTC calendar time") from exc
    operator = value["observation_operator"]
    keys(operator, {"kind", "channels", "spatial_semantics"})
    if operator["kind"] != "direct_retained_state_linear_time_interpolation.v1" or operator["spatial_semantics"] != "lumped_reservoir_state_no_local_sensor_field_resolution":
        raise ValueError("Only the declared lumped direct-state observation operator is supported")
    channels = operator["channels"]
    if type(channels) is not list or not 1 <= len(channels) <= MAX_CHANNELS:
        raise ValueError("Observation channel budget exceeded")
    for channel in channels:
        keys(channel, {"column", "model_field", "unit"})
        if channel["model_field"] not in UNITS or channel["column"] != channel["model_field"] or channel["unit"] != UNITS[channel["model_field"]]:
            raise ValueError("Exact supported SI channel names and units are required; conversion is not implicit")
    if len({row["column"] for row in channels}) != len(channels):
        raise ValueError("Duplicate observation channels")
    clock = value["clock"]
    keys(clock, {"id", "target_model_clock", "scale", "offset_s", "offset_standard_uncertainty_s", "distribution", "propagation", "alignment_window_sigma"})
    text(clock["id"])
    number(clock["scale"])
    number(clock["alignment_window_sigma"])
    if clock["target_model_clock"] != CLOCK_ID or clock["scale"] != 1.0 or clock["distribution"] != "zero_mean_gaussian" or clock["propagation"] != "linearized_common_offset_outer_product" or clock["alignment_window_sigma"] != 3.0:
        raise ValueError("Clock alignment requires an explicit common Gaussian offset and unit scale")
    number(clock["offset_s"])
    if abs(clock["offset_s"]) > 1e6:
        raise ValueError("Clock offset exceeds bound")
    if clock["offset_standard_uncertainty_s"] is not None and not 0 <= number(clock["offset_standard_uncertainty_s"]) <= 1e3:
        raise ValueError("Clock standard uncertainty exceeds bound")
    split = value["split"]
    keys(split, {"holdout_dataset_id", "calibration_dataset_ids", "parameter_fit_dataset_ids", "calibration_sample_ids", "parameter_fit_sample_ids", "calibration_refs", "parameter_fit_refs", "fixed_parameters_before_holdout", "uncertainty_specified_before_holdout"})
    text(split["holdout_dataset_id"])
    for key in ("calibration_dataset_ids", "parameter_fit_dataset_ids", "calibration_sample_ids", "parameter_fit_sample_ids"):
        labels(split[key])
    if split["holdout_dataset_id"] in split["calibration_dataset_ids"] + split["parameter_fit_dataset_ids"]:
        raise ValueError("Holdout dataset overlaps calibration or parameter fitting")
    refs(split["calibration_refs"])
    if not split["calibration_dataset_ids"]:
        raise ValueError("Calibration references require a separate declared calibration dataset")
    if split["parameter_fit_refs"]:
        refs(split["parameter_fit_refs"])
    elif type(split["parameter_fit_refs"]) is not list:
        raise ValueError("Parameter fit references must be a list")
    if bool(split["parameter_fit_refs"]) != bool(split["parameter_fit_dataset_ids"]):
        raise ValueError("Parameter fitting requires both separate dataset identities and content references")
    if value["csv_sha256"] in split["calibration_refs"] + split["parameter_fit_refs"]:
        raise ValueError("Holdout CSV cannot calibrate or fit the evaluated model")
    if split["fixed_parameters_before_holdout"] is not True or split["uncertainty_specified_before_holdout"] is not True:
        raise ValueError("Fixed parameters and uncertainty specified before holdout are mandatory")
    uncertainty = value["uncertainty"]
    keys(uncertainty, {"distribution", "terms_mutually_independent", "axes", "alpha", *TERMS})
    if uncertainty["distribution"] != "joint_zero_mean_gaussian" or uncertainty["terms_mutually_independent"] is not True:
        raise ValueError("Gaussian covariance combination requires declared mutual independence")
    if not 1e-6 <= number(uncertainty["alpha"]) <= 0.25:
        raise ValueError("Declared significance level exceeds supported range")
    axes = uncertainty["axes"]
    labels(axes, empty=False)
    if len(axes) > MAX_AXES:
        raise ValueError("Stacked covariance budget exceeded")
    for term in TERMS:
        keys(uncertainty[term], {"matrix", "rationale", "source_refs"})
        matrix(uncertainty[term]["matrix"], len(axes))
        text(uncertainty[term]["rationale"])
        refs(uncertainty[term]["source_refs"])
        if value["csv_sha256"] in uncertainty[term]["source_refs"]:
            raise ValueError("Held-out observations cannot specify their own uncertainty or model discrepancy")
    return deepcopy(value)


def parse_csv(raw, metadata):
    metadata = validate_metadata(metadata)
    if type(raw) is not str or not 0 < len(raw.encode("utf-8")) <= MAX_INPUT_BYTES:
        raise ValueError("CSV exceeds bounded UTF-8 input budget")
    if "sha256:" + sha256(raw.encode("utf-8")).hexdigest() != metadata["csv_sha256"]:
        raise ValueError("CSV bytes differ from declared file hash")
    columns = [row["column"] for row in metadata["observation_operator"]["channels"]]
    reader = csv.reader(io.StringIO(raw, newline=""), strict=True)
    if next(reader, None) != ["sample_id", "time_s", "role", *columns]:
        raise ValueError("CSV header must exactly match the declared observation operator")
    rows = []
    for row in reader:
        if len(rows) >= MAX_ROWS or len(row) != 3 + len(columns):
            raise ValueError("CSV row count or width exceeds the declared schema")
        sample_id, timestamp, role, *values = row
        text(sample_id)
        if role not in {"holdout", "calibration"}:
            raise ValueError("CSV rows must explicitly declare holdout or calibration role")
        try:
            timestamp = number(float(timestamp))
            values = [number(float(item)) for item in values]
        except (ValueError, OverflowError) as exc:
            raise ValueError("CSV numeric observations must be finite SI values") from exc
        if timestamp < 0 or (rows and timestamp <= rows[-1]["time_s"]):
            raise ValueError("CSV acquisition times must be nonnegative and strictly increasing")
        if sample_id in {item["sample_id"] for item in rows}:
            raise ValueError("CSV sample identities must be distinct")
        rows.append({"sample_id": sample_id, "time_s": timestamp, "role": role, "values": values})
    heldout = [row for row in rows if row["role"] == "holdout"]
    if not heldout:
        raise ValueError("A held-out observation is required")
    split = metadata["split"]
    ids = {row["sample_id"] for row in heldout}
    if ids.intersection(split["calibration_sample_ids"] + split["parameter_fit_sample_ids"]):
        raise ValueError("Holdout samples overlap calibration or parameter fitting")
    if any(row["sample_id"] not in split["calibration_sample_ids"] for row in rows if row["role"] == "calibration"):
        raise ValueError("Calibration CSV rows require declared calibration sample identities")
    axes = [row["sample_id"] + "/" + column for row in heldout for column in columns]
    if axes != metadata["uncertainty"]["axes"]:
        raise ValueError("Covariance axes must exactly follow held-out row-major sample/channel order")
    return rows


def template(profile="reservoir"):
    if profile != "reservoir":
        raise ValueError("EXPAND: no qualified spatial observation operator for this profile")
    reference = "sha256:" + sha256(b"synthetic fixture uncertainty declaration; no measured calibration").hexdigest()
    axes = ["s" + str(index) + "/head1_m" for index in range(3)]
    zero = [[0.0] * 3 for _ in range(3)]
    terms = {term: {"matrix": deepcopy(zero), "rationale": "Declared zero only for this synthetic pipeline fixture", "source_refs": [reference]} for term in TERMS}
    terms["measurement"]["matrix"] = [[1e-8 if i == j else 0.0 for j in range(3)] for i in range(3)]
    metadata = {"schema": METADATA_SCHEMA, "profile": "reservoir", "csv_sha256": "sha256:" + "0" * 64,
                "target_request_digest": digest(example_request()), "coordinate_frame": FRAME, "baseline": BASELINE,
                "provenance": {"source_kind": "synthetic_fixture", "acquisition_id": "synthetic-example", "operator_id": "fixture-generator", "sensor_id": "no-physical-sensor", "acquired_at_utc": "2026-10-03T00:00:00Z", "declaration": "operator_declaration_only_not_authenticated"},
                "observation_operator": {"kind": "direct_retained_state_linear_time_interpolation.v1", "channels": [{"column": "head1_m", "model_field": "head1_m", "unit": "m"}], "spatial_semantics": "lumped_reservoir_state_no_local_sensor_field_resolution"},
                "clock": {"id": "fixture-clock", "target_model_clock": CLOCK_ID, "scale": 1.0, "offset_s": 0.0, "offset_standard_uncertainty_s": 0.0, "distribution": "zero_mean_gaussian", "propagation": "linearized_common_offset_outer_product", "alignment_window_sigma": 3.0},
                "split": {"holdout_dataset_id": "synthetic-holdout", "calibration_dataset_ids": ["synthetic-external-calibration-declaration"], "parameter_fit_dataset_ids": [], "calibration_sample_ids": [], "parameter_fit_sample_ids": [], "calibration_refs": [reference], "parameter_fit_refs": [], "fixed_parameters_before_holdout": True, "uncertainty_specified_before_holdout": True},
                "uncertainty": {"distribution": "joint_zero_mean_gaussian", "terms_mutually_independent": True, "axes": axes, "alpha": 0.05, **terms}}
    return {"metadata": metadata, "csv_header": ["sample_id", "time_s", "role", "head1_m"]}


def validate_comparison(source, model, value):
    from .fluid_experiment import source_data, validate_model
    metadata, rows = source_data(source)
    validate_model(model)
    keys(value, {"schema", "evidence_id", "model_digest", "model_result_id", "model_execution_id", "model_verification_id", "axes", "aligned_time_s", "observed", "predicted", "residual", "prediction_slopes", "covariance", "statistics", "outcome", "support", "limitations", "record_digest"})
    check_seal(value)
    if value["schema"] != RESULT_SCHEMA or value["evidence_id"] != source["evidence_id"] or value["model_digest"] != model["record_digest"] or value["model_result_id"] != model["candidate"]["result_id"] or value["model_execution_id"] != model["candidate"]["execution_id"] or value["model_verification_id"] != model["fresh_verification"]["verification_id"]:
        raise ValueError("Experimental comparison model/source occurrence binding differs")
    holdout = [row for row in rows if row["role"] == "holdout"]
    size = len(metadata["uncertainty"]["axes"])
    if value["axes"] != metadata["uncertainty"]["axes"] or value["observed"] != [x for row in holdout for x in row["values"]]:
        raise ValueError("Experimental comparison observations differ from exact held-out CSV")
    if value["aligned_time_s"] != [row["time_s"] + metadata["clock"]["offset_s"] for row in holdout]:
        raise ValueError("Comparison clock alignment differs from declared offset")
    for name in ("predicted", "residual", "prediction_slopes"):
        if type(value[name]) is not list or len(value[name]) != size:
            raise ValueError("Comparison vectors must follow stacked covariance axes")
        for item in value[name]:
            number(item)
    if any(value["residual"][i] != value["observed"][i] - value["predicted"][i] for i in range(size)):
        raise ValueError("Retained comparison residual differs from observation minus prediction")
    keys(value["covariance"], {*TERMS, "clock_common_offset", "total", "unknown_terms", "semantics"})
    for term in TERMS:
        if value["covariance"][term] != metadata["uncertainty"][term]["matrix"]:
            raise ValueError("Covariance term differs from declared metadata")
    for name in ("clock_common_offset", "total"):
        matrix(value["covariance"][name], size)
    labels(value["covariance"]["unknown_terms"])
    if value["covariance"]["semantics"] != "full_stacked_covariance_axis_units_products_no_repair":
        raise ValueError("Covariance semantics differ")
    keys(value["statistics"], {"method", "degrees_of_freedom", "chi_square", "upper_tail_probability", "critical_chi_square", "alpha", "reason"})
    stat = value["statistics"]
    if stat["method"] != "fixed_parameter_gaussian_mahalanobis_upper_tail.v1" or type(stat["degrees_of_freedom"]) is not int or stat["degrees_of_freedom"] != size or stat["alpha"] != metadata["uncertainty"]["alpha"]:
        raise ValueError("Statistics must declare fixed parameters and stacked degrees of freedom")
    for name in ("chi_square", "upper_tail_probability", "critical_chi_square"):
        if stat[name] is not None:
            number(stat[name])
    if stat["chi_square"] is not None and stat["chi_square"] < 0:
        raise ValueError("Negative chi square")
    if stat["upper_tail_probability"] is not None and not 0 <= stat["upper_tail_probability"] <= 1:
        raise ValueError("Invalid upper tail probability")
    text(stat["reason"])
    if value["outcome"] not in OUTCOMES:
        raise ValueError("Invalid empirical outcome")
    keys(value["support"], {"source_kind", "conditional_measured_support", "scope", "authority"})
    measured = metadata["provenance"]["source_kind"] == "declared_measured"
    expected = measured and value["outcome"] == "EMPIRICALLY_COMPATIBLE"
    if type(value["support"]["conditional_measured_support"]) is not bool:
        raise ValueError("Measured support must be an explicit boolean")
    if value["support"] != {"source_kind": metadata["provenance"]["source_kind"], "conditional_measured_support": expected, "scope": "declared_heldout_observables_times_baseline_and_uncertainty_only", "authority": AUTHORITY}:
        raise ValueError("Synthetic fixture or empirical support authority differs")
    labels(value["limitations"], empty=False)
    return deepcopy(value)
