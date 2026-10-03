# SPDX-License-Identifier: MPL-2.0
"""Bounded DSP operations over explicitly timed scalar recordings.

All values use binary64. Numerical outputs are derived observations, never
admitted physical state or a calibrated leak determination. SciPy is optional
for the historical window-mean instrument; it is required by this module.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import signal as sp

from stfe.window import ContractError, digest

MAX_SAMPLES = 32768
MAX_NFFT = 65536
MAX_SPECTRAL_CELLS = 1048576
SIGNAL_FIELDS = {"source_id", "unit", "clock_id", "sample_rate_hz", "time_s", "values"}
METHODS = frozenset({"quality", "detrend", "resample", "delay", "fractional_delay", "filter", "fft", "welch", "spectrogram", "features", "coherence"})
WINDOWS = frozenset({"hann", "hamming", "blackman", "boxcar"})


def _number(value: Any, name: str) -> float:
    if type(value) not in (int, float):
        raise ContractError(f"{name} must be a finite JSON number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ContractError(f"{name} must be finite binary64") from exc
    if not math.isfinite(result):
        raise ContractError(f"{name} must be finite binary64")
    if type(value) is int and int(result) != value:
        raise ContractError(f"{name} integer is not exactly representable as binary64")
    return result


def _integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ContractError(f"{name} must be an integer in [{low}, {high}]")
    return value


def _allowed(parameters: dict, fields: set[str]) -> None:
    if any(type(key) is not str for key in parameters):
        raise ContractError("parameter names must be strings")
    unknown = set(parameters) - fields
    if unknown:
        raise ContractError(f"unknown parameters: {sorted(unknown)}")


def _choice(value: Any, name: str, choices: set | frozenset) -> Any:
    if not isinstance(value, (str, bool)) or value not in choices:
        raise ContractError(f"{name} must be one of {sorted(map(str, choices))}")
    return value


def _time_tolerance(fs: float, t: np.ndarray) -> float:
    # Permit timestamp roundoff, including epoch timestamps, without allowing
    # it to hide interval errors larger than one percent of the period.
    return min(0.01 / fs, max(1e-6 / fs, 4 * np.finfo(float).eps * float(np.max(np.abs(t)))))


def _signal(raw: dict, *, quality: bool = False) -> tuple[dict, np.ndarray, np.ndarray]:
    if not isinstance(raw, dict) or set(raw) != SIGNAL_FIELDS:
        raise ContractError("signal fields must exactly match source_id, unit, clock_id, sample_rate_hz, time_s, values")
    for key in ("source_id", "unit", "clock_id"):
        if not isinstance(raw[key], str) or not raw[key].strip() or len(raw[key]) > 1024:
            raise ContractError(f"{key} must be a nonempty string of at most 1024 characters")
    fs = _number(raw["sample_rate_hz"], "sample_rate_hz")
    if fs <= 0 or not math.isfinite(1.0 / fs):
        raise ContractError("sample_rate_hz must have a finite positive reciprocal")
    if type(raw["values"]) is not list or type(raw["time_s"]) is not list:
        raise ContractError("values and time_s must be JSON arrays")
    n = len(raw["values"])
    if not 1 <= n <= MAX_SAMPLES or len(raw["time_s"]) != n:
        raise ContractError(f"values and time_s must have equal lengths in [1, {MAX_SAMPLES}]")
    times = [_number(v, "time_s item") for v in raw["time_s"]]
    values = [None if v is None else _number(v, "values item") for v in raw["values"]]
    normalized = {**raw, "sample_rate_hz": fs, "time_s": times, "values": values}
    t, x = np.asarray(times, dtype=np.float64), np.asarray(values, dtype=np.float64)
    if not quality:
        if not np.all(np.isfinite(x)):
            raise ContractError("numerical DSP requires finite complete samples; missing data is never imputed")
        if n < 2:
            raise ContractError("numerical DSP requires at least two samples")
        dt = np.diff(t)
        tolerance = _time_tolerance(fs, t)
        if np.any(dt <= 0) or np.any(np.abs(dt - 1 / fs) > tolerance):
            raise ContractError("numerical DSP requires strictly increasing uniform timestamps at declared sample_rate_hz")
    return normalized, t, x


def _contract(n: int, ref: str, mode: str = "offline") -> dict:
    return {"mode": mode, "missing_policy": "reject", "precision": "float64",
            "uncertainty_propagation": "not_propagated; filtering/resampling changes variance and temporal correlation; downstream noise models require requalification",
            "timing_offset_s": 0.0, "latency_samples": None,
            "valid_sample_range": [0, n],
            "source_support": {"input_ref": ref, "input_sample_range": [0, n]}}


def _finite_output(value: Any) -> None:
    if isinstance(value, dict):
        for child in value.values():
            _finite_output(child)
    elif isinstance(value, list):
        for child in value:
            _finite_output(child)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ContractError("operation generated a nonfinite result; input magnitude or numerical conditioning exceeds this operation's scope")


def _derived(source: dict, values: np.ndarray, ref: str, method: str, p: dict,
             *, times: np.ndarray | None = None, fs: float | None = None) -> dict:
    y = np.asarray(values, dtype=np.float64)
    if not 1 <= len(y) <= MAX_SAMPLES:
        raise ContractError("derived recording exceeds sample bound")
    return {"source_id": digest({"input_ref": ref, "method": method, "parameters": p}),
            "unit": source["unit"], "clock_id": source["clock_id"],
            "sample_rate_hz": source["sample_rate_hz"] if fs is None else fs,
            "time_s": source["time_s"].copy() if times is None else times.tolist(),
            "values": y.tolist()}


def _paired(reference: dict | None, source: dict, t: np.ndarray) -> tuple[dict, np.ndarray]:
    if reference is None:
        raise ContractError("this operation requires a reference signal")
    other, rt, rx = _signal(reference)
    if (other["sample_rate_hz"] != source["sample_rate_hz"] or len(rt) != len(t)
            or other["clock_id"] != source["clock_id"]):
        raise ContractError("paired signals require matching rate, length and clock_id")
    if not np.allclose(rt, t, rtol=0, atol=_time_tolerance(source["sample_rate_hz"], t)):
        raise ContractError("paired signals require aligned timestamps; clock correction must be separately declared")
    return other, rx


def _spectrum_params(parameters: dict, n: int) -> dict:
    _allowed(parameters, {"window", "nperseg", "noverlap", "nfft", "detrend"})
    segment = _integer(parameters.get("nperseg", min(256, n)), "nperseg", 2, n)
    overlap = _integer(parameters.get("noverlap", segment // 2), "noverlap", 0, segment - 1)
    nfft = _integer(parameters.get("nfft", segment), "nfft", segment, MAX_NFFT)
    window = _choice(parameters.get("window", "hann"), "window", WINDOWS)
    detrend = _choice(parameters.get("detrend", "constant"), "detrend", {False, "constant", "linear"})
    count = 1 + (n - segment) // (segment - overlap)
    if count * (nfft // 2 + 1) > MAX_SPECTRAL_CELLS:
        raise ContractError("spectral grid exceeds bounded cell count")
    return {"window": window, "nperseg": segment, "noverlap": overlap,
            "nfft": nfft, "detrend": detrend}


def _quality(s: dict, t: np.ndarray, x: np.ndarray, p: dict, c: dict) -> tuple[dict, dict]:
    _allowed(p, {"lower_bound", "upper_bound", "saturation_run_samples", "time_tolerance_s"})
    fs, n = s["sample_rate_hz"], len(x)
    q = {"lower_bound": None, "upper_bound": None,
         "saturation_run_samples": _integer(p.get("saturation_run_samples", 3), "saturation_run_samples", 2, MAX_SAMPLES),
         "time_tolerance_s": _number(p.get("time_tolerance_s", _time_tolerance(fs, t)), "time_tolerance_s")}
    if not 0 <= q["time_tolerance_s"] < 0.5 / fs:
        raise ContractError("time_tolerance_s must be nonnegative and less than half a sample period")
    for key in ("lower_bound", "upper_bound"):
        if p.get(key) is not None:
            q[key] = _number(p[key], key)
    if q["lower_bound"] is not None and q["upper_bound"] is not None and q["lower_bound"] >= q["upper_bound"]:
        raise ContractError("lower_bound must be less than upper_bound")
    dt = np.diff(t)
    duplicate = np.flatnonzero(dt == 0) + 1
    backwards = np.flatnonzero(dt < 0) + 1
    irregular = np.flatnonzero(np.abs(dt - 1 / fs) > q["time_tolerance_s"])
    gaps = np.flatnonzero(dt > 1 / fs + q["time_tolerance_s"])
    clipped = np.zeros(n, dtype=bool)
    if q["lower_bound"] is not None:
        clipped |= x <= q["lower_bound"]
    if q["upper_bound"] is not None:
        clipped |= x >= q["upper_bound"]
    runs = []
    start = 0
    while start < n:
        end = start + 1
        while end < n and np.isfinite(x[start]) and x[end] == x[start]:
            end += 1
        if end - start >= q["saturation_run_samples"]:
            runs.append({"start_sample": start, "stop_sample": end, "value": float(x[start]),
                         "at_declared_bound": bool(clipped[start]),
                         "classification": "declared_bound_plateau" if clipped[start] else "constant_plateau_candidate"})
        start = end
    positive = dt[dt > 0]
    out = {"sample_count": n, "missing_indices": np.flatnonzero(~np.isfinite(x)).tolist(),
           "duplicate_time_indices": duplicate.tolist(), "nonmonotone_time_indices": backwards.tolist(),
           "gap_after_indices": gaps.tolist(), "irregular_interval_indices": irregular.tolist(),
           "clipped_indices": np.flatnonzero(clipped).tolist(), "saturation_runs": runs,
           "observed_sample_rate_hz": float(1 / np.median(positive)) if len(positive) else None,
           "max_timing_error_s": float(np.max(np.abs(dt - 1 / fs))) if len(dt) else None,
           "supports_uniform_analysis": bool(n >= 2 and np.all(np.isfinite(x)) and np.all(dt > 0) and not len(irregular))}
    c["missing_policy"] = "report_without_imputation"
    return q, out


def _filter(s: dict, x: np.ndarray, p: dict, c: dict) -> tuple[dict, np.ndarray]:
    _allowed(p, {"family", "kind", "cutoff_hz", "numtaps", "order", "q", "mode", "taps", "state", "chunks", "padlen", "window"})
    fs, n = s["sample_rate_hz"], len(x)
    family = _choice(p.get("family", "fir"), "family", {"fir", "butter", "notch"})
    mode = _choice(p.get("mode", "causal"), "mode", {"causal", "offline_zero_phase"})
    q = {"family": family, "mode": mode}
    sos = None
    if family == "fir" and p.get("taps") is not None:
        if set(p) & {"cutoff_hz", "numtaps", "order", "q", "window"}:
            raise ContractError("custom taps cannot be combined with filter design parameters")
        if "kind" in p and p["kind"] != "custom":
            raise ContractError("custom FIR taps require omitted kind or kind='custom'")
        taps = p["taps"]
        if type(taps) is not list or not 1 <= len(taps) <= 1025:
            raise ContractError("taps must be a JSON array of length 1..1025")
        b = np.asarray([_number(v, "tap") for v in taps])
        a = np.asarray([1.0])
        q.update({"kind": "custom", "taps": b.tolist()})
    else:
        kind = _choice(p.get("kind", "lowpass"), "kind", {"lowpass", "highpass", "bandpass", "bandstop"})
        if "cutoff_hz" not in p:
            raise ContractError("filter design requires cutoff_hz")
        cutoff = p["cutoff_hz"]
        if kind in {"bandpass", "bandstop"} and family != "notch":
            if type(cutoff) is not list or len(cutoff) != 2:
                raise ContractError("band filter requires cutoff_hz=[low,high]")
            cutoff = [_number(v, "cutoff_hz") for v in cutoff]
            if not 0 < cutoff[0] < cutoff[1] < fs / 2:
                raise ContractError("band cutoff must satisfy 0 < low < high < Nyquist")
        else:
            cutoff = _number(cutoff, "cutoff_hz")
            if not 0 < cutoff < fs / 2:
                raise ContractError("cutoff must be strictly between zero and Nyquist")
        q.update({"kind": kind, "cutoff_hz": cutoff})
        if family == "fir":
            if set(p) & {"order", "q"}:
                raise ContractError("FIR design does not accept order or q")
            taps = _integer(p.get("numtaps", 65), "numtaps", 3, 1025)
            if taps % 2 != 1:
                raise ContractError("designed FIR numtaps must be odd")
            window = _choice(p.get("window", "hamming"), "window", WINDOWS)
            b = sp.firwin(taps, cutoff, pass_zero=kind, fs=fs, window=window)
            a = np.asarray([1.0])
            q.update({"numtaps": taps, "window": window})
        elif family == "butter":
            if set(p) & {"numtaps", "q", "taps", "window"}:
                raise ContractError("Butterworth design does not accept FIR/notch parameters")
            order = _integer(p.get("order", 4), "order", 1, 12)
            sos = sp.butter(order, cutoff, btype=kind, fs=fs, output="sos")
            q["order"] = order
        else:
            if set(p) & {"numtaps", "order", "taps", "window"}:
                raise ContractError("notch design does not accept FIR/Butterworth parameters")
            if "kind" in p and p["kind"] != "bandstop":
                raise ContractError("notch kind must be bandstop")
            quality = _number(p.get("q", 30.0), "q")
            if quality <= 0 or cutoff / quality >= fs / 2:
                raise ContractError("notch q must be positive and its bandwidth cutoff_hz/q strictly below Nyquist")
            b, a = sp.iirnotch(cutoff, quality, fs=fs)
            sos = sp.tf2sos(b, a)
            q.update({"kind": "bandstop", "q": quality})
    if sos is not None:
        for section in sos:
            poles = np.roots(section[3:])
            if np.any(np.abs(poles) >= 1.0):
                raise ContractError("IIR design is numerically unstable; every pole must lie strictly inside the unit circle")
    coefficients = {"sos": sos.tolist()} if sos is not None else {"b": b.tolist(), "a": a.tolist()}
    if sos is not None:
        freq, response = sp.sosfreqz(sos, worN=np.linspace(0, fs / 2, 257), fs=fs)
        shape = (len(sos), 2)
    else:
        freq, response = sp.freqz(b, a, worN=np.linspace(0, fs / 2, 257), fs=fs)
        shape = (max(len(a), len(b)) - 1,)
    c.update({"coefficients": coefficients,
              "frequency_response": {"frequency_hz": freq.tolist(), "real": response.real.tolist(),
                                     "imag": response.imag.tolist(), "magnitude": np.abs(response).tolist(),
                                     "applied_magnitude": (np.abs(response) ** (2 if mode == "offline_zero_phase" else 1)).tolist()},
              "mode": mode})
    if mode == "causal":
        if "padlen" in p:
            raise ContractError("padlen applies only to offline zero-phase filtering")
        chunks = p.get("chunks", [n])
        if type(chunks) is not list or not chunks or len(chunks) > n:
            raise ContractError("chunks must be a nonempty list of positive sample counts")
        chunks = [_integer(v, "chunk size", 1, n) for v in chunks]
        if sum(chunks) != n:
            raise ContractError("chunks must sum to the input sample count")
        initial = p.get("state")
        if initial is None:
            zi = np.zeros(shape)
            initialization = "zero_state"
        else:
            def check_state(v: Any) -> None:
                if type(v) is list:
                    for item in v:
                        check_state(item)
                else:
                    _number(v, "state item")
            check_state(initial)
            try:
                zi = np.asarray(initial, dtype=np.float64)
            except (ValueError, TypeError) as exc:
                raise ContractError("state must match the filter state shape") from exc
            if zi.shape != shape:
                raise ContractError(f"state must have shape {shape}")
            initialization = "provided_state; predecessor samples are not independently verified"
        q.update({"state": zi.tolist(), "chunks": chunks})
        parts, offset = [], 0
        for size in chunks:
            if sos is not None:
                part, zi = sp.sosfilt(sos, x[offset:offset + size], zi=zi)
            elif len(zi):
                part, zi = sp.lfilter(b, a, x[offset:offset + size], zi=zi)
            else:
                part = sp.lfilter(b, a, x[offset:offset + size])
            parts.append(part)
            offset += size
        y = np.concatenate(parts)
        c.update({"initialization": initialization, "final_state": zi.tolist(),
                  "chunk_boundaries": np.cumsum([0] + chunks).tolist()})
        if family == "fir":
            c["valid_sample_range"] = [min(len(b) - 1, n), n] if initial is None else None
            linear_phase = np.allclose(b, b[::-1], rtol=1e-12, atol=1e-15)
            c["latency_samples"] = (len(b) - 1) / 2 if linear_phase else None
            c["timing_offset_s"] = (len(b) - 1) / (2 * fs) if linear_phase else None
            c["source_support"]["past_samples"] = len(b) - 1
            c["source_support"]["future_samples"] = 0
        else:
            c["valid_sample_range"] = None
            c["timing_offset_s"] = None
            c["transient_policy"] = "IIR impulse response has infinite support; no finite settling interval is asserted"
    else:
        if "state" in p or "chunks" in p:
            raise ContractError("offline zero-phase filtering does not accept streaming state or chunks")
        default_pad = (3 * (2 * len(sos) + 1 - min((sos[:, 2] == 0).sum(), (sos[:, 5] == 0).sum()))) if sos is not None else 3 * max(len(a), len(b))
        if sos is None and len(b) == len(a) == 1:
            default_pad = 0
        padlen = _integer(p.get("padlen", int(default_pad)), "padlen", 0, n - 2)
        q.update({"padlen": padlen, "padtype": "odd"})
        if sos is None and len(b) == len(a) == 1:
            y = x * (b[0] / a[0]) ** 2
        else:
            y = sp.sosfiltfilt(sos, x, padlen=padlen, padtype="odd") if sos is not None else sp.filtfilt(b, a, x, padlen=padlen, padtype="odd")
        c.update({"final_state": None, "initialization": "odd reflection padding with endpoint steady-state initialization",
                  "latency_samples": None, "timing_offset_s": 0.0,
                  "valid_sample_range": [min(len(b) - 1, n), max(min(len(b) - 1, n), n - len(b) + 1)] if family == "fir" else None,
                  "transient_policy": "two-sided processing uses future samples; IIR edges have no exact finite validity bound"})
    return q, y


def process(signal: dict, method: str, parameters: dict, *, reference: dict | None = None) -> dict:
    """Execute one DSP operation, returning complete effective parameters and contract.

    Delay sign: positive means ``signal[n]`` resembles ``reference[n-delay]``.
    State for FIR uses SciPy lfilter direct-form-II delay state; IIR uses SOS
    state of shape (sections, 2). Chunks partition exactly the supplied samples.
    All sample ranges are half-open. ``None`` validity/latency is unknown, not zero.
    """
    if type(method) is not str or method not in METHODS:
        raise ContractError("unsupported DSP method")
    if type(parameters) is not dict:
        raise ContractError("parameters must be a JSON object")
    if reference is not None and method not in {"delay", "coherence"}:
        raise ContractError("reference is supported only by delay and coherence")
    s, t, x = _signal(signal, quality=method == "quality")
    ref, fs, n = digest(signal), s["sample_rate_hz"], len(x)
    c, p = _contract(n, ref), dict(parameters)
    if method == "quality":
        p, out = _quality(s, t, x, p, c)
    elif method == "detrend":
        _allowed(p, {"type"})
        p = {"type": _choice(p.get("type", "linear"), "type", {"linear", "constant"})}
        out = _derived(s, sp.detrend(x, type=p["type"]), ref, method, p)
        c["source_support"]["dependence"] = "whole recording fit"
    elif method == "resample":
        _allowed(p, {"up", "down"})
        up = _integer(p.get("up", 1), "up", 1, 64)
        down = _integer(p.get("down", 1), "down", 1, 64)
        requested_up, requested_down = up, down
        factor = math.gcd(up, down)
        up, down = up // factor, down // factor
        p = {"up": requested_up, "down": requested_down, "reduced_up": up, "reduced_down": down,
             "window": ["kaiser", 5.0], "padtype": "constant", "cval": 0.0}
        expected = (n * up + down - 1) // down
        if expected > MAX_SAMPLES:
            raise ContractError("resampling would exceed output sample bound")
        new_fs = fs * up / down
        if not math.isfinite(new_fs) or new_fs <= 0:
            raise ContractError("resampled rate exceeds finite range")
        half = 10 * max(up, down) if max(up, down) > 1 else 0
        taps = sp.firwin(2 * half + 1, 1 / max(up, down), window=("kaiser", 5.0)) if half else np.asarray([1.0])
        y = sp.resample_poly(x, up, down, window=taps, padtype="constant", cval=0.0)
        times = t[0] + np.arange(len(y)) / new_fs
        edge = math.ceil(half / down)
        start, stop = min(edge, len(y)), max(min(edge, len(y)), len(y) - edge)
        c.update({"mode": "offline_noncausal", "valid_sample_range": [start, stop],
                  "source_support": {"input_ref": ref, "input_sample_range": [0, n], "ratio": [up, down],
                                     "fir_half_length_upsampled": half, "boundary_extension": "zero"},
                  "coefficients": {"b": taps.tolist(), "a": [1.0], "upsampling_gain": up},
                  "anti_alias": "SciPy resample_poly Kaiser FIR at reduced rational rate; finite transition band",
                  "sample_time_mapping": "t_out[k] = t_in[0] + k / output_sample_rate_hz"})
        out = _derived(s, y, ref, method, p, times=times, fs=new_fs)
    elif method == "delay":
        _allowed(p, {"max_lag_samples", "detrend"})
        limit = _integer(p.get("max_lag_samples", min(n - 1, 1024)), "max_lag_samples", 0, n - 1)
        detrend = _choice(p.get("detrend", "constant"), "detrend", {False, "constant", "linear"})
        p = {"max_lag_samples": limit, "detrend": detrend}
        other, rx = _paired(reference, s, t)
        a = sp.detrend(x, type=detrend) if detrend is not False else x
        b = sp.detrend(rx, type=detrend) if detrend is not False else rx
        norm = float(np.linalg.norm(a) * np.linalg.norm(b))
        if norm == 0 or not math.isfinite(norm):
            raise ContractError("delay estimation requires finite nonzero variation/energy in both channels")
        corr = sp.correlate(a, b, mode="full", method="fft") / norm
        lags = sp.correlation_lags(n, n, mode="full")
        select = np.abs(lags) <= limit
        corr, lags = corr[select], lags[select]
        index = int(np.argmax(corr))
        out = {"delay_samples": int(lags[index]), "delay_s": float(lags[index] / fs),
               "peak_correlation": float(corr[index]), "lags_samples": lags.tolist(),
               "correlation": corr.tolist(), "at_search_boundary": bool(limit and abs(lags[index]) == limit),
               "sign_convention": "positive means signal delayed relative to reference", "resolution_samples": 1}
        c["source_support"]["reference_input_ref"] = digest(reference)
        c["estimator_scope"] = "integer-lag positive-correlation peak; not a unique physical clock-offset identification"
    elif method == "fractional_delay":
        _allowed(p, {"delay_samples", "numtaps", "window"})
        delay = _number(p.get("delay_samples", 0.0), "delay_samples")
        count = _integer(p.get("numtaps", 33), "numtaps", 5, 1025)
        if count % 2 != 1 or abs(delay) > count // 2 - 2:
            raise ContractError("fractional delay requires odd numtaps and abs(delay_samples) <= numtaps//2 - 2")
        window = _choice(p.get("window", "hamming"), "window", WINDOWS)
        p = {"delay_samples": delay, "numtaps": count, "window": window}
        half = count // 2
        taps = np.sinc(np.arange(count) - half - delay) * sp.get_window(window, count, fftbins=False)
        taps /= np.sum(taps)
        y = sp.convolve(x, taps, mode="full", method="direct")[half:half + n]
        out = _derived(s, y, ref, method, p)
        freq, response = sp.freqz(taps, worN=257, fs=fs)
        centered = response * np.exp(2j * np.pi * freq * half / fs)
        c.update({"mode": "offline_noncausal", "timing_offset_s": delay / fs,
                  "valid_sample_range": [min(half, n), max(min(half, n), n - half)],
                  "coefficients": {"b": taps.tolist(), "a": [1.0]},
                  "frequency_response": {"frequency_hz": freq.tolist(), "real": centered.real.tolist(), "imag": centered.imag.tolist(), "magnitude": np.abs(centered).tolist()},
                  "source_support": {"input_ref": ref, "input_sample_range": [0, n], "past_samples": half, "future_samples": half, "boundary_extension": "zero"},
                  "approximation": "finite windowed-sinc interpolation; y[n] approximates x[n-delay]; timestamps retained"})
    elif method == "filter":
        try:
            p, y = _filter(s, x, p, c)
        except (ValueError, np.linalg.LinAlgError) as exc:
            if isinstance(exc, ContractError):
                raise
            raise ContractError(f"filter cannot honor declaration: {exc}") from exc
        out = _derived(s, y, ref, method, p)
    elif method == "fft":
        _allowed(p, {"window", "nfft", "detrend"})
        p = {"window": _choice(p.get("window", "hann"), "window", WINDOWS),
             "nfft": _integer(p.get("nfft", n), "nfft", n, MAX_NFFT),
             "detrend": _choice(p.get("detrend", False), "detrend", {False, "constant", "linear"})}
        w = sp.get_window(p["window"], n, fftbins=True)
        xx = sp.detrend(x, type=p["detrend"]) if p["detrend"] is not False else x
        z = np.fft.rfft(xx * w, n=p["nfft"])
        factor = np.full(len(z), 2.0)
        factor[0] = 1
        if p["nfft"] % 2 == 0:
            factor[-1] = 1
        out = {"frequency_hz": np.fft.rfftfreq(p["nfft"], 1 / fs).tolist(),
               "real": z.real.tolist(), "imag": z.imag.tolist(),
               "amplitude": (np.abs(z) * factor / np.sum(w)).tolist(),
               "power_spectral_density": (np.abs(z) ** 2 * factor / (fs * np.sum(w * w))).tolist()}
        c["spectral_normalization"] = "one-sided coherent-gain amplitude; density in input_unit^2/Hz; DC and even-Nyquist not doubled"
    elif method in {"welch", "spectrogram", "coherence"}:
        p = _spectrum_params(p, n)
        kwargs = {**p, "fs": fs, "return_onesided": True, "scaling": "density"}
        count = 1 + (n - p["nperseg"]) // (p["nperseg"] - p["noverlap"])
        c["source_support"].update({"window_samples": p["nperseg"], "hop_samples": p["nperseg"] - p["noverlap"], "tail_policy": "drop incomplete final window"})
        c["spectral_normalization"] = "one-sided density in input_unit^2/Hz; arithmetic segment average"
        if method == "welch":
            freq, psd = sp.welch(x, **kwargs, average="mean")
            out = {"frequency_hz": freq.tolist(), "power_spectral_density": psd.tolist(), "segment_count": count}
        elif method == "spectrogram":
            freq, tt, psd = sp.spectrogram(x, **kwargs, mode="psd")
            out = {"frequency_hz": freq.tolist(), "time_s": (tt + t[0]).tolist(), "power_spectral_density": psd.tolist(), "axis_order": ["frequency", "time"], "segment_count": count}
        else:
            if count < 2:
                raise ContractError("coherence requires at least two complete segments")
            other, rx = _paired(reference, s, t)
            freq, pxx = sp.welch(x, **kwargs, average="mean")
            _, pyy = sp.welch(rx, **kwargs, average="mean")
            _, pxy = sp.csd(x, rx, **kwargs, average="mean")
            defined = (pxx > 0) & (pyy > 0)
            values = np.zeros_like(pxx)
            # Divide by square roots separately: multiplying the two PSDs
            # spuriously underflows for perfectly ordinary scaled recordings.
            values[defined] = (np.abs(pxy[defined]) / np.sqrt(pxx[defined]) / np.sqrt(pyy[defined])) ** 2
            values = np.clip(values, 0, 1)
            transfer = np.zeros_like(pxy)
            transfer[pxx > 0] = pxy[pxx > 0] / pxx[pxx > 0]
            nullable = lambda array, mask: [float(v) if bool(ok) else None for v, ok in zip(array, mask)]
            out = {"frequency_hz": freq.tolist(), "coherence": nullable(values, defined),
                   "cross_spectrum_real": pxy.real.tolist(), "cross_spectrum_imag": pxy.imag.tolist(),
                   "transfer_real": nullable(transfer.real, pxx > 0), "transfer_imag": nullable(transfer.imag, pxx > 0),
                   "transfer_direction": "reference response / signal input (H1 estimate)", "segment_count": count}
            c["source_support"]["reference_input_ref"] = digest(reference)
            c["interpretation"] = "association and H1 linear response estimate; no causal or leak identification"
    else:  # features
        _allowed(p, {"window_samples", "hop_samples", "band_hz", "threshold"})
        window = _integer(p.get("window_samples", min(256, n)), "window_samples", 2, n)
        hop = _integer(p.get("hop_samples", max(1, window // 2)), "hop_samples", 1, n)
        band = p.get("band_hz")
        if band is not None:
            if type(band) is not list or len(band) != 2:
                raise ContractError("band_hz must be [low, high]")
            band = [_number(v, "band_hz") for v in band]
            if not 0 <= band[0] < band[1] <= fs / 2:
                raise ContractError("band_hz must lie within [0, Nyquist]")
        threshold = p.get("threshold")
        if threshold is not None:
            threshold = _number(threshold, "threshold")
            if threshold < 0:
                raise ContractError("threshold must be nonnegative")
        p = {"window_samples": window, "hop_samples": hop, "band_hz": band,
             "threshold": threshold, "band_window": "boxcar", "band_detrend": False,
             "kurtosis_convention": "population Pearson; undefined for constant window"}
        windows = []
        for start in range(0, n - window + 1, hop):
            stop = start + window
            xx = x[start:stop]
            rms, peak = float(np.sqrt(np.mean(xx * xx))), float(np.max(np.abs(xx)))
            centered = xx - np.mean(xx)
            variance = float(np.mean(centered ** 2))
            power = None
            if band is not None:
                freq, psd = sp.periodogram(xx, fs, window="boxcar", detrend=False, scaling="density")
                select = (freq >= band[0]) & (freq <= band[1])
                power = float(np.sum(psd[select]) * fs / window)
            windows.append({"start_sample": start, "stop_sample": stop, "time_start_s": float(t[start]),
                            "time_stop_s": float(t[start] + window / fs), "rms": rms, "peak": peak,
                            "crest_factor": peak / rms if rms > 0 else None,
                            "kurtosis": float(np.mean(centered ** 4) / variance ** 2) if variance > 0 else None,
                            "band_power": power, "threshold_exceeded": bool(peak >= threshold) if threshold is not None else None})
        events = []
        if threshold is not None:
            mask = np.abs(x) >= threshold
            edges = np.diff(np.r_[False, mask, False].astype(np.int8))
            for start, stop in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
                events.append({"start_sample": int(start), "stop_sample": int(stop),
                               "time_start_s": float(t[start]), "time_stop_s": float(t[start] + (stop - start) / fs),
                               "peak": float(np.max(np.abs(x[start:stop]))), "classification": "absolute_amplitude_threshold_candidate"})
        out = {"windows": windows, "events": events}
        c["source_support"].update({"window_samples": window, "hop_samples": hop, "tail_policy": "drop incomplete final window; threshold events inspect all samples"})
    result = {"schema": "stfe.dsp-result.v1", "method": method, "input_ref": ref,
              "parameters": p, "contract": c, "output": out}
    _finite_output(result)
    return result
