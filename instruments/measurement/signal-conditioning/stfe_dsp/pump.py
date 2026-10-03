# SPDX-License-Identifier: MPL-2.0
"""Deterministic synthetic pump-and-pipe recordings and declared DSP workload.

This is an illustrative signal generator, not a hydraulic solver, calibrated
pump model, cavitation model, or physically validated leak detector.
"""
from __future__ import annotations

import math
import random

from .pipeline import MAX_TOTAL_INPUT_SAMPLES, validate_request
from stfe.window import ContractError, digest


def make_pump_request(seed: int = 1729, duration_s: float = 8.0,
                      sample_rate_hz: float = 512.0) -> dict:
    """Return a strict JSON-native request; analysis never consumes its truth.

    The three sensor clocks intentionally carry different known offsets. Their
    inverses are retained as caller-declared synthetic mappings, not fitted
    from correlation. A finite disturbance interval drives a pressure change,
    reduced flow and extra vibration; its cause is deliberately non-identifying.
    """
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise ContractError("pump seed must be an integer in [0, 2147483647]")
    if type(duration_s) not in (float, int) or not math.isfinite(duration_s) or not 4 <= duration_s <= 32:
        raise ContractError("pump duration_s must be finite in [4,32]")
    if type(sample_rate_hz) not in (float, int) or not math.isfinite(sample_rate_hz) or not 256 <= sample_rate_hz <= 2048:
        raise ContractError("pump sample_rate_hz must be finite in [256,2048]")
    raw_count = duration_s * sample_rate_hz
    if raw_count != int(raw_count):
        raise ContractError("pump duration_s times sample_rate_hz must be an integer")
    count = int(raw_count)
    if count * 3 > MAX_TOTAL_INPUT_SAMPLES:
        raise ContractError("pump request exceeds the three-channel input sample bound")
    rate = float(sample_rate_hz)
    duration = float(duration_s)
    recording_ref = digest({"generator": "stfe.synthetic-pump.v1", "seed": seed,
                            "sample_rate_hz": rate, "duration_s": duration}).split(":", 1)[1]
    rng = random.Random(seed)
    time = [index / rate for index in range(count)]
    event_start = 0.4 * duration
    event_stop = 0.6 * duration
    offsets = {"pressure": 0.013, "flow": -0.007, "vibration": 0.029}
    units = {"pressure": "Pa", "flow": "m^3/s", "vibration": "m/s^2"}
    values = {"pressure": [], "flow": [], "vibration": []}
    for instant in time:
        phase = 2 * math.pi * 24.0 * instant
        pump = math.sin(phase)
        harmonic = math.sin(2 * phase)
        # Tapered disturbance avoids an unphysical ideal discontinuity while
        # retaining an explicit, known support interval for numerical testing.
        relative = (instant - event_start) / (event_stop - event_start)
        envelope = math.sin(math.pi * relative) ** 2 if 0 <= relative <= 1 else 0.0
        disturbance = envelope * math.sin(2 * math.pi * 80.0 * instant)
        values["pressure"].append(150000 + 8000 * pump + 1800 * harmonic
                                  - 4500 * envelope + 1400 * disturbance + rng.gauss(0, 250))
        values["flow"].append(0.002 + 0.00012 * pump - 0.00030 * envelope
                              + rng.gauss(0, 0.000015))
        values["vibration"].append(0.38 * pump + 0.12 * harmonic
                                   + 3.0 * disturbance + rng.gauss(0, 0.06))
    signals = {
        channel: {
            "source_id": f"synthetic:pump:{recording_ref}:{channel}", "unit": units[channel],
            "clock_id": f"synthetic:{channel}-clock", "sample_rate_hz": rate,
            "time_s": [instant + offsets[channel] for instant in time],
            "values": values[channel],
        } for channel in values
    }
    steps = []
    analysis = {}
    # Decimate only when the chosen rate leaves the declared 100 Hz pass band
    # below the new Nyquist limit. resample_poly supplies its anti-alias filter.
    down = 2 if rate >= 512 else 1
    analysis_rate = rate / down
    nperseg = 256
    spectral = {"nperseg": nperseg, "noverlap": 128, "nfft": nperseg,
                "window": "hann", "detrend": "constant"}
    for channel in signals:
        quality = f"{channel}.quality"
        aligned = f"{channel}.aligned"
        filtered = f"{channel}.filtered"
        steps.extend([
            {"id": quality, "input": channel, "method": "quality", "parameters": {}},
            {"id": aligned, "input": quality, "method": "clock_shift", "parameters": {
                "offset_s": -offsets[channel], "target_clock_id": "synthetic:reference-clock",
                "mapping_ref": f"synthetic:known-additive-clock-map:{channel}",
            }},
            {"id": filtered, "input": aligned, "method": "filter", "parameters": {
                "family": "fir", "kind": "lowpass", "cutoff_hz": 100.0,
                "numtaps": 65, "mode": "offline_zero_phase",
            }},
        ])
        current = filtered
        if down > 1:
            current = f"{channel}.resampled"
            steps.append({"id": current, "input": filtered, "method": "resample",
                          "parameters": {"up": 1, "down": down}})
        analysis[channel] = current
        steps.append({"id": f"{channel}.psd", "input": current, "method": "welch",
                      "parameters": dict(spectral)})
    steps.extend([
        {"id": "vibration.spectrogram", "input": analysis["vibration"],
         "method": "spectrogram", "parameters": dict(spectral)},
        {"id": "vibration.features", "input": analysis["vibration"], "method": "features",
         "parameters": {"window_samples": int(analysis_rate / 2),
                        "hop_samples": int(analysis_rate / 8),
                        "band_hz": [60.0, 100.0], "threshold": 1.5}},
        {"id": "pressure-vibration.coherence", "input": analysis["pressure"],
         "reference": analysis["vibration"], "method": "coherence",
         "parameters": dict(spectral)},
    ])
    request = {
        "schema": "stfe.dsp-pipeline.v1", "signals": signals, "steps": steps,
        "provenance": {
            "synthetic": True, "generator": "stfe.synthetic-pump.v1", "seed": seed,
            "duration_s": duration, "sample_rate_hz": rate,
            "pump_frequency_hz": 24.0, "harmonic_frequency_hz": 48.0,
            "disturbance_frequency_hz": 80.0,
            "clock_convention": "recorded_time = reference_time + declared_offset_s",
            "declared_clock_offsets_s": offsets,
            "noise_standard_deviation": {"pressure_Pa": 250.0,
                                          "flow_m3_per_s": 0.000015,
                                          "vibration_m_per_s2": 0.06},
            "scope": "illustrative synthetic signals; no hydraulic solution or physical leak diagnosis",
            "conditioning": "offline zero-phase FIR, followed by anti-aliased decimation when rate permits",
            "detector": "fixed vibration amplitude threshold independent of ground_truth",
        },
        "ground_truth": {
            "kind": "synthetic_disturbance_support", "events": [{
                "id": "synthetic:disturbance:1", "label": "non-identifying pressure-flow-vibration disturbance",
                "start_s": event_start, "stop_s": event_stop,
                "clock_id": "synthetic:reference-clock",
            }],
            "physical_leak": "not_established",
        },
    }
    return validate_request(request)
