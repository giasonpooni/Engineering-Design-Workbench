# Changelog

## 0.1.0 — release candidate (not yet published)

First ClockSync distribution, extending the existing TBRT instrument.

- `clocksync` and `python -m tbrt` entry points; `--version` and bundled synthetic examples.
- Strict JSON object fields, duplicate-key rejection, bounded input size, non-finite value refusal and no silent boolean/string coercion of scientific inputs.
- Independent destination-frame pin and retained request policy alongside numerical results.
- Wheel/sdist packaging with MPL-2.0 license and the existing Bespoke Polymer Inc. notice.
- Cross-platform installed-package tests, optional source-pinned SET exchange tests and clean-environment distribution checks.

### Compatibility

The `tbrt` imports, numerical API, `tbrt.affine-clock-reconcile.v1`, `first-order.v1`, and core `clock.py` remain unchanged. Valid existing request JSON continues to work. Invalid values and unknown keys that the draft CLI silently coerced or discarded now fail closed. The result adds `request_options`; existing result fields remain.

The distribution name is `notations-clocksync`, not the historical `time-base-reconciliation-runtime`. Do not install both distributions into one environment: they own the same `tbrt` import. Migrate using a clean virtual environment.

The `exchange` extra remains as an empty compatibility marker. Its Git dependency moved to `requirements-exchange.txt` so wheel metadata can be uploaded to PyPI. Installing `.[exchange]` alone no longer installs SET; explicitly install the pinned requirements file before using `tbrt.exchange.export_result`.

No clock fitting, network synchronization, clock control, evidence admission, or production metrological validation is claimed.
