# Thermofluids reference tools

`net thermofluids` adds executable reference calculations for five areas of NET's
tool set. These are bounded, steady-state analytical models with retained
inputs and results. The subject labels describe the areas being extended;
they do not claim that a complete advanced CFD or thermal design suite has
been implemented.

| Requested area | Executable profile | Useful first application |
| --- | --- | --- |
| Convective Heat Transfer | `convection` | Local heat transfer coefficient and heat flux in developed laminar circular-tube flow |
| Advanced Heat Transfer / Advanced Thermofluids Design | `heat-exchanger` | Counterflow or parallel-flow heat exchanger duty and outlet temperatures |
| Advanced Fluid Dynamics | `pipe-flow` | Laminar pipe pressure loss, wall shear and centerline velocity |
| Radiative Heat Transfer, including energy and building systems | `radiation` | Thermal radiation between large facing opaque surfaces |
| Two-Phase Flow and Heat Transfer | `two-phase` | Saturated homogeneous mixture properties and latent heat duty |

These profiles extend the existing [fluid dynamics instrument](FLUID_DYNAMICS.md)
and [polymer processing work](POLYMER_PROCESSING.md). The fluid instrument's
time-dependent reservoir and wave models retain their separate scopes. There
is no automatic coupling between instruments in this increment.

## Run, inspect and replay

Install this checkout using `python -m pip install .`, then use a writable
investigation directory:

```sh
net thermofluids catalog
net thermofluids example --profile convection --output convection-request.json
net thermofluids run convection-request.json --output convection-run.json
net thermofluids inspect convection-run.json
net thermofluids verify convection-run.json --output convection-verification.json
net thermofluids replay convection-run.json --output convection-replay.json
```

Choose `heat-exchanger`, `pipe-flow`, `radiation` or `two-phase` with the same
`example` command to obtain an editable declaration for that profile. Generated
examples are synthetic demonstrations. Their property values are declared
inputs, not a property database or material certification.

Use the generated declaration as the input schema. Numeric quantities use SI:
metres, seconds, kilograms, pascals, kelvin, watts and joules. Temperatures are
absolute kelvin; a temperature difference has the same numerical magnitude in
kelvin and degrees Celsius, but absolute values are not interchangeable.

Each request has exactly `schema`, `profile`, `input_semantics` and
`parameters`. The schema is `ciw.thermofluids-request.v1`; input semantics must
be `synthetic` or `declared`. A declared input is not a measured or admitted
observation. Unknown or missing parameter keys are rejected.

## Scientific scope

### Convection

For a Newtonian, incompressible fluid with constant properties in a circular
tube, the fully developed laminar reference is

```math
Re=\frac{\rho\bar uD}{\mu},\quad Pr=\frac{\mu c_p}{k},\quad
Nu=\frac{hD}{k}.
```

The fixed-wall-temperature profile uses `Nu = 3.66`; the uniform-wall-heat-flux
profile uses `Nu = 48/11` (approximately 4.36). Set `boundary_condition` to
`constant-wall-temperature` or `constant-wall-heat-flux` explicitly.
The tool returns the local coefficient `h = Nu k/D`
and local heat flux `q'' = h (Twall - Tbulk)`. It does not integrate a heated
segment or calculate outlet temperature. A uniform wall heat flux generally
implies a varying wall temperature; the declared temperatures refer to the
evaluated section.

The [IIT Kharagpur NPTEL derivation](https://archive.nptel.ac.in/content/storage2/courses/103105052/AdvHeatMass_L_29.pdf)
gives the two limits, constant-property assumptions and entrance estimates.
They do not apply to a developing thermal boundary layer or arbitrary channel
shape.

The source's common entrance estimates are `Lh ≈ 0.05 Re D` and
`Lt ≈ 0.05 Re Pr D`. NET deliberately applies larger screening distances:
`Lh,screen = max(10 D, 0.1 Re D)` and
`Lt,screen = max(10 D, 0.1 Re Pr D)`. These are implementation screening
rules, not independently validated entrance correlations. The declaration
separately supplies `axial_distance_from_inlet_m` and
`heated_distance_to_section_m`; both must meet their respective screens,
and the heated distance cannot exceed the distance from the inlet.
A long total pipe does not make its entire entrance-to-exit heat transfer
fully developed.

The implemented envelope is `1 ≤ Re ≤ 2000`, `0.1 ≤ Pr ≤ 1000` and
`100 ≤ Pe = Re Pr ≤ 2,000,000`. The Peclet cutoff screens out requests where
neglecting axial conduction is particularly questionable. These finite bounds
do not establish that all accepted material properties or apparatuses are
physically consistent.

This profile excludes natural/mixed convection, non-Newtonian melts, entrance
enhancement, viscous heating, temperature-dependent properties, boiling and
conjugate wall conduction.

### Heat exchanger design

For steady flow with constant heat capacities, define `Ch = mdot_h cp_h`,
`Cc = mdot_c cp_c`, `Cmin = min(Ch,Cc)`, `Cr = Cmin/Cmax`, and
`NTU = UA/Cmin`. The implemented arrangements use

```math
\epsilon_{counter}=\frac{1-\exp[-NTU(1-C_r)]}
 {1-C_r\exp[-NTU(1-C_r)]},\qquad
\epsilon_{parallel}=\frac{1-\exp[-NTU(1+C_r)]}{1+C_r}.
```

At `Cr = 1`, counterflow uses the finite limit `NTU/(1+NTU)`.
Heat duty is `Qdot = epsilon Cmin (Th,in - Tc,in)`; the outlet temperatures
follow from each stream's energy balance. These relationships are documented
in the official
[EnergyPlus engineering reference](https://energyplus.readthedocs.io/en/latest/guides/engineering-reference/16.8-heat-exchangers.html#plant-loop-fluid-to-fluid-heat-exchanger).

`UA` is a declared conductance, not a fitted output or inferred geometry.
Select `arrangement` as `counterflow` or `parallel-flow`. Both mass flows and
heat capacities must be positive, `Th,in ≥ Tc,in`, and `0 ≤ NTU ≤ 1,000,000`.
Zero conductance and equal inlet temperatures are supported zero-duty limits.
This profile excludes external heat loss, phase change, transient storage,
pressure-drop prediction and geometry optimization. It can support a design
sweep, but supplies no unsupported optimizer or mechanical design claim.

### Pipe flow

For a straight, rigid circular tube with fully developed, steady laminar flow,
no slip and constant viscosity,

```math
\Delta p=\frac{32\mu L\bar u}{D^2},\quad
Q_v=\frac{\pi D^4\Delta p}{128\mu L},\quad
u(r)=2\bar u\left[1-(2r/D)^2\right],\quad
\tau_w=\frac{\Delta pD}{4L}.
```

The Darcy friction factor is `64/Re`; the Fanning factor is one quarter of
that. This distinction matters when comparing the result with the
[MIT Couette and Poiseuille reference](https://ocw.mit.edu/courses/2-25-advanced-fluid-mechanics-fall-2013/1a114d602956fa0dd328155f9b45f93d_MIT2_25F13_Couet_and_Pois.pdf).
The parabolic profile is an analytical field reference, not a discretized
Navier–Stokes solution. The tool reports its centerline velocity, not a sampled
radial field. `length_m` is the length of the already developed segment;
`upstream_development_length_m` must separately meet
`max(10 D, 0.1 Re D)`, with `1 ≤ Re ≤ 2000`. The reported hydraulic pumping
power is `Delta p Qv`; it does not include pump or motor inefficiency.
Entrance loss, fittings, roughness, turbulence,
compressibility, non-Newtonian flow and elevation head are excluded.

### Radiation for energy and building systems

For two isothermal, opaque, diffuse-gray surfaces forming the parallel-plate
limit with view factor one,

```math
q''_{1\to2}=\frac{\sigma(T_1^4-T_2^4)}
 {1/\epsilon_1+1/\epsilon_2-1},\qquad \dot Q=Aq''_{1\to2}.
```

The [MIT radiation derivation](https://web.mit.edu/16.unified/www/FALL/thermodynamics/notes/node136.html)
provides this exchange relation. Positive output denotes transfer from
surface 1 to surface 2; reversing their temperatures reverses the sign.
The implementation uses the equivalent factorization
`hrad = epsilon_eff sigma (T1+T2)(T1²+T2²)` and `q'' = hrad (T1-T2)`.
This remains finite at equal temperatures. Each emissivity must be in
`[1e-12, 1]`; perfectly reflecting zero-emissivity surfaces are outside this
implementation.

The calculation can represent an idealized radiant panel or longwave exchange
across a large, thin envelope cavity. Conductive and convective cavity heat
transfer must be evaluated separately. Finite-edge view factors, transparent
glazing, shortwave sunlight, participating gases, spectral emissivity,
sky radiation and whole-building energy performance are outside this profile.
The gray model integrates thermal emission over all wavelengths; the dominant
emission wavelength changes with temperature. The numerical temperature
envelope does not establish a material's emissivity or the spectral validity of
a longwave building-surface approximation.

### Two-phase mixture and latent heat

For a saturated liquid–vapor mixture with mass quality `x`, the homogeneous
model assumes equal phase velocities. Given coexisting-phase densities,

```math
\rho_m^{-1}=x/\rho_v+(1-x)/\rho_l,\qquad
\alpha=\frac{x/\rho_v}{x/\rho_v+(1-x)/\rho_l}.
```

At constant saturation pressure, `h = (1-x)hf + x hg` and `hfg = hg-hf`.
The declared inlet and outlet qualities determine the required heat duty:
`Qdot = mdot hfg (xout - xin)`. Positive duty adds heat to the mixture;
negative duty removes it. This is an energy balance between specified states,
not a prediction of wall heat transfer or achievable evaporation rate.
[MIT two-phase-flow notes](https://ocw.mit.edu/courses/22-06-engineering-of-nuclear-systems-fall-2010/2e8614e58cc569d96acff67df51d9aef_MIT22_06F10_lec13.pdf)
derive these expressions and emphasize that equal phase velocity is a
restrictive assumption.

Quality is a mass fraction; void fraction is a volume fraction. They must not
be substituted for one another. Phase properties must correspond to the same
declared saturation state. The current tool accepts properties supplied by the
caller; it does not independently establish their thermodynamic consistency.
Use a qualified property source when constructing a real case.
Both `quality_in` and `quality_out` must lie in `[0,1]`, liquid density must
exceed vapor density, and vapor enthalpy must exceed liquid enthalpy. Positive
`saturation_pressure_pa` and `saturation_temperature_k` label the declared
state; the code does not derive or cross-check one from the other. Enthalpy
reference offsets can be negative because only consistent differences drive
the energy balance.

The profile excludes slip, flow-regime prediction, nucleation, wall heat
transfer coefficients, dryout, critical heat flux and two-phase pressure drop.
It rejects input qualities outside `[0,1]` instead of silently clipping them
or inventing superheated/subcooled properties.

## Guardrails and retained meaning

The models reject malformed and nonfinite values, nonphysical material or
geometry parameters, incompatible declarations and requests outside their
implemented domains. Laminar-domain cutoffs are conservative tool policies,
not claims that turbulence begins at one universal Reynolds number. A valid
input does not establish that an actual apparatus satisfies the assumptions.

All numeric intervals below are inclusive and are numerical input envelopes,
not material-property validity claims:

| Input category | Accepted interval |
| --- | --- |
| Absolute temperatures, including saturation temperature | 1–3000 K |
| Vapor mass qualities | 0–1 |
| Emissivities | `1e-12`–1 |
| Specific phase enthalpies | `-1e12`–`1e12` J/kg |
| Exchanger `ua_w_k` | 0–`1e12` W/K |
| Other numeric parameters | `1e-12`–`1e12`, in each field's specified SI unit |

The profile-specific dimensionless and cross-field checks above apply in
addition to these intervals. Finite values alone cannot verify an equation of
state, phase stability, surface optics or the constancy of transport properties.

Input evidence, operation, execution and verification identities remain
separate. Numerical outputs remain modeled predictions; recording or replaying
them does not admit them as observed state or authorize physical actuation.
Changing a model input requires a new run.

Inspection checks record structure, content binding and declared scope without
a fresh numerical calculation. Verification creates a new verification identity
and checks exact recomputation with the same source fingerprints and Python
version; changed runtime identity is refused. Replay requires that check and
performs a fresh execution from the retained declaration, retaining a link to
the original run while assigning new execution and result identities.
Both use the implemented models: same-implementation recomputation is not
independent scientific validation. Hashes establish binding and integrity
within the record; they do not establish measurement truth, third-party trust
or calibrated uncertainty.

Analytical limits, conservation checks, domain rejection and installed-command
tests qualify the software within this scope. Physical validation requires
independent measurements with traceable geometry, property data, boundary
conditions, sensor calibration and uncertainty. Calibration and held-out
validation cases should be kept separate.

For installed-command qualification, first install the package, then run:

```sh
python scripts/check_thermofluids_installed.py --output-dir thermofluids-qualification
```

The script launches `python -I -m ciw.net` in a temporary directory outside the
checkout. It exercises all five profiles, retained inspection, fresh verification,
replay, unchanged source files, overwrite refusal and malformed-input refusal.
The output directory must not already exist. Successful qualification preserves
the run artifacts and a JSON summary there. This tests the installed command
lifecycle; it is not independent scientific or experimental validation.

## Extending the suite

Add each new capability as a declared workload with its own applicability
limits, property provenance, output semantics and independent check:

| Extension | Evidence needed before claiming availability |
| --- | --- |
| Turbulent and natural convection | Named correlation, geometry and regime bounds, benchmark data |
| Conjugate heat transfer and transient conduction | Conservation across interfaces, time/mesh convergence, reference solutions |
| Resolved advanced fluid dynamics | Qualified solver adapter, boundary-condition contract, mesh studies and benchmark comparisons |
| Radiation enclosures and building energy | Reciprocal and closed view-factor matrix, enclosure energy balance, optical/spectral assumptions |
| Boiling, condensation and two-phase dynamics | Property provider, regime-specific closures, slip/phase balances, held-out experiments |

The existing evidence and execution substrate remains the common interface;
these workloads do not need separate state authorities.
