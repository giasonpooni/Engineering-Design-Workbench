# Impact crush example

This example runs NET's unilateral elastic-perfectly-plastic contact benchmark.
It adds permanent compression and an explicit plastic-work ledger alongside the
[elastic contact example](../impact-contact/README.md), using the same Session
and typed preservation substrate. It needs no external finite-element or
molecular runtime.

With NET installed:

```sh
net impact crush example --output impact-crush-request.json
net impact crush run impact-crush-request.json --output-dir impact-crush-run
net impact crush inspect impact-crush-run
net impact crush verify impact-crush-run
net impact crush export impact-crush-run --output impact-crush-observations.csv
```

The generated request schema is `ciw.impact-crush-request.v1`, with scope
`unilateral_elastic_perfectly_plastic_crush` and contact law
`compression_only_elastic_perfectly_plastic`. Its parameters are data, not
executable equations or arbitrary provider commands. The default uses
`mass_kg: 1.0`, `stiffness_n_per_m: 10000.0`, `initial_speed_m_per_s: 2.0` and
`yield_force_n: 100.0`; initial total/plastic compression, damping and gravity
are zero. Integration selects `velocity_verlet`, 1024 primary
`steps_per_contact` and `duration_factor: 1.5`; the refined trace uses 2048
steps per contact. Default tolerances are `0.001`, except
`momentum_relative: 1e-10`. The original `net impact example` and `net impact run`
commands retain their elastic request law and reject a crush request passed to
the elastic run command.

A point mass approaches a massless effective crush element at a fixed support.
The state has total approach `q`, velocity `v` and irreversible compression `p`.
The contact force is `F = k max(q - p, 0)` and is capped at the yield force
`F_y` through irreversible evolution of `p`. Plastic state increases during
the compression plateau and freezes during unloading and separated flight.
Release occurs when `q - p = 0`; yielded release does not occur at the original
contact position `q = 0`.

Initial kinetic energy is `E0 = 0.5 m v0^2` and yield elastic energy is
`Uy = F_y^2 / (2 k)`. At or below the threshold, the result reduces to elastic
contact, with zero permanent compression and zero plastic work. Above threshold,
the reference predicts residual compression `(E0 - Uy) / F_y`, final plastic
work `E0 - Uy`, rebound-speed magnitude `F_y / sqrt(m k)` and restitution
`F_y / (v0 sqrt(m k))`. Total impulse is `m (v0 + rebound_speed)`.

| Observable | Default exact reference |
| --- | --- |
| Initial energy | `2 J` |
| Final rebound energy | `0.5 J` |
| Final plastic work | `1.5 J` |
| Maximum total compression | `0.025 m` |
| Residual compression | `0.015 m` |
| Peak force | `100 N` |
| Rebound-speed magnitude | `1 m/s` |
| Restitution | `0.5` |
| Contact impulse | `3 N s` |
| Contact duration | `0.0382644590996207 s` |

Accepted yield ratio `F_y / (v0 sqrt(m k))` is `0.2..5.0`; primary step count
is `32..4096`. Together these bounds imply `omega dt <= 0.209`, limiting how
coarse the elastic phases become during a plastic plateau. They do not guarantee
accuracy: analytic-history, accounting and half-timestep refinement checks must
still pass. At exact yield, analytic plastic work is zero; small numerical
turning-point overshoot of order `dt^2` is checked against the declared plastic
history/work, residual-compression and yield-branch tolerances.

The conserved accounting quantity is striker kinetic energy plus recoverable
elastic energy plus accumulated plastic work. Striker/element mechanical energy
decreases during plastic loading. Numerical energy drift must remain distinct
from the declared plastic work. The fixed support receives reaction impulse;
it has no motion or external mechanical work in this model.

`run` explicitly binds `impact.crush-contact.v1` and
`impact.crush-contact-verify.v1` through the original Session. It requires a new
directory and retains `request.json`, `workspace.json`, `verification.json` and
`preservation.json` with the Session's source, execution and result records.
Numerical result schema is `ciw.impact-crush-result.v1`, independent report
schema is `ciw.impact-crush-verification.v1` and typed receipt schema is
`ciw.impact-crush-preservation.v1`. A complete report with release detected in
both traces contains 59 checks. `inspect` checks retained structure and bindings. `verify`
recomputes the independent arithmetic from retained inputs and observations;
it does not rerun the solver or modify the run. Export first freshly verifies a
LOCAL run and writes a new primary-trace CSV without overwriting an existing
file, with columns `time_s`, `compression_m`, `velocity_m_per_s`, `force_n`,
`plastic_compression_m` and `plastic_work_j`. Re-verification does not create a
new solver execution or verification occurrence. Explicit requests for unavailable material, plate, failure, molecular or
scale-transfer properties retain EXPAND scope and block CSV export.

The seven supported desired observables are `force_time`, `impulse`,
`restitution`, `energy_accounting`, `separation_time`, `plastic_work` and
`residual_compression`. The preservation receipt contains 14 BOUND effects
and four REQUIRE obligations, with explicit FORGET effects for absent higher
properties. Numerical-bound receipts supply sampled acceptance for this run;
ELIGIBLE status never admits a canonical state. The benchmark contract lists
all supported expansion names and exact request bounds.

The effective stiffness is in N/m and plateau force in N. They are not polymer
modulus, yield stress, hardness or toughness. This synthetic law has no finite
stroke, densification, hardening, damage, fracture, temperature evolution,
strain-rate dependence, gravity-driven drop motion or spatial specimen field.
Numerical acceptance does not create physical validation, formal proof or
canonical-state admission.

Read the [benchmark contract](../../docs/IMPACT_CRUSH_BENCHMARK.md) for independent
phase solutions, the impulse/energy ledger, edge fixtures, numerical-resolution
constraints, primary references and the physical qualification boundary.
