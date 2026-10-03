"""Independent analytical and adversarial qualification of retained DSP transforms.

These checks use closed-form signals, conservation identities and input/output
invariants. They do not reproduce the implementation with a second SciPy call.
"""

from copy import deepcopy

import numpy as np
import pytest

# DSP is an optional instrument in the base NET installation. The dedicated
# DSP qualification job installs it and rejects every skipped test in JUnit.
process = pytest.importorskip("stfe_dsp.dsp").process


def signal(values, fs=1024.0, *, source_id="qualification.synthetic", unit="Pa"):
    values = np.asarray(values, dtype=float)
    return {
        "source_id": source_id,
        "unit": unit,
        "clock_id": "qualification.clock",
        "sample_rate_hz": fs,
        "time_s": (np.arange(len(values)) / fs).tolist(),
        "values": values.tolist(),
    }


def project_amplitude(values, frequency, fs):
    """Least-squares sinusoid amplitude, independent of PSD/window conventions."""
    values = np.asarray(values, dtype=float)
    t = np.arange(len(values)) / fs
    basis = np.column_stack((np.sin(2 * np.pi * frequency * t),
                             np.cos(2 * np.pi * frequency * t),
                             np.ones(len(values))))
    coefficients = np.linalg.lstsq(basis, values, rcond=None)[0]
    return float(np.hypot(coefficients[0], coefficients[1]))


@pytest.mark.parametrize("field,value", [
    ("sample_rate_hz", True), ("sample_rate_hz", 0.0),
    ("sample_rate_hz", float("inf")), ("source_id", ""),
    ("unit", ""), ("clock_id", ""),
])
def test_invalid_signal_metadata_is_refused(field, value):
    record = signal(np.zeros(32))
    record[field] = value
    with pytest.raises((ValueError, TypeError)):
        process(record, "fft", {})


@pytest.mark.parametrize("fault", ["missing", "nan", "boolean", "gap", "duplicate", "length"])
def test_numerical_operations_do_not_silently_repair_samples(fault):
    record = signal(np.zeros(32))
    if fault == "missing":
        record["values"][7] = None
    elif fault == "nan":
        record["values"][7] = float("nan")
    elif fault == "boolean":
        record["values"][7] = True
    elif fault == "gap":
        record["time_s"][7] += 0.2 / record["sample_rate_hz"]
    elif fault == "duplicate":
        record["time_s"][7] = record["time_s"][6]
    else:
        record["values"].pop()
    with pytest.raises((ValueError, TypeError)):
        process(record, "fft", {})


def test_processing_does_not_mutate_source_or_parameters():
    record = signal(np.arange(32))
    parameters = {"type": "linear"}
    before = deepcopy((record, parameters))
    process(record, "detrend", parameters)
    assert (record, parameters) == before


def test_quality_inspects_defects_without_turning_them_into_zeroes():
    record = signal([0, 1, 1, 1, 0, -1, 0, 0], fs=8.0)
    record["values"][6] = None
    record["time_s"][3] = record["time_s"][2]
    report = process(record, "quality", {
        "lower_bound": -1.0, "upper_bound": 1.0, "saturation_run_samples": 3,
    })["output"]
    assert report["missing_indices"] == [6]
    assert report["duplicate_time_indices"]
    assert report["gap_after_indices"]
    assert report["clipped_indices"] == [1, 2, 3, 5]
    assert report["saturation_runs"]
    assert report["supports_uniform_analysis"] is False
    assert record["values"][6] is None


def test_linear_detrend_removes_affine_signal():
    record = signal(3.25 + 0.07 * np.arange(127), fs=64.0)
    output = process(record, "detrend", {"type": "linear"})["output"]
    assert np.max(np.abs(output["values"])) < 1e-12
    assert output["time_s"] == record["time_s"]
    assert output["unit"] == "Pa"


def test_fir_impulse_matches_hand_convolution():
    taps = [0.25, 0.5, 0.25]
    record = signal([1.0] + [0.0] * 31)
    result = process(record, "filter", {"family": "fir", "taps": taps, "mode": "causal"})
    np.testing.assert_array_equal(result["output"]["values"], taps + [0.0] * 29)
    np.testing.assert_array_equal(result["contract"]["final_state"], [0.0, 0.0])


def test_fir_streaming_chunks_and_explicit_state_match_one_pass():
    values = np.random.default_rng(418).normal(size=511)
    params = {"family": "fir", "taps": [0.125, 0.25, 0.5, 0.125], "mode": "causal"}
    whole = process(signal(values), "filter", params)
    chunks = process(signal(values), "filter", {**params, "chunks": [1, 7, 23, 480]})
    np.testing.assert_allclose(chunks["output"]["values"], whole["output"]["values"], atol=1e-15, rtol=1e-14)
    np.testing.assert_allclose(chunks["contract"]["final_state"], whole["contract"]["final_state"], atol=1e-15, rtol=1e-14)
    first = process(signal(values[:137]), "filter", params)
    second = process(signal(values[137:]), "filter", {**params, "state": first["contract"]["final_state"]})
    joined = first["output"]["values"] + second["output"]["values"]
    np.testing.assert_allclose(joined, whole["output"]["values"], atol=1e-15, rtol=1e-14)


def test_causal_filter_has_future_noninterference():
    values = np.random.default_rng(513).normal(size=256)
    altered = values.copy()
    altered[128:] += 1000.0
    params = {"family": "butter", "kind": "lowpass", "cutoff_hz": 64.0, "order": 4, "mode": "causal"}
    left = process(signal(values), "filter", params)["output"]["values"]
    right = process(signal(altered), "filter", params)["output"]["values"]
    np.testing.assert_array_equal(left[:128], right[:128])


def test_butter_filter_passband_stopband_and_stream_state():
    fs = 1024.0
    t = np.arange(8192) / fs
    values = np.sin(2 * np.pi * 16 * t) + np.sin(2 * np.pi * 300 * t)
    params = {"family": "butter", "kind": "lowpass", "cutoff_hz": 64.0, "order": 4, "mode": "causal"}
    whole = process(signal(values, fs), "filter", params)
    output = whole["output"]["values"][1024:]
    assert project_amplitude(output, 16.0, fs) == pytest.approx(1.0, abs=1e-4)
    assert project_amplitude(output, 300.0, fs) < 0.005
    chunked = process(signal(values, fs), "filter", {**params, "chunks": [13, 127, 1024, 7028]})
    np.testing.assert_allclose(chunked["output"]["values"], whole["output"]["values"], atol=2e-14, rtol=2e-13)


@pytest.mark.parametrize("count,kind,expected_power", [(256, "dc", 4.0), (256, "nyquist", 1.0), (255, "last_positive", 0.5)])
def test_fft_one_sided_endpoint_scaling_and_parseval(count, kind, expected_power):
    fs = 1024.0
    indices = np.arange(count)
    if kind == "dc":
        values = np.full(count, 2.0)
        expected_amplitude = 2.0
        expected_bin = 0
    elif kind == "nyquist":
        values = (-1.0) ** indices
        expected_amplitude = 1.0
        expected_bin = count // 2
    else:
        values = np.cos(2 * np.pi * (count // 2) * indices / count)
        expected_amplitude = 1.0
        expected_bin = count // 2
    output = process(signal(values, fs), "fft", {"window": "boxcar", "detrend": False})["output"]
    assert np.argmax(output["amplitude"]) == expected_bin
    assert output["amplitude"][expected_bin] == pytest.approx(expected_amplitude, rel=1e-12)
    power = sum(output["power_spectral_density"]) * fs / count
    assert power == pytest.approx(expected_power, rel=1e-12)
    assert power == pytest.approx(np.mean(values ** 2), rel=1e-12)


def test_welch_boxcar_power_matches_disjoint_segment_mean_square():
    rng = np.random.default_rng(146)
    values = rng.normal(size=1024)
    output = process(signal(values), "welch", {
        "window": "boxcar", "nperseg": 128, "noverlap": 0, "detrend": False,
    })["output"]
    assert output["segment_count"] == 8
    integrated = np.sum(output["power_spectral_density"]) * 1024.0 / 128
    assert integrated == pytest.approx(np.mean(values ** 2), rel=2e-13)


def test_spectrogram_localizes_frequency_change():
    fs = 1024.0
    t = np.arange(1024) / fs
    values = np.where(t < 0.5, np.sin(2 * np.pi * 32 * t), np.sin(2 * np.pi * 128 * t))
    output = process(signal(values, fs), "spectrogram", {
        "window": "boxcar", "nperseg": 128, "noverlap": 0, "detrend": False,
    })["output"]
    density = np.asarray(output["power_spectral_density"])
    peaks = np.asarray(output["frequency_hz"])[np.argmax(density, axis=0)]
    np.testing.assert_array_equal(peaks, [32.0] * 4 + [128.0] * 4)
    np.testing.assert_allclose(output["time_s"], np.arange(8) / 8 + 1 / 16, atol=1e-15)


def test_resampling_suppresses_out_of_band_aliases():
    fs = 1024.0
    t = np.arange(8192) / fs
    values = np.sin(2 * np.pi * 40 * t) + np.sin(2 * np.pi * 350 * t)
    output = process(signal(values, fs), "resample", {"up": 1, "down": 4})["output"]
    assert output["sample_rate_hz"] == 256.0
    assert len(output["values"]) == 2048
    interior = output["values"][128:-128]
    assert project_amplitude(interior, 40.0, 256.0) == pytest.approx(1.0, abs=0.003)
    assert project_amplitude(interior, 94.0, 256.0) < 0.003
    np.testing.assert_allclose(np.diff(output["time_s"]), 1 / 256.0, atol=1e-15)


def test_rational_resampling_preserves_grid_rate_and_dc_interior():
    output = process(signal(np.ones(1024)), "resample", {"up": 3, "down": 2})["output"]
    assert output["sample_rate_hz"] == 1536.0
    assert len(output["values"]) == 1536
    np.testing.assert_allclose(output["time_s"], np.arange(1536) / 1536.0, atol=1e-15)
    np.testing.assert_allclose(output["values"][50:-50], 1.0, atol=0.002)


def test_delay_estimation_pins_lag_sign_with_aperiodic_signal():
    reference_values = np.random.default_rng(719).normal(size=1024)
    delayed_values = np.r_[np.zeros(7), reference_values[:-7]]
    output = process(signal(delayed_values), "delay", {"max_lag_samples": 20},
                     reference=signal(reference_values, source_id="qualification.reference"))["output"]
    assert output["delay_samples"] == 7


def test_features_match_exact_population_moments_and_source_windows():
    output = process(signal([0, 3, 0, -3, 0, 0, 0, 0], fs=8.0), "features", {
        "window_samples": 4, "hop_samples": 4, "threshold": 2.0,
    })["output"]
    first, second = output["windows"]
    assert (first["start_sample"], first["stop_sample"]) == (0, 4)
    assert first["rms"] == pytest.approx(np.sqrt(4.5))
    assert first["peak"] == 3.0
    assert first["crest_factor"] == pytest.approx(np.sqrt(2.0))
    assert first["kurtosis"] == pytest.approx(2.0)
    assert first["threshold_exceeded"] is True
    assert (second["start_sample"], second["stop_sample"]) == (4, 8)
    assert second["rms"] == second["peak"] == 0.0
    assert second["crest_factor"] is None
    assert second["kurtosis"] is None
    assert second["threshold_exceeded"] is False


@pytest.mark.parametrize("method,parameters", [
    ("filter", {"family": "butter", "kind": "lowpass", "cutoff_hz": 512.0}),
    ("filter", {"family": "fir", "taps": [1.0, float("nan")]}),
    ("filter", {"family": "fir", "taps": [1.0], "chunks": [10]}),
    ("resample", {"up": True, "down": 2}),
    ("resample", {"up": 1, "down": 0}),
    ("fft", {"nfft": 32}),
    ("welch", {"nperseg": 64, "noverlap": 64}),
    ("features", {"window_samples": 16, "hop_samples": 0}),
])
def test_unqualified_parameter_ranges_are_refused(method, parameters):
    with pytest.raises((ValueError, TypeError)):
        process(signal(np.arange(128)), method, parameters)


@pytest.mark.parametrize("method,parameters", [
    ("delay", {"max_lag_samples": 8}),
    ("coherence", {"nperseg": 64, "noverlap": 32}),
])
def test_pairwise_analysis_requires_matching_sample_grids(method, parameters):
    values = np.random.default_rng(772).normal(size=256)
    with pytest.raises((ValueError, TypeError)):
        process(signal(values, fs=1024.0), method, parameters,
                reference=signal(values, fs=512.0, source_id="qualification.other-rate"))


def test_fractional_delay_phase_and_declared_interior_support():
    fs, frequency, delay = 1024.0, 32.0, 0.5
    t = np.arange(1024) / fs
    record = signal(np.cos(2 * np.pi * frequency * t), fs)
    result = process(record, "fractional_delay", {"delay_samples": delay, "numtaps": 65})
    start, stop = result["contract"]["valid_sample_range"]
    assert (start, stop) == (32, 992)
    expected = np.cos(2 * np.pi * frequency * (t[start:stop] - delay / fs))
    np.testing.assert_allclose(result["output"]["values"][start:stop], expected, atol=0.003)
    assert result["output"]["time_s"] == record["time_s"]
    assert result["contract"]["mode"] == "offline_noncausal"
    assert result["contract"]["timing_offset_s"] == delay / fs


def test_offline_zero_phase_filter_declares_and_exhibits_future_dependence():
    values = np.zeros(256)
    altered = values.copy()
    altered[128] = 1.0
    parameters = {"family": "fir", "kind": "lowpass", "cutoff_hz": 100.0,
                  "numtaps": 33, "mode": "offline_zero_phase"}
    result = process(signal(altered), "filter", parameters)
    unaltered = process(signal(values), "filter", parameters)
    assert result["contract"]["mode"] == "offline_zero_phase"
    assert result["contract"]["valid_sample_range"] == [32, 224]
    assert max(np.abs(np.array(result["output"]["values"])[110:128])) > 0.01
    np.testing.assert_array_equal(unaltered["output"]["values"], values)


@pytest.mark.parametrize("scale", [1.0, 1e-100])
def test_coherence_and_transfer_are_scale_invariant_for_known_gain(scale):
    values = scale * np.random.default_rng(753).normal(size=4096)
    output = process(signal(values), "coherence", {"nperseg": 256, "noverlap": 128},
                     reference=signal(3 * values, source_id="qualification.gain-three", unit="m/s"))["output"]
    assert output["segment_count"] == 31
    assert all(value is not None for value in output["coherence"])
    np.testing.assert_allclose(output["coherence"], 1.0, atol=2e-13)
    np.testing.assert_allclose(output["transfer_real"], 3.0, atol=2e-13)
    np.testing.assert_allclose(output["transfer_imag"], 0.0, atol=2e-13)


def test_coherence_zero_power_is_explicitly_undefined():
    record = signal(np.zeros(256))
    output = process(record, "coherence", {"nperseg": 64, "noverlap": 32},
                     reference={**record, "source_id": "qualification.zero-reference"})["output"]
    assert all(value is None for value in output["coherence"])
    assert all(value is None for value in output["transfer_real"])
    assert all(value is None for value in output["transfer_imag"])


def test_coherence_does_not_mislabel_a_single_segment_as_evidence():
    values = np.random.default_rng(931).normal(size=256)
    with pytest.raises(ValueError, match="at least two"):
        process(signal(values), "coherence", {"nperseg": 256, "noverlap": 0},
                reference=signal(2 * values, source_id="qualification.reference"))


def test_unrelated_seeded_channels_have_low_averaged_coherence():
    rng = np.random.default_rng(1294)
    output = process(signal(rng.normal(size=8192)), "coherence", {"nperseg": 256, "noverlap": 0},
                     reference=signal(rng.normal(size=8192), source_id="qualification.independent"))["output"]
    assert np.mean(output["coherence"]) < 0.08


def test_unstable_notch_design_is_refused():
    # A nominally positive Q alone does not constrain a valid digital notch:
    # this declaration gives unstable poles in the unconstrained design call.
    with pytest.raises(ValueError):
        process(signal([1.0] + [0.0] * 30), "filter", {
            "family": "notch", "cutoff_hz": 64.0, "q": 0.1, "mode": "causal",
        })


def test_json_integer_cannot_silently_round_to_different_sample():
    record = signal(np.zeros(32))
    record["values"][7] = 2**53 + 1
    with pytest.raises(ValueError):
        process(record, "fft", {})


def test_sampling_tolerance_does_not_hide_large_relative_timing_errors():
    record = signal(np.zeros(32), fs=1e10)
    record["time_s"][7] += 0.25 / record["sample_rate_hz"]
    with pytest.raises(ValueError):
        process(record, "fft", {})
