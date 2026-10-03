"""Retained native calibration/acquisition evidence into a polymer cycle.

This is a data projection, not acquisition, numerical replay, clock certification,
or physical qualification. The full upstream graph and covariance stay retained.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import math
import os
from pathlib import Path
import tempfile

from . import acquired_window, calibrated_window
from .control_contracts import content_ref, keys, number, text
from .polymer_contract import AUTHORITY, MODALITIES, UNITS, validate_request
from .telemetry import canonical, digest, _instant

SCHEMA = "ciw.polymer-ingress.v1"
RECEIPT_SCHEMA = "ciw.polymer-ingress-mapping.v1"
MAX_BYTES = 4 * 1024 * 1024
POLICY = {
    "projection": "all_native_calibrated_samples_without_overrides",
    "metrology": "pointwise_marginal_intervals_without_precision_gain",
    "time": "nominal_mapped_coordinates_with_full_retained_joint_covariance",
    "mapped_covariance_check": "shape_symmetry_marginal_coherence_not_rederived_or_repaired",
    "timing_certificate": "not_established",
    "cycle_membership": "operator_declared_at_nominal_times_not_certified",
    "origin": "caller_declared_not_authenticated_by_native_bundle",
    "cooling": "abstain_unqualified_joint_input_dependence",
    "native_reexecution": "not_performed",
    "fresh_native_numerical_verification": "not_performed",
    "state_and_feature": "retained_separately_not_imported_as_acquired_measurements",
}


def _matrix(value, size):
    """Check retained shape/marginals without requalifying rounded propagation.

    The native source reader validates its declared covariance exactly. Native
    projected matrices are rounded binary64 and may lose exact PSD at a singular
    boundary; do not repair them or confer a new covariance qualification here.
    """
    if type(value) is not list or len(value) != size or any(type(row) is not list or len(row) != size for row in value):
        raise ValueError("Require the full retained mapped covariance matrix")
    for i, row in enumerate(value):
        for j, item in enumerate(row):
            number(item)
            if item != value[j][i] or i == j and item < 0:
                raise ValueError("Mapped covariance must be symmetric with nonnegative marginal variances")
    return value


def _native(bundle):
    if type(bundle) is not dict:
        raise ValueError("Require a retained native bundle")
    if bundle.get("schema") == calibrated_window.SCHEMA:
        source = calibrated_window._source(calibrated_window._validate(bundle))
        child = bundle
    elif bundle.get("schema") == acquired_window.SCHEMA:
        acquired_window._validate(bundle)
        child = bundle["child_window"]
        source = calibrated_window._source(calibrated_window._validate(child))
    else:
        raise ValueError("Only native calibrated-window and acquired-window bundles are supported")
    times, values = (child["steps"][i]["result"]["data"] for i in (0, 1))
    n = len(source["samples"])
    if (type(times.get("samples")) is not list or len(times["samples"]) != n or
            type(values.get("samples")) is not list or len(values["samples"]) != n):
        raise ValueError("Native sample count differs from the retained source")
    time_cov = _matrix(times["temporal_covariance"], n)
    value_cov = _matrix(values["temporal_covariance"], n)
    joint = _matrix(values["joint_time_value_covariance"], 2 * n)
    if ([row[:n] for row in joint[:n]] != time_cov or
            [row[n:] for row in joint[n:]] != value_cov):
        raise ValueError("Native joint covariance blocks differ from retained marginal matrices")
    profile = source["calibration_profile"]
    samples = []
    for i, (raw, aligned, calibrated) in enumerate(zip(source["samples"], times["samples"], values["samples"])):
        if aligned.get("observation_id") != raw["observation_id"]:
            raise ValueError("Native mapped time observation differs from source sample")
        number(aligned["event_time"])
        reconciliation = aligned["reconciliation"]
        observation = reconciliation["observation"]
        if (observation.get("evidence_id") != raw["artifact_id"] or
                observation.get("device_time") != raw["device_time"] or
                observation.get("frame") != source["device_clock"] or
                observation.get("received_at") != {"value": raw["received_at"], "frame": source["receipt_clock"]} or
                reconciliation.get("operation_id") != "tbrt.affine-clock-reconcile.v1" or
                reconciliation.get("propagation") != "first-order.v1"):
            raise ValueError("Native timestamp reconciliation differs from its retained raw observation")
        if (Fraction(source["clock_model"]["reference_origin"]) + Fraction(number(reconciliation["event_time_delta"])) !=
                Fraction(aligned["event_time"]) or reconciliation.get("model") != source["clock_model"] or
                reconciliation.get("variance") != time_cov[i][i]):
            raise ValueError("Native time marginal differs from its retained reconciliation")
        expected = {"observation_id": raw["observation_id"], "source_artifact_id": raw["artifact_id"],
                    "operation_id": "mcur.affine-first-order.v1",
                    "profile_id": profile["profile_id"], "calibration_artifact_id": profile["artifact_id"],
                    "reference_ids": profile["reference_ids"], "acquired_at": _instant(source["epoch"], aligned["event_time"]),
                    "raw_value": raw["raw_value"], "indicated_value": raw["indicated_value"],
                    "input_unit": profile["input_unit"], "output_unit": profile["output_unit"]}
        if any(calibrated.get(key) != value for key, value in expected.items()):
            raise ValueError("Native calibrated sample identity/raw quantity differs from retained source")
        number(calibrated["corrected_value"])
        variance = number(calibrated["variance"])
        uncertainty = number(calibrated["standard_uncertainty"])
        if variance < 0 or variance != value_cov[i][i] or uncertainty != math.sqrt(variance):
            raise ValueError("Native calibrated standard uncertainty differs from its covariance marginal")
        samples.append({"time_s": aligned["event_time"], "value": calibrated["corrected_value"],
                        "standard_uncertainty": calibrated["standard_uncertainty"]})
    return source, child, samples, any(time_cov[i][i] != 0 for i in range(n))


def _project(template, upstreams, bindings):
    template = validate_request(template)
    if type(upstreams) is not list or not 1 <= len(upstreams) <= 32:
        raise ValueError("Require 1..32 full retained native upstreams")
    native, native_digests = {}, {}
    for upstream in upstreams:
        keys(upstream, {"bundle_ref", "bundle"})
        content_ref(upstream["bundle_ref"])
        if upstream["bundle_ref"] != digest(upstream["bundle"]) or upstream["bundle_ref"] in native:
            raise ValueError("Native full-bundle content reference differs or repeats")
        native[upstream["bundle_ref"]] = _native(upstream["bundle"])
        native_digests[upstream["bundle_ref"]] = upstream["bundle"]["bundle_digest"]
    if type(bindings) is not list or len(bindings) != len(upstreams):
        raise ValueError("Bind every native bundle exactly once; no hidden upstream selection")
    request = deepcopy(template)
    request["sensors"] = []
    rows, used, sensor_ids, epochs, uncertain_pressure = [], set(), set(), set(), set()
    for binding in bindings:
        keys(binding, {"sensor_id", "bundle_ref", "quantity", "modality", "max_age_s"})
        sid = text(binding["sensor_id"])
        ref = content_ref(binding["bundle_ref"])
        if ref not in native or ref in used or sid in sensor_ids:
            raise ValueError("Require distinct exact native sensor/bundle bindings")
        used.add(ref)
        sensor_ids.add(sid)
        source, child, samples, uncertain_time = native[ref]
        profile = source["calibration_profile"]
        quantity = binding["quantity"]
        if (quantity not in UNITS or profile["quantity_id"] != quantity or
                profile["sensor_id"] != sid or profile["output_unit"] != UNITS[quantity]):
            raise ValueError("Sensor identity, quantity semantics and SI unit must match native calibration exactly")
        if binding["modality"] not in MODALITIES:
            raise ValueError("Unsupported declared quantitative modality")
        if source["frame"]["id"] != template["frame"] or source["receipt_clock"]["clock_id"] != template["clock"]["id"]:
            raise ValueError("Native frame and reference clock must match the template; no implicit mapping")
        epochs.add(source["epoch"])
        sensor = {"sensor_id": sid, "quantity": quantity, "unit": profile["output_unit"],
                  "modality": binding["modality"], "frame": source["frame"]["id"],
                  "clock_id": source["receipt_clock"]["clock_id"],
                  "calibration_ref": digest(profile), "clock_ref": digest(source["clock_model"]),
                  "source_ref": child["steps"][1]["result_id"],
                  "origin": "synthetic" if template["source_kind"] == "synthetic" else "observed",
                  "samples": deepcopy(samples), "max_age_s": binding["max_age_s"]}
        request["sensors"].append(sensor)
        if uncertain_time and quantity == "cavity_pressure":
            uncertain_pressure.add(sid)
        rows.append({"sensor_id": sid, "bundle_ref": ref, "native_bundle_digest": native_digests[ref],
            "child_bundle_digest": child["bundle_digest"], "native_source_ref": child["source"]["evidence"][0]["artifact_ref"],
            "time_result_ref": child["steps"][0]["result_id"], "calibration_result_ref": child["steps"][1]["result_id"],
            "time_execution_ref": child["steps"][0]["execution_id"],
            "calibration_execution_ref": child["steps"][1]["execution_id"],
            "calibration_ref": sensor["calibration_ref"], "clock_ref": sensor["clock_ref"],
            "observation_ids": [sample["observation_id"] for sample in source["samples"]],
            "artifact_ids": [sample["artifact_id"] for sample in source["samples"]],
            "sample_projection_ref": digest(samples), "retained_joint_covariance_ref": digest(source["joint_covariance"]),
            "mapped_joint_covariance_ref": digest(child["steps"][1]["result"]["data"]["joint_time_value_covariance"]),
            "nonzero_mapped_time_uncertainty": uncertain_time})
    if len(epochs) != 1:
        raise ValueError("Native bundles must share their exact retained epoch; no implicit rebasing")
    # The existing cooling oracle assumes independent input uncertainties. An
    # ingress declaration does not qualify that assumption for native joint data.
    token = digest({"template": template, "bindings": bindings, "upstreams": [u["bundle_ref"] for u in upstreams]})[7:]
    withheld_part = "polymer-ingress.unqualified-part." + token
    withheld_boundary = "polymer-ingress.unqualified-boundary." + token
    withheld_pressure = "polymer-ingress.unqualified-pressure." + token
    if any(sid in sensor_ids for sid in (withheld_part, withheld_boundary, withheld_pressure)):
        raise ValueError("Reserved abstention identity collides with an imported channel")
    request["model"]["cooling"]["temperature_sensor_id"] = withheld_part
    request["model"]["cooling"]["ambient_sensor_id"] = withheld_boundary
    original_arrivals = template["model"]["cavity_arrival"]["pressure_sensor_ids"]
    request["model"]["cavity_arrival"]["pressure_sensor_ids"] = [
        withheld_pressure + "." + str(i) if sid in uncertain_pressure else sid
        for i, sid in enumerate(original_arrivals)]
    if any(sid in sensor_ids for sid in request["model"]["cavity_arrival"]["pressure_sensor_ids"] if sid.startswith(withheld_pressure)):
        raise ValueError("Reserved timing abstention identity collides with an imported channel")
    request = validate_request(request)
    receipt = {"schema": RECEIPT_SCHEMA, "template_ref": digest(template),
               "upstream_refs": [u["bundle_ref"] for u in upstreams], "request_ref": digest(request),
               "epoch": next(iter(epochs)), "policy": deepcopy(POLICY), "channels": rows,
               "withheld_model_bindings": {"temperature_sensor_id": withheld_part,
                   "ambient_sensor_id": withheld_boundary,
                   "pressure_sensor_ids": [sid for sid in original_arrivals if sid in uncertain_pressure]},
               "authority": deepcopy(AUTHORITY)}
    receipt["receipt_ref"] = digest(receipt)
    return request, receipt


def make_envelope(template: dict, bundles: list[dict], bindings: list[dict]) -> dict:
    """Build an offline envelope; bindings cannot override native sample fields.

    A binding names exact sensor_id, bundle_ref=digest(full bundle), quantity,
    declared modality and max_age_s. Template sensor rows are wholly replaced.
    """
    upstreams = [{"bundle_ref": digest(bundle), "bundle": deepcopy(bundle)} for bundle in bundles]
    request, receipt = _project(template, upstreams, bindings)
    value = {"schema": SCHEMA, "template": deepcopy(template), "upstreams": upstreams,
             "bindings": deepcopy(bindings), "derived_request": request,
             "mapping_receipt": receipt, "authority": deepcopy(AUTHORITY)}
    value["receipt_ref"] = digest(value)
    return validate(value)


def validate(envelope: dict) -> dict:
    """Validate complete retained lineage and exact mapping, without execution."""
    try:
        keys(envelope, {"schema", "template", "upstreams", "bindings", "derived_request",
                        "mapping_receipt", "authority", "receipt_ref"})
        if len(canonical(envelope)) > MAX_BYTES:
            raise ValueError("Polymer ingress envelope exceeds 4 MiB")
        if envelope["schema"] != SCHEMA or envelope["authority"] != AUTHORITY:
            raise ValueError("Polymer ingress schema or authority differs")
        content_ref(envelope["receipt_ref"])
        if envelope["receipt_ref"] != digest({k: v for k, v in envelope.items() if k != "receipt_ref"}):
            raise ValueError("Polymer ingress full content binding differs")
        request, receipt = _project(envelope["template"], envelope["upstreams"], envelope["bindings"])
        if canonical(envelope["derived_request"]) != canonical(request) or canonical(envelope["mapping_receipt"]) != canonical(receipt):
            raise ValueError("Polymer ingress differs from exact native sample and uncertainty derivation")
        return deepcopy(envelope)
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("Malformed polymer ingress envelope") from exc


def derive(envelope: dict) -> dict:
    """Return the detached exact cycle request of a validated retained envelope."""
    return validate(envelope)["derived_request"]


def load_file(path: Path) -> dict:
    """Strict bounded ingress read, including native retained byte encodings."""
    from .session import loads_json
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Require a regular native ingress envelope")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Native ingress envelope exceeds the 4 MiB file budget")
    return validate(loads_json(raw.decode("utf-8")))


def save_file(path: Path, envelope: dict) -> None:
    """Atomically create a complete envelope; preserve native strings unchanged."""
    raw = canonical(validate(envelope))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".polymer-ingress-", dir=path.parent) as temporary:
        staged = Path(temporary) / "ingress.json"
        with staged.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, path)
