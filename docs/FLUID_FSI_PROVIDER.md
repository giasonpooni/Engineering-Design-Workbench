# Resolved fluid–structure benchmark and conservative interface port

NET now has two distinct capabilities: a resolved one-dimensional fluid–structure
benchmark and a retained conservative interface transfer. The benchmark qualifies
its declared fluid and wall equations together. The generic port qualifies only
the supplied interface algebra; it does not qualify either attached solver or
the complete coupled model.

## Run the resolved benchmark

```sh
net fluid example --profile fsi --output fsi-request.json
net fluid run --request fsi-request.json --output-dir fsi-bundle
net fluid inspect fsi-bundle
net fluid verify fsi-bundle --output fsi-fresh-verification.json
net fluid export-csv fsi-bundle --output fsi-primary-fields.csv
```

The request describes an unforced, uniform-depth, linear shallow-water channel
with a fixed left wall and a preloaded compliant right wall. It uses SI units and
an explicit provider-owned elapsed model clock. The initial state is the
fundamental continuous coupled eigenmode at maximum displacement. A damper
coefficient is represented explicitly and fixed at zero in this qualification.
A nonzero coefficient is refused until a separate damped continuum reference is
qualified; requesting `structural_damping` gives `EXPAND`.

The fluid equations and structural boundary are

\[
\eta_t+H u_z=0,\qquad u_t+g\eta_z=0,\qquad
u(0)=0,\quad u(L)=v,
\]

\[
\dot x=v,\qquad m\dot v=F-k_sx,\qquad
F=\rho gWH\eta_b.
\]

Here \(\eta\) is elevation relative to the resting free surface, \(u\) is
depth-averaged horizontal velocity, and positive wall displacement extends the
channel outward. The resting hydrostatic force is balanced by preload. Reported
wall force is the perturbation resultant. The pressure in channel cells is
hydrostatic bottom gauge pressure; boundary pressure deviation is reported
separately.

The finite-volume grid stores cell-average elevation and face velocity, including
both walls. At the compliant wall, the half-dual-cell liquid mass is
\(M_h=\rho WH\Delta z/2\). The discrete wall equation is

\[
(m+M_h)\dot v=\rho gWH\eta_{N-1}-k_sx,
\qquad
\eta_b=\eta_{N-1}-\frac{\Delta z}{2g}\dot v.
\]

This acceleration correction makes the boundary force satisfy
\(F=m\dot v+k_sx\). Using the last cell's pressure directly as physical wall
traction would omit liquid boundary inertia. That half-cell inertia remains in
fluid kinetic energy; it is not counted as structural mass or energy.

The monolithic solver uses a fixed implicit-midpoint clock. A symmetric modal
factorization evaluates the spatially discrete midpoint recurrence. Every
interface work increment uses the same midpoint physical force and velocity:
fluid work is \(-Fv\Delta t\), structural work is \(+Fv\Delta t\). The linear
volume invariant includes the signed swept wall volume:

\[
V=WLH+W\Delta z\sum_i\eta_i+WHx.
\]

No partitioned lag, external solver process, adaptive clock, material failure,
nonlinear moving mesh or three-dimensional Navier–Stokes model is implied.

## Independent reference and acceptance

The reference solves the continuous characteristic equation independently of the
finite-volume matrices and midpoint recurrence. With \(K=qL\),
\(\mu=m/(\rho WHL)\) and
\(\kappa=k_sL/(\rho gWH^2)\), the fundamental positive root satisfies

\[
(\mu K^2-\kappa)\sin K-K\cos K=0.
\]

The exact continuum fields are

\[
\eta(z,t)=A\cos(qz)\cos(\omega t),\qquad
u(z,t)=\frac{Ac}{H}\sin(qz)\sin(\omega t),
\]

\[
x(t)=-\frac{A\sin(qL)}{Hq}\cos(\omega t),\qquad
c=\sqrt{gH},\quad\omega=cq.
\]

Reference elevation is analytically averaged over each cell, rather than sampled
at its center. Velocity is evaluated at the corresponding faces. Verification
checks the fluid continuity and momentum equations, structural motion, physical
boundary traction, both sides of interface work, mass, energy, initial state and
agreement with this independent continuous solution.

Five retained traces distinguish temporal and spatial effects:

| Trace | Cells | Time steps |
| --- | ---: | ---: |
| `primary` | N | S |
| `time_refined` | N | 2S |
| `time_fine` | N | 4S |
| `spatial_refined` | 2N | 4S |
| `spatial_fine` | 4N | 4S |

Spatial comparisons conservatively average finer elevation cells onto the
coarser grid and select coincident velocity faces. Temporal comparisons use
coincident model times. Both observed refinement ratios must lie inside the
declared second-order acceptance interval when differences exceed the numerical
resolution floor. These finite comparisons are empirical checks, not certified
error bounds or a general continuum convergence proof.

The hard model domain requires \(A/H\le0.01\), \(qH\le0.2\), continuous wall
amplitude within its declared travel, and \(|x|/L\le0.001\). Numerical fields are
screened against those same amplitude and travel limits, allowing only a
\(10^{-12}\) relative floating-point guard. Additional bounds cover mass and
stiffness ratios, refinement allocations, accuracy CFL and modal time resolution.

The default 32-cell/32-step benchmark yields:

| Check | Default result |
| --- | ---: |
| Finest normalized continuous-mode error | approximately 5.47e-6 |
| Maximum normalized error over all five traces | approximately 8.64e-5 |
| Temporal refinement ratio | approximately 3.9997 |
| Spatial refinement ratio | approximately 3.9637 |
| Relative mass residual | approximately 2.22e-16 |
| Relative total-energy residual | approximately 3.51e-13 |
| Equal opposite force/work residual | zero |

The default indented result payload is approximately 4.16 MB, below 4 MiB.
Session archives additionally retain operation identities and dependencies.
These numbers qualify the declared synthetic linear benchmark. They are not
experimental validation, certified design accuracy or physical uncertainty
estimates.

## Retain and audit a generic interface transfer

```sh
net fluid coupling template --output interface-request.json
net fluid coupling run --request interface-request.json --output-dir interface-bundle
net fluid coupling inspect interface-bundle
net fluid coupling verify interface-bundle --output interface-fresh-verification.json
```

The template wraps the finite interface request in a provenance declaration.
Inputs must be `synthetic` or `declared_solver_output`; acquired measurements
are outside this workflow. Declared solver-output provenance requires explicit
fluid and structural content references. Those references are declarations:
this workflow does not fetch, authenticate, replay or qualify the referenced
solvers or their complete coupled model.

The supplied geometry identifies fluid face areas, centroids and signed normals,
structural nodes, a common right-handed Cartesian SI frame and a moment origin.
Traction is already a signed force-per-area vector exerted by fluid on structure.
The port does not infer traction from pressure or a stress tensor.

For face-motion map \(P\), face-area diagonal \(A_f\), supplied traction \(t_f\)
and structural velocity \(v_s\), transfer uses

\[
v_f=P v_s,\qquad f_f=A_ft_f,\qquad f_s=P^T f_f.
\]

Partition of unity conserves total force. Linear coordinate reproduction
conserves moment and infinitesimal rigid-body motion on the supplied geometry.
The weighted-transpose relation preserves interface power and virtual work.
Fluid reaction forces have the opposite sign. The port propagates only supplied
traction covariance; geometry, map, clock and constitutive uncertainty remain
explicitly omitted.

Both sides must declare the same model clock, compatible sample times and the
same time step and coupling iteration. This checks declared compatibility; it
does not authenticate acquisition clocks, interpolate histories or prove
stability of a lagged partitioned coupling. Virtual work at one supplied sample
is not an accumulated physical-energy measurement.

A geometry change, deformation or remesh requires a newly declared map and a
fresh verification. The default template has two fluid faces and three
structural nodes; its declaration and verification receipt are each a few KB.

## Evidence and execution identities

Each bundle's evidence is exactly one configuration declaration with a selection
marker, not a simulated trajectory or an acquired signal. The fixed operations
are `fluid.interface.transfer.v1` and `fluid.interface.verify.v1`. Evidence,
transfer execution, transfer result, verification execution and verification
occurrence identities remain distinct. The verifier can execute only against
the exact candidate already retained in the Session.

The default operation registry does not activate either interface provider.
`run` explicitly registers the installed providers. `inspect` and ordinary
archive restoration perform static validation and activate no provider. Static
reads do not repeat covariance eigenvalue or Cholesky factorizations;
active input validation and fresh verification still check covariance eligibility.
A content seal establishes retained integrity, not numerical truth. A coherent
forged numerical report can pass a static read; `verify` recomputes the interface
checks in a new verification occurrence and leaves the original archive unchanged.
The result qualifies finite interface algebra only and retains
`coupled_model_qualified: false`.

## Extending to production CFD

The benchmark and port can be used now within their declared scopes. Coupling
OpenFOAM, Clawpack, preCICE, another CFD engine or a richer structural solver
requires a separately qualified adapter. That adapter must establish frame and
unit semantics, traction conversion, geometry and mapping validity, conservative
force/moment/work transfer, boundary motion, clock ownership, iteration
convergence, and each solver's own conservation and refinement checks. Physical
prediction additionally requires suitable experimental validation and uncertainty
assessment. Solver integration must preserve existing evidence and execution
boundaries; a port pass alone cannot grant those qualifications.

Primary implementation background:

- [Clawpack shallow-water solvers](https://www.clawpack.org/v5.10.x/riemann/Shallow_water_Riemann_solvers.html).
- [preCICE mapping configuration](https://precice.org/configuration-mapping): extensive forces need conservative maps; motion and intensive fields need appropriate consistent maps.
- [preCICE mapping constraints](https://precice.org/doxygen/main/classprecice_1_1mapping_1_1Mapping.html).

These references inform the implementation. No Clawpack or preCICE runtime
binding is claimed by this release.

Run the owned regressions with:

```sh
PYTHONPATH=src python -m pytest -q tests/test_fluid_fsi.py tests/test_fluid_interface_workflow.py
```
