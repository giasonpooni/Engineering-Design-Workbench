"""Provider-free DSP result contracts and source bindings, not numerical proof."""
from __future__ import annotations

from hashlib import sha256
import json
import math


AUTHORITY = {
    "state_admission": "not_performed", "physical_leak_confirmation": False,
    "actuation_authorized": False, "independent_verification": "not_performed",
    "scope": "declared numerical signal processing; source authenticity and physical validity are not established",
}
SIGNAL_FIELDS = {"source_id", "unit", "clock_id", "sample_rate_hz", "time_s", "values"}
SIGNAL_METHODS = {"clock_shift", "detrend", "filter", "resample", "fractional_delay"}
METHODS = SIGNAL_METHODS | {"quality", "fft", "welch", "spectrogram", "features", "coherence", "delay"}
UNCERTAINTY = "not_propagated; filtering/resampling changes variance and temporal correlation; downstream noise models require requalification"


def dsp_digest(value):
    """STFE's UTF-8 JSON canonicalization; distinct from historical CIW hashes."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "sha256:" + sha256(raw.encode("utf-8")).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError("DSP " + message)


def _keys(value, required, optional=frozenset()):
    _require(type(value) is dict and required <= value.keys() <= required | optional,
             "contract fields differ")


def _number(value, nullable=False):
    _require((nullable and value is None) or
             (type(value) in (int, float) and math.isfinite(value)), "requires finite numeric data")


def _integer(value, lower, upper):
    _require(type(value) is int and lower <= value <= upper, "index/count exceeds its declared support")


def _array(value, count=None, nullable=False):
    _require(type(value) is list and (count is None or len(value) == count), "array shape mismatch")
    for item in value:
        _number(item, nullable)


def _same(left, right):
    """Exact semantic JSON equality; numeric int/float equivalence excludes bool."""
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    if type(left) is list:
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left == right


def _range(value, count):
    _require(type(value) is list and len(value) == 2, "sample support must be a half-open pair")
    _integer(value[0], 0, count)
    _integer(value[1], value[0], count)


def _finite(value):
    if type(value) is dict:
        _require(all(type(k) is str for k in value), "keys must be text")
        for child in value.values():
            _finite(child)
    elif type(value) is list:
        for child in value:
            _finite(child)
    elif type(value) in (int, float):
        _number(value)
    else:
        _require(value is None or type(value) in (str, bool), "requires JSON-native data")


def _signal(value):
    _keys(value, SIGNAL_FIELDS)
    for name in ("source_id", "unit", "clock_id"):
        _require(type(value[name]) is str and value[name].strip(), "signal metadata must be nonempty text")
    _number(value["sample_rate_hz"])
    _require(value["sample_rate_hz"] > 0, "sample rate must be positive")
    _require(type(value["values"]) is list and 1 <= len(value["values"]) <= 32768, "signal sample bound")
    _array(value["values"], nullable=True)
    _array(value["time_s"], len(value["values"]))


def _parameters(declared, effective, method, contract):
    _require(type(effective) is dict, "requires effective parameters")
    for name, value in declared.items():
        if method == "resample" and name in {"up", "down"}:
            continue
        if method == "filter" and name == "state" and value is None:
            _require(contract.get("initialization") == "zero_state", "null state must initialize zero state")
            continue
        _require(name in effective and _same(value, effective[name]), "effective parameters contradict declaration")
    if method == "resample":
        for key in ("up", "down"):
            _integer(effective.get(key), 1, 128)
        _require(effective["up"] * declared.get("down", 1) == effective["down"] * declared.get("up", 1),
                 "effective resampling ratio contradicts declaration")


def _contract(contract, method, source, output, parameters, reference):
    required = {"mode", "missing_policy", "precision", "uncertainty_propagation",
                "timing_offset_s", "latency_samples", "valid_sample_range", "source_support"}
    _require(type(contract) is dict and required <= contract.keys(), "requires complete execution contract")
    expected_mode = (parameters.get("mode", "causal") if method == "filter" else
                     "offline_clock_coordinate_change" if method == "clock_shift" else
                     "offline_noncausal" if method in {"resample", "fractional_delay"} else "offline")
    _require(contract["mode"] == expected_mode, "processing mode contradicts operation")
    _require(contract["precision"] == ("binary64" if method == "clock_shift" else "float64"), "precision mismatch")
    _require(contract["uncertainty_propagation"] == ("not_performed" if method == "clock_shift" else UNCERTAINTY),
             "cannot claim uncertainty propagation")
    _require(contract["missing_policy"] == ("preserve" if method == "clock_shift" else
             "report_without_imputation" if method == "quality" else "reject"), "missing-data policy mismatch")
    _number(contract["timing_offset_s"], nullable=True)
    _number(contract["latency_samples"], nullable=True)
    _require(contract["latency_samples"] is None or contract["latency_samples"] >= 0, "negative latency")
    n = len(source["values"])
    if contract["valid_sample_range"] is not None:
        _range(contract["valid_sample_range"], len(output["values"]) if method in SIGNAL_METHODS else n)
    support = contract["source_support"]
    _require(type(support) is dict, "source support must be an object")
    if method == "clock_shift":
        _keys(support, {"clock_id", "time_s"})
        _require(support["clock_id"] == source["clock_id"] and _same(support["time_s"], source["time_s"]),
                 "clock transformation source support mismatch")
        _require(contract.get("clock_mapping_ref") == parameters["mapping_ref"] and
                 contract.get("clock_mapping_status") == "caller_declared_not_independently_calibrated" and
                 contract.get("signal_delay_applied") is False, "clock mapping authority mismatch")
    else:
        _require(support.get("input_ref") == dsp_digest(source), "source support reference mismatch")
        _require(_same(support.get("input_sample_range"), [0, n]), "source support sample range mismatch")
    if method in {"delay", "coherence"}:
        _require(reference is not None and support.get("reference_input_ref") == dsp_digest(reference),
                 "paired reference binding mismatch")
    else:
        _require("reference_input_ref" not in support, "unexpected paired reference")
    if method in {"filter", "fractional_delay", "resample"}:
        coefficients = contract.get("coefficients")
        _require(type(coefficients) is dict, "requires retained filter coefficients")
        if "sos" in coefficients:
            _keys(coefficients, {"sos"})
            _require(type(coefficients["sos"]) is list and coefficients["sos"], "requires SOS coefficients")
            for row in coefficients["sos"]:
                _array(row, 6)
        else:
            _keys(coefficients, {"a", "b"}, {"upsampling_gain"})
            _array(coefficients["a"])
            _array(coefficients["b"])
            _require(coefficients["a"] and coefficients["b"], "empty filter coefficients")
        if method in {"filter", "fractional_delay"}:
            response = contract.get("frequency_response")
            _keys(response, {"frequency_hz", "real", "imag", "magnitude"}, {"applied_magnitude"})
            for values in response.values():
                _array(values, len(response["frequency_hz"]))
    if method == "filter":
        _require({"initialization", "final_state"} <= contract.keys(), "requires filter state contract")
        if expected_mode == "causal":
            _require(contract["initialization"] in {"zero_state", "provided_state; predecessor samples are not independently verified"},
                     "unknown causal initialization")
            for state in (parameters.get("state"), contract["final_state"]):
                if "sos" in coefficients:
                    _require(type(state) is list and len(state) == len(coefficients["sos"]), "SOS state shape mismatch")
                    for row in state:
                        _array(row, 2)
                else:
                    _array(state, max(len(coefficients["a"]), len(coefficients["b"])) - 1)
            chunks = parameters.get("chunks")
            _require(type(chunks) is list and chunks and all(type(k) is int and k > 0 for k in chunks)
                     and sum(chunks) == n, "invalid retained chunk partition")
            bounds = [0]
            for count in chunks:
                bounds.append(bounds[-1] + count)
            _require(_same(contract.get("chunk_boundaries"), bounds), "chunk boundaries mismatch")
        else:
            _require(contract["final_state"] is None and contract["initialization"] ==
                     "odd reflection padding with endpoint steady-state initialization", "offline filter state mismatch")


def _signal_output(output, source, method, parameters):
    _signal(output)
    _require(output["unit"] == source["unit"], "derived signal unit mismatch")
    expected = dsp_digest({"input_ref": dsp_digest(source), "method": method, "parameters": parameters})
    if method == "clock_shift":
        expected = "stfe-derived:" + expected.split(":", 1)[1]
    _require(output["source_id"] == expected, "derived source identity mismatch")
    if method == "clock_shift":
        _require(output["clock_id"] == parameters["target_clock_id"], "target clock mismatch")
        _require(_same(output["values"], source["values"]) and
                 _same(output["time_s"], [t + parameters["offset_s"] for t in source["time_s"]]),
                 "clock transformation must preserve samples and declared time map")
    else:
        _require(output["clock_id"] == source["clock_id"], "derived clock mismatch")
    if method == "resample":
        up, down = parameters["up"], parameters["down"]
        _require(len(output["values"]) == (len(source["values"]) * up + down - 1) // down,
                 "resampling length mismatch")
        _require(output["sample_rate_hz"] == source["sample_rate_hz"] * up / down,
                 "resampling rate mismatch")
    else:
        _require(_same(output["sample_rate_hz"], source["sample_rate_hz"]) and
                 len(output["values"]) == len(source["values"]), "derived signal grid mismatch")
        if method != "clock_shift":
            _require(_same(output["time_s"], source["time_s"]), "derived timestamps changed unexpectedly")


def _analysis_output(output, method, source, parameters):
    n = len(source["values"])
    if method == "quality":
        lists = {"missing_indices", "duplicate_time_indices", "nonmonotone_time_indices", "gap_after_indices",
                 "irregular_interval_indices", "clipped_indices"}
        _keys(output, lists | {"sample_count", "saturation_runs", "observed_sample_rate_hz",
                              "max_timing_error_s", "supports_uniform_analysis"})
        _require(type(output["sample_count"]) is int and output["sample_count"] == n and
                 type(output["supports_uniform_analysis"]) is bool, "quality support mismatch")
        for name in lists:
            _require(type(output[name]) is list, "quality indices must be arrays")
            for index in output[name]:
                _integer(index, 0, n - 1)
        _number(output["observed_sample_rate_hz"], nullable=True)
        _number(output["max_timing_error_s"], nullable=True)
        _require(type(output["saturation_runs"]) is list, "saturation runs must be arrays")
        for row in output["saturation_runs"]:
            _keys(row, {"start_sample", "stop_sample", "value", "at_declared_bound", "classification"})
            _range([row["start_sample"], row["stop_sample"]], n)
            _number(row["value"])
            _require(type(row["at_declared_bound"]) is bool and row["classification"] in
                     {"declared_bound_plateau", "constant_plateau_candidate"}, "invalid plateau classification")
    elif method == "features":
        _keys(output, {"windows", "events"})
        for name in ("windows", "events"):
            _require(type(output[name]) is list, "feature records must be arrays")
            for row in output[name]:
                fields = {"start_sample", "stop_sample", "time_start_s", "time_stop_s", "peak", "pipeline_edge_support_valid"}
                fields |= ({"rms", "crest_factor", "kurtosis", "band_power", "threshold_exceeded"}
                           if name == "windows" else {"classification"})
                _keys(row, fields)
                _range([row["start_sample"], row["stop_sample"]], n)
                for key in fields - {"start_sample", "stop_sample", "classification", "threshold_exceeded", "pipeline_edge_support_valid"}:
                    _number(row[key], nullable=key in {"crest_factor", "kurtosis", "band_power"})
                _require(row["pipeline_edge_support_valid"] is None or type(row["pipeline_edge_support_valid"]) is bool,
                         "edge support flag must be boolean or unknown")
                if name == "events":
                    _require(row["classification"] == "absolute_amplitude_threshold_candidate", "event overclaims identification")
                else:
                    _require(row["threshold_exceeded"] is None or type(row["threshold_exceeded"]) is bool,
                             "threshold result must be boolean or absent")
    elif method == "delay":
        _keys(output, {"delay_samples", "delay_s", "peak_correlation", "lags_samples", "correlation",
                       "at_search_boundary", "sign_convention", "resolution_samples"})
        limit = parameters["max_lag_samples"]
        _integer(output["delay_samples"], -limit, limit)
        _require(output["lags_samples"] == list(range(-limit, limit + 1)), "lag support mismatch")
        _array(output["correlation"], 2 * limit + 1)
        _number(output["delay_s"])
        _number(output["peak_correlation"])
        _require(type(output["at_search_boundary"]) is bool and type(output["resolution_samples"]) is int
                 and output["resolution_samples"] == 1, "invalid delay resolution")
    else:
        fields = {"frequency_hz"}
        if method == "fft":
            fields |= {"real", "imag", "amplitude", "power_spectral_density"}
        elif method == "coherence":
            fields |= {"coherence", "cross_spectrum_real", "cross_spectrum_imag", "transfer_real",
                       "transfer_imag", "transfer_direction", "segment_count"}
        else:
            fields |= {"power_spectral_density", "segment_count"}
            if method == "spectrogram":
                fields |= {"time_s", "axis_order"}
        _keys(output, fields)
        count = parameters["nfft"] // 2 + 1
        _array(output["frequency_hz"], count)
        if method != "fft":
            frames = 1 + (n - parameters["nperseg"]) // (parameters["nperseg"] - parameters["noverlap"])
            _require(type(output["segment_count"]) is int and output["segment_count"] == frames,
                     "spectral segment count mismatch")
        if method == "spectrogram":
            _require(output["axis_order"] == ["frequency", "time"], "spectrogram axis mismatch")
            _array(output["time_s"], frames)
            _require(type(output["power_spectral_density"]) is list and
                     len(output["power_spectral_density"]) == count, "spectrogram frequency shape mismatch")
            for row in output["power_spectral_density"]:
                _array(row, frames)
        else:
            for key in fields - {"frequency_hz", "segment_count", "transfer_direction"}:
                _array(output[key], count, nullable=key in {"coherence", "transfer_real", "transfer_imag"})


def _validate_result(request, data):
    """Validate source links, declared policies and shapes without executing DSP."""
    _keys(data, {"schema", "request_ref", "stages", "authority"}, {"diagnostics"})
    _finite(data)
    _require(data["schema"] == "stfe.dsp-pipeline-result.v1" and data["request_ref"] == dsp_digest(request),
             "request binding mismatch")
    _require(_same(data["authority"], AUTHORITY), "authority claims exceed numerical processing")
    _require(type(data["stages"]) is list and len(data["stages"]) == len(request["steps"]), "stage count mismatch")
    signals = dict(request["signals"])
    valid_ranges = {key: [0, len(value["values"])] for key, value in signals.items()}
    checked = set()
    for step, stage in zip(request["steps"], data["stages"]):
        _keys(stage, {"id", "input", "reference", "method", "parameters", "result"})
        expected = {k: step.get(k) for k in ("id", "input", "reference", "method", "parameters")}
        _require(dsp_digest({k: stage[k] for k in expected}) == dsp_digest(expected), "stage declaration mismatch")
        method = step["method"]
        _require(method in METHODS and step["input"] in signals and step["id"] not in signals,
                 "invalid processing graph")
        _require(method == "quality" or step["input"] in checked, "processing requires preceding quality stage")
        source = signals[step["input"]]
        reference = signals.get(step.get("reference"))
        if method in {"delay", "coherence"}:
            _require(reference is not None and step["reference"] in checked, "paired input requires quality stage")
        else:
            _require(step.get("reference") is None, "unexpected reference")
        result = stage["result"]
        _keys(result, {"schema", "method", "input_ref", "parameters", "contract", "output"})
        _require(result["schema"] == "stfe.dsp-result.v1" and result["method"] == method and
                 result["input_ref"] == dsp_digest(source), "stage source/method binding mismatch")
        _parameters(step["parameters"], result["parameters"], method, result["contract"])
        output = result["output"]
        _require(type(output) is dict, "output must be an object")
        if method in SIGNAL_METHODS:
            _signal_output(output, source, method, result["parameters"])
        else:
            _analysis_output(output, method, source, result["parameters"])
        _contract(result["contract"], method, source, output, result["parameters"], reference)
        contract = result["contract"]
        required_lineage = {"pipeline_input_valid_sample_range", "pipeline_effective_valid_sample_range",
                            "includes_boundary_affected_samples", "pipeline_edge_validity_scope"}
        _require(required_lineage <= contract.keys(), "requires inherited edge validity contract")
        _require(contract["pipeline_edge_validity_scope"] == "conservative finite-support boundary dependence only; unknown IIR settling stays unknown; no automatic cropping or physical-validity claim",
                 "edge validity scope mismatch")
        _require(_same(contract["pipeline_input_valid_sample_range"], valid_ranges[step["input"]]),
                 "inherited input validity mismatch")
        effective = contract["pipeline_effective_valid_sample_range"]
        count = len(output["values"]) if method in SIGNAL_METHODS else len(source["values"])
        if effective is not None:
            _range(effective, count)
        _require(_same(contract["includes_boundary_affected_samples"],
                       None if effective is None else effective != [0, count]), "boundary flag mismatch")
        if reference is not None:
            _require("pipeline_reference_valid_sample_range" in contract and
                     _same(contract["pipeline_reference_valid_sample_range"], valid_ranges[step["reference"]]),
                     "inherited reference validity mismatch")
        else:
            _require("pipeline_reference_valid_sample_range" not in contract, "unexpected reference validity")
        if method == "features":
            for group in ("windows", "events"):
                for row in output[group]:
                    expected_edge = None if effective is None else effective[0] <= row["start_sample"] and row["stop_sample"] <= effective[1]
                    _require(_same(row["pipeline_edge_support_valid"], expected_edge), "feature edge support mismatch")
        if method == "quality":
            checked.add(step["input"])
            signals[step["id"]] = source
            valid_ranges[step["id"]] = effective
            checked.add(step["id"])
        elif method in SIGNAL_METHODS:
            signals[step["id"]] = output
            valid_ranges[step["id"]] = effective
            checked.add(step["id"])
    if "diagnostics" in data:
        _keys(data["diagnostics"], {"synthetic_event_comparison"})
        diagnostics = data["diagnostics"]["synthetic_event_comparison"]
        _keys(diagnostics, {"scope", "ground_truth_used_for_detection", "ground_truth_ref", "declared_event_count",
                            "candidate_count", "comparisons", "candidate_definition"})
        _require(diagnostics["candidate_definition"] == "contiguous amplitude-threshold excursions; one injected disturbance can produce many candidates",
                 "candidate interpretation mismatch")
        _require(diagnostics["scope"] == "synthetic event overlap only; no physical leak confirmation or independent verification"
                 and diagnostics["ground_truth_used_for_detection"] is False, "diagnostic authority mismatch")
        _require(diagnostics["ground_truth_ref"] == dsp_digest(request.get("ground_truth", {})), "ground truth reference mismatch")
        _require(type(diagnostics["comparisons"]) is list and type(diagnostics["declared_event_count"]) is int
                 and len(diagnostics["comparisons"]) == diagnostics["declared_event_count"], "event comparison shape mismatch")
        _integer(diagnostics["candidate_count"], 0, 32768 * len(request["steps"]))


def validate_result(request, data):
    """Validate source links, declared policies and shapes without executing DSP."""
    try:
        _validate_result(request, data)
    except (KeyError, TypeError, IndexError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError("DSP malformed retained contract") from exc
