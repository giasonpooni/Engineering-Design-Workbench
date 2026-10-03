# Impact contact benchmark

This workload extends the existing NET session and operation substrate with a
bounded, one-dimensional contact model. It compares a numerical trajectory with
an independent closed-form reference and checks force, impulse and energy
accounting. Its qualification scope is numerical agreement for this declared
model. Physical material validation, deformable plates and molecular scale
preservation remain future work.

## Physical model and units

A point mass strikes a massless, compression-only linear compliant element at a
fixed support. The coordinate `q` is signed compression: positive values compress
the element, zero is first contact or release, and negative values represent a
gap. Velocity is positive toward the support. The outward contact-force
magnitude is

$$
F=k\max(q,0),\qquad \dot q=v,\qquad m\dot v=-F.
$$

The initial state is `q(0) = 0`, `v(0) = v0 > 0`. Mass `m` is in kg, effective
stiffness `k` in N/m, velocity in m/s, simulation time in s, force in N, impulse
in N s and energy in J. The compliant element has no separately resolved mass.
There is no gravity during contact or subsequent free flight, friction, damping,
plasticity, fracture, thermal evolution, specimen vibration or spatial stress
field. This is an impact-at-first-contact benchmark rather than a complete
gravity-driven drop test.

Positive `q` represents compression of a compliant element, not permission for
continuum contact surfaces to interpenetrate. The effective `k` is a spring
constant. It is not a polymer Young's modulus, hardness, strength, toughness or
an experimentally identified plate stiffness. Turning a continuum modulus into
an effective spring constant requires geometry, supports, a declared reduction
and independent qualification.

## Closed-form reference

Define `omega = sqrt(k / m)`. For the first contact interval,

$$
q(t)=\frac{v_0}{\omega}\sin(\omega t),\qquad
v(t)=v_0\cos(\omega t),\qquad
F(t)=m v_0\omega\sin(\omega t),
\qquad 0\le t\le t_c=\frac{\pi}{\omega}.
$$

After release,

$$
q(t)=-v_0(t-t_c),\qquad v(t)=-v_0,\qquad F(t)=0.
$$

The oscillator must end at the first release. Extending its sinusoid beyond that
event would create an attractive force and a second compression cycle absent
from this model.

| Observable | Exact reference |
| --- | --- |
| Maximum compression | `v0 / omega` |
| Maximum force | `m * v0 * omega` |
| Peak-force time | `pi / (2 * omega)` |
| Contact duration | `pi / omega` |
| Contact impulse | `2 * m * v0` |
| Rebound velocity | `-v0` |
| Coefficient of restitution | `1` |
| Initial energy | `0.5 * m * v0**2` |
| Physical dissipation | `0` |

The force impulse and mechanical energy provide independent history checks:

$$
J(t)=\int_0^t F(s)\,ds=m[v_0-v(t)],
\qquad
E(t)=\tfrac12mv(t)^2+\tfrac12k\max(q(t),0)^2=E(0).
$$

The mass alone does not conserve momentum: the fixed support receives the
opposite contact impulse. The support performs no work because it does not move.
Energy transferred into the compliant element during compression is stored
elastic energy and is returned on release. It must not be reported as irreversible
material absorption or fracture energy.

## Request contract and default example

The strict `ciw.impact-request.v1` request contains `schema`, `scope`, `model`,
`integration`, `desired_observables` and `tolerances`. The scope is
`undamped_point_mass_massless_spring_contact`; unknown fields and duplicate or
unknown observable names are rejected.

| Model field | Accepted value/domain |
| --- | --- |
| `mass_kg` | `1e-6` to `1e6` kg |
| `stiffness_n_per_m` | `1e-6` to `1e12` N/m |
| `initial_speed_m_per_s` | `1e-6` to `1e4` m/s |
| `initial_compression_m` | Exactly zero |
| `damping_n_s_per_m` | Exactly zero |
| `gravity_during_contact_m_per_s2` | Exactly zero |
| `contact_law` | `compression_only_linear_spring` |
| `support` | `fixed` |

Derived contact duration, compression, peak force, impulse and initial energy
must also lie within the finite binary64 profile `1e-18` to `1e18` in their
respective SI units. The request does not silently rescale those quantities.

Integration requires `method: velocity_verlet`, integer `steps_per_contact`
between 16 and 4096, and `duration_factor` between 1.25 and 4.0. Each tolerance is
between `1e-12` and `0.1`. The tolerance fields are `analytic_normalized`,
`impulse_relative`, `momentum_relative`, `energy_relative`,
`restitution_absolute`, `separation_relative` and `refinement_normalized`.

The generated example uses 1 kg, 10000 N/m and 2 m/s, 256 primary steps per
analytic contact duration and 512 refined steps per contact. Its duration factor
is 1.5. The exact reference gives contact duration `0.0314159265359` s, maximum
compression `0.02` m, peak force `200` N, support impulse `4` N s and initial
energy `2` J. The default tolerances are `0.001`, except the all-history momentum
balance tolerance `momentum_relative = 1e-10`.

## Numerical verification and retained scope

The numerical evolution and closed-form reference are separate calculations.
The solver uses fixed-step velocity Verlet with
`dt = analytic_contact_duration / steps_per_contact`, then reruns at half that
timestep. It evolves the compression-only force law throughout the retained
duration; it does not stop or change the force law at the analytic release time.
The analytic release is aligned with the declared grid. The verifier independently
finds the numerical positive-to-nonpositive compression crossing and linearly
interpolates its bracket; that numerical event can occur between grid points.
Verification evaluates the retained numerical observations against the analytic
history and declared observable tolerances; it also checks contact-force and
impulse/energy consistency. The reference is not a replacement for execution.
The current implementation makes one timestep-refinement comparison. It does
not establish a convergence order, continuum convergence or a material/geometric
scale transition.

Each comparison must retain its physical units, normalization and tolerance.
Displacement agreement does not establish force agreement, and energy closure
alone does not establish the correct force or trajectory. A normal complete
report contains 33 checks: one schema-integrity check, 12 primary and 12 refined
checks, and eight refinement comparisons. The per-trace checks cover the force
law, velocity-Verlet update equations, nonnegative force, analytic compression,
velocity and force histories, support impulse, all-history momentum balance,
maximum energy drift, restitution, release event and interpolated release time.
Refinement compares aligned compression/velocity/force samples, impulse,
restitution, peak force, maximum compression and release time. All calculations
consume retained samples; the verifier does not import or call the integrator.

The explicitly bound workflow uses `impact.spring-contact.v1` for simulation
and `impact.spring-contact-verify.v1` for verification through the original
Session. The default operation registry is unchanged; saved data cannot activate
these operations. Evidence or request identity, operation identity, execution
occurrence and verification identity have separate roles. An independent numerical check does
not create an experimental observation, a chemical proof or canonical-state
admission. Content digests detect inconsistent retained bytes; they do not
authenticate a physical experiment. Calibration and measurement uncertainty
are not established by this synthetic benchmark.

`run` requires a new output directory. It retains `request.json`, `workspace.json`,
`verification.json` and `preservation.json`, alongside the original Session's
source, execution and result files. The workspace binds one solver occurrence
and one independent-verification occurrence when both complete; refused
operation attempts are retained through the existing Session behavior.

`inspect` checks retained structure, content identities and declared bindings
without running the solver or recomputing the numerical audit. `verify`
recomputes the independent arithmetic from retained inputs and observations and
compares the complete report with the retained report. It neither reruns the
solver nor modifies the retained run or creates a new verification occurrence.
`export` first performs that fresh verification and creates a new CSV only for
a LOCAL trace. It exports primary columns `time_s`, `compression_m`,
`velocity_m_per_s` and `force_n`; it refuses to overwrite an existing output.
Neither inspection nor re-verification is a fresh numerical reproduction, and
CSV export does not increase validation scope.

The existing representation/preservation APIs bind a MODEL initial-reference
representation to a SIGNAL sampled-trace representation with a descriptive
SIMULATE morphism. `preservation.json` contains nine BOUND effects for compression,
velocity and force histories, impulse, momentum balance, energy, restitution,
release time and refinement. They retain observable-specific SI thresholds.
`NUMERICAL_BOUND` records sampled and aggregate numerical acceptance for this
run; it is not a formal error bound, a FORMAL_PROOF or experimental qualification.
Explicit FORGET effects record that higher observables are absent from the
schema. They do not establish that a richer physical state was simulated and
then reduced.

Useful failure and edge fixtures include invalid or nonfinite mass/stiffness,
invalid integration settings, unresolved contact at a coarse timestep, force-sign
errors, bilateral-spring attraction and modified force or velocity observations.
Zero and negative incoming speeds are refused by the current request domain.
Physically they imply no impact at this initial state, and restitution would be
undefined; refusal tests do not assign them the positive-speed benchmark's
restitution value or extend the accepted domain.

## Commands

With NET installed in the current environment:

```sh
net impact example --output impact-request.json
net impact run impact-request.json --output-dir impact-run
net impact inspect impact-run
net impact verify impact-run
net impact export impact-run --output impact-observations.csv
```

See the [example walkthrough](../examples/impact-contact/README.md). The generated
request provides the current field names, parameter bounds, observables and
verification policy. Edit data within that contract; changing equations or
loading assumptions requires a new qualified operation/profile.

## Expansion boundary

The supported `desired_observables` are `force_time`, `impulse`, `restitution`,
`energy_accounting` and `separation_time`. Explicit expansion names are
`plate_deformation`, `stress`, `strain`, `damage`, `fracture`, `hardness`,
`molecular_response`, `morphology`, `robustness` and `scale_preservation`.

| Retained result | Numerical qualification | Typed loss-policy eligibility |
| --- | --- | --- |
| All numerical checks pass; only supported observables requested | LOCAL | ELIGIBLE for the declared numerical policy |
| Checks pass; one or more explicit expansion observables requested | EXPAND | REFUSED because a requested property is absent |
| Numerical checks fail | REFUSE | REFUSED when its required/bounded property is refuted |

ELIGIBLE never performs canonical-state admission. An EXPAND request can retain
the passing spring/contact calculation; it does not calculate the requested
plate, material or molecular response, and CSV export remains blocked.
Rate-dependent constitutive response, crack initiation and bond breaking likewise
need new qualified profiles/providers/evidence. Malformed inputs or unrecognized
laws and observables are refused. An expansion requirement is not a claim that
its solver or coupling is already implemented.

The same-state analytic-versus-numeric comparison is not evidence for

$$
P\circ F_{\mathrm{fine}}
\approx_{\mathcal D,\varepsilon}
F_{\mathrm{coarse}}\circ P
$$

between molecular, material and component models. A future scale connection must
declare the state map `P`, consistently mapped loading, observable, validity
domain, tolerance and the evidence qualifying that connection. Bulk displacement
agreement cannot establish molecular damage or crack initiation. The industrial
and game/simulation applications retain their own qualification scope.

## Future plate and provider qualification

The first physical extension should be an instrumented impact on one polymer
plate and one defined loading regime. Retain the following metadata before
comparing a model with measurement:

| Record | Required context |
| --- | --- |
| Specimen | Material identity/batch, measured dimensions, geometry, mass, processing history, morphology/orientation, conditioning, temperature and specimen identifier |
| Apparatus | Striker mass and tip geometry, supports/joints, fixture compliance, alignment, impact velocity and apparatus configuration |
| Measurements | Force/displacement/velocity channels, units, timebase and synchronization, bandwidth/sampling, filtering, calibration identity and uncertainty |
| Model | Geometry/mesh identity, density, constitutive-law version and parameter provenance, contact law, boundary conditions and initial conditions |
| Execution | Provider/version and runtime binding, integration settings, mesh/timestep studies, numerical damping and any mass scaling |
| Comparison | Observable definitions, preprocessing, acceptance tolerance, uncertainty treatment, validity domain and retained discrepancies |

Begin with elastic plate response and verify discretization and contact
sensitivity. Introduce a calibrated rate-dependent law only after the relevant
temperature and strain-rate regime is measured. Add a declared damage law with a
demonstrated route to mesh-objective fracture predictions. The energy ledger
must distinguish striker/specimen kinetic energy, recoverable strain energy,
irreversible material/friction/fracture losses, fixture and external work, and
artificial numerical losses. Striker kinetic-energy loss is not automatically
fracture energy.

MOOSE Solid Mechanics and Contact are candidate external providers for continuum
models; there is no MOOSE integration in this increment. Its current dynamics
documentation identifies explicit dynamics as experimental, so a future provider
qualification must pin and test the chosen version, integrator and contact
formulation. LAMMPS is another candidate for separately qualified microscopic or
granular workloads; no LAMMPS integration or validated molecular chemistry is
provided here.

## Primary references

- [MIT: Modeling a Spring](https://math.mit.edu/~djk/calculus_beginners/chapter17/section02.html)
  gives the linear oscillator equation and closed-form evolution. The contact
  interval, release continuation and impulse/energy references above are direct
  derivations for the declared compression-only model.
- [LAMMPS: Hooke contact](https://docs.lammps.org/pair_gran.html) documents linear
  normal-contact compliance, stiffness units and damping-related attraction.
- [MOOSE: Solid Mechanics](https://mooseframework.inl.gov/modules/solid_mechanics/),
  [Contact](https://mooseframework.inl.gov/modules/contact/index.html) and
  [Dynamics](https://mooseframework.inl.gov/modules/solid_mechanics/Dynamics.html)
  describe continuum/provider capabilities for future qualification.
- [NIST: Polymer Mechanics](https://www.nist.gov/programs-projects/polymer-mechanics)
  describes deformation-rate-sensitive polymer mechanics, hierarchical
  dissipation mechanisms, instrumented drop-tower testing and projectile impact
  measurements.
