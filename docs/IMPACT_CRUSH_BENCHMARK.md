# Impact crush benchmark

This workload adds a dissipative contact profile alongside NET's existing
[elastic contact benchmark](IMPACT_CONTACT_BENCHMARK.md). A point mass strikes a
massless, compression-only, elastic-perfectly-plastic element at a fixed
support. The model retains an irreversible compression state and a plastic-work
ledger. Qualification is numerical agreement for this declared synthetic model;
it does not establish a polymer constitutive law, specimen fracture energy or
molecular damage.

## State, sign convention and units

The coordinate `q` is total approach from the initial contact position and `v`
is its velocity, positive toward the support. The internal variable `p` is
irreversible residual compression. Recoverable elastic compression is
`delta = max(q - p, 0)`. The force `F` is the magnitude of the outward contact
force on the mass. All parameters and retained states use SI units.

| Symbol | Meaning | Unit |
| --- | --- | --- |
| `m` | Striker point mass | kg |
| `k` | Effective elastic spring stiffness | N/m |
| `F_y` | Effective yield/plateau force | N |
| `q` | Total approach from first contact | m |
| `p` | Irreversible compression | m |
| `delta` | Recoverable elastic compression | m |
| `v` | Signed approach velocity | m/s |
| `U` | Recoverable elastic energy | J |
| `D` | Accumulated plastic work | J |
| `J` | Outward contact-force impulse magnitude | N s |

The effective `k` and `F_y` are element parameters. They are not Young's modulus,
polymer yield stress, indentation hardness or fracture toughness. Mapping them
to a physical specimen requires geometry, supports, a declared reduction and
measurements. The element has unlimited plastic travel in this benchmark; no
densification, finite stroke, force hardening, damage or failure is represented.

## Constitutive law and irreversible evolution

The initial state is `q(0) = p(0) = 0`, `v(0) = v0 > 0`, with finite positive
`m`, `k` and `F_y`. Evolution satisfies

$$
\dot q=v,\qquad m\dot v=-F,\qquad
F=k\max(q-p,0),\qquad 0\le F\le F_y.
$$

Plastic compression is irreversible. The rate-independent flow conditions are

$$
\dot p\ge0,\qquad F_y-F\ge0,\qquad
(F_y-F)\dot p=0.
$$

When compression is increasing at the plateau force, `p` increases so that
`q - p = F_y / k`. During elastic unloading, `p` stays fixed and the force
decreases to zero. After separation, `q < p`, the element supplies no attractive
force and `p` remains fixed. Separation therefore occurs at **`q = p`**, rather
than necessarily at `q = 0`. Negative `q - p` denotes a gap.

For a displacement step whose increment does not hide a loading reversal, the
scalar elastic-trial/plastic-correction update is

$$
p_{n+1}=\max\!\left(p_n,q_{n+1}-\frac{F_y}{k}\right),\qquad
F_{n+1}=k\max(q_{n+1}-p_{n+1},0).
$$

This update prevents force above the plateau and prevents healing. It is a
one-dimensional unilateral element update, not a full tensorial J2 plasticity
model. Endpoint return mapping alone cannot resolve an interior turning point;
the numerical trajectory and its refinement must also be checked.

## Energy and impulse ledger

For this ideal law,

$$
K=\tfrac12mv^2,\qquad U=\tfrac12k\max(q-p,0)^2,\qquad D=F_y p.
$$

During active contact,

$$
\frac{d}{dt}(K+U+D)=(F_y-F)\dot p=0.
$$

The same ledger remains constant after release because `F = 0`, velocity is
constant and `p` is frozen. Thus

$$
K(t)+U(t)+D(t)=E_0=\tfrac12mv_0^2,\qquad
J(t)=\int_0^tF(s)\,ds=m[v_0-v(t)].
$$

The mass alone does not conserve momentum. The fixed support receives the
opposite impulse and performs no mechanical work. `D` is irreversibly expended
plastic work in the declared element law. No temperature or microscopic energy
partition is resolved; calling it measured heat, fracture energy or polymer
toughness would exceed this model's scope. Artificial numerical energy drift is
reported separately from `D`.

## Independent closed-form reference

Define

$$
\omega=\sqrt{k/m},\qquad \delta_y=F_y/k,\qquad
U_y=F_y^2/(2k),\qquad E_0=mv_0^2/2.
$$

### Elastic or exactly threshold impact: `E0 <= Uy`

The yield threshold is not exceeded, `p = D = 0`, and the first contact
trajectory is the original elastic benchmark:

$$
q(t)=\frac{v_0}{\omega}\sin(\omega t),\quad
v(t)=v_0\cos(\omega t),\quad
F(t)=kv_0\sin(\omega t)/\omega,
\quad 0\le t\le\pi/\omega.
$$

Release occurs at `q = 0`, the rebound velocity is `-v0`, the impulse is
`2 m v0` and restitution is `1`. At exact threshold the force reaches `F_y`
only at the turning point; it has no finite plastic plateau and no plastic
work. The yielded formulas below approach this case continuously.

### Yielded impact: `E0 > Uy`

The response consists of elastic loading, a force plateau, elastic unloading
and separated free flight. Let

$$
t_y=\frac{1}{\omega}\arcsin\!\left(\frac{\delta_y\omega}{v_0}\right),
\qquad v_y=\sqrt{v_0^2-\frac{F_y^2}{mk}},\qquad
t_p=\frac{mv_y}{F_y},\qquad
p_{\max}=\frac{mv_y^2}{2F_y}.
$$

For `0 <= t <= t_y`, use the elastic loading formulas above and `p = 0`.
On the plateau use `s = t - t_y`, with `0 <= s <= t_p`:

$$
q=\delta_y+v_y s-\frac{F_y}{2m}s^2,\qquad
v=v_y-\frac{F_y}{m}s,\qquad
p=q-\delta_y,\qquad F=F_y.
$$

At `t = t_y + t_p`, velocity is zero and total compression is
`q_max = delta_y + p_max`. During unloading use
`tau = t - (t_y + t_p)`, with `0 <= tau <= pi / (2 omega)`:

$$
q=p_{\max}+\delta_y\cos(\omega\tau),\qquad
v=-\delta_y\omega\sin(\omega\tau),\qquad
p=p_{\max},\qquad F=F_y\cos(\omega\tau).
$$

Release and subsequent flight are

$$
t_c=t_y+t_p+\frac{\pi}{2\omega},\qquad
v_r=\frac{F_y}{\sqrt{mk}},\qquad
q(t)=p_{\max}-v_r(t-t_c),\quad v(t)=-v_r,\quad F(t)=0.
$$

Here `v_r` is the positive rebound-speed magnitude. The signed rebound
velocity is `-v_r`.

| Observable | Yielded exact reference |
| --- | --- |
| Maximum total compression | `delta_y + p_max` |
| Residual compression | `p_max` |
| Maximum force | `F_y` |
| Maximum-compression time | `t_y + t_p` |
| Contact duration | `t_y + t_p + pi / (2 omega)` |
| Rebound-speed magnitude | `F_y / sqrt(m k)` |
| Coefficient of restitution | `F_y / (v0 sqrt(m k))` |
| Total contact impulse | `m (v0 + v_r)` |
| Final plastic work | `F_y p_max = E0 - Uy` |
| Final kinetic energy | `Uy` |

The peak force is a plateau rather than a unique time point in the yielded
case. A reported first-peak time must be distinguished from the time of
maximum compression. Below yield the peak is unique at `pi / (2 omega)`.

## Numerical verification and qualification boundaries

The numerical solver must evolve its internal state and force law; the exact
reference supplies comparison data, not the numerical trajectory. Independent
verification consumes retained observations and checks analytic histories,
constitutive consistency, irreversible-state evolution, plastic work, impulse,
all-history momentum balance, energy closure, restitution, release and
timestep-refinement differences.

Release detection must find the returning positive-to-nonpositive crossing of
`q - p`. A crossing of the initial reference position `q = 0` would occur later
in yielded flight and is the wrong event. The initial state `q - p = 0` is
first contact, not release. Retained observations must continue beyond the
release event to demonstrate zero force, frozen plastic state and free flight.

The contact duration can be dominated by a long plastic plateau. The implemented
request contract bounds the yield ratio `r = F_y / (v0 sqrt(m k))` to `0.2..5.0`
and primary `steps_per_contact` to `32..4096`. With
`dt = t_c / steps_per_contact`, these bounds imply `omega dt <= 0.209`, including
the smallest accepted yield ratio and primary step count. Requests outside
that ratio/profile are refused. This domain restriction prevents arbitrarily
long plateaus from making the elastic phase arbitrarily coarse; it does not
guarantee the requested accuracy. Independent history and invariant checks and
the half-timestep refinement comparison still determine numerical acceptance.
The implementation does not establish a convergence order, a rigorous global
error bound or continuum convergence.

Each tolerance names its observable, units and normalization. Mechanical
energy alone decreases during plastic loading; the total `K + U + D` is the
conserved ledger. A force plateau or a plausible final restitution does not
establish correct history or correct irreversible work. Plastic work has a
well-defined zero limit below and at yield; an error normalized by initial
energy can be used there without division by zero.

At the exact yield threshold, the analytic plastic state and work are zero.
Fixed-step Verlet can slightly overshoot the elastic turning point and create
small numerical plastic compression of order `dt^2`. The verifier checks this
against the declared normalized plastic-history, final-work, residual-compression
and yield-branch tolerances, and compares refinement; it does not classify a
tiny timestep error as physically established yielding. The analytic threshold
branch remains elastic.

## Strict request contract and default example

The strict request schema is `ciw.impact-crush-request.v1`, with scope
`unilateral_elastic_perfectly_plastic_crush`. It contains exactly `schema`,
`scope`, `model`, `integration`, `desired_observables` and `tolerances`.

| Model field | Accepted value/domain |
| --- | --- |
| `mass_kg` | `1e-6..1e6` kg |
| `stiffness_n_per_m` | `1e-6..1e12` N/m |
| `initial_speed_m_per_s` | `1e-6..1e4` m/s |
| `yield_force_n` | `1e-18..1e18` N, subject to the yield-ratio bound |
| `initial_compression_m` | Exactly zero |
| `initial_plastic_compression_m` | Exactly zero |
| `damping_n_s_per_m` | Exactly zero |
| `gravity_during_contact_m_per_s2` | Exactly zero |
| `contact_law` | `compression_only_elastic_perfectly_plastic` |
| `support` | `fixed` |

The yield ratio must be `0.2..5.0`. Derived contact duration, elastic compression
scale `v0 / omega`, uncapped elastic force scale `v0 sqrt(m k)`, impulse scale
`2 m v0`, initial energy and yield compression must each be finite and within
`1e-18..1e18` in their SI units. Unknown fields, nonfinite values and unknown or
duplicate observable names are rejected; no hidden rescaling is applied.

Integration requires `method: velocity_verlet`, integer `steps_per_contact`
in `32..4096` and `duration_factor` in `1.25..4.0`. The primary trace uses
`ceil(steps_per_contact * duration_factor)` steps. The refined trace has twice
the primary resolution and twice that step count, covering the same final time.
The maximum retained trace has 32769 samples.

Every tolerance is in `1e-12..0.1`. The fields are `analytic_normalized`,
`impulse_relative`, `momentum_relative`, `energy_relative`,
`restitution_absolute`, `separation_relative` and `refinement_normalized`.
The seven supported observables are `force_time`, `impulse`, `restitution`,
`energy_accounting`, `separation_time`, `plastic_work` and
`residual_compression`. The request contains one to sixteen unique observable
names. Supported expansion names are `plate_deformation`, `stress`, `strain`,
`damage`, `fracture`, `hardness`, `molecular_response`, `morphology`, `robustness`,
`scale_preservation`, `rate_response` and `thermal_response`.

The default example uses `m = 1 kg`, `k = 10000 N/m`, `v0 = 2 m/s` and
`F_y = 100 N`, with 1024 primary steps per contact, 2048 refined steps per
contact and `duration_factor: 1.5`. The default tolerances are `0.001`, except
`momentum_relative: 1e-10`. The exact reference values are:

| Observable | Default exact reference |
| --- | --- |
| Initial energy | `2 J` |
| Yield elastic energy/final rebound energy | `0.5 J` |
| Yield force | `100 N` |
| Yield compression | `0.01 m` |
| Maximum total compression | `0.025 m` |
| Residual compression | `0.015 m` |
| Final plastic work | `1.5 J` |
| Rebound-speed magnitude | `1 m/s` |
| Coefficient of restitution | `0.5` |
| Contact impulse | `3 N s` |
| Contact duration | `0.0382644590996207 s` |

The result schema is `ciw.impact-crush-result.v1`, with numerical solver
`fixed_step_velocity_verlet_return_mapping_binary64`. Primary and refined
traces retain `time_s`, `compression_m`, `velocity_m_per_s`, `force_n`,
`plastic_compression_m` and `plastic_work_j`, plus their resolution and timestep.
The independent report schema is `ciw.impact-crush-verification.v1`. A complete
report with detected release in both traces contains 59 checks: one integrity
check, 23 checks for each trace and 12 refinement comparisons. The verifier
never imports or calls the integrator.

## Retained operations, preservation and commands

The workload binds `impact.crush-contact.v1` and
`impact.crush-contact-verify.v1` explicitly through the original Session; the
default operation registry remains unchanged. Saved data cannot activate these
operations. It retains the existing typed representation/preservation APIs.
Evidence/request, operation, execution occurrence and verification
identities remain separate. Numerical acceptance supports only the declared
contact/crush observables and accepted numerical tolerances. It does not create
experimental evidence, formal proof, calibrated material parameters or
canonical-state admission. Explicitly requesting unavailable plate, stress,
damage, fracture, hardness, molecular, morphology, robustness or scale-transfer
observables requires EXPAND; numerical failures require REFUSE. Export remains
restricted to freshly verified LOCAL runs.

The preservation receipt schema is `ciw.impact-crush-preservation.v1`. It binds
a MODEL initial-reference representation to a SIGNAL sampled-trace
representation with a descriptive SIMULATE morphism. Four REQUIRE obligations
cover schema integrity, contact law, plastic-state law and integrator equations;
14 BOUND effects retain numerical history, aggregate and refinement acceptance
with observable-specific SI thresholds. FORGET effects explicitly record the
twelve unavailable expansion properties. `NUMERICAL_BOUND` describes acceptance
of sampled histories and aggregates in this retained run; it is not a rigorous
error bound, FORMAL_PROOF, continuum or cross-scale validation. A passing LOCAL
run is ELIGIBLE for its numerical loss policy. EXPAND remains REFUSED by the
typed eligibility gate because a requested property is absent. Eligibility
never performs canonical-state admission.

Existing `net impact` elastic commands keep their original law and contract.
This profile is addressed explicitly through `net impact crush`:

```sh
net impact crush example --output impact-crush-request.json
net impact crush run impact-crush-request.json --output-dir impact-crush-run
net impact crush inspect impact-crush-run
net impact crush verify impact-crush-run
net impact crush export impact-crush-run --output impact-crush-observations.csv
```

The generated JSON supplies a complete current request. `run` requires a
new output directory and retains `request.json`, `workspace.json`,
`verification.json` and `preservation.json`, alongside the original Session's
source, execution and result records. `inspect` checks retained structure and bindings;
`verify` independently recomputes arithmetic from the retained inputs and
observations without rerunning the solver or rewriting the run. Export creates
a new CSV after fresh verification and refuses overwrite. Its primary-trace
columns are `time_s`, `compression_m`, `velocity_m_per_s`, `force_n`,
`plastic_compression_m` and `plastic_work_j`. Re-verification does not create a
new solver execution or verification occurrence. No external MOOSE runtime or
provider integration is implemented by this benchmark.

## Edge and rejection fixtures

| Fixture | Required behavior |
| --- | --- |
| Impact below yield | Elastic V1 limit; zero residual compression and plastic work |
| Exact yield threshold | Analytic zero-duration plateau; elastic release and restitution `1`; numerical plastic overshoot remains tolerance-checked |
| Just above threshold | Continuous result with nonnegative, small plastic work |
| Clearly yielded impact | Plateau force, permanent compression and restitution below `1` |
| Yielded unloading | Frozen `p`; declining nonnegative force; release at `q = p` |
| Separated flight | Zero force, frozen `p`, constant outward velocity |
| Long plastic plateau | Ratio below `0.2` is refused; accepted profiles remain independently accuracy-checked |
| Zero/negative mass, stiffness, yield force or incoming speed | Refuse current positive-impact parameter domain |
| Nonfinite input or overflowing derived scale | Refuse rather than silently rescale |
| Decreasing or overwritten plastic state | Independent state/history audit fails |
| Force above `F_y` or attractive force | Constitutive and force-sign audits fail |
| Plastic work assigned during elastic unloading | Work/history audit fails |
| `q = 0` reported as yielded release | Release audit fails |
| Modified force, velocity, `p` or work observation | Retained identity and/or independent arithmetic checks fail |
| Unsupported physical observable | EXPAND with unavailable property retained explicitly |

As `F_y` tends to zero, yielded travel and contact duration diverge in this
unlimited-stroke model. A zero yield force does not provide a meaningful
finite-duration impact benchmark. As `F_y` exceeds the elastic peak force, the
profile reduces to the elastic benchmark. Neither limit supplies a physical
finite-crush-capacity model.

## Physical qualification and future extensions

A physical crush or polymer plate experiment requires calibrated force and
motion measurements, specimen identity and measured geometry, striker/support
configuration, temperature, conditioning, processing and morphology history,
timebase, bandwidth/filtering and uncertainty. A force-based element law cannot
predict a spatial stress field or crack location. Rate dependence, hardening,
densification, finite stroke and failure each need an explicitly qualified law
and evidence in the relevant domain.

For a real structure, striker kinetic-energy loss may also enter specimen
motion, fixture deformation, recoverable strain energy, friction, fracture,
thermal processes and unresolved vibrations. The simple benchmark's equality
between final striker energy loss and `D` follows from its declared ideal
assumptions. It is not a general experimental attribution rule.

Linking a molecular or morphology model to this element requires a declared
state/parameter map, mapped loading, observables, validity domain, uncertainty
and independently qualifying evidence. Analytic-versus-numerical agreement for
the same reduced model does not establish a molecular/component preservation
square or an inverse molecular identification.

## Primary references and derivation status

- [MOOSE: Radial Return Stress Update](https://mooseframework.inl.gov/source/materials/RadialReturnStressUpdate.html)
  documents elastic trial states and plastic correction to a yield surface.
  [Isotropic Plasticity Stress Update](https://mooseframework.inl.gov/source/materials/IsotropicPlasticityStressUpdate.html)
  documents stateful plastic strain and its constitutive integration. These
  sources support the general return-mapping principle; the scalar unilateral
  law, phase solutions and energy/impulse equations above are direct
  derivations for this benchmark, not a claim of MOOSE J2 equivalence.
- [NIST: Polymer Mechanics](https://www.nist.gov/programs-projects/polymer-mechanics)
  describes hierarchy-dependent dissipation, deformation-rate sensitivity and
  instrumented impact measurements. It supports keeping synthetic element
  qualification separate from measured polymer response.
- [NIST: Metrologies for Non-linear Materials in Impact Mitigation](https://www.nist.gov/programs-projects/metrologies-non-linear-materials-impact-mitigation)
  identifies nonlinear, temperature-, strain- and rate-dependent material
  response and the need to connect architecture, measurement and modeling.

These references establish context and existing scientific methods. They do not
validate the default numerical parameters as a particular polymer, device,
specimen or manufactured structure.
