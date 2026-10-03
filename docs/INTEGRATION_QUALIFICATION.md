# Integrated NET workload qualification

This review branch assembles the existing work rather than replacing it:

| Source | Exact reviewed head |
| --- | --- |
| Current main, including the newer game-development README | `2e5e0afb720b3d2b3609f9b5bd0ae51f0a6e8e73` |
| Local-provider provisioning, PR #39 | `53459ed27c1bf4063e7f3133af219ff5be487140` |
| Persistent simulation, PR #43, including covariance PR #40 | `834f632c6565f1dbd55e575e9ec0ae73b92b7816` |
| Retained FSRT view, PR #42 | `ef4c55361b05740f6c58d1a2c065633481e4a1ad` |
| Controller/domain ownership, PR #41 | `2dcdfe1b793ec97bf034442c0195db41df8209f2` |
| Interactive projectile, PR #45, including architecture PR #44 | `76075f9fa2235c109f800fd9d38a10cb6131c877` |

Original branches and specialist implementations remain intact. The latest main README
is retained; the earlier architecture details remain in their imported guide. No approved numerical-provider pin, numerical
tolerance, private-source visibility or equipment authorization is changed.

## Implemented integration checks

`tests/test_simulation_coexistence.py` checks the existing SimulationSession with
retained projectile records and a separately attached oscillator. These unit
checks use explicitly labelled doubles. The actual native gate is:

```sh
python scripts/check_simulation_coexistence.py \
  --binding /operator/scr-binding.json \
  --blender /operator/blender --godot /operator/godot \
  --bevy /operator/ciw-bevy-projectile \
  --adapter-root /checkout/tools/interactive-simulation \
  --output-dir results/coexistence
```

It requires real Blender, Godot, Bevy and approved SCR/Julia/C++ providers. One
Session retains the projectile operation history while the attached oscillator
keeps its own model and sole state writer. Engine execution must not advance the
oscillator; oscillator commands must not rewrite recorded projectile evidence.
Provider-free reopening must not implicitly restore a simulation owner. The
ordinary comparison and checkpoint receipts retain their separate meanings.

The [installed-wheel adapter-root path](INTERACTIVE_INSTALLED.md) and committed tested Cargo.lock close
source-location and initial dependency-resolution gaps. No engine is installed
as a core NET dependency, and saved content cannot choose code to execute.

## Failure audit: source provisioning is not a numerical failure

For PR #45 head `76075f9`, audit run `36386424664` collected every job from all
20 associated workflows with pagination. Sixteen workflows had 24 failed jobs;
each first failed at `Configure read-only private-provider access`. Tests behind
that step did not execute. The core Python matrix, installed wheel, old Godot
bridge, Windows/container deployment checks, projectile, energy and closed-pilot
checks had successes under their respective scopes. This is not an all-green
repository claim.

The current credential helper intentionally refuses private credentials for PR
jobs. Neither adding a secret to an untrusted PR nor replacing missing sources
with doubles closes the qualification gate. Existing workflows and zero-skip
requirements remain in place. Authenticated qualification needs the existing
reviewed/manual route; an operator-provisioned source set can instead use the
[local-only Git route](CI_ALTERNATIVE_SOURCES.md). The same actual numerical
commands must run. Private owner-repository qualification can exercise an exact
NET revision without giving a public PR access to private source.

A source-metadata inventory is informational only. HTTP success is not a source
pin check, an HTTP error is not proof that a repository is empty or absent, and
neither is a numerical qualification outcome.

## Completion criteria and status

Do not infer release readiness from this document. Required outcomes are retained
CI/JUnit/native reports bound to the exact integrated NET and provider revisions,
with no skipped mandatory test. Original independent native campaigns must be
rerun on the integrated revision. Public contracts, private source provisioning,
actual native execution, physical validation and deployment are distinct gates.

Main was reported `protected: false` during this review. No default-branch merge,
public service deployment, policy weakening or protection change is performed by
assembling the review branch. The final PR report records the actually observed
campaigns and any unresolved source/administrative gates.
