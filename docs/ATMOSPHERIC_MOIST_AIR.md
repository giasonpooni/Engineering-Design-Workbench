# Unsaturated moist-air atmospheric column

The moist-air extension compiles a prescribed mixture of dry air and water
vapour into a retained hydrostatic column. It adds explicit composition,
water-vapour pressure, relative humidity and liquid-water dewpoint diagnostics
to NET's existing atmospheric workflow. The dry atmospheric profile retains
its own contracts and qualified laws.

The model is an ideal, calorically perfect gas mixture with constant water
mixing ratio, constant gravity, a prescribed linear temperature profile and
declared constant ENU wind. Constant composition is a configured well-mixed
column assumption; the compiler does not solve species diffusion, turbulent
mixing, evaporation or a molecular equilibrium profile. Numerical verification
qualifies agreement with these equations. Location, timestamp and source
context remain declarations until separate observations validate them.

The request schema is `ciw.atmosphere-moist-request.v1`; its claim scope is
`unsaturated_constant_mixing_ratio_hydrostatic_column`. The result schema is
`ciw.atmosphere-moist-result.v1`, with compiler identity
`analytic_frozen_composition_moist_column_binary64`. The separate verification
report schema is `ciw.atmosphere-moist-verification.v1`.

## Bounded declaration

The exact request groups are `schema`, `scope`, `reference`, `profile`,
`sampling`, `desired_observables` and `tolerances`. The moist declaration uses
`profile.composition: dry_air_water_vapour` and explicitly supplies
`water_mixing_ratio_kg_per_kg_dry_air`. Missing fields, unknown fields,
nonfinite values, boolean numeric aliases and repeated heights are refused.

| Quantity | Declared domain |
| --- | --- |
| Reference temperature | `293.15..308.15 K` |
| Reference total pressure | `80000..110000 Pa` |
| Reference height-origin label | `-500..10000 m`; no inferred coordinate transform |
| Relative query height | `0..2000 m`; `2..129` increasing samples starting at zero |
| Prescribed lapse rate | `0..0.0065 K/m` |
| Ambient temperature | At least `273.15 K` throughout the column |
| Water mass per dry-air mass | Exactly zero, or `0.002..0.02 kg/kg dry air` |
| Nonzero-water liquid-equilibrium dewpoint | `253.15..308.15 K` |
| Pure-phase relative-humidity fraction | At most `0.95` throughout the column |
| Declared ENU wind components | Each `-300..300 m/s` |
| Constitutive, hydrostatic and quadrature relative tolerances | Each `1e-12..0.01` |

These limits bound this provider's supported declarations and qualification;
they do not assert that atmospheric water below `0.002 kg/kg` is impossible.
Temperature, pressure and mixing-ratio bounds alone do not guarantee an
unsaturated column. The verifier retains a failed humidity-domain candidate
as REFUSE evidence rather than clipping humidity or inventing condensed water.

## Composition and thermodynamic state

Water-vapour mixing ratio `r` is kilograms of vapour per kilogram of dry air.
It differs from specific humidity `q`, which is kilograms of vapour per
kilogram of the entire gas mixture:

$$
r=\frac{m_v}{m_d},\qquad q=\frac{r}{1+r}.
$$

Let `Rd` and `Rv` be the dry-air and water-vapour specific gas constants. Their
ratio is `epsilon = Rd / Rv`. Total gas pressure `p` is the sum of dry-air
partial pressure `pd` and water-vapour partial pressure `e`. For the declared
ideal mixture,

$$
e=\frac{rp}{\epsilon+r},\qquad p_d=p-e,
\qquad R_m=\frac{R_d+rR_v}{1+r}.
$$

The mixture density can be computed from its specific gas constant or from
the two partial densities:

$$
\rho=\frac{p}{R_mT}
=\frac{p-e}{R_dT}+\frac{e}{R_vT}
=\rho_d+\rho_v.
$$

The independent verifier can compare these two forms and check the retained
mixing ratio through `rho_v / rho_d`. It must use mass mixing ratio rather
than substituting specific humidity into the partial-pressure formula.
At the same total pressure and temperature, water vapour increases `Rm` and
lowers mixture density within this composition domain.

Calorically perfect component heat capacities give

$$
c_{p,m}=\frac{c_{p,d}+rc_{p,v}}{1+r},\qquad
c_{v,m}=c_{p,m}-R_m,\qquad
\gamma_m=\frac{c_{p,m}}{c_{v,m}},\qquad
a=\sqrt{\gamma_m R_m T}.
$$

This sound speed describes the declared gas with composition frozen during
the acoustic perturbation. It does not resolve acoustic attenuation,
frequency-dependent molecular relaxation or phase-change effects.
Fixed heat capacities are model constants rather than temperature-dependent
thermochemical fits. A small numerical tolerance establishes agreement with
the declared constants, not the accuracy of that physical approximation.

| Constant | Retained value | SI unit |
| --- | --- | --- |
| Dry-air specific gas constant `Rd` | `287.05` | J/(kg K) |
| Water-vapour specific gas constant `Rv` | `461.5` | J/(kg K) |
| Dry-air heat-capacity ratio | `1.4` | 1 |
| Dry-air `cp` | `1.4 * Rd / (1.4 - 1)`, approximately `1004.675` | J/(kg K) |
| Water-vapour `cp` | `1864.53`, rounded from NIST-JANAF at `298.15 K` | J/(kg K) |
| Fixed heat-capacity reference temperature | `298.15` | K |
| Constant gravity | `9.80665` | m/s² |
| Potential-temperature reference pressure | `100000` | Pa |

The mixture retains `r`, `q`, `Rm`, `cp,m`, `cv,m` and `gamma,m` separately.
At zero water content, the shared pressure, temperature, density and sound
speed recover the previous dry-gas law exactly. The moist schema still omits
viscosity; zero water does not change its declared operation into the dry
transport provider.

## Prescribed hydrostatic column

Height `z` is measured above the configured reference origin. The origin
supplies `T0` and `p0`; its label does not perform a geodetic or
geometric-to-geopotential transformation. With `L >= 0`,

$$
T(z)=T_0-Lz,\qquad\frac{dp}{dz}=-\rho g
=-\frac{pg}{R_mT}.
$$

Because `r` and therefore `Rm` are constant, positive lapse rate gives

$$
p(z)=p_0\left(\frac{T(z)}{T_0}\right)^{g/(R_mL)}.
$$

The zero-lapse solution is

$$
p(z)=p_0\exp\left(-\frac{gz}{R_mT_0}\right).
$$

The stable `log1p` form of the positive-lapse solution preserves the
isothermal limit for arbitrarily small positive binary64 lapse declarations.
Prescribing `T` does not solve an atmospheric energy balance or latent-heat
feedback. Declared wind likewise supplies environmental data rather than a
solution of atmospheric momentum or mass-continuity equations.

The retained frozen-composition potential temperature is

$$
\theta_f=T\left(\frac{100000\ {\rm Pa}}p\right)^{R_m/c_{p,m}}.
$$

It compares a parcel under an ideal adiabatic transformation with its water
content held fixed and without condensation. It is not equivalent potential
temperature, a moist-adiabatic ascent model or a cloud/convection forecast.
The diagnostic reference pressure differs from the configured `p0` whenever
the column's origin pressure is not `100000 Pa`.

For this fixed-composition parcel model,

$$
\frac{d\log\theta_f}{dz}=\frac{g/c_{p,m}-L}{T},\qquad
N_f^2=g\frac{g/c_{p,m}-L}{T}.
$$

The verifier checks the frozen-composition lapse domain and increasing
retained `theta_f`. This is a static stability diagnostic under the stated
parcel law; shear, condensation and variable-composition instability remain
outside that qualification.

## Liquid-water saturation diagnostic

The saturation reference is the pure-phase Magnus approximation over liquid
water. In SI pressure units, with `t = T - 273.15` in degrees Celsius,

$$
e_s(T)=611.2\exp\left(\frac{17.62t}{243.12+t}\right)\ {\rm Pa},
\qquad H(T,p,r)=\frac{e}{e_s(T)}.
$$

`H` is a dimensionless relative-humidity fraction; `0.95` means 95%, not
0.95%. WMO-No. 8 lists this pure-water approximation separately from its
pressure-dependent moist-air enhancement factor. This extension explicitly
uses the pure-phase reference and omits that enhancement. It therefore does
not claim to implement the complete WMO thermodynamic moist-air saturation
definition. The hard humidity guard applies to the declared approximation.

For `r > 0`, invert the same law using `y = log(e / 611.2 Pa)`:

$$
T_d=273.15+\frac{243.12y}{17.62-y}.
$$

This is a liquid-water dewpoint diagnostic. If its temperature is below
freezing, it remains relative to liquid water; it is not a frost point or an
ice-nucleation prediction. The ambient and diagnostic temperature domains
must each remain inside their declared bounds. At `r = 0`, vapour pressure,
vapour density, specific humidity and relative humidity are zero, while
dewpoint is `null`. No finite dewpoint or fabricated logarithmic limit is
reported for a gas containing no water vapour.

## Continuous humidity-domain check

A sampled profile needs a humidity qualification over the entire declared
column, including heights between retained samples. For this particular law
and domain, the maximum can be found exactly from the two endpoints.

For nonzero water content, set `aM = 17.62`, `bM = 243.12 K` and
`d = 273.15 K - bM = 30.03 K`. Since `e / p` is constant,

$$
\frac{d\log H}{dz}
=-\frac{g}{R_mT}
+\frac{L a_M b_M}{(T-d)^2}.
$$

The derivative is positive exactly when

$$
L>L_{\rm crit}(T),\qquad
L_{\rm crit}(T)=\frac{g(T-d)^2}{R_ma_Mb_MT}.
$$

For `T > d`,

$$
\frac{dL_{\rm crit}}{dT}
=\frac{g}{R_ma_Mb_M}\left(1-\frac{d^2}{T^2}\right)>0.
$$

Temperature decreases or stays constant as height increases. Consequently
the humidity derivative can cross zero only from negative to positive;
every interior stationary point is a minimum. Isothermal humidity decreases
with height. Throughout the declared above-freezing ambient domain,

$$
\max_{0\le z\le z_{\max}}H(z)
=\max\bigl(H(0),H(z_{\max})\bigr).
$$

Checking only the top endpoint would miss a too-humid reference state in an
isothermal or weak-lapse column. Checking both endpoints covers all heights
under these assumptions, regardless of sampling density. A changed lapse
sign, composition profile or saturation law requires a new domain proof.
The `0.95` ceiling is a hard model boundary and cannot be enlarged by a
numerical tolerance or by requesting an unsupported observable.

At zero water content, relative humidity is identically zero and no logarithm
of humidity is needed. For positive water content, vapour pressure decreases
with hydrostatic total pressure and its inverse Magnus dewpoint decreases
with height. The endpoint dewpoints therefore also bound the entire declared
column's dewpoint-temperature range.

## Independent numerical verification

The verifier identity is
`independent_composite_simpson_frozen_moist_hydrostatic_binary64`.
It evaluates constitutive relations independently and integrates
`g / (Rm T)` over each declared height interval using composite Simpson rules
with 16 and 32 subintervals. The report retains both cumulative pressure
references, individual interval integrals, rule-refinement residuals and the
continuous humidity reference. At most 128 height intervals use at most 6400
quadrature evaluations.

The report contains 30 checks:

| Check group | Exact check names |
| --- | --- |
| Prescribed inputs | `prescribed_temperature`, `prescribed_wind` |
| Mixture and pressure partition | `mixture_parameters`, `vapour_partial_pressure`, `dry_partial_pressure`, `partial_pressure_closure` |
| Density and equations of state | `dry_air_equation_of_state`, `water_vapour_equation_of_state`, `density_closure`, `equation_of_state` |
| Humidity diagnostics | `relative_humidity`, `liquid_water_saturation_pressure`, `dew_point_closure` |
| Frozen parcel properties | `frozen_sound_speed`, `frozen_potential_temperature` |
| Reference boundaries | `boundary_temperature`, `boundary_pressure` |
| Hard state and domain conditions | `positive_properties`, `declared_temperature_domain`, `declared_dew_point_domain`, `sampled_unsaturation`, `continuous_unsaturation`, `dry_limit_water_state` |
| Monotonicity and frozen stability | `pressure_monotonicity`, `frozen_potential_temperature_stability`, `frozen_stability_domain` |
| Hydrostatic reference and computation | `segment_hydrostatic_balance`, `cumulative_pressure_profile`, `quadrature_refinement`, `quadrature_budget` |

The endpoint-maximum proof covers the declared continuous law, while a
separate conservative guard controls numerical pressure error near the hard
humidity ceiling. A nominal Simpson pressure can slightly underestimate
pressure and humidity, so finite-rule agreement alone cannot establish
unsaturation. The guard uses the signed composite Simpson remainder for
`f(z) = g / (Rm T(z))`:

$$
f^{(4)}(z)=\frac{24gL^4}{R_mT(z)^5}\ge0.
$$

For a height interval of width `Delta z`, let `h = Delta z / 32`, let `S` be
its refined Simpson integral and let `Tmin` be its upper-height temperature.
The [NIST DLMF composite Simpson remainder](https://dlmf.nist.gov/3.5#E8)
gives the real-arithmetic enclosure

$$
S-E\le\int f(z)\,dz\le S,\qquad
E=\frac{\Delta z}{180}h^4\frac{24gL^4}{R_mT_{\min}^5}.
$$

The implementation additionally subtracts a fixed binary64 integral
allowance and propagates the resulting lower integral bounds into upper
pressures and upper humidity fractions:

$$
I_{\rm low}=\max\left(0,S-E-\delta_I\max(1,|S|)\right),
$$

$$
\overline p(z_i)=p_0\exp\left(-\sum_{j<i}I_{{\rm low},j}\right)(1+\delta_p),
\qquad
\overline H=\frac{r\overline p}{(\epsilon+r)e_s(T)}(1+\delta_H).
$$

Each of `deltaI`, `deltap` and `deltaH` is fixed at `1e-12`; request tolerances
cannot change them. The hard `continuous_unsaturation` check uses
`max(H_upper at the two endpoints) <= 0.95`. A candidate that caps its stored
humidity at `0.95` cannot bypass the independent guard. A column sufficiently
close to the ceiling can be refused conservatively even when its nominal
humidity is slightly below it.

The reference retains `integral_bound_method`, `refined_segment_error_bounds`,
`segment_integral_roundoff_allowances`, `segment_integral_lower_bounds` and
`pressure_upper_bound_pa`, with the fixed integral and pressure allowances.
Its `continuous_humidity` group retains `relative_humidity_upper_bound`,
`maximum_relative_humidity_upper_bound` and the fixed humidity allowance.
The signed remainder uses the existing refined rule and adds no integrand
evaluations.

The remainder encloses quadrature error in real arithmetic. The implemented
fixed rounding allowances do not constitute directed interval arithmetic or
a formal certificate for every binary64/libm operation. The 16/32 comparison
remains a refinement check, and neither it nor the guard measures the physical
error of the ideal-mixture or Magnus approximation.

All checks must pass for LOCAL qualification within the supported observable
set. A failed numerical or domain check takes REFUSE precedence over a desired
unsupported observable. Unsupported requested physics yields EXPAND only
after the supported candidate passes every check. Static inspection validates
schema, content seals and identity bindings without numerical replay; fresh
verification is required before a qualified export.

## Environmental use and qualification boundaries

An exact retained sample can supply temperature, pressure, component and
mixture densities, sound speed, declared wind and explicit humidity to a
receiving provider. Its identity remains linked to the request, source,
execution, result and independent verification. A successful atmospheric
handoff does not validate the receiving model or admit a canonical state.

The typed preservation receipt has schema
`ciw.atmosphere-moist-preservation.v1`. It uses the existing MODEL-to-SIGNAL
contracts and requires all 30 report checks plus LOCAL qualification. Its
recommendation can be ELIGIBLE, while admission remains a separate action.
The exact-sample handoff schema is `ciw.atmosphere-moist-handoff.v1`.

All three fixed receiving providers retain temperature, pressure, mixture
density, wind, `r`, `q`, vapour pressure, relative humidity and liquid-water
dewpoint. Impact and fluid receipts additionally retain frozen sound speed;
fluid receipts retain component pressures and densities. No receipt supplies
humid-mixture viscosity. The receiver must establish frame/time alignment,
transport validity, the frozen acoustic timescale when relevant, and any
needed phase, ice or pressure-enhancement qualification under its own model.

| Receiving task | Additional model and evidence required |
| --- | --- |
| Aerodynamic loading | Geometry, body-relative velocity, receiver frame, drag/compressibility domain and a qualified mixture transport law when Reynolds effects matter |
| Fluid boundary conditions | Species interpretation, boundary/time alignment, flow equations, transport properties and receiver validation |
| Polymer conditioning | Material-specific sorption isotherm, diffusion coefficients, temperature dependence, specimen/process history and conditioning measurements |
| Optical environment | Wavelength, aerosol/particle state, absorption/scattering laws and independent optical validation |

This profile does not provide mixture viscosity or conductivity. The dry
engine's Sutherland viscosity cannot be reused silently for humid air, and
pure-water viscosity alone does not establish an air-vapour mixture law.
Dry potential-temperature stability is not exported as a moist-convective
qualification. Clouds, condensation, latent heat, frost, precipitation,
turbulence, weather evolution and atmospheric chemistry remain separately
qualified extensions.

## Primary references and physical validation

- [WMO: Guide to Instruments and Methods of Observation, WMO-No. 8](https://community.wmo.int/site/knowledge-hub/programmes-and-initiatives/instruments-and-methods-of-observation-programme-imop/guide-instruments-and-methods-of-observation-wmo-no-8-0), Chapter 4. The inspected [WMO-authored 2008 edition, updated in 2010](https://radiometrics.com/wp-content/uploads/2021/10/wmo_8_en-2012.pdf), Annex 4.B, gives the pure-water Magnus coefficients and separate moist-air enhancement. Its quoted liquid-water range is -45..60 degrees Celsius.
- [NOAA/NWS: Mixing ratio](https://www.weather.gov/media/epz/wxcalc/mixingRatio.pdf) defines the relation between vapour pressure and vapour mass per dry-air mass. NET uses its explicitly retained `Rd / Rv` rather than a rounded independent ratio.
- [NIST-JANAF: Gas-phase water thermochemical table](https://janaf.nist.gov/tables/H-064.html) gives molar heat capacity `33.590 J/(mol K)` at `298.15 K`. The [NIST Chemistry WebBook water entry](https://webbook.nist.gov/cgi/cbook.cgi?Name=water&cTG=on&cTP=on) supplies molecular mass and higher-temperature Shomate fits; the latter's declared lower bound is `500 K` and is not extrapolated into this column.
- [NIST DLMF: Simpson's rule, equation 3.5.8](https://dlmf.nist.gov/3.5#E8) supplies the signed composite-rule remainder used to derive the independent lower integral and upper humidity guard.
- [IAPWS SR1-86(1992): Saturation properties of ordinary water substance](https://www.iapws.org/relguide/Supp-sat.html) provides a more detailed pure-water saturation formulation for a future independently qualified provider.

Physical validation would compare pressure, temperature and humidity samples
with calibrated measurements and their uncertainties at identified locations
and times. It would separately assess the Magnus approximation, enhancement
omission, ideal-mixture equation of state and fixed heat capacities. Such
measurements can justify a wider validity domain; numerical self-consistency
alone cannot.
