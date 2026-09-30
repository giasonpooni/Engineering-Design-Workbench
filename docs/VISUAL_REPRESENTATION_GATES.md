# Visual Representation Gates V1

This increment binds the Visual System Board to the existing representation,
morphism, intervention-gate and evidence-bound expansion substrate.

It implements the brief's rule that a visual node is an address into typed
scientific structure, not merely a drawing. The browser does not infer
representation meaning from labels.

## Identity chain

```text
Board node + exposed parameter
        |
        v
ciw.board-intervention-binding.v1
        |
        +-- exact Board digest
        +-- exact morphism-registry digest
        +-- exact current representation
        +-- exact intervention identity
        +-- optional richer representation
        +-- optional projection morphism
        |
        v
existing ciw.intervention-gate.v1
        |
   +----+---------+
   |              |
 LOCAL          REFUSE
   |              |
   |         retained source available?
   |              |
   |             yes
   |              v
   |            EXPAND
   |              |
   |       existing expansion record
   |              |
   |       independent replay verify
   |              |
   |             PASS
   |              |
   |        existing promotion record
   |              |
   +----------> LOCAL
                  |
                  v
          existing represented Needle
                  |
                  v
          ordinary Needle execution
```

No new scientific planner or executor is introduced.

## Complete exposed-coordinate binding

The new `ciw.board-intervention-binding.v1` record must cover every exposed
parameter on every OPERATION node in the supplied Board. Partial bindings refuse.

Each bound node retains:

- current representation identity and digest;
- parameter -> intervention identity;
- optional richer recovery representation identity and digest;
- optional scientific projection morphism identity and digest.

If a projection morphism is supplied, its codomain must be the bound current
representation and its semantic capability must equal the existing Board
operation capability. The bound parameters must be declared by that morphism.

This means the browser cannot decide that a node "looks spectral" or "looks like
a state" and invent representation semantics.

## Visual decision states

After the ordinary candidate Board has compiled, the inspector displays the
existing intervention gate:

- **LOCAL** — current representation explicitly supports the intervention.
- **REFUSE** — current representation does not support it and no verified
  expansion has occurred.
- **EXPAND** — only during an explicit retained-evidence expansion action.
- **promoted LOCAL** — only after the existing replay verification and promotion
  chain succeeds.

Candidate compilation is still separate from authorization.

## Qualified oscillator specimen

The demo binds all three exposed `channel` coordinates.

### Signal statistics

```text
statistics.channel
    -> signal.timeseries.uniform-scalar.v1
    -> select-channel-and-half-open-interval
    -> LOCAL
```

Changing `q -> v` can therefore proceed through the existing represented Needle
planner.

### Periodogram

```text
spectrum.channel
    -> signal.periodogram.one-sided-density.v1
    -> select-channel-and-half-open-interval
    -> REFUSE
```

The periodogram representation preserves frequency-domain queries but declares
no local support for the time/source-selection intervention.

When the operator explicitly asks to verify retained expansion:

```text
retained q time series
      |
      | signal.periodogram.transform.v1
      v
retained q periodogram
```

NET uses the exact baseline periodogram execution/result, resolves the exact
retained source evidence, independently replays the periodogram projection and
compares evidence, operation, parameters, runtime and scientific data.

Only a PASS creates the existing promotion record whose nested gate is LOCAL on
`signal.timeseries.uniform-scalar.v1`.

The subsequent candidate run delegates to
`plan_after_verified_expansion -> plan_represented_needle -> execute_needle`.

The replay execution occurs in a separate Session and is not hidden inside the
main Board execution count.

## CLI

The demo now also retains the exact scientific fixture:

```sh
net board demo --output-dir board-demo
```

produces:

```text
board.json
source.json
morphism-registry.json
intervention-binding.json
board.html
```

Run the gated visual workbench explicitly:

```sh
net board serve \
  board-demo/board.json \
  --source board-demo/source.json \
  --morphism-registry board-demo/morphism-registry.json \
  --intervention-binding board-demo/intervention-binding.json \
  --output-dir board-session \
  --allow-run
```

Without the two scientific binding files, the Visual Board retains its previous
behavior and does not claim representation gating.

## Browser workflow

Direct LOCAL case:

```text
Run baseline
-> Signal statistics
-> q -> v
-> Compile candidate
-> gate LOCAL
-> Run candidate Needle
```

Lossy representation case:

```text
Run baseline
-> Periodogram
-> q -> v
-> Compile candidate
-> gate REFUSE
-> Verify retained expansion
-> replay PASS
-> promoted LOCAL
-> Run candidate Needle
```

The Run button remains disabled across the REFUSE boundary.

## Boundaries

This increment does not:

- infer a representation from a visual label;
- invert a periodogram;
- treat a compatible fibre as an observed state;
- admit canonical state;
- change the underlying Board during view navigation;
- create new provider or scheduler semantics;
- convert replay agreement into physical calibration;
- authorize hardware or physical actuation;
- claim causal effects from Needle deltas.

The representation gate is planning authority only. Physical authority remains
separate.

## Next seam

The Board now has an explicit scientific control boundary. The next bounded
extension is to project retained **representation realizations and witnesses**
onto the same selected node: artifact realization status, morphism witness
checks, uncertainty/provenance, and verification state should become additional
view layers without changing intervention authority.

## Evidence projection extension

The stacked Visual Evidence Projection increment adds exact retained representation
realizations and finite morphism-witness summaries to the selected node after a
completed baseline exists. It does not alter LOCAL / EXPAND / REFUSE decisions.
See [Visual evidence projection](VISUAL_EVIDENCE_PROJECTION.md).
