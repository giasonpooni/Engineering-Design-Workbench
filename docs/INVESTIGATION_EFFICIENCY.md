# Investigation efficiency and representation-preservation experiments

Notation Systems now has enough architecture that the next question is empirical:

> Does a structured/reduced investigation preserve the required scientific or
> production result while reducing context, recomputation and human translation?

This is more demanding than measuring token count alone.

## Trial contract

`ciw.investigation-efficiency.v1` records one method:

- `CONVENTIONAL`
- `LLM_CENTRIC`
- `NET`

against one exact task, acceptance policy and outcome class.

It records:

- the source representation and selected representation;
- source/selected item counts;
- the reduction method;
- required preservation checks:
  - `OUTPUT`
  - `INVARIANT`
  - `EPISTEMIC`
  - `PROVENANCE`;
- resource metrics;
- exact evidence references.

## Unknown means unknown

Every metric carries both a value and provenance:

`MEASURED | PROVIDER_REPORTED | HUMAN_LOGGED | DECLARED | UNKNOWN`.

An `UNKNOWN` metric must have `value=null` and no source reference. The
measurement layer never infers provider cost, token count or human time from a
workflow transcript.

This preserves the discipline already used by the single-agent game experiment.

## Comparability gate

Two runs can only be compared when they have:

- the same `task_id`;
- the same domain;
- the same acceptance policy;
- the same accepted outcome class;
- `accepted=true` for both;
- every required preservation check = `PASS`.

Only then does NET calculate per-metric ratios/deltas.

It deliberately emits **no aggregate winner or universal productivity multiplier**.

For example, a candidate may use 25% of the context but 120% of compute. That
tradeoff should remain visible instead of being hidden in a synthetic score.

## Derived measurements

Where inputs are actually known, NET derives:

- selected/source representation fraction;
- retrieved/raw evidence fraction;
- reused/(reused+recomputed) operation fraction;
- accepted outputs per human hour.

Missing measurements remain null.

## Research programme

The useful test is to repeat the same task three ways:

1. conventional human + specialist tools;
2. LLM-centric generic tool use;
3. NET/NISE/instruments.

Then repeat across genuinely different domains:

- physical-system investigation;
- scientific-computing investigation;
- creative-production investigation.

The architectural hypothesis becomes falsifiable:

```text
reduced representation
    + preserved required outputs/invariants/epistemic distinctions/provenance
    + less context/recomputation/human translation
        => useful middle-layer evidence
```

If preservation fails, the reduction is bad regardless of how cheap it was.

This is not yet a proof of a universal representation theory. It is the
experimental apparatus for discovering which abstractions actually transfer.
