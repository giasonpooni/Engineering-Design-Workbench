# Reaction kinetics benchmark

This profile compares two genuine numerical providers through the existing SCR
host and `ciw.native-interop.v1` operation: Catalyst with Tsit5, and Cantera with
CVODES. It describes **abstract model species**, not an experimentally validated
chemical mechanism. Local package provisioning and qualified runtime bindings are
required; a reference-only test pass does not qualify either engine.
Exact pins, completed tests and remaining gates are recorded in the
[validation report](REACTION_BENCHMARK_VALIDATION.md).

## Fixed model, variable state

The model is a closed, homogeneous, fixed-volume, isothermal first-order reaction:

$$
A \longrightarrow B,\qquad \dot c_A=-k c_A,\quad \dot c_B=k c_A.
$$

The continuous state is `(c_A, c_B)`. For a fixed initial total, its permitted
variation satisfies `delta c_A + delta c_B = 0`. Nonnegative concentration adds a
boundary: this entire admissible set is not an unrestricted smooth manifold.
Adding a species or changing the mechanism is a configuration change outside this
profile. Reordering the two species is a lossless representation change and must
reorder both initial conditions and returned arrays. Total concentration alone
cannot represent reaction progress.

A and B are mathematical gas species with identical elemental composition `H:1`,
zero charge, and identical constant heat capacity. The declared reference is
300 K, zero reference enthalpy and entropy, and
`cp0 = 20786.156545383 J/(kmol K)`, with a 200–1000 K thermodynamic range.
This artificial equal-property closure makes the engines comparable without
asserting real hydrogen chemistry. Temperature is prescribed, volume is fixed,
and no flow, walls, heat transfer or temperature evolution is modelled.

The interface uses **mol/m³**, **mol/m³/s**, seconds, kelvin and cubic metres.
Cantera's native kmol basis is converted explicitly. Concentrations and production
rates are time-major arrays in the declared species order. The frame is a
homogeneous control volume and the clock is declared simulation time; these are
not acquisition timestamps or spatially resolved measurements.

## Domain and checks

The allowlist contains only `reaction-a-to-b.v1` with binary64 arithmetic. Requests
contain data, never equations, package names or executable paths. The domain is:

- Two nonnegative initial concentrations, total between `1e-6` and `1000 mol/m³`.
- `0 <= k <= 10 s^-1`, 250–500 K, `1e-6 <= volume <= 1 m³`.
- 2–128 strictly increasing times beginning at zero, final time at most 100 s,
  and `k * final_time <= 30`.
- Fixed solver tolerances `reltol=1e-9`, `abstol_mol_m3=1e-11`; an explicit
  step budget from 1 to 100000. Solver failure refuses a result.

The independent Python reference uses `exp(-kt)` for reactant concentration and
`-expm1(-kt)` for product growth. It checks the full sampled trajectory and each
provider's own rate evaluator. It separately records conservation error and the
minimum unmodified concentration. Negative values are not silently clipped.
Numerical comparison uses the existing native policy, absolute and relative
`tolerance=2e-8`; it establishes agreement within that policy, not exact equality.
For this profile, the common `max_abs_discrepancy` field reports concentration
error in mol/m³. Rate-law and conservation discrepancies have separate named
metrics; the cross-engine report likewise keeps concentration and rate errors
separate. Their numerical values are not combined into a unitless physical score.
The small allowed numerical negativity is not a claim of physically admissible
negative concentration.

Conservation alone is insufficient: the tests deliberately reject a wrong-rate
trajectory that preserves the same total. Zero rate, absent reactant, initial
product, irregular sampling and species permutation are explicit fixtures.
Catalyst conversion declares `combinatoric_ratelaws=false`; this first-order case
alone cannot test factorial differences in higher-order reaction conventions.

## Retention and replay

Both providers retain exact framed request/response bytes, mechanism bytes,
worker/environment hashes, package versions and SCR commitments. A numerical
content identity remains separate from each execution and result occurrence.
Fresh reproduction runs the provider again and compares it with the independent
reference. It does not create a physical measurement or an SP1 proof.

The existing workspace format and native operation own the records. Reopening
validates retained bindings without launching a provider or rerunning the oracle.
Replay requires the original qualified runtime and creates fresh occurrences.
Uncertainty is **not declared**; calibration is **not applicable** to this
mathematical reference. State admission and hardware actuation are not performed.
The manual `Reaction benchmark qualification` CI workflow provisions locked
environments and runs the installed-wheel gate on Windows. It fails if the
installation differs from the checked-in qualification; adding a new platform
requires review, not automatic pin replacement. A workflow definition alone is
not evidence of a successful CI run.

Host hashes identify bytes; source-to-binary and complete installed-environment
attestation remain explicitly unestablished.

## Operator commands

The current qualification is Windows x86-64 with Julia 1.10.12 and managed
Python 3.12.14. The exact environment is in
[Project.toml](../runtimes/reaction-kinetics/Project.toml),
[Manifest.toml](../runtimes/reaction-kinetics/Manifest.toml) and the
[hash-locked Cantera requirements](../runtimes/cantera-reaction/requirements.txt).
Provision these outside live execution; the workers never install packages.
For example, with those executables and uv 0.10.10 already available:

```powershell
$env:JULIA_DEPOT_PATH = 'C:/ciw-runtimes/reaction-julia-depot'
julia --startup-file=no --project=runtimes/reaction-kinetics -e 'using Pkg; Pkg.instantiate(); Pkg.precompile()'
uv venv --python 3.12.14 C:/ciw-runtimes/cantera
uv pip sync --python C:/ciw-runtimes/cantera/Scripts/python.exe --require-hashes runtimes/cantera-reaction/requirements.txt
```

First Julia precompilation is separate from solver execution and may be lengthy.
Provision the SCR host using its [native build guide](NATIVE_INTEROP.md).
A different executable or package fingerprint requires separate qualification;
the operator binding does not override the checked-in worker pins.

Create operator bindings for each provider. Each JSON file supplies `scr`,
`host`, `host_sha256`, `provider`, `executable`, and `runtime`. `runtime` points to
the PDT checkout containing its exact qualified runtime files. Catalyst also
requires `depot`. Paths are operator configuration and are not accepted from an
experiment payload. Cantera must use its isolated, locked Python environment.

From an environment with the CIW wheel installed:

```sh
python scripts/check_reaction_benchmark.py run \
  --catalyst /path/to/catalyst-binding.json \
  --cantera /path/to/cantera-binding.json \
  --fixtures examples/reaction-benchmark/fixtures.json \
  --output /path/to/new-reaction-run
python scripts/check_reaction_benchmark.py inspect \
  --workspace /path/to/new-reaction-run/workspace.json \
  --artifacts /path/to/new-inspection-artifacts
```

The output directory must be new. The gate saves completed history even if a
later case fails. Its report links individual retained engine results, the
cross-engine comparisons, fresh replay and provider-free reopen. Inspect reports
retained checks; it does not assert that they were rerun.

This bounded profile is not a generic mechanism importer, stiff-chemistry
qualification, thermodynamic coupling interface, chemical sensor calibration,
or physical validation. Those require separate declared profiles and evidence.

The engine conventions are documented by
[Catalyst](https://docs.sciml.ai/Catalyst/stable/) and
[Cantera](https://cantera.org/3.2/python/kinetics.html).

## Consolidation boundary and next dependency

This increment adds a bounded execution profile to the existing native operation;
it does not yet implement the proposed general domain-profile registry or a typed
investigation planner. No standalone chemistry repository or parallel evidence
store is introduced. The reusable requirements established here are explicit
model family, state/parameter domain, species-order transformations, units,
provider capabilities, numerical checks and retained provenance.

A later registry should select host-approved capabilities from data-only profiles.
A later composition graph must distinguish lossless species reordering from
coupling this concentration model to an energy balance. In particular, this
artificial equal-enthalpy model is not a heat-generation source: chemical–thermal
feedback needs a new thermochemical model and coupling validation. OpenUSD,
general asynchronous fusion, generic ESM admission and physical actuation remain
separate work with their own contracts and gates.
