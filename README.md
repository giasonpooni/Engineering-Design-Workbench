# Time-Base Reconciliation Runtime

[Stack placement and ownership](docs/STACK.md) · [License](LICENSE)

**TBRT** is a bounded numerical instrument for translating a device event timestamp into an explicitly identified reference clock. It retains the original observation, supplied model, and uncertainty inputs. This repository implements one operation: affine clock reconciliation with first-order joint-covariance propagation.

The model is anchored to reduce arithmetic on large epoch coordinates:

\[
t_\mathrm{ref}=t_{\mathrm{ref},0}+a(t_\mathrm{device}-t_{\mathrm{device},0})+b.
\]

The result keeps `reference_origin` and `event_time_delta` separately. Its scalar `event_time` property is a rounded convenience representation. Source timestamps already rounded before input cannot be reconstructed.

## Run

Python 3.11+ and NumPy are required.

```bash
python -m pip install -e '.[dev]'
python -m pytest
python examples/replay.py
```

The example uses synthetic clock identities and prints a replayable input/result record. CI runs tests and examples on Python 3.11 and 3.12.

For the optional existing SET exchange contract:

```bash
python -m pip install -e '.[dev,exchange]'
python examples/exchange.py
```

`tbrt.exchange.export_result` exports `notation.instrument.result-artifact.v1` and validates it using the source-pinned SET package. It preserves complete `input_payload` and `numerical_result` snapshots. The example maps the event-time delta from its declared reference origin into a seconds-valued component, with propagated variance; the full anchored model remains in the numerical result. The all-zero source revision is an explicit synthetic caller placeholder. Artifact creation time is caller-supplied metadata, separate from event time. Conformance does not establish CIW execution integration or independent verification.

## API

```python
import numpy as np
from tbrt import AffineClockModel, ClockFrame, TimestampObservation, reconcile_time

device = ClockFrame("sensor-1", "device-monotonic", "s")
reference = ClockFrame("reference-1", "reference-monotonic", "s")
raw = TimestampObservation(103.0, device, evidence_id="observation-17")
clock = AffineClockModel(
    model_id="clock-map-4",
    source_frame=device,
    reference_frame=reference,
    device_origin=100.0,
    reference_origin=1000.0,
    skew=1.00002,
    offset=0.0003,
    valid_device_interval=(100.0, 110.0),
)
# Covariance variable order is [device_time, skew, offset].
result = reconcile_time(raw, clock, np.diag([1e-6, 1e-10, 4e-6]))
assert result.observation is raw
assert result.reference_origin == 1000.0
```

`reconcile_time` validates identities, the inclusive applicability interval, covariance symmetry/positive semidefiniteness, and finite arithmetic. Covariance cross-terms are included. `expected_reference=` optionally pins the destination frame. Inputs and result snapshots are immutable; the caller's covariance is copied.

## Position and authority

PPDA preserves acquisition evidence and raw timestamps. TBRT produces a derived event-time coordinate for STFE, GSIE, GTE, or calibration workloads that require aligned time. It does not acquire samples, change clocks, infer missing timestamps, admit evidence, authorize state, or actuate hardware. Receipt time and knowledge time remain separate metadata.

This package is independently executable, with optional SET contract export. The stack relationships describe numerical boundaries; no live PPDA, STFE, GSIE, GTE, CIW, SCR, or ESM adapter is included.

## Limits

- Supplied, positive-skew affine models only; no clock fitting, piecewise drift model, resampling, or out-of-order buffering.
- Explicit seconds only. Time-scale names are identities, not implementations of UTC/TAI/GNSS conversion or leap-second handling.
- Domain checks apply to the nominal input timestamp. Uncertainty support is not bounded by those checks.
- Uncertainty is first-order propagation. With uncertain, correlated skew and timestamp, it is not the exact transformed distribution or exact transformed mean.
- Model IDs and evidence IDs are caller references; they are not certificates of synchronization quality or metrological traceability.

See [contract](docs/CONTRACT.md), [numerics](docs/NUMERICS.md), and [stack role](docs/STACK_ROLE.md). License: MPL-2.0.
