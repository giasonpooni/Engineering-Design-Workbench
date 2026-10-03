# Qualified multiscale fluid testbed

The fluid catalog is additive: `reservoir` and `wave` retain their existing
contracts. `molecular`, `sph`, and `fsi` supply their own state, clocks,
hard domains, independent references, and numerical qualification reports.
Saved workspaces never select arbitrary installed code or replay a provider.
Every fresh verification uses a new Session operation occurrence; CSV export
and particle reduction require fresh `LOCAL` numerical qualification.

| Profile | Particle or state meaning | Qualified dynamic scope | Reference and checks |
| --- | --- | --- | --- |
| Reservoir | Continuum exchange volume, flow, heads, linear piston | Two reservoirs with hydraulic inertia/resistance and a preloaded spring/mass/damper boundary | Independent continuous linear system; mass, energy, work, and time refinement |
| Wave | Cell surface elevation and face depth-averaged velocity | Periodic one-dimensional, uniform-depth linear surface gravity waves | Continuous Fourier solution; time/space refinement, mass and energy |
| Molecular | Structureless atomistic interaction sites | Periodic three-dimensional force-shifted 12–6 Lennard–Jones dynamics in reduced units | Separately derived scalar pair forces and high-resolution RK4; force/potential gradient, momentum, energy and Verlet refinement |
| SPH | Equal-mass computational parcels of continuum fluid | Periodic one-dimensional weakly compressible SPH with fixed smoothing length and a linear barotropic equation of state | Separately derived kernel and RK4; Hamiltonian gradient, acoustic reference, mass/momentum/energy and time/space refinement |
| FSI | Resolved horizontal gravity-wave field and one compliant wall | Linear shallow-water channel coupled synchronously to an undamped, preloaded spring/mass wall | Independent continuous coupled eigenmode; reconstructed physical pressure, mass, force, opposite interface work, total energy and time/space refinement |

A molecular interaction site is not a water molecule. An SPH parcel is not a
grain or atom. SPH acoustic pressure waves and FSI surface gravity waves have
different governing models. A numerical PASS establishes the declared checks
for the finite synthetic trajectory; it does not establish experimental validity.

## Run and retain a trajectory

```sh
net fluid example --profile molecular --output molecular.json
net fluid run --request molecular.json --output-dir molecular-run
net fluid inspect molecular-run
net fluid verify molecular-run --output molecular-fresh.json
net fluid export-csv molecular-run --output molecular.csv

net fluid example --profile sph --output sph.json
net fluid run --request sph.json --output-dir sph-run
net fluid verify sph-run --output sph-fresh.json

net fluid example --profile fsi --output fsi.json
net fluid run --request fsi.json --output-dir fsi-run
net fluid verify fsi-run --output fsi-fresh.json
net fluid export-csv fsi-run --output fsi.csv
```

Outputs are create-only. Unsupported observables request `EXPAND`; failed
checks or contradictory declarations cause `REFUSE`. A receipt is not canonical
state admission or hardware authority. Existing reservoir snapshot handoff stays
limited to its declared simulated-state semantics.

## Qualified instantaneous scale arrows

```sh
net fluid reduce molecular-run --sample-index 0 --bins 2 2 2 --output molecular-bins.json
net fluid reduce sph-run --sample-index 0 --bins 4 --output sph-bins.json
```

Each reduction first freshly verifies its source, binds one exact retained
sample, and independently audits the finite map. The bin map conserves total
mass and momentum. It records mean-motion kinetic energy and the kinetic energy
discarded within bins separately. Empty bins have an undefined mean velocity.
It discards individual identities, subcell positions, pair correlations, force
laws, pressure tensors and temporal evolution. It supplies no constitutive
closure, viscosity, thermal conductivity or validated LJ-to-water conversion.
Optional molecular SI scales must be declared explicitly and retain their
uncalibrated status. Reduced-unit density is never silently labeled kg/m³.

## CFD–structure interface contract

`ciw.fluid_coupling` provides a reusable bounded SI interface map. Fluid face
centroids, structural nodes, areas, normals, frame and traction orientation are
explicit. Its interpolation matrix reproduces constant translations and linear
coordinates. Face displacement and velocity use the same matrix; structural
force uses its area-weighted transpose. This preserves resultant force, moment
and virtual work. Declared traction covariance propagates through the same force
map. Independent audits check the actual fields, equal opposite reactions,
power, geometry and clock synchronization.

```sh
net fluid coupling template --output interface.json
net fluid coupling run --request interface.json --output-dir interface-run
net fluid coupling inspect interface-run
net fluid coupling verify interface-run --output interface-fresh.json
```

The retained port workflow records distinct evidence, transfer, execution,
result and verification identities. Input content references for external
solver outputs remain declared references; they do not authenticate or execute
those solvers. Static inspection activates no transfer or verification provider.

This qualifies an interface operation, not an arbitrary external solver.
Each external CFD or structure adapter needs its own model validity, temporal
integration, convergence, boundary and empirical evidence before its assembled
investigation can be qualified. The `fsi` profile supplies an executable
wave/structure example with a continuous reference. Its boundary-face liquid
half-cell inertia belongs to fluid energy; reconstructed boundary pressure
drives the physical wall force. Nonzero wall damping, breaking waves, turbulence,
three-dimensional flow and nonlinear structures require additional providers.

## Experimental evidence path

```sh
net fluid experiment template --profile reservoir --output experiment-template.json
net fluid experiment ingest --csv observations.csv --metadata metadata.json --output-dir measurements
net fluid experiment compare --model-dir reservoir-run --measurement-dir measurements --output-dir comparison
net fluid experiment inspect comparison
net fluid experiment verify comparison --output comparison-fresh.json
```

The template contains metadata and an exact CSV header; extract and complete
the metadata before ingestion. The current observation operator accepts declared
SI reservoir state channels. File hashes, frame, equilibrium baseline, target
request, calibration references, acquisition provenance, clock alignment and
held-out sample identities are required. Declared calibration and fitting
dataset, sample and content-reference overlaps are refused. Hidden reuse with
new identities cannot be authenticated from these supplied files.

Comparison uses full stacked covariance, including correlated uncertainty from
a shared clock offset. Measurement, parameter prediction, model discrepancy and
numerical/interpolation uncertainty remain separately declared. Gaussian
compatibility is conditional on those declarations; missing or singular evidence
is inconclusive. Synthetic fixtures always remain synthetic. Operator-declared
measured data can support a domain-limited empirical compatibility result, not
sensor authentication, universal physical validation or causal inference.
No measured tank data accompanies this implementation.

See [experimental protocol](FLUID_EXPERIMENTS.md),
[atomistic provider](FLUID_MOLECULAR_PROVIDER.md),
[SPH provider](FLUID_SPH_PROVIDER.md),
[wave–structure and coupling providers](FLUID_FSI_PROVIDER.md), and
[original continuum providers](FLUID_DYNAMICS.md) for exact limits and formulas.

## Qualification

Run `python -m pytest -q tests/test_fluid*.py`. The dedicated Linux/Windows
workflow also tests the existing operation and preservation substrate, builds a
wheel, and exercises the installed CLI outside the source checkout. Retained
qualification records identify the tested commit/tree and keep numerical,
empirical, admission and execution claims separate.
