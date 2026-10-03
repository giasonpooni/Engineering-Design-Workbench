# DSP instrument through the original NET workbench

For the additive Python/SciPy signal-conditioning pipeline and synthetic
pump diagnostics, see [DSP_PIPELINE.md](DSP_PIPELINE.md). This document describes
the original native FIR interface, whose operation and contracts remain intact.

The first DSP instrument is a caller-owned causal FIR filter in the existing
Scientific Computation Runtime (SCR). NET retains the original Session,
OperationRegistry, CapabilityRegistry, graph runner and observation format.
No filtering algorithm, alternate numerical runtime or evidence authority is
added to NET. The existing oscillator periodogram and bounded Julia-to-C
oscillator exporter/native consumers are unchanged.

## A compiler for contracts, not arbitrary language source

SCR's `tools/instrument_bindings.py` translates one bounded buffer-operation
contract into native C/C++, Python, Rust and Julia interfaces. All four languages
can call the same compiled instrument directly; Python/NET need not sit inside
an application or real-time processing loop. This does not compile arbitrary
Julia/Python/Rust/C++ programs into one another. Native ABI exposure also does
not eliminate a language runtime required by an implementation.

`src/ciw/dsp_abi.py` is exactly the compiler's generated Python binding. The
cross-repository CI regenerates it from the pinned source and requires byte
identity. It contains buffer/type/identity handling, not FIR mathematics.
For the compiler, native wrappers, numerical oracle and complete four-language
qualification, see SCR `docs/DSP_INSTRUMENT.md` and its DSP PR #11.

## Build the instrument, then bind it explicitly

NET feature base: game-project production PR #67; this increment is additive.
SCR source: branch `feat/dsp-instrument-bindings-v1-20260929`, pinned revision
`91a6d3b37f28623332acd485e9f8a12953acf71e`. Existing providers and runtime pins
are not upgraded. First native target is Linux x86-64 with g++ and binary64.

From a checkout of that SCR revision:

```sh
python tools/instrument_bindings.py instruments/dsp/interface.json --output-dir build/dsp-bindings
g++ -std=c++17 -O2 -shared -fPIC -fno-fast-math -ffp-contract=off \
  -I build/dsp-bindings instruments/dsp/fir.cpp -o build/libscr_dsp.so
sha256sum build/libscr_dsp.so
```

From this NET feature checkout:

```sh
python -m pip install -e '.[dev]'
net dsp demo --library /absolute/path/SCR/build/libscr_dsp.so \
  --library-sha256 sha256:REPLACE_WITH_EXACT_BINARY_DIGEST \
  --output-dir results/dsp-001
net dsp inspect results/dsp-001/workspace.json
```

Use a new output directory for every execution. The demo filters the original
synthetic oscillator's 768 retained position samples using `[0.25,0.5,0.25]`
and explicitly declared pre-recording history `[0,0]`. It is not measured sensor
evidence. One ordinary operation/execution/result is retained plus the existing
graph-run and typed observation stream. No formal verification or state admission
occurs. Inspecting a workspace does not require SCR or a native library.

## Filter a retained channel

```sh
net dsp run --source /absolute/path/recording.json --channel acceleration \
  --interval 0 1 --taps /absolute/path/taps.json \
  --initial-history /absolute/path/history.json --clock-id rig-01/sample-clock \
  --semantics estimated --library /absolute/path/SCR/build/libscr_dsp.so \
  --library-sha256 sha256:REPLACE_WITH_EXACT_BINARY_DIGEST \
  --output-dir results/filtered-001
```

`taps.json` and `history.json` are plain JSON arrays. The operation ID is
`signal.filter.fir.v1`; Python users explicitly construct `ciw.dsp.FirBinding`
and bind its `operation()` or use `ciw.dsp.registry(binding)` with the existing
Session/graph runner. No default provider discovery or dynamic import is driven
by a saved work order. The operator supplies the binary path and its trusted hash.

The example channel, interval and clock must correspond to the actual recording;
NET does not infer acquisition, calibration or clock synchronization from a label.
Native libraries are trusted executable code, not a sandbox. Keep build/library
paths in stable operator-controlled storage. Hash checks are content-drift checks,
not compiler correctness, full shared-library attestation or hostile-race protection.

## Signal and state contract

The first profile accepts 1..64 dimensionless taps and 1..4096 selected samples
from a source with an explicit positive sample rate. Sampling intervals must agree
with that rate under the declared numerical time-grid check. Irregular timing,
gaps, unknown sample rate, and null/nonfinite required samples refuse; no implicit
resampling, interpolation or zero-fill is performed.

Initial history contains exactly M-1 samples preceding the start of the recording,
oldest first. Later time selections derive the needed predecessors from that same
retained recording, using the initial history only where required. Selecting a
new interval does not silently reset filter state. Missing data outside the
required support is not manufactured or unnecessarily used. The native callable
also returns final history for application-owned streaming between buffers.

The output retains source evidence, selected sample indices/times, quantity unit,
frame, declared clock, tap and initialization digests, history used and final
history. Unit/frame labels are preserved, not converted. Sample timestamps are
not shifted to conceal phase delay. Output is causal and uncompensated; general
group delay is not estimated. No general anti-aliasing property follows just from
using an FIR filter; it depends on the chosen coefficients and sampling model.

Filtering can introduce temporal correlations. The original source remains
unchanged; its uncertainty is not copied into output covariance as though the
samples were independent. `uncertainty_propagation` is explicitly `not_performed`.
No PSD, IIR, STFT, resampling, reconstruction, detector, sensor fusion or physical
calibration is implemented by this first filtering operation.

## Verification and retention

The specialist's native gate checks Python/C++/Rust/Julia access, caller-owned
history, whole-versus-chunk equivalence, and independent exact-rational/256-bit
Julia convolution. Agreement between callers sharing one library checks the ABI;
it is not four independent numerical implementations.

NET's saved-payload reader validates source bindings, dimensions, history, units,
clock and claim scope without loading a provider. This is deliberately labelled
**structural/source validation, not numerical verification**. A retained output
cannot acquire a formal verification identity or state-admission claim by hashing
itself. Explicit numerical comparisons use the existing typed comparator.

Run the focused native-bound NET tests:

```sh
CIW_REQUIRE_DSP_NATIVE=1 SCR_DSP_LIBRARY=/absolute/path/libscr_dsp.so python -m pytest -q tests/test_dsp.py
```

The dedicated NET workflow compiles the pinned SCR kernel, checks regenerated
binding identity, runs new plus unchanged game/controller/production tests, then
repeats the new tests and real Session demo using an installed wheel outside the
source checkout. Dedicated qualification sets `CIW_REQUIRE_DSP_NATIVE=1` and
rejects missing setup and all skipped cases. Ordinary provider-free test runs
explicitly skip optional native cases rather than requiring an installed kernel.
Generated records, JUnit, wheel, exact NET source and native build are retained.

Qualification is scoped to actual reports and revisions, not the presence of
this guide. No 10kHz guarantee, frame deadline, GPU/SIMD acceleration, Windows or
macOS native profile, physical equipment operation, release or autonomous coding
agent is claimed. Existing unrelated private-provider gates remain independent.
