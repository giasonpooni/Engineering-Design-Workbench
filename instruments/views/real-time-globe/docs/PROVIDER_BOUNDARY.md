# Geographic provider and comparison boundary

This client remains a read-only geographic projection with a synthetic provider.
Runtime eligibility is not source authentication, canonical admission, scientific
verification, or proof that a shipment or facility exists.

## Snapshot loading and state

`WorldStore.init(provider)` validates the complete loaded snapshot, clones it,
deeply freezes it, and builds fresh indexes before changing any active state.
Failed loading or validation preserves the previous snapshot and provider.
When loads overlap, only the newest requested load may commit; older requests
reject with `Snapshot load superseded`, including when the newer request fails.
Repeated loading does not accumulate old entities, joins or flow memberships.
Snapshot getters and indexed record arrays expose immutable data.

`src/data/validation.ts` checks:

- Plain-data objects without getters, functions, cycles, sparse arrays or symbols.
- Unique identities across snapshot records and nested segment/route-constraint
  identities; bounded identifiers and nonempty source/unit fields.
- Finite numbers, declared numeric ranges, WGS84 `[longitude, latitude]` positions,
  geometry type, lifecycle and transport enums.
- Real-calendar UTC instants with seconds and at most millisecond precision;
  ordered validity intervals and an ordered snapshot time range.
- Referential kinds: route endpoints identify nodes; flows identify commodities,
  routes and nodes; observations, assertions, constraints and events identify
  existing geographic entities. Unresolved references reject the snapshot.
- Declared flow segment order and chain continuity. Whole-route segment endpoints
  must match route endpoints, allowing reversal only for a bidirectional route.
  Partial spans have bounded ordered fractions and referenced nodes; correspondence
  between intermediate nodes and physical route geometry is not established here.

Unknown optional units or validity stay absent. They are not replaced by default
units, dimensionless measurements, open validity intervals, or inferred evidence.
`corridorId` is an external grouping label, not a materialized entity reference;
provenance evidence descriptors name external evidence and are not resolved.

Current structural limits are 10,000 entries per array, 250,000 visited values,
32 nesting levels, 4,096 characters per text, 256 per identifier, and 128 per
unit label. These bound the in-memory inspection; a future network provider must
also bound response bytes before parsing. Provider callable code and the local
runtime are trusted, not sandboxed. TypeScript's existing mutable-looking types
remain compatible, but writes to returned frozen objects now fail at runtime.

`stateAt(entityId, t)` refuses unknown IDs before invoking the provider and
requires `t` within the inclusive snapshot range. The returned entity ID and
timestamp string must exactly match the request. Finite state values and active
event IDs are checked. Every active event must affect that entity and contain
`t` in its `[start,end)` interval. Its severity's effect on the model is not
recomputed or independently verified. The synthetic provider follows these
identity/time rules and has no unknown-entity fallback.

## Comparison API tightening

The window is mandatory:

```ts
store.deviationsFor('route:example', {
  knownAt: '2026-09-05T00:00:00Z',
  from: '2026-09-01T00:00:00Z',
  to: '2026-09-05T00:00:00Z',
});
```

`knownAt` is a knowledge cutoff, not an event timestamp. `[from,to)` is the
event-time analysis window within the snapshot range. The start is included,
the end excluded; an empty or reversed window is invalid. No wall clock or
unrecorded default is used. The current inspector explicitly supplies the
simulation cursor as `knownAt` and `to`, and the dataset start as `from`.

A compatible observation must identify the same entity and metric, carry the
same explicitly declared unit label, be known by the cutoff, and occur inside
the window. The assertion must already be asserted and known, declare both
validity endpoints, and apply at the observation time. An observation before
the assertion or outside its own declared validity is excluded. Different unit
labels, including `h` versus `s`, are refused rather than converted; both units
missing does not make them dimensionless or equal. The synthetic assertions
explicitly declare their generated dataset applicability interval.

Each returned comparison has `status: ready | unavailable`, a reason, excluded
observation IDs with reasons, explicit selection/method/unit metadata, and the
complete admitted-to-comparison observation records. An unavailable comparison
has `meanObserved: null` and `deviation: null`. Nonfinite aggregate arithmetic
also yields an unavailable result rather than an invalid plotted number.

The arithmetic mean is descriptive. Source IDs and all contributing observation
IDs are retained; `independence: not_established` forbids interpreting record
count as independent evidence or improved precision. Duplicates are rejected at
snapshot loading, but distinct records may still describe correlated sources.
No weighting, covariance propagation, calibration or independence inference is
performed.

For ready comparisons, `deviation.observationIds` lists every contributor in
event-time/ID order. The legacy `observationId` remains the final member, not a
claim that it alone produced the mean. `ratio` is now `number | null`, with
`null` for a zero asserted value. Consumers must handle nullable comparisons and
ratios; the inspector has been updated accordingly. Source records remain
unchanged and comparison outputs are deeply frozen.

## View tools and checks

The structured view-tool surface rejects unknown/extra parameters, accessors,
wrong primitive types and nonfinite numbers. It validates coordinate bounds,
time fractions, known layers/presets/entities and bounded text before dispatch.
`"false"` is not a Boolean. Camera altitude is limited to 0–1,000 Earth radii
above the surface. These controls still change views only.

Run `npm test` with Node 24+ for dependency-free tests against the actual
TypeScript sources, including the real synthetic provider, replacement races,
malformed snapshots, comparison clocks/units/lineage, state bindings and view
tools. `npm run check` also runs provenance, seam and TypeScript checks;
`npm run build` runs them before the production Vite build.

The seam check now uses path-component containment, rejecting sibling directories
such as `src/data-extra`. Its literal-import scan is a development guardrail,
not a JavaScript sandbox or comprehensive analysis of computed imports.

There is no live data provider, native instrument-result importer, external
agent connection, workbench session/replay connection, or automatic promotion
of an inspected value to scientific or canonical state.
