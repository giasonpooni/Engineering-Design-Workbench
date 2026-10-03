# Evidence timeline: commands, observations, images and branch checks

One offline operator view of **existing CIW Session evidence**. Follow a captured
image back to its exact observation, inspect when samples became available,
trace a restored branch to its checkpoint, and open the campaign/replay checks
that reference those occurrences. No simulation, renderer or operation executes
when building or inspecting this view.

## Use your existing captures

After running the existing observation-image demo:

```sh
net simulation timeline build \
  --capture results/images-001/current \
  --capture results/images-001/delayed \
  --capture results/images-001/unavailable \
  --output-dir results/timeline-001
net simulation timeline inspect results/timeline-001
```

Open `results/timeline-001/index.html`. It is a self-contained offline page with
embedded, checked PNGs. Filter by kind, instance or observer; search identities
and quantities; navigate explicit source/dependent links; expand exact indexed
records and sample values. There is no service, upload, CDN, external font, paid
API, dynamic code loading or network request. The packaged JavaScript uses DOM
text APIs and a hash-restricted Content Security Policy, not HTML from labels.

The page is an **operator index across the selected observers**, not a new
embodied-agent observation. Filtering is a convenience, not access control. Full
original workspaces remain privileged evidence in the bundle, even though the
page omits snapshots, world configuration and intervention parameter payloads.

## Add a workspace, branches and retained checks

```sh
net simulation timeline build \
  --workspace results/native-001/workspace.json \
  --report results/native-001/campaign.json \
  --report results/native-001/replay.json \
  --output-dir results/native-timeline-001
```

`--workspace`, `--capture` and `--report` are repeatable. Capture inputs include
their exact source and extended workspace automatically. A workspace can also
supply refused attempts that have no successful capture bundle. Reports must be
existing simulation-campaign or simulation-replay records; every referenced
result must be present and identical in the selected workspace union.

Workspaces must share the **exact original source recording**, not merely the
same model label or similar samples. Distinct recordings are not relabelled to
force a join. Identical repeated execution/result IDs are deduplicated. Different
content under an existing ID refuses; there is no last-file-wins resolution.

A capture record without a supplied capture bundle is shown as **metadata only**.
No claim that image bytes have been checked is made until the original capture,
source workspace, extended workspace and PNG all pass the existing capture
reader. A failed render retains its refusal, never a fabricated image/result.

## Time and causality

The view keeps three time concepts separate:

- The original host `created_at` timestamp is record-creation time, not execution
  duration, completion time or a global simulation clock.
- Provider clock identifiers and before/after world times remain unchanged.
- Each observation retains its sample acquisition times and separate availability
  time. Rendering a delayed observation does not upgrade it to current world truth.

The index adds only edges supported by retained contracts: consecutive instance
control revisions with matching before/after records; the selected source
checkpoint occurrence for a restore; and the original observation occurrence for
an image capture. Topological sorting respects these edges. UTC timestamps and
IDs only break ties between unrelated occurrences for display; they do **not**
establish global causal order between branches or clocks.

Missing predecessors or unselected checkpoint occurrences appear as explicit
history gaps (`INDETERMINATE`). They are not filled from state hashes, snapshots,
nearby timestamps or a fresh simulation. Contradictory adjacent bindings,
ambiguous accepted revisions, changed provider/clock identity, and conflicting
occurrences refuse. A refusal records an attempted instance, where available,
but supplies no invented post-failure state, owner or world time.

Observation values, quantities, units, frames, missingness and optional covariance
are copied as recorded. The enclosing execution remains distinct from original
sample identities. No resampling, covariance calculation, physics validation,
state admission or new verification identity is introduced. Campaign FAIL still
means its declared comparison failed, not that a branch is worse; replay PASS
retains its original bounded claim scope.

## Retention and rechecking

The bundle contains content-addressed original JSON/PNG evidence, `timeline.json`,
`index.html` and a sealed `manifest.json`. The index is a **derived projection**,
not a second execution ledger. Source files are frozen and validated in scratch
before the requested destination is created. All outputs are create-only. The
manifest is written last: interrupted publication can leave partial files, but
not a completed manifest. This is not crash-atomic directory publication.

`timeline inspect` reopens the frozen sources through the original Session and
capture readers, revalidates selected campaign/replay reports, then rebuilds the
index and HTML using the installed projection code. It requires byte-for-byte
agreement. Changing a verdict/page and recomputing a manifest hash does not pass.
Changing installed projection templates can require rebuilding the view; a bundle
is not an executable archive and never loads code from its saved files.

An external manifest byte pin can additionally be supplied:

```sh
net simulation timeline inspect results/timeline-001 \
  --expected-manifest-sha256 sha256:EXTERNALLY_SELECTED_MANIFEST_HASH
```

Hashes check content consistency, not publisher authenticity. Coherently forged
source evidence cannot be authenticated by rechecking its own hashes. Filesystem
checks are not an adversarial same-user race sandbox.

## Bounded v1 profile

At most 16 distinct workspace snapshots, 16 selected capture bundles and 16
reports are admitted. Captures consume workspace slots for both source and
extended workspaces. Per-file bounds reuse 8 MiB JSON and 4 MiB PNG limits;
aggregate original inputs are limited to 96 MiB, and the union to 1,024 executions
and 1,024 results. The derived JSON is capped at 8 MiB; HTML includes bounded image
copies. Repeated paths/identical bytes do not allocate additional identities.

This first profile indexes recording Session workspace versions 1/2. Version 3
retained-Workbench histories explicitly refuse rather than being presented as
fully indexed. Legacy non-operation results are counted as unindexed, not lost or
converted into new executions. Other original top-level operations can appear as
metadata when the existing Session has their trusted reader; no provider is
loaded to guess an unknown schema.

This is not a live control UI, multirate scheduler, general event bus, video
recorder, universal provider registry or arbitrary-game debugger. The original
Session, SimulationControl, campaign/replay implementations, capture operation,
numerical comparator, Godot workers, private-provider configuration and existing
qualification gates are unchanged.

## Qualification

38 new tests exercise real existing Session/reference/campaign code and explicitly
labelled capture doubles. They cover union/conflicts, gaps, branch dependencies,
clock ordering, missing image bytes, refusal semantics, source preservation,
report binding, tampering/resealing, output ordering, bounds and CLI dispatch.
The new workflow retains exact source, installed wheel, JUnit and environment.

The Linux workflow additionally reruns the existing 26-check native image campaign
and 23-check native stateful campaign, builds timelines from those actual files,
rechecks them with subprocess creation forbidden, and exercises actual-file
Chromium navigation/filters/images. Windows qualifies host tests and packaging,
not native Godot rendering. Local content-mode browser inspection, when used,
is explicitly distinguished from actual file navigation. Observed outcomes belong
to their exact CI/source revisions, not to this workflow description.
