# ClockSync

**Notation Systems — Frontier Tooling and Instrumentation for Digital Futures.**

**Apply a declared clock mapping. Keep the original timestamp. Propagate timing uncertainty.**

A small **Notation Systems** instrument for telemetry, measurement and simulation pipelines. ClockSync turns one device event timestamp into a reference-clock coordinate using a caller-supplied affine model and joint covariance. It does not set clocks or estimate a synchronization model.

**Status:** INSTRUMENT / 0.1.0 release candidate. Source and distribution checks are available; this README does not assert that a PyPI release has been published. See the [publishing checklist](https://github.com/giasonpooni/Notations-ClockSync/blob/main/docs/PUBLISHING.md).

| Interface | Identity |
|---|---|
| Distribution | `notations-clocksync` |
| Command | `clocksync` |
| Module command | `python -m tbrt` |
| Stable Python import | `tbrt` |
| Numerical operation | `tbrt.affine-clock-reconcile.v1` |
| Semantic capability | `time.sync.v1` — declared in `instrument.json`, not automatically registered in NET |
| License / copyright | MPL-2.0 / Bespoke Polymer Inc. |

## Instrument surface

ClockSync follows the Notation Systems instrument grammar:

```text
Problem → Inputs → Model → Computation → Output → Verification → Limits
```

The canonical machine-readable identity is [`instrument.json`](instrument.json).
The documented scientific specimen lives under [`portfolio/`](portfolio/);
[`notebooks/clocksync_demo.ipynb`](notebooks/clocksync_demo.ipynb) is a viewing
surface, not a second implementation. `scripts/build_instrument_surface.py`
regenerates the canonical input/output, refusal example, SVG diagnostics,
instrument card and `notations.verification.v1` report from the actual installed
package. CI retains those generated artifacts with the tested distributions.

The maturity label **INSTRUMENT** means tested API + examples + verification. It
does not claim that version 0.1.0 has been published to a package registry.

## Run a complete example

Python 3.11+ is required. From a reviewed source checkout:

```sh
python -m pip install .
clocksync --version
clocksync --example offset > clock-input.json
clocksync clock-input.json
```

The synthetic offset example produces `event_time = 203.25` seconds and `variance = 0.000005` seconds squared. `standard_uncertainty` is the square root of the variance, **not a guaranteed error bound or a confidence interval**.

Examples are shipped inside the wheel; a repository checkout is not needed after installation. `--example` emits a **request**, not a computed result. Three cases are included: `offset`, `drift`, and `correlated`.

```sh
clocksync --example correlated | clocksync - --compact
python -m tbrt --example drift
clocksync examples/clocksync.json
```

An approved wheel can also be installed directly with `python -m pip install path/to/notations_clocksync-0.1.0-py3-none-any.whl`. Use a clean virtual environment if migrating from the historical `time-base-reconciliation-runtime` distribution: both distributions own the `tbrt` import and should not be installed together.

## Numerical contract

With fixed anchors, the supplied model is

```text
t_ref = reference_origin + skew * (t_device - device_origin) + offset
J     = [skew, t_device - device_origin, 1]
var   = J @ joint_covariance @ J.T
```

Covariance coordinates are **`[device_time, skew, offset]`**, with units **`[s, 1, s]`**. All cross-covariance terms are retained. The result keeps `reference_origin` and `event_time_delta` separate. `event_time` is their rounded binary64 sum; it cannot recover precision already lost in the input.

```python
import numpy as np
from tbrt import AffineClockModel, ClockFrame, TimestampObservation, reconcile_time

source = ClockFrame("sensor-1", "device-monotonic")
reference = ClockFrame("reference-1", "reference-monotonic")
observation = TimestampObservation(103.0, source, evidence_id="observation-17")
model = AffineClockModel(
    model_id="clock-map-4", source_frame=source, reference_frame=reference,
    device_origin=100.0, reference_origin=1000.0,
    skew=1.00002, offset=0.0003, valid_device_interval=(100.0, 110.0),
)
result = reconcile_time(
    observation, model, np.diag([1e-6, 1e-10, 4e-6]),
    expected_reference=reference,
)
assert result.observation is observation
print(result.event_time, result.standard_uncertainty)
```

`from tbrt.cli import reconcile_payload` exposes the same JSON boundary as the CLI. Existing typed APIs and the numerical core are unchanged. Read the [JSON/CLI contract](https://github.com/giasonpooni/Notations-ClockSync/blob/main/docs/CLI.md) for field names, defaults, refusal behavior and exit codes.

## Retained information and refusal behavior

The result retains the observation, affine model, Jacobian, covariance and timing uncertainty. Receipt and knowledge timestamps remain separate metadata. The CLI additionally retains the requested destination and evidence-presence policy in `request_options`; it does not manufacture execution or verification identities.

Invalid numerical input, wrong destination identity, non-PSD covariance and nominal timestamps outside the model interval are refused. The JSON transport also rejects duplicate/unknown keys, non-finite constants, malformed objects, and string/boolean coercion of scientific inputs. Validation errors emit no result JSON.

`replay_reconciliation` recomputes a retained **typed** result without reading the clock. There is no CLI result-replay command: retain the request JSON alongside its output. Numerical replay and a content digest are not independent verification or authentication of source evidence.

## Optional SET exchange

The standalone command and numerical API require only NumPy. To use the existing source-pinned SET exchange adapter from a checkout:

```sh
python -m pip install '.[dev]' -r requirements-exchange.txt
python examples/exchange.py
```

The immutable SET pin remains `bd261a765281a95312f7c91a3857233476294c5b`. The Git requirement is deliberately outside published wheel metadata. The `exchange` extra is retained as an **empty compatibility marker**; `pip install '.[exchange]'` alone no longer installs SET. This migration is recorded in the changelog.

`tbrt.exchange.export_result` produces `notation.instrument.result-artifact.v1`, with separate evidence, operation, execution and result references. SET conformance is not NET registration, evidence admission or independent verification.

## Verify and build

```sh
python -m pip install '.[dev,release]'
python -m pytest
python examples/replay.py
python -m build
python -m twine check --strict dist/*
python scripts/check_release.py
python scripts/build_instrument_surface.py --output-dir instrument-evidence
python benchmarks/benchmark.py --iterations 10000
```

The release checker expects a clean `dist/` containing one wheel and one sdist. It checks metadata/license inclusion, installs the wheel in a fresh environment outside the checkout, rebuilds and installs the sdist, tests packaged examples/CLI, and writes `release-evidence.json` with source revision and SHA-256 digests.

CI tests installed packages on Linux (Python 3.11/3.12/3.13), Windows and macOS (Python 3.12), plus NumPy 1.24.0 and a separate pinned-exchange job. The distribution artifact is emitted only after these jobs pass. CI also emits the generated instrument surface and a benchmark observation. This is a software verification matrix, not validation of any physical synchronization system.

## Limits and stack ownership

Only supplied positive-skew affine maps and seconds-valued coordinates are supported. Both anchors are fixed. Domain checks apply to the nominal timestamp, not the entire uncertainty distribution. With uncertain skew and timestamp, propagation is first order; it does not provide the exact transformed distribution or mean.

ClockSync does **not** fit models, implement NTP/PTP/GNSS protocols, convert UTC/TAI/leap seconds, set device clocks, resample streams, infer missing timestamps, authenticate evidence, admit state or actuate equipment. Time-scale strings identify frames; they do not activate a conversion algorithm.

NET owns composition and dispatch. ClockSync remains an independently usable numerical provider. ESM keeps evidence admission and canonical-state authority. No live workbench, acquisition or device-control adapter is installed by this release.

[Operation contract](https://github.com/giasonpooni/Notations-ClockSync/blob/main/docs/CONTRACT.md) · [Numerics](https://github.com/giasonpooni/Notations-ClockSync/blob/main/docs/NUMERICS.md) · [Stack role](https://github.com/giasonpooni/Notations-ClockSync/blob/main/docs/STACK_ROLE.md) · [Portfolio specimen](portfolio/problem.md) · [Changelog](https://github.com/giasonpooni/Notations-ClockSync/blob/main/CHANGELOG.md) · [License](https://github.com/giasonpooni/Notations-ClockSync/blob/main/LICENSE)
