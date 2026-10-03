# Oscillator representation-reduction experiment V1

This is the first committed same-task test of the intermediate-representation
hypothesis.

## Task

Using the same retained damped-oscillator evidence, return:

1. descriptive statistics for channel `q`;
2. the periodogram for channel `q`.

## Baseline

The baseline executes a deliberately broad eight-operation graph:

- the two required operations;
- six additional statistics/spectrum computations that are not structurally
  connected to the investigation focus.

This is a controlled redundancy experiment, not a claim that ordinary scientific
practice always wastes 75% of its operations.

## Candidate

A NISE system catalog contains the same broad operation set, but only the two
required operation nodes are connected to the oscillator focus.

NISE constructs the query-specific schematic. The normal NISE→NET handoff then
compiles the two selected semantic capabilities through NET's existing semantic
registry into the same built-in providers.

## Preservation requirements

The reduction is accepted only if all four checks pass:

- required statistics + periodogram data exactly equal;
- required operation contracts exactly equal;
- source evidence identity exactly equal;
- provider runtime identity exactly equal.

The experiment then records the baseline/candidate through
`ciw.investigation-efficiency.v1`.

## What is measured

Measured:
- NISE/source representation node count;
- NET graph node count;
- deterministic operation calls;
- experiment graph bytes;
- source evidence bytes;
- wall time;
- accepted/rejected outputs/errors/retries.

Unknown remains unknown:
- token counts;
- human active time;
- model/API cost beyond the declared zero LLM/model-call cost.

Wall-time ratio is recorded but **not gated**, because hosted-runner noise is not a
stable performance benchmark.

## Scope

A successful result demonstrates one thing:

> for this declared oscillator task, a query-conditioned structural reduction
> preserved the required results/contracts/evidence/provider identity while
> executing fewer deterministic operations.

It does not establish universal NISE sufficiency, human productivity gains, a
multi-scale precision theorem, or a general law of representation.
