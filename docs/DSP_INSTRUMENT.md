# DSP instrument and four-language interface compiler

This is an optional instrument in the existing Scientific Computation Runtime,
not another runtime, terminal, dispatcher or evidence store. The new causal FIR
kernel is owned by SCR. NET binds it through its original Session/operations.
All pre-existing SCR execution hosts, Julia providers, native workloads and pins
remain unchanged. No mandatory runtime dependency is introduced.

## One contract, four native callers

`tools/instrument_bindings.py` translates `scr.native-buffer-interface.v1` into:

| Generated artifact | Native interface |
| --- | --- |
| `scr_dsp.h` / `scr_dsp.hpp` | C ABI declarations and checked C++ vector wrapper |
| `scr_dsp.py` | Python ctypes wrapper; explicit library and binary digest |
| `scr_dsp.rs` | Rust slice-to-buffer wrapper over the same linked library |
| `scr_dsp.jl` | Julia Vector/ccall wrapper; explicit library and binary digest |

The compiler handles 1..16 functions with bounded binary64 input buffers,
caller-owned output buffers whose lengths reference input buffers, explicit
length arguments, int32 status, ABI version and a canonical-contract digest.
Unknown fields/types, unsafe names, unsupported shapes and unbounded buffers
refuse. The generated wrappers contain no filtering mathematics.

This is **contract translation and binding generation**, not arbitrary
Julia/Python/Rust/C++ source translation. It creates no universal AST, new
numerical compiler backend or hidden language-to-language RPC. The earlier
bounded Julia-to-C oscillator exporter remains unchanged. A Julia function
exposed with `@cfunction` may still require the Julia runtime; sharing an ABI
does not automatically produce a runtime-free compiled library.

```sh
python tools/instrument_bindings.py instruments/dsp/interface.json --output-dir build/dsp-bindings
g++ -std=c++17 -O2 -fPIC -shared -fno-fast-math -ffp-contract=off \
  -I build/dsp-bindings instruments/dsp/fir.cpp -o build/libscr_dsp.so
```

Use a new bindings directory. Importing generated Python/Julia source does not
load a provider. Python and Julia explicitly bind a trusted library by binary
hash; C++ and Rust link a trusted build. Every wrapper checks the ABI/contract.
Digests detect content drift; they do not authenticate a compiler or make native
code safe. Valid aligned live buffers remain a C-caller obligation. Use trusted,
stable executable directories; no hostile filesystem-race or OS-sandbox claim.

## First scientific operation: causal FIR

`y[n] = sum(taps[k] * x[n-k], k=0..M-1)`.

The kernel accepts 1..64 dimensionless taps, 1..4096 samples and exactly M-1
prior input samples, ordered oldest to newest. It returns N filtered samples and
the M-1 most recent input samples. History is explicit: initialization is never
silently inferred, and independent caller streams do not share state. Processing
successive chunks with returned history must agree with whole-block processing.
The caller owns all state, buffers and memory. The kernel allocates no heap,
retains no pointers, owns no clock and starts no thread.

Status codes: 0 success; 1 null pointer; 2 invalid lengths; 3 nonfinite input;
4 nonfinite output; 5 overlapping output buffers/address-range overflow;
6 non-nearest rounding mode. Wrappers separately refuse ABI/contract mismatch.
Nonzero status leaves output and next-history buffers unchanged. Input/output
aliasing is supported because all inputs are consumed before outputs commit;
the two output ranges must not overlap. IEEE binary64, nearest rounding,
no fast-math and disabled contraction are part of the first build profile.

No filter design, IIR, FFT, PSD, STFT, resampling, anti-aliasing guarantee,
reconstruction or detector is claimed here. The existing NET oscillator
periodogram remains unchanged. FIR is the first streaming-state and language
interop qualification target, not an implementation of the entire DSP family.

Filtering is causal, not zero-phase. Its frequency-dependent phase/group delay
is not silently removed. The native kernel uses sample indices; NET additionally
requires declared sample timing, units, frames and complete required samples.
Input uncertainty is not automatically inherited as output covariance: filtering
can introduce temporal dependence. Calibration, covariance propagation and
physical interpretation require separate explicitly qualified operations.

## Build and qualify

```sh
python -m pytest -q --confcutdir=instruments/dsp instruments/dsp/test_dsp.py
python instruments/dsp/qualify.py --cxx /path/to/g++ \
  --rustc /path/to/rustc --julia /path/to/julia --output-dir results/dsp-001
```

The initial profile is Linux x86-64. The dedicated workflow selects Python3.12,
Julia1.10.12 and Rust1.90.0; actual tool hashes/versions, commands, flags, inputs,
outputs, generated interfaces and source hashes are retained. Windows/macOS,
GPU/SIMD acceleration and real-time deadlines are not qualified by that run.

The nine-case corpus contains 4,492 signal samples, maximum/short histories,
asymmetric coefficients, nonzero initialization, an impulse and a Nyquist-null
case. Each language calls the actual shared native library and checks whole
versus split processing. Python exact-rational convolution and Julia 256-bit
convolution are independent reference calculations. Native-caller agreement
alone is ABI evidence, not independent mathematical verification.

The comparison policy is fixed at abs(error) <= 1e-12 + 1e-12*abs(reference),
for this bounded synthetic corpus. This is not a global error bound for all
finite binary64 inputs. Overflow/nonfinite results refuse. Missing Julia/Rust
produces an **incomplete** report and exit3; no fallback pretends they ran.

Generated files can be reused in native projects without running NET/Python in
their processing loop. The NET adapter retains ordinary execution/result records
and typed observations; it does not automatically admit state, authorize
hardware, certify a filter, or create a formal verification occurrence.

## References

Julia C interop: https://docs.julialang.org/en/v1/manual/calling-c-and-fortran-code/
Rust FFI: https://doc.rust-lang.org/nomicon/ffi.html
DSP filter state/background: https://docs.juliadsp.org/stable/filters/
Filtering reference: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.lfilter.html
These references motivate interface conventions; their packages are not new
mandatory dependencies or copied numerical implementations.
