# Qualified fluid dynamics

The `net fluid` instrument adds **time-dependent model execution and independent
numerical checks** to the existing Terminal. The original FlowState snapshot
estimator, its imported tree, operation versions, runtime pin, observation
covariance and guarded reconstruction behavior remain unchanged.

## Model boundaries

| Profile | Retained state | Governing scope | Discarded information |
| --- | --- | --- | --- |
| Reservoir | Exchange volume and flow, two free-surface heads, pressure, connector velocity, compliant-boundary displacement and velocity, energy and interface work | Linear incompressible liquid exchange with hydraulic inertia/resistance and a linear compliant boundary about a balanced equilibrium | Resolved connector field, compressibility, acoustic water hammer, vortex structure, nonlinear losses, geometry changes beyond piston swept volume |
| Wave | Surface elevation at cells, velocity/volume flux at faces, hydrostatic bottom pressure, volume and energy on a declared periodic grid | One-dimensional, uniform-depth, small-amplitude, long-wavelength linear surface gravity waves | Vertical velocity/shear, dispersion beyond shallow-water approximation, viscosity, breaking, wetting/drying and open-boundary reflections |

The wave profile and the reservoir profile are independently qualified models.
The additive [multiscale catalog](FLUID_MULTISCALE.md) supplies separate atomistic,
SPH and resolved wave–wall providers, explicit particle reductions, a generic SI
coupling interface and an experimental-data comparison path. There is no hidden
wave-to-reservoir interface or automatic parameter inference. The reservoir's
compliant boundary is this profile's bidirectional fluid–structure interface.
Its structure is a spring/mass/damper degree of freedom, not a resolved plate or
nonlinear polymer constitutive law. An incompressible connector slug is a lumped
continuum state; it is not an SPH particle, suspended grain or molecule.

## Reservoir equations and coupling

Let `r` be cumulative liquid volume transferred from reservoir 1 to reservoir 2,
`Q` its derivative, `x` an outward piston displacement, and `v` its derivative.
For reservoir surface areas `A1,A2` and piston area `ap`, perturbation heads are

```math
h_1=-r/A_1,\qquad h_2=(r-a_p x)/A_2.
```

The connector hydraulic inertance is `I=rho*L/ac` and its resistance is `R`.
The bidirectional model is

```math
\dot r=Q,\quad I\dot Q=\rho g(h_1-h_2)-RQ,\quad
\dot x=v,\quad m\dot v=a_p\rho g h_2-kx-cv.
```

Equilibrium pressure is balanced by a declared preload; the structure receives
the pressure **perturbation**. Piston motion changes reservoir 2's available
volume and therefore its head, which changes flow and subsequent loading.
Equilibrium free surfaces share a horizontal datum; different equilibrium
depths represent different bottom levels. Liquid volume includes the connector
inventory and swept volume `ap*x`. Interface power into the
structure is `rho*g*h2*ap*v`, with equal negative work on the fluid.

```math
E=\tfrac12\rho g(A_1h_1^2+A_2h_2^2)+\tfrac12 IQ^2
  +\tfrac12 mv^2+\tfrac12 kx^2,\qquad
\dot E=-RQ^2-cv^2.
```

The initial head displacement supplies the exchange pulse. The model is
unforced. Nonnegative resistance and damping make the initial energy a bound on
later excursions; hard validity limits apply independently of user tolerances.

## Wave equations

For fixed depth `H`, perturbation elevation `eta` and depth-averaged velocity
`u`, the declared linear equations are

```math
\eta_t+H u_x=0,\qquad u_t+g\eta_x=0,\qquad c_0=\sqrt{gH}.
```

The input pulse is a finite Fourier superposition. The reference propagates
those modes analytically. Elevation and hydrostatic bottom pressure use cell
coordinates; velocity and volume flux use face coordinates. These distinct
locations remain explicit in retained arrays and CSV output. The pressure
includes the equilibrium hydrostatic component; it is not an acoustic wave.
Volume flux is the linear quantity `width*H*u`; the nonlinear `eta*u` term is
outside this profile. Mechanical energy is linear perturbation energy, excluding
the resting liquid's gravitational baseline. The smooth zero-mean three-mode
pulse is periodic and is not an isolated open-domain surge.

The [Clawpack shallow-water derivation](https://www.clawpack.org/riemann_book/html/Shallow_water.html)
explains the depth-averaged hydrostatic approximation and characteristic speeds.
This instrument uses the linear uniform-depth specialization and does not claim
Clawpack's nonlinear shock or inundation capabilities.

## Qualification and identities

Both solvers use bounded binary64 computation and return sealed results. The
reservoir is checked against a separately implemented continuous linear-system
reference. The wave is checked against its analytical continuum Fourier
solution. Refinement checks inspect actual numerical outputs, rather than
accepting a provider's convergence claim. Mass, constitutive quantities,
energy/dissipation, initial/boundary conditions and coupling work are checked.

The shared workflow retains declaration evidence, operation execution, result,
and verification occurrences as different identities in the existing Session.
Model time is solver-owned simulation time. Reopening a bundle validates data,
seals, dependency links and source provenance without executing either solver
or verifier. Explicit fresh verification invokes the fixed verifier and gives
the verification attempt a new occurrence identity. Export requires fresh
successful verification and leaves the archived bundle unchanged.

`LOCAL` means the requested observations are numerically qualified within the
declared profile. `EXPAND` means the numerical profile passes but a requested
quantity needs additional physics. `REFUSE` covers malformed data, broken
bindings, physical-domain violations, insufficient resolution or failed checks.
None of these statuses provides experimental validation, empirical uncertainty
coverage, canonical state admission or permission to actuate equipment.

The reservoir interface checks work-conjugate pressure/force and displacement.
A future nonmatching mesh adapter must preserve these relationships as well as
force and mass transfer; the [preCICE mapping documentation](https://precice.org/configuration-mapping.html)
distinguishes interpolation of intensive quantities from conservation of
extensive quantities. No external solver adapter is activated by this increment.

## Experimental validation and additional model arrows

The [experimental-data workflow](FLUID_EXPERIMENTS.md) accepts held-out reservoir
observations with explicit covariance and provenance. Physical validation still
requires a recorded two-tank experiment with independently
measured areas, connector dimensions, density, levels/flows, clock uncertainty,
boundary motion, preload and dissipation. Calibration data and held-out runs
must stay separate. Agreement against an analytical model validates the
numerical implementation; it cannot certify that the model describes a
particular pipe, wave tank or polymer boundary.

The next model arrows remain explicit: qualified material parameters into a
constitutive model; resolved CFD traction into a structural mesh; structural
motion back into the moving fluid boundary; conservative temporal/spatial
mapping; and uncertainty transport. Each needs its own physical domain,
discarded-information declaration and verification evidence.

## Run it

Install the Terminal package from this checkout using `python -m pip install .`.
Run all commands from a writable investigation directory:

```sh
net fluid example --profile reservoir --output reservoir-request.json
net fluid run --request reservoir-request.json --output-dir reservoir-run
net fluid inspect reservoir-run
net fluid verify reservoir-run --output reservoir-fresh-audit.json
net fluid export-csv reservoir-run --output reservoir.csv
net fluid handoff reservoir-run --sample-index 0 --output reservoir-state.json

net fluid example --profile wave --output wave-request.json
net fluid run --request wave-request.json --output-dir wave-run
net fluid verify wave-run
net fluid export-csv wave-run --output wave.csv
```

Each run directory is create-only. It retains the request, workspace,
verification and preservation records. The wave CSV includes both cell and face
positions so velocity is not silently moved to the elevation grid. The reservoir
CSV exports the finest retained temporal resolution.

The reservoir handoff exports one finest-resolution sample through the existing
`ciw.state.v1` scalar state contract. It retains simulation semantics, elapsed
model time, exact SI values, source/execution/result bindings and a distinct
fresh verification occurrence. The remaining trajectory and refinement traces
are explicitly discarded. Uncertainty remains unestablished. The existing
FlowState estimator needs an independently declared observation operator and
sensor covariance before these simulated states can become estimator inputs;
the handoff does not execute it.

Run the dedicated qualification suite with `python -m pytest -q tests/test_fluid*.py`.
The installed lifecycle gate is
`python scripts/check_fluid_installed.py --net /absolute/path/to/net --output-dir /new/output/directory`.
The dedicated CI workflow runs the fluid and shared-substrate checks and an
installed wheel on Linux and Windows; its actual completion status is evidence
separate from the workflow definition.
