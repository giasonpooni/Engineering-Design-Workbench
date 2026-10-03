# Atmospheric engine example

This example compiles a synthetic dry hydrostatic atmospheric column on NET's
existing Session substrate. It produces temperature, pressure, density, sound
speed, dynamic and kinematic viscosity, potential temperature and declared
wind at exact retained heights. The independent verifier checks the governing
relations and hydrostatic quadrature. The result is configured environmental
data rather than a weather forecast.

With NET installed:

```sh
net atmosphere example --output atmosphere-request.json
net atmosphere run atmosphere-request.json --output-dir atmosphere-run
net atmosphere inspect atmosphere-run
net atmosphere verify atmosphere-run
net atmosphere export atmosphere-run --output atmosphere-profile.csv
net atmosphere handoff atmosphere-run --sample-index 0 --provider impact --output atmosphere-impact-boundary.json
```

The checked-in [request.json](request.json) is the same request produced by
`example`. It has schema `ciw.atmosphere-request.v1`, scope
`dry_hydrostatic_constant_gravity_column`, and these defaults:

| Declaration | Default |
| --- | --- |
| Origin temperature and pressure | `288.15 K`, `101325 Pa` |
| Height origin and local frame | `0 m`, `atmosphere.local_enu.v1` |
| Source context | `synthetic`, `atmosphere.default-example`, null valid time |
| Temperature lapse rate | `0.0065 K/m` |
| Gas and gravity | Dry air, constant `9.80665 m/s²` |
| Declared wind | East/north/up `[0, 0, 0] m/s` |
| Sampling | `0..10000 m` above the origin, in `1000 m` increments |
| Constitutive tolerance | `1e-10` relative |
| Hydrostatic and quadrature tolerances | Each `1e-8` relative |

The resulting profile has eleven retained spatial samples. Approximate values
from the declared equations are:

| Relative height | Temperature | Pressure | Density | Sound speed |
| --- | --- | --- | --- | --- |
| `0 m` | `288.15 K` | `101325 Pa` | `1.225012 kg/m³` | `340.2923 m/s` |
| `5000 m` | `255.65 K` | `54019.55 Pa` | `0.736118 kg/m³` | `320.5278 m/s` |
| `10000 m` | `223.15 K` | `26435.89 Pa` | `0.412705 kg/m³` | `299.4617 m/s` |

At the origin, dynamic viscosity is approximately `1.789298e-5 Pa s` and
kinematic viscosity `1.460636e-5 m²/s`. Potential temperature increases from
approximately `287.0683 K` to `326.3506 K` over the retained column. Its
diagnostic reference pressure is fixed at `100000 Pa`, so its origin value
differs from the configured actual temperature when origin pressure differs
from that comparison pressure.

The compiler uses the analytic pressure solution for a linear temperature
profile, with a stable logarithmic evaluation covering the isothermal limit.
The verifier integrates the hydrostatic relation independently and separately
checks the gas/transport properties and dry static stability. Compilation and
verification are fixed explicit operations `atmosphere.compile.v1` and
`atmosphere.verify.v1`; retained JSON does not register or activate providers.
The complete report has 17 checks, including separate local and cumulative
hydrostatic pressure checks and 16/32-subinterval Simpson-rule refinement on
each declared height segment. Agreement between these finite rules is not a
certified integration-error bound.

`inspect` checks retained schemas, seals and identity bindings without
recompiling the atmosphere or replaying the verifier. `verify` independently
audits retained candidate values. Qualified exports use fresh verification of
one retained snapshot and create new files. The original workspace records
remain unchanged.

The CSV contains eleven scalar columns: relative height, temperature, pressure,
density, sound speed, dynamic viscosity, kinematic viscosity, potential
temperature and the east/north/up wind components. The three wind components
remain expressed in the declared local ENU frame.

`handoff` selects an exact retained `--sample-index`; it does not interpolate
between heights. The sealed `ciw.atmosphere-handoff.v1` receipt supports the
fixed `impact`, `fluid` and `render` providers. It includes the selected
environment, origin/frame/context, source and verification identity bindings,
preserved/forgotten properties and receiving-provider requirements. A `fluid`
or `render` receipt uses the fields appropriate to that provider. A receipt is
a boundary declaration; the receiving engine must validate and use it under
its own contract.

The atmospheric request admits origin temperatures `250..330 K`, origin
pressures `50000..120000 Pa`, a lapse rate `0..0.009 K/m`, and `2..129`
strictly increasing heights starting at zero and no higher than `11000 m`
above the reference. All temperatures must remain at least `180 K`. Each wind
component is a declared external value in `-300..300 m/s`. Those limits do not
qualify a particular aerodynamic load model at every permitted velocity.

The supported observables produce LOCAL qualification when all numerical
checks pass. Humidity, precipitation, clouds, turbulence, weather forecasting,
radiation, chemistry, visual scattering, material conditioning and full fluid
dynamics remain declared expansion capabilities. Requesting one of them does
not silently enable its physics. Failed numerical qualification retains REFUSE
evidence. No profile or handoff performs canonical state admission.

Air temperature does not establish specimen temperature or polymer conditioning.
The existing elastic, crush and plate impact workloads keep their governing
equations and verified invariants. Aerodynamic loads require body-relative
wind, geometry, area and a qualified aerodynamic law; optical rendering needs
its own scattering and illumination model. This example computes the usable
ambient profile without granting those receiving-model claims.

See [the atmospheric engine contract](../../docs/ATMOSPHERIC_ENGINE.md) for
equations, numerical/reference separation, primary NASA/NOAA sources and the
physical validation path.
