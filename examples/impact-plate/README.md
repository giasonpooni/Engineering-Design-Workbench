# Impact plate example

This example extends NET's contact workloads to a spatial, elastic rectangular
plate using a retained sine-mode representation. An initially resting,
isotropic plate is simply supported on all four edges. A rigid striker mass
loads a fixed finite rectangular patch through a massless compression-only
spring. It uses the original Session and typed preservation substrate.

With NET installed:

```sh
net impact plate example --output impact-plate-request.json
net impact plate run impact-plate-request.json --output-dir impact-plate-run
net impact plate inspect impact-plate-run
net impact plate verify impact-plate-run
net impact plate export impact-plate-run --output impact-plate-observations.csv
net impact plate field impact-plate-run --time-index 512 --output impact-plate-field.json
```

The generated request schema is `ciw.impact-plate-request.v1`, with scope
`simply_supported_kirchhoff_love_plate_patch_contact` and contact law
`compression_only_linear_patch_spring`. Its default plate is
`0.2 m × 0.2 m × 0.003 m`, with `E = 2e9 Pa`, `nu = 0.35` and
`rho = 1200 kg/m³`. A centred `0.02 m × 0.02 m` patch receives the spring load.
Striker mass is `1 kg`, contact stiffness `10000 N/m` and initial speed
`0.03 m/s`. The initial energy is `0.00045 J`.

Integration uses `velocity_verlet`, a primary `3 × 3` basis, 1024 nominal
contact steps and `duration_factor: 1.5`. Temporal refinement halves the timestep
in the same basis; spatial refinement uses `5 × 5` modes at the half timestep.
The nominal timestep is approximately `3.06796e-5 s` and the retained horizon
is approximately `0.0471239 s`. Actual release is determined from the relative
spring gap, rather than assumed equal to the nominal contact scale. Default
tolerances are `0.001`, except `momentum_relative: 1e-10` and
`spatial_refinement_normalized: 0.02`.

The generated request contains the exact geometry, material constants, patch,
striker, timestep, mode counts, observables and tolerances. Striker motion and
plate bending modes evolve numerically; independent verification compares
against an active-contact spectral reference, contact release, energy/impulse
accounting and both timestep and mode refinement. A complete independent report
has 105 checks, including common modal histories and a conservative spatial
bound on the difference between finite-basis displacement fields. The field
comparison detects modal changes hidden by cancellation in the patch average;
it does not establish continuum convergence.

The spring acts through the patch-average plate displacement. The same patch
couplings transfer force into the modes, preserving the displacement/force
work pairing. This is an effective uniform-pressure contact model; it does not
resolve local punch contact, indentation hardness or a three-dimensional
contact stress field.

Striker energy can remain in plate vibration after release, reducing striker
restitution even though the whole model is elastic. The ledger distinguishes
striker kinetic energy, plate kinetic/bending energy and recoverable contact
spring energy. Remaining plate vibration is not plastic work or measured
fracture absorption. Fixed supports exchange momentum while doing no work.

`inspect` checks retained records without numerical replay. `verify` recomputes
independent checks from retained observations without rerunning the solver,
replaying operation executions or modifying the run. Verification and exports
use one validated snapshot of the retained candidate. Export requires fresh
LOCAL qualification and creates a new file. Out-of-domain trajectories, unsupported desired properties and unverified
histories must not be exported as qualified output.

`field` evaluates the retained primary sine modes at a selected recorded
`--time-index` after fresh verification. It creates a sealed
`ciw.impact-plate-field.v1` JSON file with a default `17 × 17` spatial query grid,
geometry, modal amplitudes and exact evidence/result/execution/verification
references. `--grid-size` accepts odd integers `3..33`. Increasing this query
grid changes only spatial evaluation; it does not refine the underlying modal
dynamics. It performs no interpolation in time or stress/damage reconstruction.

The runtime deflection/thickness and slope bounds must each be at most `0.1`.
`plate_peak_deflection_m` is the recorded maximum of `sum(abs(q_mn))`, a
conservative global spatial bound, rather than the actual peak at a mesh point.
`plate_contact_peak_deflection_m` concerns the patch-average displacement.
The request guards both high-mode thickness-wavenumber (`<= 0.35`) and a
conservative active-contact timestep-frequency product (`<= 0.5`). These guards
do not replace independent accuracy and refinement checks.

This specimen is a synthetic small-deflection Kirchhoff-Love benchmark. Material
constants have no experimental calibration lineage. The model has no damping,
viscoelasticity, plasticity, membrane stiffening, fracture, thermal state or
molecular damage. Its finite patch and retained modes must be included in every
qualified claim. Existing elastic and crush profiles keep their own contracts.

See [the plate benchmark contract](../../docs/IMPACT_PLATE_BENCHMARK.md) for the
equations, numerical/reference split, validity limits and physical validation
path.
