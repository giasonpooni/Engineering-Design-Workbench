"""Offline mapping boundaries plus an optional actual pinned-provider fixture.

The local graph fixture is an integrity-only provider double, not evidence that
native numerical code executed. The separately supplied native gate covers that.
"""
import base64
from copy import deepcopy
from hashlib import sha256
import json
import math
import os
from pathlib import Path

import pytest

from ciw import acquired_window, calibrated_window as window, polymer_ingress as ingress
from ciw.polymer_contract import AUTHORITY, example_request
from ciw.polymer_models import engineering_estimate
from ciw.telemetry import canonical, digest, _instant

ROOT = Path(__file__).resolve().parents[1]


def native_seal(value, field="result_id"):
    value[field] = "sha256:" + sha256(value["schema"].encode() + b"\0" + canonical(value)).hexdigest()
    return value


class IntegrityRuntime:
    def __init__(self, role):
        self.role = role

    def runtime_identity(self):
        return dict(window._pins()[self.role], schema="ciw.subprocess-runtime.v1",
                    source_tree="a" * 40, python_sha256="b" * 64,
                    python_version="integrity-fixture-only", dependencies={})


def integrity_bundle(monkeypatch, quantity="part_dimension", sensor_id="sensor:dimension", epoch=None, tamper=None):
    source = json.loads((ROOT / "examples/calibrated-window/source.json").read_bytes())
    source["calibration_profile"].update(quantity_id=quantity, sensor_id=sensor_id)
    source["calibration_profile"]["output_unit"] = "K" if "temperature" in quantity else "Pa" if quantity == "cavity_pressure" else "m"
    for sample in source["samples"]:
        sample.update(quantity_id=quantity, sensor_id=sensor_id)
    if epoch:
        source["epoch"] = epoch
    def invoke(role, adapters, request):
        if role == "tbrt":
            return {"samples": [{"observation_id": row["observation_id"], "event_time": i,
                "reconciliation": {"event_time_delta": i, "model": deepcopy(source["clock_model"]),
                    "variance": [.25, .5][i], "operation_id": "tbrt.affine-clock-reconcile.v1", "propagation": "first-order.v1",
                    "observation": {"evidence_id": row["artifact_id"], "device_time": row["device_time"],
                                    "frame": source["device_clock"], "received_at": {"value": row["received_at"], "frame": source["receipt_clock"]}}
                }} for i, row in enumerate(source["samples"])],
                "temporal_covariance": [[.25, .25], [.25, .5]], "time_policy": window.COMPOSITION["time_policy"]}
        if role == "mcur":
            profile = source["calibration_profile"]
            samples = []
            for i, row in enumerate(source["samples"]):
                samples.append({"observation_id": row["observation_id"], "source_artifact_id": row["artifact_id"],
                    "operation_id": "mcur.affine-first-order.v1",
                    "profile_id": profile["profile_id"], "calibration_artifact_id": profile["artifact_id"],
                    "reference_ids": profile["reference_ids"], "acquired_at": _instant(source["epoch"], i),
                    "raw_value": row["raw_value"], "indicated_value": row["indicated_value"],
                    "input_unit": profile["input_unit"], "output_unit": profile["output_unit"],
                    "corrected_value": [5, 9][i], "variance": [5.5, 8.5][i],
                    "standard_uncertainty": math.sqrt([5.5, 8.5][i])})
            data = {"samples": samples, "temporal_covariance": [[5.5, 3.5], [3.5, 8.5]],
                    "joint_time_value_covariance": [[.25, .25, .125, .125], [.25, .5, .125, .125],
                                                     [.125, .125, 5.5, 3.5], [.125, .125, 3.5, 8.5]]}
            if tamper:
                tamper(data)
            return data
        artifact = {"schema": "ciw.integrity-test-double.v1", "execution_ref": request["execution_id"],
                    "components": [{"name": "scalar", "value": 7, "unit": source["calibration_profile"]["output_unit"]}],
                    "covariance": {"matrix": [[5.25]], "frame": source["frame"]},
                    "calibration_refs": [source["calibration_profile"]["artifact_id"]]}
        if role == "gsie":
            artifact.update(diagnostics={}, observation_binding={"elapsed_seconds": 2})
        native_seal(artifact)
        return {"operation_id": "stfe.window-mean.v1" if role == "stfe" else "ciw.gsie-predict-update.v1",
                "result_artifact": artifact, "numerical_result": {"mean": 7, "variance": 5.25}}
    with monkeypatch.context() as patch:
        patch.setattr(window, "_invoke", invoke)
        bundle = window._execute(canonical(source), {role: IntegrityRuntime(role) for role in window.ROLES})
    assert window._validate(bundle) == canonical(source)
    return bundle


def template_for(bundle):
    request = example_request()
    source = window._source(window._validate(bundle))
    request["frame"] = source["frame"]["id"]
    request["clock"] = {"id": source["receipt_clock"]["clock_id"], "start_s": 0, "end_s": 10, "max_skew_s": .1}
    for sensor in request["sensors"]:
        sensor.update(frame=request["frame"], clock_id=request["clock"]["id"])
    return request


def binding_for(bundle, *, modality="vision_3d"):
    source = window._source(window._validate(bundle))
    profile = source["calibration_profile"]
    return {"sensor_id": profile["sensor_id"], "bundle_ref": digest(bundle),
            "quantity": profile["quantity_id"], "modality": modality, "max_age_s": 10}


def envelope_for(monkeypatch):
    bundle = integrity_bundle(monkeypatch)
    return ingress.make_envelope(template_for(bundle), [bundle], [binding_for(bundle)])


def reseal(envelope):
    envelope["receipt_ref"] = digest({k: v for k, v in envelope.items() if k != "receipt_ref"})


def test_native_file_roundtrip_preserves_large_retained_strings_and_is_create_only(tmp_path, monkeypatch):
    # Native retained graphs allow strings beyond generic control-document text
    # limits. Use an explicit integrity double, not a new provider execution.
    original_identity = IntegrityRuntime.runtime_identity
    def long_identity(self):
        return dict(original_identity(self), python_version="integrity-double:" + "x" * 70000)
    monkeypatch.setattr(IntegrityRuntime, "runtime_identity", long_identity)
    envelope = envelope_for(monkeypatch)
    path = tmp_path / "ingress.json"
    ingress.save_file(path, envelope)
    assert ingress.load_file(path) == envelope
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        ingress.save_file(path, envelope)
    assert path.read_bytes() == before
    from ciw import polymer_workflow, polymer_operator
    directory = tmp_path / "cycle"
    assert polymer_workflow.run(ingress.derive(envelope), directory, ingress=envelope)["status"] == "PASS"
    polymer_operator.export(directory, tmp_path / "export")
    assert ingress.load_file(tmp_path / "export/ingress.json") == envelope


@pytest.mark.parametrize("raw", ['{"schema":"x","schema":"y"}', '{"value":NaN}', '{"value":1e999}'])
def test_ingress_file_reader_rejects_duplicate_and_nonfinite_json(tmp_path, raw):
    path = tmp_path / "invalid.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        ingress.load_file(path)


def test_exact_all_sample_projection_retains_full_native_lineage(monkeypatch):
    envelope = envelope_for(monkeypatch)
    request = ingress.derive(envelope)
    native = envelope["upstreams"][0]["bundle"]
    sensor, = request["sensors"]
    assert sensor["samples"] == [{"time_s": 0, "value": 5, "standard_uncertainty": math.sqrt(5.5)},
                                 {"time_s": 1, "value": 9, "standard_uncertainty": math.sqrt(8.5)}]
    assert sensor["source_ref"] == native["steps"][1]["result_id"]
    assert envelope["upstreams"][0]["bundle"] == native
    assert native["steps"][1]["result"]["data"]["joint_time_value_covariance"][0][2] == .125
    assert envelope["mapping_receipt"]["policy"] == ingress.POLICY
    assert envelope["mapping_receipt"]["policy"]["timing_certificate"] == "not_established"
    assert request["clock"]["max_skew_s"] == envelope["template"]["clock"]["max_skew_s"] == .1
    request["sensors"][0]["samples"][0]["value"] = 999
    assert ingress.derive(envelope)["sensors"][0]["samples"][0]["value"] == 5


def test_import_does_not_execute_or_replay_scientific_providers(monkeypatch):
    envelope = envelope_for(monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline import reached a scientific provider")
    for module in (window, acquired_window):
        monkeypatch.setattr(module, "_adapters", forbidden)
        monkeypatch.setattr(module, "create_session", forbidden)
        monkeypatch.setattr(module, "replay_session", forbidden)
    monkeypatch.setattr(window, "_invoke", forbidden)
    assert ingress.validate(envelope) == envelope
    assert ingress.derive(envelope) == envelope["derived_request"]


def test_deterministic_receipts_no_new_occurrences(monkeypatch):
    envelope = envelope_for(monkeypatch)
    bundle = envelope["upstreams"][0]["bundle"]
    assert ingress.make_envelope(envelope["template"], [bundle], envelope["bindings"]) == envelope


@pytest.mark.parametrize("field", ["value", "time_s", "standard_uncertainty"])
def test_resealed_sample_override_or_deletion_refuses(monkeypatch, field):
    envelope = envelope_for(monkeypatch)
    envelope["derived_request"]["sensors"][0]["samples"][0][field] += .01
    reseal(envelope)
    with pytest.raises(ValueError, match="exact native"):
        ingress.validate(envelope)
    envelope = envelope_for(monkeypatch)
    envelope["derived_request"]["sensors"][0]["samples"].pop()
    reseal(envelope)
    with pytest.raises(ValueError):
        ingress.validate(envelope)


@pytest.mark.parametrize("field", list(AUTHORITY))
def test_resealed_authority_promotion_refuses(monkeypatch, field):
    envelope = envelope_for(monkeypatch)
    envelope["authority"][field] = "performed"
    reseal(envelope)
    with pytest.raises(ValueError, match="authority"):
        ingress.validate(envelope)


@pytest.mark.parametrize("attack", ["quantity", "unit", "sensor_alias", "frame", "clock", "source_ref", "binding_override", "receipt_policy"])
def test_mapping_semantic_and_lineage_attacks_refuse(monkeypatch, attack):
    envelope = envelope_for(monkeypatch)
    if attack == "quantity": envelope["bindings"][0]["quantity"] = "wall_thickness"
    elif attack == "unit": envelope["derived_request"]["sensors"][0]["unit"] = "mm"
    elif attack == "sensor_alias": envelope["bindings"][0]["sensor_id"] = "renamed-sensor"
    elif attack == "frame": envelope["template"]["frame"] = "different-frame"
    elif attack == "clock": envelope["template"]["clock"]["id"] = "different-clock"
    elif attack == "source_ref": envelope["derived_request"]["sensors"][0]["source_ref"] = digest({"invented": 1})
    elif attack == "binding_override": envelope["bindings"][0]["standard_uncertainty"] = 0
    else: envelope["mapping_receipt"]["policy"]["timing_certificate"] = "established"
    reseal(envelope)
    with pytest.raises(ValueError): ingress.validate(envelope)


def test_statistical_time_uncertainty_never_becomes_clock_skew_or_cooling_independence(monkeypatch):
    envelope = envelope_for(monkeypatch)
    request = ingress.derive(envelope)
    assert request["clock"]["max_skew_s"] == .1
    assert request["model"]["cooling"]["temperature_sensor_id"] not in {s["sensor_id"] for s in request["sensors"]}
    assert request["model"]["cooling"]["ambient_sensor_id"] not in {s["sensor_id"] for s in request["sensors"]}
    assert engineering_estimate(request)["cooling"]["status"] == "ABSTAINED"
    assert envelope["template"]["model"]["cooling"]["temperature_sensor_id"] == "part-temperature"


def test_pressure_with_uncertain_time_abstains_nominal_arrival(monkeypatch):
    bundle = integrity_bundle(monkeypatch, "cavity_pressure", "cavity-1")
    envelope = ingress.make_envelope(template_for(bundle), [bundle], [binding_for(bundle, modality="pressure")])
    request = ingress.derive(envelope)
    arrival, = engineering_estimate(request)["cavity_arrival"]
    assert arrival["status"] == "ABSTAINED"
    assert envelope["mapping_receipt"]["withheld_model_bindings"]["pressure_sensor_ids"] == ["cavity-1"]
    assert request["model"]["cavity_arrival"]["pressure_sensor_ids"][0] != "cavity-1"


def test_different_epoch_and_duplicate_upstreams_refuse(monkeypatch):
    one = integrity_bundle(monkeypatch)
    two = integrity_bundle(monkeypatch, "wall_thickness", "sensor:wall", "2026-09-21T00:00:00Z")
    with pytest.raises(ValueError, match="epoch"):
        ingress.make_envelope(template_for(one), [one, two], [binding_for(one), binding_for(two)])
    with pytest.raises(ValueError, match="repeats"):
        ingress.make_envelope(template_for(one), [one, one], [binding_for(one), binding_for(one)])


def test_unsupported_quantity_is_not_silently_renamed(monkeypatch):
    bundle = integrity_bundle(monkeypatch, "level")
    binding = binding_for(bundle)
    binding["quantity"] = "part_dimension"
    with pytest.raises(ValueError, match="quantity semantics"):
        ingress.make_envelope(template_for(bundle), [bundle], [binding])


def test_full_bundle_ref_binds_retained_verification_and_source_bytes(monkeypatch):
    envelope = envelope_for(monkeypatch)
    native = envelope["upstreams"][0]["bundle"]
    native["source"]["evidence"][0]["bytes_b64"] = base64.b64encode(b"{}").decode()
    reseal(envelope)
    with pytest.raises(ValueError, match="full-bundle"):
        ingress.validate(envelope)


@pytest.mark.parametrize("field,replacement", [("standard_uncertainty", 0), ("source_artifact_id", "invented"),
                                              ("profile_id", "invented"), ("acquired_at", "2026-09-21T00:00:00Z")])
def test_native_marginal_and_identity_checked_even_with_all_native_hashes_resealed(monkeypatch, field, replacement):
    # _execute regenerates every downstream request/result/numerical hash after
    # the integrity double supplies an altered output; native _validate passes.
    bad = integrity_bundle(monkeypatch, tamper=lambda data: data["samples"][0].update({field: replacement}))
    with pytest.raises(ValueError):
        ingress.make_envelope(template_for(bad), [bad], [binding_for(bad)])


def test_native_joint_marginal_mismatch_with_resealed_graph_refuses(monkeypatch):
    def tamper(data):
        data["joint_time_value_covariance"][0][0] = .5
    bad = integrity_bundle(monkeypatch, tamper=tamper)
    with pytest.raises(ValueError, match="covariance blocks"):
        ingress.make_envelope(template_for(bad), [bad], [binding_for(bad)])


def test_native_rounded_covariance_is_retained_without_exact_psd_repair():
    # A valid native rank-one propagation can round just outside exact PSD. The
    # importer does not use this joint covariance to infer precision or cooling.
    matrix = window._project([[.3], [.7]], [[1]])
    with pytest.raises(ValueError, match="positive semidefinite"):
        window._covariance(matrix, 2)
    assert ingress._matrix(matrix, 2) is matrix
    for bad in ([[1, 2], [3, 1]], [[-1, 0], [0, 1]], [[1], [0]]):
        with pytest.raises(ValueError): ingress._matrix(bad, 2)


def test_acquired_route_requires_native_validator_and_retains_the_whole_graph(monkeypatch):
    child = integrity_bundle(monkeypatch)
    acquisition = {"schema": "explicit-integrity-routing-double", "evidence": {"snapshot_bytes": "retained"}}
    outer = {"schema": acquired_window.SCHEMA, "bundle_digest": digest({"routing": 1}),
             "child_window": child, "upstream_acquisition": acquisition}
    calls = []
    def checked(value):
        calls.append(value)
        if value["upstream_acquisition"] != acquisition:
            raise ValueError("routing-double acquisition binding differs")
    # This test covers routing only. Native _validate itself is exercised by the
    # acquired-window suite; the actual gate below accepts either bundle family.
    monkeypatch.setattr(acquired_window, "_validate", checked)
    binding = binding_for(child)
    binding["bundle_ref"] = digest(outer)
    envelope = ingress.make_envelope(template_for(child), [outer], [binding])
    assert calls and calls[0] == outer
    assert envelope["upstreams"][0]["bundle"]["upstream_acquisition"] == acquisition
    assert ingress.derive(envelope)["sensors"][0]["samples"][1]["value"] == 9


def test_origin_declaration_preserved_without_authentication_claim(monkeypatch):
    bundle = integrity_bundle(monkeypatch)
    template = template_for(bundle)
    template["source_kind"] = "retained_observation"
    for sensor in template["sensors"]:
        sensor["origin"] = "observed"
    envelope = ingress.make_envelope(template, [bundle], [binding_for(bundle)])
    assert ingress.derive(envelope)["sensors"][0]["origin"] == "observed"
    assert envelope["mapping_receipt"]["policy"]["origin"] == "caller_declared_not_authenticated_by_native_bundle"
    assert envelope["authority"] == AUTHORITY


def test_actual_pinned_native_fixture():
    filename = os.environ.get("CIW_POLYMER_NATIVE_BUNDLE", str(ROOT / "examples/polymer/native-dimension.bundle.json"))
    bundle = json.loads(Path(filename).read_bytes())
    envelope = ingress.make_envelope(template_for(bundle), [bundle], [binding_for(bundle)])
    assert ingress.validate(envelope) == envelope
    assert ingress.derive(envelope)["sensors"][0]["samples"] == [
        {"time_s": time["event_time"], "value": value["corrected_value"],
         "standard_uncertainty": value["standard_uncertainty"]}
        for time, value in zip(bundle["steps"][0]["result"]["data"]["samples"],
                               bundle["steps"][1]["result"]["data"]["samples"])]
