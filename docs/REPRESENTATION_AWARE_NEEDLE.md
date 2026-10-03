# Representation-aware Needle V1

Needle now respects the scientific contract of the representation through which
an intervention is proposed.

The governing rule is:

```text
query sufficiency != intervention sufficiency
```

A compressed or projected representation may be perfectly adequate for a named
query while lacking the distinctions required to perform a local intervention.

## Decisions

`ciw.intervention-gate.v1` produces exactly one of:

- `LOCAL` — the current representation explicitly supports the intervention;
- `EXPAND` — the current representation does not support it, but a richer
  declared representation plus retained evidence does;
- `REFUSE` — no resolved representation supporting the intervention is
  available.

The gate does not materialize richer state. Expansion remains a separate explicit
operation.

## Example

The qualified signal registry contains:

```text
time series
    ↓ lossy periodogram transform
periodogram
```

The time-series representation supports:

```text
select-channel-and-half-open-interval
```

The periodogram representation supports spectral queries but no time-domain
interventions.

Therefore:

```text
Needle through retained time series -> LOCAL

Needle through periodogram
    without richer retained state -> REFUSE

Needle through periodogram
    with declared time-series representation + evidence -> EXPAND
```

Only a LOCAL gate may create an ordinary Needle plan in V1.

## Why this matters

This prevents a reduced representation from silently being treated as though it
preserved distinctions it actually discarded.

It also gives NET a practical form of progressive scientific disclosure:

```text
coarse representation
      ↓ intervention unsupported
recover richer retained representation
      ↓
plan intervention
```

The system does not assume that a coarse state determines a unique fine state.
A future expansion layer may need to expose a set/distribution of compatible
fine states rather than a single inverse.

## Authority

The gate:

- does not execute providers;
- does not materialize state;
- does not mutate canonical state;
- does not admit evidence/state;
- does not claim physical truth;
- does not infer causality.

It is a planning guard over representation contracts.
