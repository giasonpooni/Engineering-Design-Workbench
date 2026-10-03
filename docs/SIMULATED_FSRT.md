# Simulated observations into FSRT

This is a bounded extension of NET's interactive-simulation direction: an
engine-owned mass snapshot can supply an estimator without transferring world
ownership to NET or passing the simulator's hidden reference state to FSRT.
Blender authoring, the Godot/Bevy projectile comparison and the persistent
oscillator remain their own work. This adapter neither replaces nor implements
those engine lifecycles. It does not start a second simulation loop.

```text
Engine-owned world
  |-- explicitly projected simulated sensor observation --> NET run.v1
  |                                                         |
  |                                            ciw.simulated-fsrt.v1
  |                                                         |
  |                                   approved fsrt.tank-reconstruct.v2
  |                                                         |
  |                                          retained synthetic result
  |
  +-- separate reference-state artifact --> independent evaluation only
```

## Run and inspect

A producer supplies `ciw.simulated-mass-observation.v1`: exactly two ordered mass
readings, entity/source identity, full covariance and missingness, a post-step
integer tick/rate, one state/clock owner, engine/source/executable identities,
and scenario/model/sensor-model/asset references. Declared IDs are not source
authentication; the operator selects an expected SHA-256 from their trusted
artifact record. The importer hashes and parses the same bounded bytes.
The committed `source.json` is an explicitly labelled **contract fixture**, not
a claimed engine execution. Actual qualification output is generated separately.

```sh
python -m ciw.simulated_fsrt create engine-observation.json \
  --expect-sha256 sha256:<source-byte-digest> \
  --parameters examples/simulation-observation/parameters.json \
  --fsrt-repo /operator/approved/fsrt --output-dir studies/case-a

python -m ciw.simulated_fsrt inspect studies/case-a/workspace.json \
  --expect-sha256 sha256:<workspace-byte-digest>

python -m ciw.simulated_fsrt replay studies/case-a/workspace.json \
  --expect-sha256 sha256:<workspace-byte-digest> \
  --fsrt-repo /operator/approved/fsrt --output-dir studies/case-a-replay
```

`--python` optionally selects the operator-provisioned interpreter. The existing
runtime allowlist and checkout/interpreter/dependency checks remain controlling.
Saved metadata cannot select executable paths or register a provider. Output
directories must be new. The source budget is 64 KiB, the inspection/replay
workspace budget 8 MiB. Inspection reopens in scratch space and does not modify
the input workspace or launch a scientific provider.

Replay is a **fresh estimator execution on the retained observation**, not a
rerun of the originating game, a restored checkpoint or a new simulator sample.
The original engine execution ID stays bound to the observation; the new NET
execution/result IDs remain separate and previous results remain in the workspace.
Regenerating an engine source requires its own producer and new occurrence IDs.

## Scientific boundary

The new operation is an explicit composition wrapper. It invokes the existing
pinned `fsrt.tank-reconstruct.v2` worker; it does not copy a Kalman filter,
reconciliation method or a new fault classifier into NET. Its result contains
`source_class: simulated_observation`, a native-input digest and the complete
native response. The ordinary RCI-backed `fsrt.tank-reconstruct.v1/v2` operations
continue to require their existing physical-calibration source records.

FSRT's native v2 schema uses the historical field/basis name
`calibrated_observation` for its already-unit-normalized input. The wrapper
preserves that native spelling, explicitly declares that the readings are
simulated and **not physically measured or calibrated**, and records
`calibration_status: not_applicable_simulated_reading` in covariance provenance.
NET source channels remain `simulated_observation`; no RCI record is fabricated.
The same notice remains visible after reopening and replay.

The estimator receives only a declared prior/total, the two selected readings,
their uncertainty and required provenance. Unknown fields, including hidden
truth fields at either source or producer level, are refused. The source API
has no reference-state input. This prevents the adapter from forwarding that
separate artifact; it cannot certify how an external producer or user obtained
their prior/model declarations.

Prior, observations and declared total must be explicitly declared mutually
independent for this operation. Within-observation correlation is supported and
retained; cross-source dependence and temporal covariance are not inferred or
repaired. A missing reading remains null/false; its declared covariance reference
is not substituted as an observation. All six native v2 covariance stages and
held/refused diagnostics remain intact. Input covariance may pass generic PSD
validation yet be refused by FSRT's stricter observation guard; no jitter or
PSD repair is introduced. Singular reconciled outputs remain eligible under
the native contract.

The native time is tick/ticks_per_second. Arrival equals that time under this
no-simulated-delay profile. The existing NET one-sample recording uses a local
zero cursor and one-second selection support, explicitly labelled **not elapsed
simulation time**. Multiple snapshots, interpolation, arbitrary units/frames,
reference-state assimilation and field-validation claims are outside this slice.

## Validation and existing substrate

The source adapter reuses `Session`, the operation runner, `run.v1`,
`ciw.execution.v1`, `ciw.operation-result.v1` and the existing pinned subprocess.
The old read-only FSRT validators expose source-independent entry points; the
RCI entry points delegate to the same validation bodies. They never recompute
an estimator. Existing covariance-reader regressions remain required.

The Godot fixture in `validation/simulation-observation/` owns two nodes, advances
one declared mass-transfer tick and emits a noisy sensor projection plus a
separate reference-state file. Its arithmetic is a qualification fixture, not
a fluid solver, collision simulation or general Godot control adapter. The
errors are deterministic challenge values and covariance is declared: this is
not Monte Carlo coverage or a calibrated-noise experiment.

The dedicated read-only workflow uses the existing Godot 4.5.2 version with a
verified archive digest and the unchanged approved FSRT revision. It tests
ordinary, held, missing, both-missing and singular-input cases; an independent
rational posterior reference; reference-truth isolation; provider-free reopening;
fresh estimator replay; coherently resealed corruption; and CLI non-overwrite.
Both runtimes are required; absent dependencies fail rather than skip.

```sh
python -m pytest -q tests/test_simulated_fsrt.py
GODOT_BIN=/operator/godot CIW_FSRT_REPO=/operator/fsrt \
  python -m pytest -q validation/simulated_fsrt_integration.py -o addopts=
```

This does not claim Blender/Bevy qualification, the persistent-instance gate,
new physics, field validation or a whole-platform green CI result. GSC's existing
RCI-only retained-view export is intentionally not made to accept this source
by impersonating RCI. A separately versioned synthetic-source view adapter
remains a follow-on; generic NET inspection already retains the complete result.
There is no ESM admission/release or equipment permission in this operation.
