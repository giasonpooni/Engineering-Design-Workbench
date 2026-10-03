# Moist-air atmospheric column example

This example compiles a synthetic, unsaturated mixture of dry air and water
vapour on NET's existing Session substrate. A prescribed constant water mass
mixing ratio changes the mixture equation of state and sound speed. The
retained column includes partial pressures, component densities, relative
humidity, a liquid-water equilibrium dewpoint and frozen-composition potential
temperature. Its pressure profile is hydrostatic; temperature and wind are
declared inputs.

With NET installed:

```sh
net atmosphere moist example --output atmosphere-moist-request.json
net atmosphere moist run atmosphere-moist-request.json --output-dir atmosphere-moist-run
net atmosphere moist inspect atmosphere-moist-run
net atmosphere moist verify atmosphere-moist-run
net atmosphere moist export atmosphere-moist-run --output atmosphere-moist-profile.csv
net atmosphere moist handoff atmosphere-moist-run --sample-index 0 --provider impact --output atmosphere-moist-impact-boundary.json
```

The checked-in [request.json](request.json) matches the canonical `example`
request. Its schema is `ciw.atmosphere-moist-request.v1`, and its scope is
`unsaturated_constant_mixing_ratio_hydrostatic_column`.

| Declaration | Default |
| --- | --- |
| Reference temperature and total pressure | `298.15 K`, `101325 Pa` |
| Height origin and frame | `0 m`, `atmosphere.local_enu.v1` |
| Source context | `synthetic`, `atmosphere.moist-default-example`, null valid time |
| Temperature lapse rate | `0.0065 K/m` |
| Composition | `dry_air_water_vapour` |
| Water mass per dry-air mass | `0.008 kg/kg`, or `8 g/kg dry air` |
| Constant gravity | `9.80665 m/s²` |
| Declared wind | East/north/up `[0, 0, 0] m/s` |
| Retained relative heights | `0`, `250`, `500`, `750`, `1000 m` |
| Constitutive tolerance | `1e-10` relative |
| Hydrostatic and quadrature tolerances | Each `1e-8` relative |

The specific humidity is `0.00793650794 kg/kg mixture`, which differs from
the declared mixing ratio. The mixture gas constant is approximately
`288.434524 J/(kg K)` and its frozen heat-capacity ratio is `1.39890554`.
Approximate values computed from this declaration are:

| Relative height | Temperature | Total pressure | Mixture density | Relative humidity | Liquid-water dewpoint |
| --- | --- | --- | --- | --- | --- |
| `0 m` | `298.15 K` | `101325 Pa` | `1.178242 kg/m³` | `0.407170` | `283.874216 K` |
| `500 m` | `294.90 K` | `95679.36 Pa` | `1.124854 kg/m³` | `0.467753` | `283.014764 K` |
| `1000 m` | `291.65 K` | `90290.90 Pa` | `1.073334 kg/m³` | `0.539632` | `282.151685 K` |

Relative humidity is retained as a fraction: `0.407170` is about 40.7%.
The origin vapour partial pressure is approximately `1286.680 Pa`; dry-air
partial pressure is approximately `100038.320 Pa`. Frozen sound speed changes
from approximately `346.84483` to `343.04319 m/s` over the column.

The saturation diagnostic uses the pure-liquid-water Magnus expression with
`611.2 Pa`, `17.62` and `243.12 K` constants. It omits the moist-air
enhancement factor; it does not claim the full WMO thermodynamic moist-air
saturation definition. Dewpoint uses the inverse of the same declared law.
There is no frost-point, condensation or latent-heat calculation.

The provider accepts reference temperatures `293.15..308.15 K`, reference
pressures `80000..110000 Pa`, lapse rates `0..0.0065 K/m`, and `2..129`
ordered samples beginning at zero and extending no higher than `2000 m`.
Water mixing ratio is exactly zero or in `0.002..0.02 kg/kg dry air`.
Ambient temperature must remain at least `273.15 K`; nonzero-water diagnostic
dewpoint must remain within `253.15..308.15 K`. Relative humidity must not
exceed `0.95` anywhere in the declared continuous column.

For this saturation law, fixed composition and nonnegative lapse, an interior
relative-humidity turning point can only be a minimum. The maximum is the
larger value at the origin and top of the column, so this domain check covers
all heights rather than depending on the retained grid's spacing. A humid
origin must be checked even when humidity decreases with height. The hard
ceiling is independent of numerical tolerances.

The compiler retains a candidate even when its declared humidity assumptions
fail. Independent verification then returns REFUSE; it does not clip humidity,
remove water, insert clouds or make the column physically admissible by
changing its declaration. Unsupported desired observables return EXPAND only
after all numerical and domain checks pass. Viscosity, phase change, ice,
clouds, turbulence, moist-adiabatic response, weather forecasting, optical
scattering and material conditioning remain expansion capabilities.

The independent report has 30 checks. It integrates the hydrostatic
`g / (Rm T)` relation with separate 16/32-subinterval composite Simpson rules
on each of the four retained height intervals; this example uses 200
quadrature evaluations. Both rule references, domain checks and constitutive
checks pass, giving LOCAL qualification. The maximum continuous-column
relative humidity is approximately `0.539632`, at the top endpoint.
The conservative endpoint humidity upper guard is approximately
`0.539632076466624`. It uses the signed Simpson fourth-derivative remainder,
lower integral bounds and fixed `1e-12` binary64 allowances for integral,
pressure and humidity calculations. The guard remains independent of request
tolerances and requires its endpoint maximum to be no higher than `0.95`.
This prevents a capped candidate humidity from receiving qualification when
its independently guarded declaration is too humid.

The mathematical remainder bounds real-arithmetic integration error; fixed
rounding allowances do not implement directed interval arithmetic. Neither
the guard nor finite-rule agreement establishes accuracy relative to a
measured atmosphere. Columns very close to the hard ceiling can receive a
conservative REFUSE result.

At a water mixing ratio of exactly zero, vapour partial pressure and density,
specific humidity and relative humidity are zero. Liquid-water dewpoint is
`null`; CSV represents that missing diagnostic with an empty cell. The shared
gas variables recover the dry-gas limit. This moist profile does not supply
the dry provider's viscosity law.

`inspect` validates retained data and identity bindings without executing the
compiler or verifier. `verify` independently audits candidate values. CSV and
handoff exports require fresh verification of one retained snapshot and create
new output files without rewriting the retained workspace.

`handoff` selects one exact retained `--sample-index` for the fixed `impact`,
`fluid` or `render` provider. The receipt carries explicit composition and
humidity with source, frame, origin and distinct identity bindings. It does
not interpolate or assert that a receiving provider has consumed or validated
the boundary. Material conditioning still needs specimen temperature,
sorption, diffusion, processing history and measurements; ambient humidity
alone does not establish a polymer's water content.

The handoff schema is `ciw.atmosphere-moist-handoff.v1`; the typed preservation
receipt is `ciw.atmosphere-moist-preservation.v1`. Preservation requires every
one of the 30 checks and LOCAL qualification. An ELIGIBLE recommendation
does not perform canonical state admission.

See [the moist-air physical contract](../../docs/ATMOSPHERIC_MOIST_AIR.md)
for the mixture derivation, continuous humidity proof, primary WMO/NOAA/NIST
references and the physical validation path.
