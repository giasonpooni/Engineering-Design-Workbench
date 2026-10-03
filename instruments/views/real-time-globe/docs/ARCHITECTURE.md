# Geospatial State Visualization — Architecture

For the current public component inventory and integration boundaries, see the
[Notation Systems stack map](https://github.com/giasonpooni/Computational-Instrumentation-Workbench/blob/main/docs/STACK.md) and [this component's role](STACK_ROLE.md).
The [diagram atlas](https://github.com/giasonpooni/Computational-Instrumentation-Workbench/blob/main/docs/DIAGRAMS.md) collects the system views.

This document describes the implemented geographic state inspection client in
Notation Systems' computational instrumentation stack. File references identify
its contracts, implementation, and checks; intended boundaries are distinguished
from guarantees the checks enforce.

## 1. The projection boundary

The client is a **projection** of provider-supplied geographic state. It has no
canonical-state write or evidence-admission API. Everything visual — globe,
routes, particle flows, panels — is derived from snapshots handed across a typed
boundary; view-level operations (select, focus, toggle layer, scrub time) act
on the projection only. `validatedSnapshot` checks bounded plain data and makes
a detached, deeply frozen snapshot. `WorldStore.init` prepares fresh indexes
before atomically replacing snapshot, provider and indexes. A stale pending
load cannot overwrite a newer selection. This does not authenticate the provider.

`SyntheticProvider` supplies a `WorldSnapshot` to `WorldStore`. The `AppApi`
facade exposes read-only state and view operations to the UI; the Earth and
route layers project that state through Three.js. This build uses synthetic
records and has no live data-service connection. Evidence and State Management
has the separate information-governance role; Scientific Computation Runtime
has the workload-execution role; Computational Instrumentation Workbench has the
session, adapter, and replay role. This repository implements the visualization
client and its provider boundary, not adapters to those components.

State flows down; nothing flows back up. UI components receive `AppApi` and
nothing else — they never import renderer internals and never mutate data
(`src/app/api.ts` header comment is the contract).

## 2. The seam and its mechanical enforcement

The semantic layer, `src/data/**`, is **renderer-blind by structure, not by
discipline**. `scripts/check-seam.mjs` walks every `.ts` file under
`src/data/` and fails the build on:

- any **bare-module import** (`three`, DOM libs, anything from npm — the data
  layer imports no packages at all), and
- any **relative import that escapes** `src/data/`,

with exactly two allowed pure-kernel exceptions:
`src/core/events.ts` (the typed `EventBus`) and `src/core/time.ts`
(`SimClock`). Both are dependency-free, erasable TypeScript.

The check runs as the first step of `npm run check` (which `npm run build`
runs first). If the renderer ever leaks into canonical-state land, the build
breaks instead of a reviewer having to notice. A useful side effect: because
`src/data` is pure, erasable TypeScript, Node can execute it directly via
type stripping — which is exactly what the provenance check does.

## 3. Provenance discipline

Every record that claims to describe the world carries a `Provenance` block
(`contracts.ts`): `source`, `knownAt`, optional validity window, evidence
descriptors, and confidence. This build uses `source: 'synthetic:demo'`.

`scripts/validate-provenance.mjs` does not lint types — it **executes the
real dataset** (`buildWorldSnapshot()` from `src/data/synthetic/world.ts`)
and fails the build if any node, route, flow, commodity, event, constraint,
assertion, or observation lacks `provenance.source`.

Source identity is carried by each record and displayed by the inspector.
The status chip is a fixed synthetic-build label; its tooltip reads the
snapshot's `meta.disclaimer`. Neither the chip nor the provenance-presence
check authenticates a source or establishes physical correctness.

Related: `Route.geometryBasis` (`'routed' | 'great_circle_estimate' |
'synthetic_corridor'`) keeps *what the geometry is* queryable too — a straight
arc over a lake is not where the truck goes, and that difference must never
become cosmetic.

## 4. Promises vs evidence

`contracts.ts` splits claims into three distinct record types, never one
field overwritten by another:

- **`Assertion`** — a promise: something the system claims about an entity
  (`transit_hours`, `capacity`, `dwell_hours`), with its own provenance and
  `assertedAt`.
- **`Observation`** — evidence: a timestamped measurement, with its own
  provenance.
- **`Deviation`** — the join: `delta = observed − asserted`,
  `ratio = observed / asserted`, referencing both records.

`WorldStore.deviationsFor(entityId, { knownAt, from, to })` (`store.ts`) performs
this join on demand. The explicit knowledge cutoff and half-open event window
`[from,to)` are distinct clocks. Comparisons require identical declared units,
an assertion with an explicit applicability interval, and point observations
inside that interval and any declared observation validity. Every exclusion has
a reason. The descriptive mean retains all contributing IDs and source records;
it does not establish independent samples, precision or source truth. A zero
assertion yields `ratio: null`; no compatible records yield an unavailable
comparison, not a zero. Nothing is stored back or overwritten.

The inspector passes the selected simulation cursor as knowledge cutoff and
event-window end, starting the window at the dataset start; the initial empty
window shows no comparison. Full API details and compatibility changes are in
[`PROVIDER_BOUNDARY.md`](PROVIDER_BOUNDARY.md).

`Route.estimatedDurationHours` and `Route.capacity` are convenience
projections of the current assertion of record. They must **never** be
overwritten by outcomes: the deviation history *is* the point. A twin that
replaces its estimate with the actual forgets that it was wrong; this one
keeps both records so it can show where its own estimates run optimistic —
per entity, per metric, over time.

### Comparison without overwriting source records

```mermaid
flowchart TD
  A["Assertion with applicability"] --> G{"Identity, unit and time eligibility"}
  O["Observation records"] --> G
  W["knownAt and event window"] --> G
  G -->|"excluded records"| X["IDs and exclusion reasons"]
  G -->|"compatible observations"| M["Descriptive arithmetic mean"]
  G -->|"no compatible observations"| U["Unavailable with null comparison"]
  M -->|"finite aggregate"| D["Delta and nullable ratio"]
  M -->|"nonfinite aggregate"| U
  D --> I["Inspector with full source lineage"]
  U --> I
  X --> I
```

Solid arrows summarize `WorldStore.deviationsFor` and the inspector. The
knowledge cutoff is distinct from the half-open event-time window. Units must
match explicitly; an absent unit is not inferred. A zero assertion gives a
`null` ratio, not an infinite score. Record count does not establish independent
evidence or precision. Every comparison is a read-only derivation: neither the
assertion nor its observations are replaced by the resulting mean or deviation.

## 5. Data contracts inventory

All shapes live in `src/data/contracts.ts` (provider-independent, WGS84
lon/lat, GeoJSON-compatible geometry subset):

| Area | Types |
|---|---|
| Identity / provenance | `EntityId`, `Timestamp`, `DataSource`, `Provenance`, `LifecycleStatus` |
| Geometry | `LonLat`, `PointGeometry`, `LineStringGeometry`, `Geometry` |
| Ontology | `TransportMode` (road/rail/maritime/air), `NodeKind` (ports … chokepoints), `EntityKind` |
| Base | `Entity` (id, kind, name, geometry, status, provenance, `importance` 0..1 for LOD, country, tags) |
| Facilities | `Facility` + `Port`, `Airport`, `RailTerminal`, `Warehouse`; `QuantityRating` |
| Routes | `Route` (first-class semantic object: origin/destination, distance, promised duration, capacity, utilization, `constraints`, `historicalState` samples, `geometryBasis`), `RouteConstraint`, `RouteStateSample`, `TransportSegment` |
| Commodities / flows | `Commodity`, `Flow` (chain of `TransportSegment`s; `intensity` drives particle density) |
| Promises vs evidence | `Assertion`, `Observation`, `Deviation` |
| Constraints / events | `Constraint`, `WorldEvent` |
| Temporal | `TemporalRegime`, `TemporalState`, `EntityState` |
| Snapshot | `WorldSnapshot` — nodes, routes, flows, commodities, events, constraints, assertions, observations, cityLights, timeRange, meta (label + **disclaimer**) |

### The provider interface

`src/data/provider.ts` defines `SpatialDataProvider` — the only thing the
visualization client uses for data:

```ts
interface SpatialDataProvider {
  readonly id: string;
  readonly label: string;
  load(): Promise<WorldSnapshot>;                       // initial hydration
  stateAt(entityId: EntityId, t: Timestamp): EntityState; // deterministic
  query?(viewport: ViewportQuery): Promise<Partial<WorldSnapshot>>; // optional
  subscribe?(onDelta: (delta: Partial<WorldSnapshot>) => void): () => void; // optional
}
```

`SyntheticProvider` (`src/data/synthetic/provider.ts`) implements it today:
all dynamic state is a pure function of `(entityId, t)` — hash-seeded
sinusoids plus smooth event ramps, no randomness, no wall clock. The interface
requires `load()` and `stateAt()`; `query()` and `subscribe()` are optional.
No live provider is implemented in this build. Unknown synthetic entities,
invalid UTC times and times outside the snapshot range are refused instead of
receiving synthetic fallback state. Returned state must name the requested
entity and exact UTC timestamp; active event references must match the entity
and event-time interval. These checks do not verify the dynamics model.

`WorldStore` (`src/data/store.ts`) sits on top of whichever provider is
plugged in: it indexes the snapshot (nodes, routes-by-node, flows-by-route,
assertions/observations-by-entity), resolves temporal state through the
provider (`stateAt`), computes deviations, filters active events, and serves
scored fuzzy search. It is read-only by design and renderer-blind by the
seam check.

## 6. Rendering architecture

Three.js scene composed from independent modules:

- **Earth** (`src/earth/*`, `src/geo/texture.ts`): procedural equirectangular
  day/night/mask textures generated at boot from Natural Earth 50m land
  topology (world-atlas TopoJSON in `public/data/`) plus corpus city lights.
  No external imagery — the planet is drawn, not photographed; seeded
  generation makes every boot identical. Atmosphere, graticule, and starfield
  are separate scene modules.
- **Countries** (`src/geo/countries.ts`): Natural Earth 110m borders as line
  geometry, point-in-polygon picking on lon/lat, selection outlines.
- **Routes** (`src/layers/routesLayer.ts`): per-mode route rendering — each
  `TransportMode` gets its palette color (`src/app/palette.ts`) and its
  routes are drawn as polylines on the sphere, driven by the semantic
  `Route` records, never decorative.
- **Flow particles** (`src/layers/flowsLayer.ts`): route polylines are baked
  into a float `DataTexture` (one row per route, 128 arc-length samples);
  each particle is `(row, phase, speed)` and the **vertex shader** advances
  phase with time and reads position from the texture — thousands of moving
  loads in one draw call with zero per-frame CPU geometry work. Particle
  density is proportional to `Flow.intensity`; particles are
  representational, not real shipments.
- **LOD / progressive disclosure**: camera altitude (`CameraFacade.
  altitudeRadii()`) and `Entity.importance` gate what is drawn and labeled —
  high orbit shows the skeleton, descending reveals detail (nodes layer,
  labels layer).
- **Layer compositing** (`src/layers/layerManager.ts`): the `LayerId` set
  from `api.ts` maps onto scene-object visibility; presets are curated layer
  combinations; `layersChange` events keep UI panels in sync.
- **Camera** (`src/core/cameraController.ts` behind `CameraFacade`): fly-to,
  route framing, and the cinematic follow-path dolly used by Follow the Load.

## 7. Command and tool interfaces

The command bar grammar lives in `src/app/commands.ts`: pure functions
(`executeCommand`, `suggestCommands`) over the `AppApi` facade — no module
state, no DOM. The facade exposes: layer toggles, presets, search/focus, flow filtering, clock
control, route comparison, the demo scenario.

`src/app/toolSurface.ts` implements **one structured registry of operations
over `AppApi`** — each entry a name, a typed
parameter list, a description, an executor, and safety flags
(`destructive` / `longRunning` / `requiresConfirmation`). All tools are
non-destructive and require no confirmation; the Follow the Load demo sets
`longRunning: true`. Every operation affects the view. The text grammar
in `commands.ts` is one front end to the same facade. The registry is exposed
at runtime as `window.payloadEarth.tools` with
`window.payloadEarth.invokeTool(name, args)`. These existing browser API names
remain stable across the repository rename. External agent/MCP bindings are
not implemented here. The registry currently exposes view operations only.

## 8. Temporal model

`SimClock` (`src/core/time.ts`) is the global temporal control: sim time is
scrubbed and played independently of the wall clock, configured against the
snapshot's `timeRange { start, end, now }`.

- **Regime**: `TemporalRegime` is derived from sim time vs the dataset's
  `now` — within ±30 minutes is `'current'`, before is `'historical'`, after
  is `'forecast'` (`'scenario'` is reserved for future scenario branches).
- **Playback**: `tick(dtSeconds)` advances sim time at `speed` sim-seconds
  per wall-second (default 3600 = 1h/s; the `speed 6h` command sets 21600),
  clamping and pausing at the range end. `setFraction` scrubs; `jumpToNow`
  returns to the regime boundary.
- **Determinism**: every dynamic layer resolves entity state as
  `store.stateAt(entityId, clock.simTime)`, which delegates to the provider.
  The provider contract requires `stateAt` to be deterministic for a given
  `(entityId, t)` — the synthetic implementation is a pure hash-seeded
  function — so scrubbing is stable: the same instant always renders the
  same world. `world.ts` precomputes `Route.historicalState` with the same
  resolver, so the sparse temporal spine and live `stateAt()` agree by
  construction.

Clock changes fan out through the typed `EventBus` (`src/core/events.ts`) as
`TemporalState` events; the timeline UI, layers, and status bar all subscribe
to the same stream.

## 9. Scope

This client presents synthetic network data at a planetary scale using
Three.js. It is an implemented visualization application, not a general-purpose
rendering engine, scientific simulator, evidence store, or replacement for the
workbench. It does not simulate physical facilities, vehicles, or ocean
dynamics, and its forecast values are synthetic demo values. No live provider,
scientific runtime adapter, or workbench session/replay integration is present.

## 10. Display semantics

The contracts and display conventions preserve the following distinctions:

- **Provenance is a property of the record, not a label on the UI.**
  Every synthetic record carries `provenance.source: 'synthetic:demo'` in
  the same field a real record will carry `'external:ais'` — "is this
  real?" can be examined at the record level. Inspector evidence sections
  expose that source. The status bar's fixed SYNTHETIC / DEMO DATA label
  and snapshot-disclaimer tooltip describe the supplied demo build.
- **A number carries its warrant.** The route inspector shows PROMISED
  transit (an `Assertion`) against OBSERVED transits (`Observation`s) and
  the resulting deviation with `n=` — never a bare number that forgets
  where it came from.
- **Which kind of nothing.** `LifecycleStatus` includes `'unknown'` and the
  palette reserves an unobserved tone (`UNKNOWN`). This supplies a display
  category for missing knowledge; it is not an implemented telemetry-freshness
  policy, and no live telemetry provider is present.
- **Geometry states its basis.** `Route.geometryBasis`
  (`'routed' | 'great_circle_estimate' | 'synthetic_corridor'`) keeps the
  difference between a routed path and an estimate queryable. All
  distances derived in this client are great-circle estimates and are
  presented as such, never as road distance.

## 11. Repository identity and compatibility

The current repository is
[`Geospatial-State-Visualization`](https://github.com/giasonpooni/Geospatial-State-Visualization),
previously `PayloadOS-Render-Engine`. The package name `payload-earth`,
`window.payloadEarth` browser API, `pe-` / `pi-` CSS namespaces, source values
such as `payload:canonical` and `payload:spatial`, and record/operation IDs
remain unchanged. Those identifiers are compatibility contracts, not display
branding. Historical records and pinned execution identities are not rewritten
when repository locations change.
