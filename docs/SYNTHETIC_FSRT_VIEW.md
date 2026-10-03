# Synthetic FSRT results in the existing GSC inspector

This integration branch extends the simulated-observation work in NET #46
(`297bf65cac98b28210c07972275c6adf715c497e`) with a source-aware retained-result
view. It carries the five additive files from #42 at
`ef4c55361b05740f6c58d1a2c065633481e4a1ad` and thirteen additive files from #45 at
`76075f9fa2235c109f800fd9d38a10cb6131c877`, byte-for-byte. These are the existing
RCI-view and interactive-projectile implementations, not rewrites. The original
branches, main, all scientific pins, and the separate persistent oscillator are
unchanged. This combined source state needs its own test evidence.

## Export one explicitly selected occurrence

```sh
python -m ciw.simulated_fsrt_view studies/case-a/workspace.json \
  --execution execution-<retained-estimator-id> \
  --expect-workspace-sha256 sha256:<independently-recorded-workspace-digest> \
  --output simulated-tank.view.json
```

Open GSC's `/numerics`, select that JSON file and the `view_sha256` printed by
the exporter. This is the payload digest, not a hash of the outer JSON file.
The compatible GSC branch is `feat/synthetic-fsrt-gsc-v1` above its #9 inspector.
The result is a local-file inspection, not a live endpoint or a shared intent bus.

The exporter reuses `Session.from_workspace` and the unchanged create-only JSON
writer from the RCI view. It reads at most 8 MiB once, verifies the selected
workspace bytes and reopens the frozen copy in scratch space. No source or result
file is overwritten. It requires an exact retained estimator execution, not the
latest operation, a scenario name or a source-engine occurrence. Refusals remain
selectable and retain `result: null`.

## Additive wire boundary

`ciw.simulated-fsrt-view-envelope.v1` contains an exact UTF-8 payload string and
SHA-256; the payload is `ciw.simulated-fsrt-view.v1`. Its source block retains the
original simulated-observation UTF-8 bytes, their digest, run/evidence IDs and
ordered channel evidence IDs. The complete original execution/result records
remain unchanged, including the `ciw.simulated-fsrt.v1` wrapper around the native
FSRT result. The 256 KiB envelope does not contain the separate reference-state
artifact. Its payload digest is the representation identity, not a fresh
execution, result, verification or admission identity.

GSC validates the outer and original-source byte bindings, exact source class,
producer/state/clock ownership declarations, simulation tick/rate/phase, entity
mapping, native times, full covariance stages and held/refused status. The native
historical `calibrated_observation` name is preserved with the explicit synthetic
notice. A source-aware header says that the observations are not physical
measurements or calibration. The local one-second NET selection support is not
substituted for elapsed simulation time. Unknown reference-truth fields and
unsupported provenance claims are refused.

The old RCI envelope/exporter remain separate and reject synthetic sources. Only
source-independent structural FSRT checks and numerical display panels are shared
in GSC. The original reader still uses its original zero-time snapshot profile;
this reader passes the explicitly retained simulation time. No simulation,
Kalman update, covariance propagation/repair or independent reference executes
inside the viewer. GSC does not recompute native record/covariance digests or
statistical calculations. A separately selected payload digest binds those bytes;
copying a digest from the same untrusted file does not authenticate its publisher.

## Qualification

The public focused gate runs the combined projectile/Session, simulated-source,
legacy covariance-reader and input suites; then creates fresh observations with
the actual Godot/FSRT providers and tests provider-free export. Missing providers
fail, and JUnit counts/zero skips are required. The unchanged projectile workflow
also runs its actual Blender/Godot/Bevy campaign on this combined branch.

The private RCI-owning qualification can additionally regenerate the unchanged
RCI/FSRT views, run both TypeScript readers, build GSC, and exercise all three
browser regressions against the same combined NET/GSC revisions. This uses RCI's
own authorized checkout, not a new secret or private source mounted on a public
PR runner. A local rerun against old downloaded evidence is labelled as retained
inspection, not fresh provider execution. Earlier PR successes are not evidence
for this new combined source state until its gates actually run.

Preserve original evidence, source, operation, execution, result and verification
identities. All ordinary results remain unverified; inspection grants no physical
acceptance, calibration, ESM admission/release or equipment permission. Export is
not automatic publication. No live control, arbitrary fluid-network scene,
projectile-to-reservoir conversion or central GSC representation-IR integration
is introduced by this bounded handoff.
