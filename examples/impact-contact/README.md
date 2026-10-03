# Impact contact example

This example executes NET's one-dimensional compression-only elastic contact
benchmark and independently checks its retained numerical observations against a
closed-form reference. It uses the existing session/operation substrate and
requires no external MOOSE or LAMMPS runtime.

With NET installed:

```sh
net impact example --output impact-request.json
net impact run impact-request.json --output-dir impact-run
net impact inspect impact-run
net impact verify impact-run
net impact export impact-run --output impact-observations.csv
```

The generated JSON is the current request contract. Its parameters are data;
they do not supply executable equations or arbitrary provider commands.
The default example uses `mass_kg: 1.0`, `stiffness_n_per_m: 10000.0` and
`initial_speed_m_per_s: 2.0`. `integration` selects `velocity_verlet`, 256
`steps_per_contact` and `duration_factor: 1.5`; the second trace uses 512 steps
per contact. The exact reference predicts `0.0314159265359` s contact duration,
`0.02` m maximum compression, `200` N peak force, `4` N s impulse and `2` J
initial energy.

`run` requires a new output directory and retains `request.json`, `workspace.json`,
`verification.json` and `preservation.json` plus the existing Session's source,
execution and result files. A complete numerical report has 33 checks. `inspect`
validates retained structure and bindings without the solver or numerical audit.
`verify` recomputes independent arithmetic, compares the retained report and
leaves the retained run unchanged. Re-verification is not a new solver execution
or verification occurrence. CSV export first performs fresh verification,
requires LOCAL qualification and creates a new primary-trace CSV with columns
`time_s`, `compression_m`, `velocity_m_per_s` and `force_n`. It does not overwrite
an existing file or create an additional experiment.

The model is a mass `m` striking an ideal compliant element with effective spring
constant `k`, with initial contact at `q = 0` and positive incoming velocity `v0`.
During contact, `F = k * max(q, 0)` and `m * dv/dt = -F`. The reference predicts
contact duration `pi * sqrt(m / k)`, rebound velocity `-v0`, contact impulse
`2 * m * v0`, restitution `1` and zero irreversible dissipation. Mechanical
energy is temporarily stored in the compliant element and returned on release.
The fixed support receives reaction impulse, so the mass's momentum is not
conserved by itself.

The `k` value is in N/m. It is not a polymer modulus, hardness or toughness.
This request does not model gravity-driven drop motion, a deformable plate,
rate-dependent polymers, fracture, temperature evolution or molecular damage.
The five supported `desired_observables` are `force_time`, `impulse`,
`restitution`, `energy_accounting` and `separation_time`. Explicitly requesting
an expansion observable can retain the passing spring model with EXPAND;
the typed admission-eligibility gate is REFUSED because the requested property
is absent, and CSV export is blocked. Malformed inputs or unknown laws/observable
names remain subject to REFUSE. A passing numerical check does not create
physical validation or canonical-state admission.

The preservation receipt uses the existing representation/preservation APIs,
with nine BOUND effects and explicit FORGET effects for absent higher observables.
`NUMERICAL_BOUND` means sampled numerical acceptance in this retained run,
without a formal error bound or molecular/component scale proof. The operations
are explicitly bound for this workflow; the default registry is unchanged.

Read the [benchmark contract](../../docs/IMPACT_CONTACT_BENCHMARK.md) for equations,
units, numerical audit requirements, qualification boundaries and the future
instrumented polymer-plate pathway.
