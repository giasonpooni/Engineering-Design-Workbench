# Atmospheric compiler and engine

NET's first atmospheric engine compiles a declared dry-air column into a
retained, independently verified environmental profile. Reference temperature,
reference pressure, a constant lapse rate, ordered query heights and a declared
constant wind define the model. This provides usable environmental boundary
data for engineering workloads while preserving NET's existing Session,
evidence, operation, execution, verification and admission boundaries.

The model scope is `dry_hydrostatic_constant_gravity_column`. It is a configured
atmospheric state, rather than a weather forecast or a time-evolving fluid
simulation. Its default source is explicitly synthetic. Numerical agreement
with the declared equations does not establish agreement with measurements at
a location or time.

## Physical model and height convention

Let `z` be height above the configured reference origin. The origin supplies
`T0` and `p0`; query heights are relative distances in metres. Changing an
origin label does not perform a geoid, terrain, latitude or geometric-to-
geopotential coordinate transformation. Constant gravity makes this a local
constant-gravity column approximation.

The prescribed temperature profile and hydrostatic ideal-gas equations are

$$
T(z)=T_0-Lz,\qquad
\frac{dp}{dz}=-\rho g,\qquad
\rho(z)=\frac{p(z)}{R T(z)}.
$$

Here `L` is a positive downward temperature lapse rate in K/m. The request
allows `0 <= L <= 0.009`; zero gives an isothermal column. `T0` lies in
`250..330 K`, `p0` in `50000..120000 Pa`, and requested relative heights in
`0..11000 m`. Every requested temperature must remain at least `180 K`.
Heights are strictly increasing, start at zero and the bounded profile admits
2..129 samples. These are model and computational limits, not a geographic forecast
domain or an experimentally established validity range for every atmosphere.

The fixed dry-air constants are

| Constant | Value | SI unit |
| --- | --- | --- |
| `g` | `9.80665` | m/s² |
| `R` | `287.05` | J/(kg K) |
| `gamma` | `1.4` | 1 |
| `cp = gamma R / (gamma - 1)` | `1004.675` | J/(kg K) |
| Potential-temperature reference pressure | `100000` | Pa |
| Sutherland reference temperature | `273.15` | K |
| Sutherland reference viscosity | `1.716e-5` | Pa s |
| Sutherland temperature offset | `110.4` | K |

NASA's atmospheric model documentation explains the altitude dependence of
temperature, pressure and density, and its use in aerodynamic calculations.
The NET profile solves the declared idealized column equations; it does not
claim to reproduce NASA's separate piecewise atmospheric curve fits or the
complete U.S. Standard Atmosphere.
[NASA: Earth Atmosphere Equation, Metric](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/earth-atmosphere-equation-metric/).
The hydrostatic balance itself is also stated in
[NOAA GFDL: Radiative-convective equilibrium](https://www.gfdl.noaa.gov/blog_held/19-radiative-convective-equilibrium/).

## Request and retained profile contracts

The request schema is `ciw.atmosphere-request.v1`. Its exact top-level keys are
`schema`, `scope`, `reference`, `profile`, `sampling`, `desired_observables` and
`tolerances`. Unknown fields, nonfinite numbers, boolean aliases for numeric
values, unordered/repeated heights and unsupported declarations are rejected.

| Request group | Fields and contract |
| --- | --- |
| `reference` | `temperature_k`, `pressure_pa`, `height_origin_m`, `frame`, `context` |
| `reference.height_origin_m` | A declared origin in `-500..10000 m`; no coordinate transform is inferred |
| `reference.frame` | Exactly `atmosphere.local_enu.v1` |
| `reference.context` | `source_kind`, `source_ref`, `valid_time_utc` |
| Source context | Kind `synthetic` or `declared_environment`; nonempty reference of at most 160 characters; UTC ISO timestamp or null |
| `profile` | `lapse_rate_k_per_m`, three-component `wind_enu_m_per_s`, `composition: dry_air`, `gravity_m_per_s2: 9.80665` |
| `sampling` | `height_m`, `interpretation: height_above_reference` |
| `desired_observables` | Unique names from the declared supported/expansion sets |
| `tolerances` | `constitutive_relative`, `hydrostatic_relative`, `quadrature_relative`, each in `1e-12..0.01` |

`valid_time_utc` accepts a complete UTC timestamp with `Z` or `+00:00`, with an
optional fractional second of one to six digits. It records declared context;
the engine does not infer freshness or retrieve weather for that time.

The sealed result schema is `ciw.atmosphere-result.v1`, with compiler identity
`analytic_dry_hydrostatic_column_binary64`. Each declared height retains
`temperature_k`, `pressure_pa`, `density_kg_per_m3`, `sound_speed_m_per_s`,
`dynamic_viscosity_pa_s`, `kinematic_viscosity_m2_per_s`,
`potential_temperature_k` and the three-component `wind_enu_m_per_s`.
Fixed constants and exact SI units remain in the result. Result structure and
content sealing can be inspected without repeating physical calculations.

## Compilation and derived properties

For positive lapse rate, the column has the closed-form pressure solution

$$
p(z)=p_0\left(\frac{T(z)}{T_0}\right)^{g/(RL)}.
$$

For zero lapse rate the exact isothermal limit is

$$
p(z)=p_0\exp\!\left[-\frac{gz}{RT_0}\right].
$$

For a very small positive `L`, the compiler retains the limit without
subtractive cancellation. Its dimensionless logarithmic form is

$$
\log\frac{p(z)}{p_0}=-\frac{gz}{RT_0}
\frac{-\operatorname{log1p}(-x)}{x},\qquad x=\frac{Lz}{T_0}.
$$

The ratio is one at `x = 0`. This avoids dividing by a tiny `L`, including
subnormal binary64 declarations, without tolerance-based switching to a
different physical law.

Density follows the equation of state. The calorically perfect dry-air sound
speed, dynamic viscosity and kinematic viscosity are

$$
a(z)=\sqrt{\gamma R T(z)},\qquad
\mu(z)=\mu_{\rm ref}
\left(\frac{T(z)}{T_{\rm ref}}\right)^{3/2}
\frac{T_{\rm ref}+S}{T(z)+S},\qquad
\nu(z)=\frac{\mu(z)}{\rho(z)}.
$$

Absolute temperature is required in these relations. `R` is a specific gas
constant per kilogram, rather than the universal molar gas constant. Dynamic
viscosity in Pa s and kinematic viscosity in m²/s remain separate quantities.
NASA gives the ideal-gas sound-speed derivation in
[Speed of Sound Derivation](https://www.grc.nasa.gov/www/k-12/BGP/snddrv.html)
and the general Sutherland reference form in the
[Wind-US transport-property documentation](https://www.grc.nasa.gov/www/winddocs/user/files.html).
Those relations supply properties; they do not resolve flow around an object.

## Dry static stability

Potential temperature is computed using the fixed reference pressure
`p_theta = 100000 Pa`:

$$
\theta(z)=T(z)\left(\frac{p_{\theta}}{p(z)}\right)^{R/c_p}.
$$

The reference pressure used in this diagnostic differs from the configured
column-origin pressure `p0`. It is a conventional comparison pressure, not an
additional atmospheric boundary condition.

Combining the declared hydrostatic and temperature equations gives

$$
\frac{d\log\theta}{dz}=
\frac{g/c_p-L}{T(z)},\qquad
N^2(z)=g\frac{g/c_p-L}{T(z)}.
$$

The dry adiabatic lapse rate from the fixed constants is approximately
`0.009761017 K/m`. The allowed maximum `0.009 K/m` therefore gives positive
dry static stability throughout the admissible temperature domain. Increasing
potential temperature with height is the corresponding dry stability test.
This says nothing about moist instability, shear instability, turbulence,
mixing rates or resolved convective motion. NOAA describes interpretation of
potential-temperature profiles in
[READY: Potential temperature versus height](https://www.ready.noaa.gov/READYthetahelp.php).

## Wind and engineering handoffs

Wind is supplied as a constant east/north/up vector in the declared local ENU
frame. Its components represent the direction the air moves, rather than the
meteorological direction from which wind originates. This data is an external
declaration: the column compiler does not infer it from pressure, terrain or
observations and does not solve wind momentum, mass continuity or circulation.
In particular, a configured vertical wind is not a dynamically solved
hydrostatic circulation state.

Each wind component is bounded to `-300..300 m/s`. A downstream aerodynamic
model still checks the magnitude of body-relative flow and its own Mach and
Reynolds domain; the atmospheric input bound is not permission to apply an
incompressible drag model at every allowed wind vector.

The atmospheric profile can support explicit, separately qualified handoffs:

| Handoff | Supplied information | Additional receiving-model obligations |
| --- | --- | --- |
| Environmental boundary | Local air temperature, pressure, density, viscosity, sound speed and wind | Select the retained height, align units/frame/time and declare how the environment enters the receiving equations |
| Aerodynamic load | Local density and body-relative wind for an explicitly declared drag model | Bind body velocity, geometry, area, coefficient and the aerodynamic model's validity domain |
| Material conditioning | Ambient air state as possible evidence | Provide exposure duration, heat/mass transfer, specimen temperature, humidity and material calibration before a material-state claim |

The sealed `ciw.atmosphere-handoff.v1` environmental receipt selects one exact
retained sample for the fixed `impact`, `fluid` or `render` provider. It binds
the source evidence, result, execution, verification and freshly recomputed
report identities. The receipt records `absolute_height_m` as the declared
origin plus the relative sample height; that affine sum does not establish a
geodetic datum. Preserved fields and explicit forgotten capabilities remain
visible. The receipt performs no interpolation, force calculation, optical
scattering, provider activation or state admission, and it carries receiving-
provider validation requirements.

The first two are environmental/mechanical composition paths. The third
remains an expansion: ambient temperature does not automatically equal the
temperature of a polymer specimen, and ambient pressure or wind does not
identify morphology, processing history, crystallinity, damage or molecular
configuration. Existing impact requests retain their own physical contracts.
A handoff does not introduce rate dependence or atmospheric loading into an
impact solver whose governing equations do not contain those terms.

NASA's
[Drag Equation](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/drag-equation/)
provides the density/relative-speed/area/coefficient force relation. A chosen
drag coefficient is supplied model evidence; this atmospheric engine does not
derive it from object shape or independently validate its Reynolds- or
Mach-number range.

## Independent verification and retained identities

The compiler's pressure path is the closed-form hydrostatic solution.
Independent verification evaluates the hydrostatic integral

$$
\log\frac{p(z)}{p_0}=-\int_0^z\frac{g}{R[T_0-L\zeta]}\,d\zeta
$$

by bounded numerical quadrature. Constitutive checks separately assess the
temperature declaration, ideal-gas density, sound speed, Sutherland viscosity,
kinematic viscosity and potential-temperature stability. Numerical verification
establishes agreement with these declared relationships and tolerances; it is
not validation against a radiosonde, station record or forecast analysis.

The independent report schema is `ciw.atmosphere-verification.v1`, with 17
checks. Composite Simpson integration uses 16 subintervals per declared height
segment for the coarse rule and 32 for the refined rule. Each segment uses 50
integrand evaluations, so the maximum 128 segments use 6400 evaluations.
Segment hydrostatic balance, cumulative pressure reconstruction and coarse/
refined pressure agreement are distinct checks. The comparison of two finite
quadrature rules is a numerical acceptance test, not a certified integration-
error bound or a continuum-convergence proof.

The selected height grid controls quadrature segmentation as well as retained
output locations. A valid two-point declaration spanning a steep long column
can fail the requested quadrature tolerance even when the compiler's analytic
pressure is correct. More declared height samples can improve the independent
quadrature comparison. The engine retains that failure rather than adapting
the rule or loosening a tolerance silently.

The retained source declaration, model request, compilation operation,
execution, resulting profile, verification report and eligibility record keep
distinct content bindings. A changed origin, source reference, valid time,
wind or model declaration changes the corresponding retained identity. A
source label records provenance claims; it does not authenticate external
measurements or grant canonical admission.

The sealed `ciw.atmosphere-preservation.v1` bridge uses the existing typed
MODEL-to-SIGNAL preservation contract, verification and gate APIs. BOUND
effects name the corresponding numerical report thresholds; REQUIRE effects
include all 17 checks, a PASS report and LOCAL qualification. FORGET effects
make omitted continuous-height, horizontal, temporal, aerodynamic, optical and
material capabilities explicit. These finite sampled bounds do not grant
physical validation or canonical admission.

Static inspection validates retained structure and identity bindings without
replaying the compiler or verifier. Fresh verification operates on retained
candidate values. Qualified export and handoffs require current LOCAL
verification of the selected profile. The existing Session substrate owns
retention and dispatch; saving a JSON request does not register executable
providers.

`LOCAL` means the requested supported quantities passed their numerical
checks within this dry-column contract. `EXPAND` means a requested capability
needs additional model or evidence support after the supported checks pass.
`REFUSE` retains a failed or invalid qualification without relabeling it as a
verified environmental state. Eligibility remains separate from admission.

Supported observables are `temperature`, `pressure`, `density`, `sound_speed`,
`viscosity`, `wind`, `potential_temperature` and `hydrostatic_profile`.
Declared expansion observables include `humidity`, `precipitation`, `clouds`,
`turbulence`, `weather_forecast`, `radiation`, `chemical_reactions`,
`visual_scattering`, `material_conditioning` and `fluid_dynamics`.

## Extension and physical validation path

This engine provides a concrete atmospheric provider on the existing NET
substrate. Additional providers can supply humidity and moist thermodynamics,
layered or measured soundings, wind shear, turbulence, thermal/radiative
exchange, aerosols, weather assimilation, or full fluid dynamics. Each needs
its own state variables, governing equations, frame/time mappings, uncertainty
and independently tested composition contract. A configured graph selects
and connects those providers; graph composition alone does not validate their
physical predictions.

Physical validation starts with paired, time- and location-bound measurements
of height, pressure and temperature, with sensor calibration and uncertainty.
Density, humidity and wind observations then test the adequacy of the dry and
constant-wind assumptions. Aerodynamic use additionally needs geometry and
force measurements under relevant flow conditions. Polymer use needs specimen
temperature and conditioning history plus a calibrated receiving constitutive
model. Preserve those independent evidence and validation scopes when the
atmospheric profile is reused across manufacturing, impact mechanics and
simulation applications.

See [the executable atmospheric example](../examples/atmosphere/README.md).
