"""Data-only binding checks do not substitute for DSP numerical qualification."""
from copy import deepcopy
import builtins
from unittest.mock import patch

import pytest

from ciw.dsp_pipeline_contract import dsp_digest, validate_result

pipeline = pytest.importorskip("stfe_dsp.pipeline")


def fixture(method="filter", parameters=None):
    source = {"source_id": "sensor:pression-é", "unit": "Pa", "clock_id": "horloge-é",
              "sample_rate_hz": 64.0, "time_s": [i / 64 for i in range(256)],
              "values": [float((i % 19) - 9) for i in range(256)]}
    request = {"schema": "stfe.dsp-pipeline.v1", "provenance": {"description": "synthétique"},
               "signals": {"p": source}, "steps": [
                   {"id": "quality", "input": "p", "method": "quality", "parameters": {}},
                   {"id": "output", "input": "quality", "method": method,
                    "parameters": parameters if parameters is not None else {"family": "fir", "taps": [1, 0]}}]}
    if method in {"delay", "coherence"}:
        request["steps"][-1]["reference"] = "quality"
    return request, pipeline.run_pipeline(request)


@pytest.mark.parametrize("method,parameters", [
    ("quality", {}), ("detrend", {}),
    ("clock_shift", {"offset_s": 1, "target_clock_id": "shifted", "mapping_ref": "declared:1"}),
    ("filter", {"family": "fir", "taps": [1, 0]}),
    ("filter", {"family": "butter", "cutoff_hz": 8, "order": 2}),
    ("filter", {"family": "fir", "taps": [.25, .5, .25], "mode": "offline_zero_phase"}),
    ("filter", {"family": "notch", "cutoff_hz": 8, "q": 20}),
    ("filter", {"family": "fir", "taps": [1, 0], "state": None}),
    ("resample", {"up": 2, "down": 2}), ("resample", {"up": 2, "down": 3}),
    ("fractional_delay", {"delay_samples": 0}), ("fft", {}),
    ("welch", {}), ("spectrogram", {}),
    ("coherence", {"nperseg": 64}), ("delay", {"max_lag_samples": 8}),
    ("features", {"threshold": 1, "band_hz": [0, 20]}),
])
def test_all_result_shapes_and_numeric_normalization(method, parameters):
    request, result = fixture(method, parameters)
    validate_result(request, result)
    assert result["request_ref"] == dsp_digest(request)


@pytest.mark.parametrize("fault", ["authority", "empty_contract", "support_ref", "derived_ref",
                                   "output_shape", "mode", "precision", "validity", "unit", "clock",
                                   "chunks", "state", "boolean_parameter", "missing_lineage", "boolean_lineage"])
def test_resealed_structural_and_source_mutations_refuse(fault):
    request, result = fixture()
    stage = result["stages"][-1]["result"]
    if fault == "authority":
        result["authority"]["physical_leak_confirmation"] = True
    elif fault == "empty_contract":
        stage["contract"] = {}
    elif fault == "support_ref":
        stage["contract"]["source_support"]["input_ref"] = "sha256:" + "0" * 64
    elif fault == "derived_ref":
        stage["output"]["source_id"] = "sha256:" + "0" * 64
    elif fault == "output_shape":
        result["stages"][0]["result"]["output"] = {"anything": "goes"}
    elif fault in {"mode", "precision"}:
        stage["contract"][fault] = "arbitrary"
    elif fault == "validity":
        stage["contract"]["valid_sample_range"] = [0, 1000000]
    elif fault in {"unit", "clock"}:
        stage["output"]["unit" if fault == "unit" else "clock_id"] = "changed"
    elif fault == "chunks":
        stage["contract"]["chunk_boundaries"] = [0, 42]
    elif fault == "state":
        stage["contract"]["final_state"] = []
    elif fault == "missing_lineage":
        stage["contract"].pop("pipeline_input_valid_sample_range")
    elif fault == "boolean_lineage":
        stage["contract"]["pipeline_effective_valid_sample_range"] = [False, 256]
    else:
        stage["parameters"]["taps"][0] = True
    with pytest.raises(ValueError):
        validate_result(request, result)


def test_relationship_reference_and_spectral_shape_are_bound():
    request, result = fixture("coherence", {"nperseg": 64})
    changed = deepcopy(result)
    changed["stages"][-1]["result"]["contract"]["source_support"]["reference_input_ref"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        validate_result(request, changed)
    changed = deepcopy(result)
    changed["stages"][-1]["result"]["output"]["coherence"].pop()
    with pytest.raises(ValueError):
        validate_result(request, changed)


def test_validation_does_not_import_provider_or_scipy():
    request, result = fixture()
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.startswith(("stfe", "scipy", "numpy")):
            raise AssertionError("validator imported numerical provider")
        return original(name, *args, **kwargs)
    with patch.object(builtins, "__import__", guarded):
        validate_result(request, result)
