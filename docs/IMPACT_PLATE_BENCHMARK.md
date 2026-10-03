# Impact plate benchmark

This workload adds a spatial elastic specimen model alongside NET's
[elastic contact](IMPACT_CONTACT_BENCHMARK.md) and
[crush contact](IMPACT_CRUSH_BENCHMARK.md) profiles. A rigid striker point mass
loads an isotropic rectangular plate through a finite, fixed rectangular
contact patch and a massless compression-only spring. A retained sine-mode
expansion resolves bending deformation and vibrational energy in the plate.

Qualification concerns this declared finite-dimensional synthetic model.
Young's modulus and density are input parameters, not experimentally calibrated
polymer properties. The workload does not establish impact strength, toughness,
indentation hardness, fracture initiation, damage, molecular response or
manufacturing performance. Small-deflection elastic plate mechanics provides a
concrete geometry-to-response connection on the existing NET substrate.

## Geometry, state and sign convention

The plate occupies `0 <= x <= a`, `0 <= y <= b` and has uniform thickness `h`.
All four edges have zero transverse displacement and zero normal bending
moment. These are ideal simply supported edges, not clamped edges. Supports
remain fixed and do no mechanical work. Initial displacement and velocity of
the plate are zero; the striker starts at first contact with positive approach
speed. Gravity, damping and in-plane membrane dynamics are absent.

Striker displacement `s` and plate deflection `w` are positive in the same
approach direction. The retained representation is

$$
w(x,y,t)=\sum_{m=1}^{N}\sum_{n=1}^{N}
q_{mn}(t)\sin(m\pi x/a)\sin(n\pi y/b).
$$

The mode functions satisfy both simply supported bending conditions. The
coefficients `q_mn` are transverse displacement amplitudes in metres, rather
than mass-normalized coordinates. The flexural rigidity, modal mass and modal
stiffness are

$$
D=\frac{Eh^3}{12(1-\nu^2)},\qquad
M_{mn}=\frac{\rho hab}{4},\qquad
K_{mn}=\frac{D\pi^4ab}{4}
\left(\frac{m^2}{a^2}+\frac{n^2}{b^2}\right)^2.
$$

Thus the uncoupled angular frequency is

$$
\omega_{mn}=\pi^2\sqrt{D/(\rho h)}
\left(\frac{m^2}{a^2}+\frac{n^2}{b^2}\right).
$$

| Quantity | Meaning | SI unit |
| --- | --- | --- |
| `a`, `b`, `h` | Span, span, thickness | m |
| `E`, `nu`, `rho` | Modulus, Poisson ratio, density | Pa, 1, kg/m³ |
| `D` | Plate flexural rigidity | N m |
| `M_mn`, `K_mn` | Modal mass and stiffness | kg, N/m |
| `s`, `q_mn`, `w_bar` | Striker, modal, patch-average displacement | m |
| `g_mn` | Patch-to-mode coupling | 1 |
| `F`, `k` | Contact force magnitude and spring stiffness | N, N/m |

## Finite patch and work-conjugate loading

Let the fixed patch have centre `(xc, yc)` and widths `(lx, ly)`, entirely
within the plate. Uniform pressure `F / (lx ly)` produces the modal coupling

$$
g_{mn}=\sin(m\pi x_c/a)\sin(n\pi y_c/b)
\operatorname{sinc}\!\left(\frac{m l_x}{2a}\right)
\operatorname{sinc}\!\left(\frac{n l_y}{2b}\right),
\qquad \operatorname{sinc}(z)=\frac{\sin(\pi z)}{\pi z}.
$$

The same coefficient defines the average patch displacement
`w_bar = sum(g_mn q_mn)` and the generalized modal load `g_mn F`. This equality
makes the displacement and load handoff work-conjugate: power transferred to
the plate is `F * d(w_bar)/dt`.

The spring gap and force are

$$
\delta=s-\bar w,\qquad F=k\max(\delta,0),\qquad
m_s\ddot s=-F,\qquad
M_{mn}\ddot q_{mn}+K_{mn}q_{mn}=g_{mn}F.
$$

A positive gap is spring compression; a negative gap is separated flight.
The contact law has no attractive force. It couples a single patch-average
coordinate to a prescribed uniform pressure shape. It does not enforce local
impenetrability at every point of the patch or resolve rigid-punch/Hertz
contact, indentation, pressure redistribution or local three-dimensional
stresses. Contact stiffness is an independent effective parameter in N/m;
it is not the plate modulus in Pa.

## Energy and impulse accounting

For this undamped ideal model, total energy is

$$
\mathcal E=
\tfrac12m_s\dot s^2+
\tfrac12\sum M_{mn}\dot q_{mn}^2+
\tfrac12\sum K_{mn}q_{mn}^2+
\tfrac12k\max(\delta,0)^2.
$$

It equals the initial striker kinetic energy. The transfer cancels because
the plate receives `+F d(w_bar)/dt` while the striker receives `-F ds/dt`,
and their difference changes the contact spring energy. After separation the
spring energy is zero, the striker travels freely and the plate continues
vibrating.

Reduced striker rebound energy is retained plate vibration, not plastic work,
heat or fracture absorption. A coefficient of restitution below one can occur
in a perfectly elastic plate/striker system because energy remains in plate
modes. This workload therefore distinguishes contact spring energy, striker
kinetic energy and plate kinetic/bending energy.

The striker impulse identity remains

$$
\int_0^tF(\tau)\,d\tau=m_s[\dot s(0)-\dot s(t)].
$$

The fixed supports exchange momentum with the plate. The model does not claim
conservation of striker-plus-plate transverse momentum or independent recovery
of boundary support forces. Modal force balance and total energy are the
appropriate checks for the retained bending representation.

## Numerical and reference paths

The numerical path evolves striker and modal coordinates with a fixed-step
velocity-Verlet method and evaluates compression-only contact from the current
state. Time refinement keeps the same basis and halves the timestep. Spatial
refinement increases the retained basis and independently evaluates the effect
on named observables. Agreement between two finite bases is a sampled numerical
comparison, not a proof of convergence to a continuum or three-dimensional
solid model.

The independent reference uses closed-form linear modal propagation within one
active-contact interval. If `x = (s, q_11, ...)` and `c = (1, -g_11, ...)`, its
active stiffness is

$$
K_\mathrm{active}=\operatorname{diag}(0,K_{11},\ldots)+kcc^{\mathsf T}.
$$

A symmetric eigendecomposition of
`M^(-1/2) K_active M^(-1/2)` propagates the coupled elastic state. The first
returning positive-to-nonpositive root of `delta` defines release, excluding
the initial zero at first contact. Thereafter the reference propagates a free
striker and uncoupled plate oscillators. This reference does not supply the
numerical trajectory or call the Verlet solver.

A single-contact reference must not silently certify later recontact. The
retained interval must contain release and separated flight; any unsupported
contact sequence must fail the declared qualification. Root brackets and the
post-release gap must be checked alongside force, displacement, velocity and
energy histories. An event-time match by itself does not establish the
trajectory or energy partition.

## Small-deflection and truncation boundaries

The linear Kirchhoff-Love idealization neglects transverse shear deformation,
rotary inertia, membrane stiffening and material nonlinearities. Thinness by
span alone does not establish that high retained modes accurately represent a
three-dimensional solid: their wavelengths decrease with mode index. An
increase in retained modes checks truncation within the declared plate model;
it does not validate the plate theory at short wavelengths.

For each retained state, conservative spatial bounds can be computed without
sampling a surface mesh. The implemented slope guard uses the sum of component
bounds:

$$
\max_{x,y}|w|\le\sum|q_{mn}|,\qquad
\max_{x,y}\|\nabla w\|\le
\pi\sum|q_{mn}|(m/a+n/b).
$$

The workload uses its declared small-deflection and slope guards to prevent
numerically successful trajectories from being qualified outside the intended
linear regime. Bounds calculated at retained times concern that recorded
history; they do not prove a continuous-time maximum between samples.
Numerical timestep and refinement checks remain necessary.

Geometry, material constants, patch position and width must be explicit.
Unsupported supports, curved/ribbed geometry, anisotropy, nonzero initial plate
state, damping, viscoelasticity, plasticity, rate/temperature dependence,
fracture and molecular transitions require separate model/provider contracts
and evidence. They are not enabled by an accurate elastic modal run.

## Strict request contract and example

The request schema is `ciw.impact-plate-request.v1`, with scope
`simply_supported_kirchhoff_love_plate_patch_contact`. It contains exactly
`schema`, `scope`, `model`, `integration`, `desired_observables` and
`tolerances`. Unknown fields, unknown/repeated observables, nonfinite values and
undeclared model extensions are rejected. No hidden clamping changes a request.

| Model field | Accepted domain/value |
| --- | --- |
| `mass_kg` | `0.001..1000` kg |
| `stiffness_n_per_m` | `10..1e8` N/m |
| `initial_speed_m_per_s` | `1e-5..10` m/s |
| `length_x_m`, `length_y_m` | Each `0.02..2` m |
| `thickness_m` | `1e-4..0.05` m, with `h / min(a,b) <= 0.05` |
| `young_modulus_pa` | `1e6..1e12` Pa |
| `poissons_ratio` | `0..0.49` |
| `density_kg_per_m3` | `100..20000` kg/m³ |
| `patch_width_x_m`, `patch_width_y_m` | Each `2h..0.5` corresponding span |
| `patch_center_x_m`, `patch_center_y_m` | Entire patch inside plate, with at least `h` edge clearance |
| `initial_compression_m`, `damping_n_s_per_m`, `gravity_during_contact_m_per_s2` | Exactly zero |
| `contact_law` | `compression_only_linear_patch_spring` |
| `support` | `simply_supported_rectangular_plate` |

Integration requires `method: velocity_verlet`, `modes_per_axis: 1` or `3`,
`spatial_refinement_increment: 2`, integer `steps_per_contact` in `256..2048`
and `duration_factor` in `1.25..2`. The high-mode thinness guard is

$$
h\pi\sqrt{(N_\mathrm{spatial}/a)^2+(N_\mathrm{spatial}/b)^2}\le0.35.
$$

This is a conservative declaration for this benchmark, not an experimentally
validated cutoff for every material. The request also enforces
`dt * omega_bound <= 0.5` for both the primary and spatial trace, with

$$
\omega_\mathrm{bound}^2=
\max\omega_{mn}^2+k\left[1/m_s+\sum g_{mn}^2/M_{mn}\right].
$$

Before creating a run directory, request validation additionally bounds the
independent reference event scan for each basis:

$$
\left\lceil T_\mathrm{horizon}\,
\omega_\mathrm{bound}\,32/\pi\right\rceil\le25000,
\qquad
T_\mathrm{horizon}=
\left\lceil n_\mathrm{steps}f_\mathrm{duration}\right\rceil
\frac{\pi\sqrt{m_s/k}}{n_\mathrm{steps}}.
$$

The reference uses at least 256 phase-aware scan intervals and caps the count
at 25000. This bounded computational profile rejects declarations whose event
scan would exceed the budget; it does not change numerical tolerances or
silently reduce reference resolution. Release candidates are bracketed and
bisected. After release, a strictly separating free gap is required at the
first small positive time offset; an immediate nonnegative gap or subsequent
recontact detected within the observation window is unsupported. These
phase-aware and retained-sample guards are numerical acceptance, rather than a
formal continuous-time theorem excluding every unrecorded contact event.

This upper bound controls the active-contact operator. It is an integration
profile guard; the history, accounting and refinement checks still determine
requested accuracy. The timestep is the **nominal** rigid-support spring
contact scale `pi sqrt(m_s/k) / steps_per_contact`; the actual plate release
is found from the trajectory. The run horizon therefore need not contain
release for every otherwise structurally valid request.

All three traces cover the same fixed horizon. The primary uses `N` modes per
axis and `ceil(steps_per_contact * duration_factor)` steps. The temporal refined
trace uses the same basis and twice as many steps; the spatial trace uses
`N + 2` modes per axis at the same half timestep. Arrays include striker
position, signed spring compression, striker velocity, force, patch-average
position/velocity and one displacement/velocity history per mode. Modal mass,
stiffness, mode indices and patch coupling are retained and bound to the
request. Numerical result schema is `ciw.impact-plate-result.v1`.

The supported observable names are `force_time`, `impulse`, `restitution`,
`energy_accounting`, `separation_time`, `plate_deformation` and `plate_modes`.
Recognized expansion names are `stress`, `strain`, `damage`, `fracture`,
`hardness`, `molecular_response`, `morphology`, `robustness`,
`scale_preservation`, `rate_response`, `thermal_response` and `plastic_work`.
Requesting an expansion does not equip the elastic plate model to compute it.

Tolerance keys are `analytic_normalized`, `impulse_relative`,
`momentum_relative`, `energy_relative`, `restitution_absolute`,
`separation_relative`, `refinement_normalized` and
`spatial_refinement_normalized`; each is finite in `1e-12..0.1`.
`momentum_relative` concerns the striker impulse identity, not conservation of
total striker-plus-plate momentum.

The generated example uses a `0.2 m × 0.2 m × 0.003 m` plate, `E = 2e9 Pa`,
`nu = 0.35` and `rho = 1200 kg/m³`, with a centred `0.02 m × 0.02 m` patch.
The striker has mass `1 kg`, spring stiffness `10000 N/m` and approach speed
`0.03 m/s`. Integration uses a primary `3 × 3` basis and 1024 nominal contact
steps, with a `5 × 5` spatial comparison at half the timestep and a duration
factor of `1.5`. Default tolerances are `0.001`, except
`momentum_relative: 1e-10` and `spatial_refinement_normalized: 0.02`.
These parameters define an unidentified synthetic elastic specimen.

| Example quantity | Value |
| --- | --- |
| Initial striker kinetic energy | `0.00045 J` |
| Total plate mass | `0.144 kg` |
| Modal mass | `0.036 kg` |
| Flexural rigidity | Approximately `5.12821 N m` |
| Uncoupled `(1,1)` natural frequency | Approximately `93.7392 Hz` |
| Nominal contact timestep | Approximately `3.06796e-5 s` |
| Retained horizon | Approximately `0.0471239 s` |
| Highest retained thickness-wavenumber product | Approximately `0.333216` |

The verification report schema is `ciw.impact-plate-verification.v1`. Metric
names distinguish a global spatial bound from a patch displacement:

| Metric | Meaning |
| --- | --- |
| `plate_peak_deflection_m` | Retained-time maximum of `sum(abs(q_mn))`, a conservative global spatial bound |
| `plate_contact_peak_deflection_m` | Retained-time maximum absolute patch-average displacement |
| `max_deflection_over_thickness` | Global deflection bound divided by thickness |
| `slope_bound` | Retained-time maximum of `sum((m pi/a + n pi/b) abs(q_mn))` |

The fixed runtime domain requires deflection bound/thickness and slope bound
both at most `0.1`. `plate_peak_deflection_m` is **not** an actual measured or
surface-sampled peak. These metrics are calculated independently for each
retained trace and remain scoped to its mode basis and recorded time interval.

## Normalization and qualification meaning

The report retains `reference.primary`, `reference.spatial`,
`reference.scales` and `reference.state_normalizations`. State normalization
maps for `primary` and `spatial` contain exactly the six scalar trace fields
and two modal-history fields. The temporal refined trace shares the primary
basis and its normalizations.

Let `E0 = 0.5 m_s v0²`, `Q0 = v0 sqrt(m_s/k)`, `F0 = k Q0` and
`T0 = pi sqrt(m_s/k)`. The independent auditor uses the following declared
normalizations:

| Field/check quantity | Normalization | Unit |
| --- | --- | --- |
| `striker_displacement_m`, `compression_m`, `plate_contact_displacement_m`, `modal_displacement_m` | `Q0` | m |
| `velocity_m_per_s` | Initial striker speed `v0` | m/s |
| `modal_velocity_m_per_s` | `sqrt(2 E0 / min(M_mn))` for the declared basis | m/s |
| `plate_contact_velocity_m_per_s` | `sqrt(2 E0 sum(g_mn² / M_mn))` for the declared basis | m/s |
| `force_n`, peak-force change | `F0` | N |
| Striker impulse/error | Initial striker momentum `m_s v0` | N s |
| Energy drift/change | `E0` | J |
| Separation-time error/change | `T0` | s |
| Restitution error/change | `1` | 1 |

The plate velocity scales follow from kinetic-energy bounds, rather than from
observed error. A light modal coordinate can attain a speed above `v0` while
its kinetic energy remains below `E0`. For the patch coordinate,
Cauchy-Schwarz gives

$$
|\dot{\bar w}|=|\sum g_{mn}\dot q_{mn}|
\le\sqrt{\sum g_{mn}^2/M_{mn}}\,
\sqrt{\sum M_{mn}\dot q_{mn}^2}
\le\sqrt{2E_0\sum g_{mn}^2/M_{mn}}.
$$

Using striker speed as the normalization for every plate velocity would
implicitly impose a common velocity scale on coordinates with different
masses and patch couplings. The retained scales depend only on the initial
energy and declared basis, not on measured numerical differences or fitted
acceptance thresholds. For the default request, the modal velocity scale is
approximately `0.158114 m/s` in both bases; patch velocity scales are
approximately `0.303569 m/s` for `3 × 3` and `0.431731 m/s` for `5 × 5`.
They are attainable-energy bounds, not predicted peak velocities.

Analytic state/history errors use each trace's own basis normalization. The
same-basis time comparison uses primary normalizations. The enlarged-basis
spatial comparison uses the larger of the primary and spatial normalization
for each scalar field. It aligns histories at the shared half-timestep grid;
it does not interpolate between time samples. Refinement comparisons
cover striker/patch coordinates, velocities, compression and force, with
separate changes for impulse, restitution, peak force/compression, plate
L1-deflection bound, total terminal energy and separation time. Both time and
spatial comparisons additionally match common modal displacement and velocity
histories by explicit `(m,n)` mode pairs, using `Q0` for displacement and the
larger declared modal energy-velocity scale for velocity. Per-mode histories
are also checked against the independently propagated reference in each
basis.

The `displacement_field_bound` refinement metric includes modes that have no
counterpart in the smaller basis. If `C` is the common mode set and `A` contains
modes added on the right, then at the aligned retained times `t_j`,

$$
\frac{\max_j\sup_{x,y}|w_L(x,y,t_j)-w_R(x,y,t_j)|}{Q_0}
\le\frac{\max_j\left[
\sum_{i\in C}|q_i^L(t_j)-q_i^R(t_j)|+
\sum_{i\in A}|q_i^R(t_j)|\right]}{Q_0}.
$$

The right-hand side is the reported bound. The implementation also includes
absolute amplitudes of modes removed on the right; that set is empty in these
same-basis or enlarged-basis comparisons. The inequality follows from the
absolute value of each sine product being at most one. It bounds the difference
between the two **finite-basis fields everywhere in space at recorded times**.
It neither bounds error against the continuum plate nor proves behavior
between time samples.

A patch-average match can hide a spatial change: opposite amplitudes in the
centred patch's `(1,5)` and `(5,1)` modes can cancel their patch projection while
changing displacement away from the patch. The finite-field bound includes
both amplitudes and detects that loss of spatial agreement. For the default
request the spatial common-mode displacement change is approximately
`0.0097432`, common-mode velocity change `0.0069100` and finite-field bound
`0.0149031`; all are normalized quantities below the declared `0.02` spatial
tolerance. The tolerance is acceptance for this one comparison, not a formal
continuum truncation-error bound.

A complete numerically well-formed report has 105 checks. Release is linearly
interpolated within a retained positive-to-nonpositive signed-gap bracket;
that interpolation estimates an event time, not an interpolated state field.
Both retained traces and independent spectral references must show one contact
and no recontact within the recorded observation window. The small-deflection
and slope guards apply at **retained times**. They are not a continuous-time
global-maximum proof or certification of motion between samples.

| Outcome | Meaning |
| --- | --- |
| `PASS` / `LOCAL` | All numerical and fixed model-domain checks pass, with only supported observables requested |
| `PASS` / `EXPAND` | The bounded plate model passes; requested richer observables need qualified additional models or evidence |
| `FAIL` / `REFUSE` | Numerical, integrity, single-contact or model-domain acceptance fails |

Only fresh `LOCAL` qualification permits observation or field export. Declared
normalized tolerances establish acceptance for the stated quantities and scales;
they are not relative errors against every observed peak, experimental
uncertainty bands or universal material-validity tolerances.

## Commands and retained authority

```sh
net impact plate example --output impact-plate-request.json
net impact plate run impact-plate-request.json --output-dir impact-plate-run
net impact plate inspect impact-plate-run
net impact plate verify impact-plate-run
net impact plate export impact-plate-run --output impact-plate-observations.csv
net impact plate field impact-plate-run --time-index 512 --output impact-plate-field.json
```

The generated example request is the executable contract for exact fields,
accepted bounds, supported observables and tolerances. `run` uses the existing
Session/operation/result path and retains request, histories, independent
verification and typed preservation records. Evidence, operation, execution,
verification and admission identities remain distinct.

`inspect` validates retained structure and bindings without replaying numerical
providers. `verify` independently recomputes checks from the retained request
and observations without rerunning the solver, replaying operation executions
or modifying retained files. Verification, CSV export and field export each
consume one validated snapshot of the retained occurrence; the observations
exported are the same candidate that was freshly verified. Export requires
fresh local qualification and creates a new observation file. A
numerical-bound preservation receipt is acceptance for named observables in
this model and recorded domain; it does not admit a canonical material state
or validate an industrial polymer specimen.

CSV export contains the primary trace columns `time_s`,
`striker_displacement_m`, `compression_m`, `velocity_m_per_s`, `force_n`,
`plate_contact_displacement_m` and `plate_contact_velocity_m_per_s`.
The sign of `compression_m` distinguishes compression from separated flight.
Modal histories remain in the bound numerical result.

`field` reconstructs a displacement surface from the retained **primary**
modal amplitudes at exactly one recorded `--time-index`. It freshly verifies
the run before exporting a sealed `ciw.impact-plate-field.v1` JSON file. The
default spatial query grid is `17 × 17`; `--grid-size` accepts odd integers
`3..33`. Arrays `x_m`, `y_m` define the coordinates and `deflection_m` has
rows indexed by `y_m` and columns indexed by `x_m`. Boundary displacement is
zero by the simply supported representation. The artifact includes geometry,
mode indices/amplitudes, SI units, exact time, evidence/result/execution
references and the retained verification identity/recomputed report digest.

This surface is evaluation of the same finite sine basis at additional spatial
query points. Increasing the query grid does not add dynamics, refine the
modal basis or establish a continuous-model accuracy bound. There is no
interpolation in time and no stress, strain, pressure, fracture or damage field.

The typed receipt schema is `ciw.impact-plate-preservation.v1`; it binds the
request, candidate and independent report through existing representation,
preservation, verification and eligibility APIs. Supported quantities carry
numerical BOUND effects and unavailable higher properties carry explicit
FORGET effects. An ELIGIBLE receipt concerns this numerical contract and does
not perform state admission or supply a fine-to-coarse commutativity witness.

## Physical validation path

A physical plate qualification requires measured geometry and support
conditions, a declared contact/loading model, material response characterized
at relevant temperature/rate/conditioning, and instrumented observations.
Useful comparisons are force-time history, striker and plate displacement,
contact duration, rebound and modal frequencies. Matching an elastic force
curve cannot establish crack initiation or polymer chain damage. Rate-dependent
constitutive laws and independently measured loss are needed before interpreting
specimen dissipation as an industrial material property.

## Primary references

- A. Konyukhov, *Wave cancellation conditions for the double impact of finite
  duration in an arbitrary structure*, Acta Mechanica 231, 2773–2798 (2020),
  [DOI: 10.1007/s00707-020-02672-0](https://doi.org/10.1007/s00707-020-02672-0),
  Appendix 1.4. This research supplies the simply supported Kirchhoff plate
  equation, boundary conditions and sine-mode frequencies. Its prescribed-load
  example does not validate NET's coupled finite-patch spring contact law.
- COMSOL, [Eigenfrequency Analysis](https://www.comsol.com/multiphysics/eigenfrequency-analysis),
  plate section. Official documentation relates elastic plate rigidity and
  natural frequencies to geometry and support conditions.
- NIST, [Metrologies for Non-linear Materials in Impact Mitigation](https://www.nist.gov/programs-projects/metrologies-non-linear-materials-impact-mitigation).
  The program identifies nonlinear, temperature-, strain- and rate-dependent
  response and microstructural characterization as relevant to impact materials.
