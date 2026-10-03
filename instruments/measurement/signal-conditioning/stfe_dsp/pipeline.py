# SPDX-License-Identifier: MPL-2.0
"""Bounded, declared DSP composition; identities of NET executions live above it.

``quality`` explicitly inspects a signal and passes the unchanged signal to
subsequent stages. ``clock_shift`` changes a declared clock coordinate using a
caller supplied additive offset. It never estimates or certifies a clock map.
No numerical provider is imported while validating a request.
"""
from __future__ import annotations

import json
import math
from typing import Any

from stfe.window import ContractError, canonical, digest

REQUEST_SCHEMA = "stfe.dsp-pipeline.v1"
RESULT_SCHEMA = "stfe.dsp-pipeline-result.v1"
MAX_SIGNALS = 8
MAX_STEPS = 32
MAX_SIGNAL_SAMPLES = 32768
MAX_TOTAL_INPUT_SAMPLES = 65536
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_RESULT_BYTES = 10 * 1024 * 1024
MAX_PROJECTED_ITEMS = 500000
METHODS = frozenset({"quality", "clock_shift", "filter", "resample", "welch",
                     "spectrogram", "features", "coherence", "delay", "detrend",
                     "fractional_delay", "fft"})
SIGNAL_METHODS = frozenset({"quality", "clock_shift", "filter", "resample", "detrend",
                            "fractional_delay"})
SIGNAL_FIELDS = frozenset({"source_id", "unit", "clock_id", "sample_rate_hz", "time_s", "values"})
AUTHORITY = {"state_admission": "not_performed", "physical_leak_confirmation": False,
             "actuation_authorized": False, "independent_verification": "not_performed",
             "scope": "declared numerical signal processing; source authenticity and physical validity are not established"}


def _number(value: Any, label: str) -> float:
    if type(value) not in (int, float):
        raise ContractError(f"{label} must be a finite JSON number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ContractError(f"{label} exceeds binary64") from exc
    if not math.isfinite(result):
        raise ContractError(f"{label} must be finite")
    if type(value) is int and int(result) != value:
        raise ContractError(f"{label} is not exactly representable as binary64")
    return result


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ContractError(f"{label} must be a nonempty string of at most 1024 characters")
    return value


def _json_value(value: Any, depth: int = 0) -> None:
    if depth > 24:
        raise ContractError("request JSON exceeds the nesting bound")
    if value is None or type(value) in (bool, str):
        return
    if type(value) in (float, int):
        _number(value, "JSON number")
        return
    if isinstance(value, list):
        for item in value:
            _json_value(item, depth + 1)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _json_value(item, depth + 1)
        return
    raise ContractError("request must contain only finite JSON-native values")


def _integer(value: Any, label: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ContractError(f"{label} must be an integer in [{lower}, {upper}]")
    return value


def validate_request(request: dict) -> dict:
    """Validate structural bounds and detach the request without importing DSP.

    Missing values are allowed solely so an explicit quality-only pipeline can
    diagnose them; numerical operations enforce their own refusal policy.
    This validation does not claim algorithm parameters are executable.
    """
    if not isinstance(request, dict):
        raise ContractError("pipeline request must be an object")
    required = {"schema", "signals", "steps", "provenance"}
    if required - request.keys() or request.keys() - required - {"ground_truth"}:
        raise ContractError("pipeline fields differ from stfe.dsp-pipeline.v1")
    if request["schema"] != REQUEST_SCHEMA:
        raise ContractError("unsupported DSP pipeline schema")
    _json_value(request)
    try:
        encoded = canonical(request)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ContractError("pipeline request must be finite JSON") from exc
    if len(encoded.encode("utf-8")) > MAX_REQUEST_BYTES:
        raise ContractError("pipeline request exceeds the 4 MiB bound")
    if not isinstance(request["provenance"], dict):
        raise ContractError("provenance must be an object")
    if "ground_truth" in request and not isinstance(request["ground_truth"], dict):
        raise ContractError("ground_truth must be an object")
    signals = request["signals"]
    if not isinstance(signals, dict) or not 1 <= len(signals) <= MAX_SIGNALS:
        raise ContractError(f"signals must contain 1 to {MAX_SIGNALS} named signals")
    lengths: dict[str, int] = {}
    for name, signal in signals.items():
        _text(name, "signal key")
        if not isinstance(signal, dict) or set(signal) != SIGNAL_FIELDS:
            raise ContractError(f"signal {name} fields differ from the declared contract")
        for key in ("source_id", "unit", "clock_id"):
            _text(signal[key], f"{name}.{key}")
        if _number(signal["sample_rate_hz"], f"{name}.sample_rate_hz") <= 0:
            raise ContractError("sample_rate_hz must be positive")
        times, values = signal["time_s"], signal["values"]
        if not isinstance(times, list) or not isinstance(values, list):
            raise ContractError("signal time_s and values must be arrays")
        if len(times) != len(values) or not 1 <= len(times) <= MAX_SIGNAL_SAMPLES:
            raise ContractError(f"signal arrays must have equal lengths in [1,{MAX_SIGNAL_SAMPLES}]")
        for value in times:
            _number(value, "signal time")
        for value in values:
            if value is not None:
                _number(value, "signal value")
        lengths[name] = len(times)
    if sum(lengths.values()) > MAX_TOTAL_INPUT_SAMPLES:
        raise ContractError("pipeline exceeds the total input sample bound")
    steps = request["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ContractError(f"steps must contain 1 to {MAX_STEPS} declarations")
    known = set(signals)
    checked: set[str] = set()
    projected_items = 0
    for step in steps:
        if not isinstance(step, dict) or {"id", "input", "method", "parameters"} - step.keys() or step.keys() - {"id", "input", "method", "parameters", "reference"}:
            raise ContractError("step fields differ from the pipeline contract")
        name = _text(step["id"], "step id")
        source = _text(step["input"], "step input")
        if name in known:
            raise ContractError("step ids must be unique and distinct from signal keys")
        if source not in lengths:
            raise ContractError("step input must identify a signal or earlier signal-producing stage")
        method = step["method"]
        if not isinstance(method, str) or method not in METHODS:
            raise ContractError("unsupported DSP pipeline method")
        params = step["parameters"]
        if not isinstance(params, dict):
            raise ContractError("step parameters must be an object")
        reference = step.get("reference")
        if method in {"coherence", "delay"}:
            if not isinstance(reference, str) or reference not in lengths:
                raise ContractError("relationship methods require an earlier signal reference")
            if reference not in checked:
                raise ContractError("reference signal requires an earlier quality stage")
        elif reference is not None:
            raise ContractError("reference is only supported by coherence and delay")
        if method != "quality" and source not in checked:
            raise ContractError("signal requires an explicit quality stage before processing")
        count = lengths[source]
        output_count = count
        if method == "clock_shift":
            if set(params) != {"offset_s", "target_clock_id", "mapping_ref"}:
                raise ContractError("clock_shift needs offset_s, target_clock_id and mapping_ref")
            _number(params["offset_s"], "clock_shift.offset_s")
            _text(params["target_clock_id"], "clock_shift.target_clock_id")
            _text(params["mapping_ref"], "clock_shift.mapping_ref")
        if method == "resample":
            up = _integer(params.get("up"), "resample.up", 1, 128)
            down = _integer(params.get("down"), "resample.down", 1, 128)
            output_count = (count * up + down - 1) // down
            if output_count > MAX_SIGNAL_SAMPLES:
                raise ContractError("resampling exceeds the per-signal output sample bound")
        if method == "spectrogram":
            nperseg = _integer(params.get("nperseg", min(256, count)), "nperseg", 2, MAX_SIGNAL_SAMPLES)
            noverlap = _integer(params.get("noverlap", nperseg // 2), "noverlap", 0, nperseg - 1)
            nfft = _integer(params.get("nfft", nperseg), "nfft", nperseg, 32768)
            frames = max(0, 1 + (count - nperseg) // (nperseg - noverlap))
            projected_items += (nfft // 2 + 1) * frames
        elif method == "features":
            window = _integer(params.get("window_samples", min(256, count)), "window_samples", 2, MAX_SIGNAL_SAMPLES)
            hop = _integer(params.get("hop_samples", max(1, window // 2)), "hop_samples", 1, MAX_SIGNAL_SAMPLES)
            projected_items += 24 * max(0, 1 + (count - window) // hop)
        else:
            projected_items += output_count * 3
        if projected_items > MAX_PROJECTED_ITEMS:
            raise ContractError("pipeline exceeds the retained numerical output budget")
        if method == "quality":
            checked.add(source)
        if method in SIGNAL_METHODS:
            lengths[name] = output_count
            checked.add(name)
        known.add(name)
    return json.loads(encoded)


def _clock_shift(signal: dict, parameters: dict) -> dict:
    offset = parameters["offset_s"]
    corrected = [_number(time + offset, "corrected time") for time in signal["time_s"]]
    input_ref = digest(signal)
    derived = {**signal, "time_s": corrected, "clock_id": parameters["target_clock_id"]}
    derived["source_id"] = "stfe-derived:" + digest({"input_ref": input_ref, "method": "clock_shift", "parameters": parameters}).split(":", 1)[1]
    return {
        "schema": "stfe.dsp-result.v1", "method": "clock_shift", "input_ref": input_ref,
        "parameters": dict(parameters),
        "contract": {
            "mode": "offline_clock_coordinate_change", "missing_policy": "preserve",
            "precision": "binary64", "uncertainty_propagation": "not_performed",
            "timing_offset_s": offset, "latency_samples": 0,
            "valid_sample_range": [0, len(corrected)],
            "source_support": {"clock_id": signal["clock_id"], "time_s": list(signal["time_s"])},
            "clock_mapping_ref": parameters["mapping_ref"],
            "clock_mapping_status": "caller_declared_not_independently_calibrated",
            "equation": "output.time_s = input.time_s + offset_s",
            "signal_delay_applied": False,
        }, "output": derived,
    }


def _lineage_support(step: dict, result: dict, signal: dict,
                     input_range: list[int] | None,
                     reference_range: list[int] | None = None) -> list[int] | None:
    """Retain local and inherited edge support without silently slicing data."""
    contract = result["contract"]
    method = step["method"]
    local = contract.get("valid_sample_range")
    count = len(signal["values"])
    effective = None
    if local is not None and input_range is not None:
        if method in {"filter", "fractional_delay"}:
            start = input_range[0] + local[0]
            stop = input_range[1] - (count - local[1])
            effective = [min(count, start), max(min(count, start), stop)]
        elif method == "resample":
            up, down = result["parameters"]["up"], result["parameters"]["down"]
            output_count = len(result["output"]["values"])
            start = math.ceil(input_range[0] * up / down) + local[0]
            stop = math.floor(input_range[1] * up / down) - (output_count - local[1])
            effective = [min(output_count, start), max(min(output_count, start), stop)]
        elif method == "detrend" and input_range != [0, count]:
            # The whole-record fit couples every output to excluded inputs.
            effective = None
        else:
            start, stop = max(local[0], input_range[0]), min(local[1], input_range[1])
            effective = [start, max(start, stop)]
    if step.get("reference") is not None:
        if reference_range is None or effective is None:
            effective = None
        else:
            start, stop = max(effective[0], reference_range[0]), min(effective[1], reference_range[1])
            effective = [start, max(start, stop)]
        contract["pipeline_reference_valid_sample_range"] = reference_range
    contract["pipeline_input_valid_sample_range"] = input_range
    contract["pipeline_effective_valid_sample_range"] = effective
    out_count = len(result["output"]["values"]) if method in SIGNAL_METHODS - {"quality"} else count
    contract["includes_boundary_affected_samples"] = None if effective is None else effective != [0, out_count]
    contract["pipeline_edge_validity_scope"] = "conservative finite-support boundary dependence only; unknown IIR settling stays unknown; no automatic cropping or physical-validity claim"
    if method == "features":
        for group in ("windows", "events"):
            for item in result["output"][group]:
                item["pipeline_edge_support_valid"] = None if effective is None else (
                    effective[0] <= item["start_sample"] and item["stop_sample"] <= effective[1])
    return effective


def _event_comparison(request: dict, stages: list[dict], signals: dict[str, dict]) -> dict | None:
    truth = request.get("ground_truth", {})
    if not truth:
        return None
    raw_truth = truth.get("events", [])
    valid_truth = []
    for event in raw_truth if isinstance(raw_truth, list) else []:
        if not isinstance(event, dict):
            continue
        start, stop = event.get("start_s"), event.get("stop_s")
        if type(start) in (int, float) and type(stop) in (int, float) and stop > start:
            valid_truth.append(event)
    candidates = []
    for stage in stages:
        if stage["method"] != "features":
            continue
        output = stage["result"].get("output", {})
        for event in output.get("events", []):
            candidates.append({"stage_id": stage["id"], "event": event,
                               "clock_id": signals[stage["input"]]["clock_id"]})
    # A comparison is computed only from explicit time support. Detector
    # thresholds and inputs are already consumed and cannot use ground truth.
    comparisons = []
    for event in valid_truth:
        overlaps = []
        not_comparable = []
        for index, candidate in enumerate(candidates):
            if candidate["event"].get("pipeline_edge_support_valid") is not True:
                not_comparable.append({"stage_id": candidate["stage_id"], "candidate_index": index,
                                       "reason": "boundary_support_invalid_or_unknown"})
                continue
            if not isinstance(event.get("clock_id"), str) or candidate["clock_id"] != event["clock_id"]:
                not_comparable.append({"stage_id": candidate["stage_id"],
                                       "candidate_index": index,
                                       "reason": "clock_id_mismatch" if isinstance(event.get("clock_id"), str) else "ground_truth_clock_unknown"})
                continue
            found = candidate["event"]
            start = found.get("time_start_s") if isinstance(found, dict) else None
            stop = found.get("time_stop_s") if isinstance(found, dict) else None
            if type(start) in (int, float) and type(stop) in (int, float):
                amount = max(0.0, min(event["stop_s"], stop) - max(event["start_s"], start))
                if amount > 0:
                    overlaps.append({"stage_id": candidate["stage_id"], "candidate_index": index,
                                     "overlap_s": amount})
        comparisons.append({"truth_id": event.get("id"), "overlapping_candidates": overlaps,
                            "overlapping_candidate_count": len(overlaps),
                            "nonoverlapping_candidate_count": len(candidates) - len(overlaps) - len(not_comparable),
                            "not_comparable": not_comparable})
    return {
        "scope": "synthetic event overlap only; no physical leak confirmation or independent verification",
        "ground_truth_used_for_detection": False,
        "ground_truth_ref": digest(truth), "declared_event_count": len(valid_truth),
        "candidate_count": len(candidates), "comparisons": comparisons,
        "candidate_definition": "contiguous amplitude-threshold excursions; one injected disturbance can produce many candidates",
    }


def run_pipeline(request: dict) -> dict:
    """Execute a validated, explicitly ordered, bounded numerical pipeline."""
    request = validate_request(request)
    from .dsp import process  # scipy and numpy are optional until execution.

    signals = dict(request["signals"])
    valid_ranges = {key: [0, len(value["values"])] for key, value in signals.items()}
    stages = []
    for step in request["steps"]:
        signal = signals[step["input"]]
        reference = signals[step["reference"]] if step.get("reference") else None
        method = step["method"]
        if method == "clock_shift":
            result = _clock_shift(signal, step["parameters"])
        else:
            result = process(signal, method, step["parameters"], reference=reference)
        effective_range = _lineage_support(step, result, signal, valid_ranges[step["input"]],
                                          valid_ranges[step["reference"]] if step.get("reference") else None)
        if method == "quality":
            signals[step["id"]] = signal
        elif method in SIGNAL_METHODS:
            signals[step["id"]] = result["output"]
        if method in SIGNAL_METHODS:
            valid_ranges[step["id"]] = effective_range
        stages.append({"id": step["id"], "input": step["input"],
                       "reference": step.get("reference"), "method": method,
                       "parameters": step["parameters"], "result": result})
    response = {
        "schema": RESULT_SCHEMA, "request_ref": digest(request), "stages": stages,
        "authority": dict(AUTHORITY),
    }
    comparison = _event_comparison(request, stages, signals)
    if comparison is not None:
        response["diagnostics"] = {"synthetic_event_comparison": comparison}
    try:
        encoded = canonical(response)
    except (ValueError, OverflowError) as exc:
        raise ContractError("pipeline result is not finite JSON") from exc
    if len(encoded.encode("utf-8")) > MAX_RESULT_BYTES:
        raise ContractError("pipeline result exceeds the 10 MiB retained-output bound")
    return json.loads(encoded)
