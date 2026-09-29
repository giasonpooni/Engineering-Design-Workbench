# Notations Game Foundry — first game-owned production workload

The Foundry is a workload layer over NET, not another engine, scheduler or
agent framework. This increment connects 1792's existing household water-round
rules, clock and save implementation to the production work orders from PR #65.

## Implemented loop

`compile objective -> lock game source -> existing NET work orders -> native
Godot -> retained observations -> independent acceptance -> dependent regression
-> accepted artifact export`

The installed objective is `1792.water-round.v1`. Compilation is an explicit
recipe, **not a natural-language planner**. One delivery fails the fixed six-unit
assignment; the declared two-delivery correction can pass. Every attempt remains
in the original Session, including failed candidates. Checks cannot be weakened
by the saved order. Missing observations hold the job; native failures refuse;
both block descendants and do not consume a speculative repair.

1792 owns `game/foundry/water_round.gd` and all gameplay source. NET snapshots a
closed list of eleven GDScript modules into a disposable minimal project. Nothing
is vendored across licences, and the user's game checkout/save files are not
modified. The adapter uses **explicit completed-inquiry and pose fixtures**: this
is a real game-domain/clock/save operation, not a played walking route, rendered
scene, historical authentication or complete playable build.

## Run

Use this NET branch with 1792 PR #30, initially pinned at
`2bb8a16e63716d54de2d4e97daabc4671d3e07f4`. Install NET normally:

```sh
python -m pip install -e '.[dev]'
net foundry compile 1792.water-round.v1 --game-root ../1792/game --output-dir results/water-order
net foundry run results/water-order --game-root ../1792/game --godot /absolute/path/to/godot --godot-sha256 sha256:YOUR_VERIFIED_EXECUTABLE_DIGEST --output-dir results/water-production
net foundry inspect results/water-production
net foundry report results/water-production
net foundry export results/water-production --destination results/accepted-water-artifact
```

`python -m ciw.foundry_workflow` exposes the same commands. The executable digest
is SHA256 of the **executable**, not its download ZIP. Native CI uses the existing
1792 Godot 4.5.1 release and verifies the ZIP before binding the executable.
Every output directory must be new. To run only the complete candidate, compile
with `--candidate-trips 2`. To exercise exhausted repair, use `--no-repair` with
the default one-trip candidate. `--max-operations` limits the worst-case declared
operation count before any dispatch; this recipe reserves at most three.

## Independent acceptance

The installed gate checks observed stage order, game-clock ticks, conserved
remaining/carried/stored water, 180-tick draw completion, original actor/receipt
order and interaction locations, unchanged currency/knowledge, the saved pending
draw's full state before/after reload, duplicate-deposit atomicity, and the final
six-unit completed assignment. It never accepts a producer's success flag.
The contract is authored gameplay, not a hydrological or historical measurement.

The native response and logs are retained byte-for-byte with content digests.
Source-lock identity, execution identity, result identity, receipt identity and
export identity stay distinct. Inspection recomputes acceptance without loading
the game or starting a subprocess. Export resolves the exact accepted **primary
candidate** through its work-order receipt, never 'the last Session result'.
It emits `water-round-observations.json` plus a source/acceptance-bound manifest.
The export is a domain-observation artifact, not a save installer or game release.

The report derives accepted/blocked jobs, rejection fraction and captured native
wall time from original records. Human hours, model-token cost and playable
minutes remain null because they are not measured. A local attempt count is not
a claim about studio-equivalent output or autonomous agent productivity.

## Boundaries

Source and executable paths are chosen by the operator, never by a saved task.
Source drift, missing files, symlinks inside the selected root, oversized data,
wrong request identity and executable drift are refused. The locked source is
copied once; a later checkout edit does not change the bound worker snapshot.
The child has a runtime/output limit. **The disposable project is not an OS,
container or network sandbox. Bind only source and executables you trust.**
Shared libraries, the OS and all possible external reads are not attested.

No model API calls, autonomous source editing, remote workers, leases, automatic
Git merging, ESM admission, deployment or release are added. Existing scientific,
GIS and agent/MCP branches are neither absorbed nor silently merged.

## Qualification

```sh
python -m pytest -q tests/test_foundry.py
python scripts/check_foundry.py --godot /absolute/path/to/godot --game-root ../1792/game --output-dir results/native-qualification
```

Unit tests label their doubles explicitly. The native script runs baseline,
fail/correct/regression and exhausted-repair campaigns against the unchanged
pinned game modules. Two extra campaigns use **separately locked disposable
diagnostic adapter copies** for missing observations and native refusal. It also
checks offline reinspection, byte-exact accepted export, blocked exports,
unchanged original source and corrected-primary equivalence to baseline.

The `NET Foundry 1792` workflow runs Linux/Windows source and installed-wheel
tests, then actual Godot qualification from the installed wheel outside the
checkout. It retains JUnit, the wheel, both exact repository source archives and
all campaign evidence. A successful domain qualification is not full-game,
rendering, performance, historical or repository-wide CI validation.
