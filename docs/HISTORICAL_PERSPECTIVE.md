# Historical perspective: authoring tool and development contract

Status: first bounded Python implementation; no live game adapter. This is a
Notations Game Foundry workload on the existing NET/CIW substrate, not a new
engine, evidence store, universal historian or autonomous narrative service.

## Available in this branch

`net history` exposes two installed operations through the existing
CapabilityRegistry, OperationRegistry and Session:

| Operation | Implemented behavior |
| --- | --- |
| `history.actor-state.v1` | Project only explicitly received observations into an actor's qualitative perspective at a logical tick. |
| `history.epistemic-audit.v1` | Check annotated statements against available receipts, modality and declared evidence classification. |

Commands: `catalog`, `example`, `demo`, `run`, `inspect`, `export-actor`.
No Godot, Blender, paid model, API key or internet service is required at runtime.
The normal NET Python dependencies still apply. There is no new mandatory package.

## Install and run

Use a separate checkout so existing worktrees and uncommitted game work remain
untouched. Python 3.12 is the CI target; the package declares Python 3.11+.

```sh
git clone --branch feat/historical-perspective-v1-20260929 https://github.com/giasonpooni/Notations-Engineering-Terminal.git NET-history
cd NET-history
python -m venv .venv
```

Windows PowerShell, without changing execution policy:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\net.exe history demo --output-dir results/history-001
.\.venv\Scripts\net.exe history inspect results/history-001/workspace.json
```

Linux/macOS:

```sh
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/net history demo --output-dir results/history-001
.venv/bin/net history inspect results/history-001/workspace.json
```

`python -m ciw.perspective_workflow` is the equivalent module entrypoint after
installation. Always use a fresh output directory. Existing destinations refuse.
This feature branch is usable before merge; it is not a PyPI release or a claim
that main, other feature branches or either game's shipped build includes it.

The demonstration retains three actor-state executions and one audit execution
in the original Session. Its seven annotated statements have expected outcomes:
FAIL, PASS, INDETERMINATE, PASS, FAIL, PASS, PASS. The two deliberate failures are
knowledge before delivery and a forecast promoted to an observed fact. The
conflicting reports remain INDETERMINATE for an unqualified assertion. A report
of what was heard and an explicitly marked forecast are still permitted.

`demo` exits zero only when those expected diagnostic outcomes match. `run`
returns 0 for PASS, 2 for FAIL, 3 for INDETERMINATE and 1 for invalid input or
execution refusal. `inspect` checks retained integrity; exit zero there does not
change a retained FAIL into acceptance. Inspection recomputes the pure authored
policy but creates no provider execution and launches no engine or model.

## Author a scenario and export a perspective

```sh
net history example --output scenario.json
net history run --scenario scenario.json --at-tick 6 --output-dir results/history-002
net history inspect results/history-002/workspace.json
net history export-actor results/history-002/workspace.json --result-id RESULT_ID_FROM_INSPECTION --output commander-view.json
```

The unchanged example intentionally fails generic `run`; edit the declarations,
not the checker, to author a different scenario. The scenario contains explicit
actors, propositions, evidence references, observation routes and annotated
statements. The declaration is data only: it cannot select executable code,
change the fixed policy or import a provider.

`export-actor` selects an exact retained actor result. Its JSON contains only that
actor's received proposition texts, modalities, attribution, qualitative status
and local receipt records. It excludes world truth, unobserved propositions,
other actors' private receipts and research classifications. Supply this export,
not the complete scenario/workspace or operator audit, to a dialogue worker.

A filtered JSON view is not an OS access-control boundary. A worker that can read
the full repository/workspace can still see operator information. File permissions
or the coding host's isolated context must enforce that separation. Export does
not establish model compliance or authenticate the source publisher.

## Contract and limitations

The scenario schema is `ciw.historical-perspective.v1`; output schemas are
`ciw.actor-perspective.v1` and `ciw.epistemic-audit.v1`. The implemented validator
in `src/ciw/historical_perspective.py` is the exact contract. Generate an example
rather than inventing field names.

A root is an explicit local observation. A relay identifies its parent, sender,
recipient, send time, nullable receipt time and authored minimum delay. A sender
must already have received its parent; claims cannot change silently in transit.
All lineages are checked, including undelivered routes. An intercepted or lost
message has a null receipt and grants no information. A changed rumor or forged
claim requires a distinct authored origin; v1 does not simulate forgery itself.

Only integer logical ticks are supported. Calendar conversion, uncertain date
intervals, historical communication speeds, geography and physical courier
movement are not implemented. `historical_binding` must remain `unbound`.
A delay is an authored requirement, not measured travel time.

Beliefs retain positive and negative receipts without majority voting or fitted
probabilities. Conflicting evidence stays conflicted. Repeated transmissions of
one root do not become independent corroboration in the audit's origin count.
No Bayesian cognition, truth scores, calibrated trust, forgetting or motive
estimation is claimed. Missing knowledge is absence, never an invented falsehood.

`about_actor` permits one explicit attribution: what A has been told about B's
belief in a proposition. It never copies B's actual private view. It does not
implement recursive theory-of-mind, a decision planner or a complete actor mind.

Evidence classes are `attested`, `inferred`, `reconstructed`, `fiction`. Synthetic
fixtures may declare only fiction. Nonfiction presentation requires matching
source classification; arbitrary upgrading fails. These are author declarations,
not authenticated evidence. An attested letter is evidence of its recorded claim,
not automatic proof of its truth, sincerity or the writer's private motive.

Free-form dialogue is not semantically parsed. An unannotated statement returns
INDETERMINATE. Even an annotation that passes may misdescribe its associated text;
human review remains necessary. Forecasts are not rejected merely for discussing
the future, but cannot substitute for reports of observed facts.

Bounds: 256 KiB scenario, 32 actors, 64 propositions, 64 evidence references,
256 observations, 128 statements, 32-hop lineage bound, ticks 0..1,000,000,000.
Inherited JSON depth/text/type guards also apply. Unsupported input refuses.

World truth here is nullable, operator-authored scenario state, not recovered
historical reality or ESM canonical admission. Source evidence, operation,
execution, result, verification and release identities remain distinct. Ordinary
checks keep null verification identities and do not admit or release anything.

## Game style and portfolio decision

Store historical research as evidence-linked claims, dates, places, relationships
and accounts; author biographies as situated trajectories through that material.
A protagonist is an entry point, not the boundary of the historical world.
Discovering another person can motivate an encounter, chapter or later campaign;
it does not automatically authorize a generated mission or prove two people met.

The intended loop is world state -> available observations -> actor beliefs ->
goals/constraints -> action -> consequences -> new observations. Distinguish
modeled world, lived experience, remembered account, retelling and later research.
An actor must not inherit the narrator's hindsight or the researcher's library.

1792 is the primary production workload: rich childhood/adolescence through the
prelude to Lahore, then the full Ranjit Singh narrative before historical-character
DLC. Hero of the Two Worlds progresses slowly as a secondary title and transfer
test. Garibaldi is its narrative anchor for interconnected lives, not a pretext to
begin every possible campaign. Geronimo is on hold; preserve its existing work.

The games own history interpretation, names, story, assets, state, clocks, saves
and release decisions. NET owns development operations and retained investigations.
The C++/Rust/Python/Julia direction and Godot/Bevy/Blender roles remain unchanged;
this increment uses Python only and copies no proprietary game implementation.

## Remaining operations, not implemented

The earlier design vocabulary is retained as a roadmap, not exported APIs:
`observation.route`, `belief.update`, `provenance.attach`, `uncertainty.retain`,
`relationship.project`, `goal_state.compile`, `decision.reconstruct`,
`perspective.switch`, `counterknowledge.test`, `narrative.compile`, `epistemic.audit`.
The two actual operation IDs are listed at the top. The current compiler covers
only authored routing validation, perspective projection and annotation audit.

Next qualification: a game-owned observation adapter using the existing game
clock and save rules; three actors, delayed/intercepted message, conflicting
accounts, view switch without private-memory transfer, and checkpoint roundtrip.
Then test the same contract on the Garibaldi harbour rather than creating another
runtime. No such native-game or cross-title execution is claimed in this branch.
Goal/relationship models, scene assembly, semantic dialogue analysis, calibrated
belief updates and larger historical graphs require separate measured increments.

## Qualification

```sh
python -m pytest -q tests/test_historical_perspective.py
```

Local source qualification: 47 new cases plus 291 unchanged production, game,
control and interactive cases passed. Local Python 3.13.5 / NumPy 2.3.5 differs
from the unchanged pinned CI dependency profile. Installed-wheel repetitions and
hosted CI are reported separately in the PR, not added as unique tests.

Tests include future-information isolation, exact delivery boundaries, lost
messages, conflicts, correlated retransmissions, explicit attribution, evidence
classes, input detachment, malformed/cyclic declarations, original Session
identities, source binding, resealed result tampering, create-only export and
provider-free reopening. A fixture initially confused knowledge of a proposition
with an attributed belief about that proposition; it now checks the explicit
attribution field. An inherited subprocess import failure was fixed by installing
the package, not by changing its test. No inherited assertion was weakened.

Measure accepted, integrated playable work per human hour, including setup,
supervision, costs, failures, rework, visual quality and transfer. Passing these
software contracts is not evidence of enjoyable gameplay, historical truth,
human theory-of-mind accuracy or studio-scale production throughput.
