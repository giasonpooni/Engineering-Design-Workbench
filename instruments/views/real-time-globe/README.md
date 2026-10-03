# Geospatial State Visualization

Part of **Notation Systems' computational instrumentation and evidence infrastructure** for industrial and cyber-physical systems.

[Diagram atlas](https://github.com/giasonpooni/Notations-Engineering-Terminal/blob/main/docs/DIAGRAMS.md) · [Stack map](https://github.com/giasonpooni/Notations-Engineering-Terminal/blob/main/docs/STACK.md) · [Component role and interfaces](docs/STACK_ROLE.md)

**Read-only visualization of geographic entities, routes, flows, and temporal state.**

Geospatial State Visualization is the geographic inspection client in Notation
Systems' computational instrumentation stack. It projects provider-supplied
state onto a Three.js globe, keeping entity identity, source provenance, time,
and geometry basis visible alongside the result. It does not retain or govern
canonical evidence, execute scientific workloads, or implement a general-purpose
rendering engine.

**Status: implemented browser client with a deterministic synthetic provider.**
Facilities, four transport modes (road, rail, maritime, air), commodity-flow
particles, a timeline, entity inspectors, search, and view commands are present.
No live data provider, scientific runtime adapter, or workbench session/replay
integration is implemented in this repository. Historical, current, and forecast
labels describe positions within the synthetic dataset's time range.

```mermaid
flowchart TD
  P["Synthetic provider snapshot"] --> V{"Validate identity and records"}
  V -->|"invalid or superseded"| R["Keep previous active snapshot"]
  V -->|"eligible replacement"| S["Immutable WorldStore"]
  S --> T["Checked state and comparisons"]
  C["Explicit simulation cursor"] --> T
  T --> G["Globe, timeline and inspector"]
  U["View commands"] --> G
```

The arrows describe local read and projection paths. Provenance, geometry basis
and declared times stay attached to displayed records. View controls change the
presentation; there is no canonical-state write or evidence-admission path.

![Geospatial State Visualization — global network view](docs/media/global.png)

| Night-side economy | Route inspector |
| --- | --- |
| ![Asia at night](docs/media/asia-night.png) | ![Route inspector](docs/media/route-inspector.png) |

The screenshots retain the earlier display branding; they illustrate the same
synthetic client.

## Responsibility in the stack

| Component | Responsibility |
| --- | --- |
| [Provenance-Preserving Data Acquisition](https://github.com/giasonpooni/Provenance-Preserving-Data-Acquisition) | Acquire source material and retain observation lineage. |
| [Evidence and State Management](https://github.com/giasonpooni/Evidence-and-State-Management) | Retain and govern evidence, versioned state, admission, and release. |
| [Scientific Computation Runtime](https://github.com/giasonpooni/Scientific-Computation-Runtime) | Specify, dispatch, and record declared scientific computations. |
| [Notations Engineering Terminal (CIW)](https://github.com/giasonpooni/Notations-Engineering-Terminal) | Operate and inspect instruments through the existing CIW sessions and adapters. |
| [Geospatial Systems Compiler (GSC)](https://github.com/giasonpooni/Geospatial-Systems-Compiler) | Browser presentation and representation-compilation project, formerly Payload Terminal V0; integration of this client's globe and provider boundary is a development target. |
| **Geospatial State Visualization** | Project geographic state through a provider interface for read-only inspection. |

These are responsibility boundaries, not a claim that cross-repository adapters
are connected in this build. View commands change camera, selection, layers, or
playback; they do not admit evidence or commit canonical state.

GSC remains separately maintained from ESM and the engineering workbench.
Combining visualization components must preserve this client's checked provider
boundary and synthetic-data labels; it must not create another evidence store,
scientific runtime, or workbench. This README update does not implement that
integration or change this repository's current project title.

## Synthetic data and provenance

Every domain record in the supplied snapshot carries
`provenance.source: 'synthetic:demo'`. The demo makes no claims about actual
shipments, facility utilization, or route conditions. The provenance check
executes the dataset and checks source-field presence; it does not validate
source authenticity or physical accuracy. Background map topology is described
separately in the architecture document.

The inspector presents record provenance, assertions, observations, and derived
deviations. Geometry basis remains distinct from route identity. Source-known
time (`knownAt`) and validity time (`validFrom` / `validTo`) remain distinct
fields. The persistent status chip labels this build as synthetic.

## Quickstart

Use Node.js 24 or newer so the existing provenance script can execute erasable
TypeScript directly. Clone the current repository location:

```sh
git clone https://github.com/giasonpooni/Geospatial-State-Visualization.git
cd Geospatial-State-Visualization
npm ci
npm run dev      # Vite dev server
npm run build    # runs check, then production build
npm run check    # seam + provenance + types
npm test         # Node 24 provider, comparison and view-tool regressions
```

`npm run check` runs the following checks and fails the build on any violation:

| Check | Script | What it enforces |
|---|---|---|
| Seam | `scripts/check-seam.mjs` | `src/data/**` is renderer-blind: no bare-module imports, no relative imports escaping the data layer (only the pure kernels `src/core/events.ts` and `src/core/time.ts` are allowed). |
| Provenance | `scripts/validate-provenance.mjs` | Executes the real synthetic dataset and fails on any record missing `provenance.source`. |
| Runtime boundary | `node --test tests/*.test.mjs` | Validated, immutable snapshot replacement; identity/reference/time/unit eligibility; explicit comparison refusals; strict view-tool inputs. |
| Types | `tsc --noEmit` | TypeScript strict mode across the whole tree. |

The provider boundary now validates and detaches snapshots before atomic
replacement. Comparisons require an explicit knowledge cutoff and half-open
event-time window; missing or different units are not converted implicitly,
and a zero assertion has an undefined (`null`) ratio. See
[`docs/PROVIDER_BOUNDARY.md`](docs/PROVIDER_BOUNDARY.md) for API changes and limits.

## Controls & interaction

- **Drag** — rotate the globe
- **Wheel** — zoom (altitude drives level of detail and progressive disclosure)
- **Click** — select a facility, route, or flow; click a country to open its summary
- **`/`** — focus the command bar / search
- **Space** — play / pause simulation time
- Command examples: `find toronto` · `show maritime` · `show bottlenecks` · `follow the load`

## Layer reference

Layers are grouped as declared in `src/app/api.ts` (`LayerDef` / `LayerId`):

| Group | Layer ids |
|---|---|
| WORLD | `world.countries` · `world.cities` · `world.terrain` · `world.nightlights` |
| TRANSPORT | `transport.road` · `transport.rail` · `transport.maritime` · `transport.air` |
| INFRASTRUCTURE | `infra.ports` · `infra.airports` · `infra.rail_terminals` · `infra.warehouses` · `infra.industrial` |
| ECONOMY | `economy.production` · `economy.demand` · `economy.inventory` · `economy.flows` |
| INTELLIGENCE | `intel.bottlenecks` · `intel.constraints` · `intel.anomalies` · `intel.dependencies` · `intel.risk` |

## Command reference

The command bar accepts a small, forgiving grammar (`src/app/commands.ts`).
Main verbs:

| Command | Effect |
|---|---|
| `find <name>` / `goto <name>` | Search entities and cinematically focus the best match. Bare text falls through to search. |
| `show <layer>` / `hide <layer>` | Toggle a layer by alias (`maritime`, `ports`, `bottlenecks`, ...). `show everything`, `show corridors` toggle groups. |
| `show <commodity> flows` | Match flows by commodity (e.g. `show copper flows`), enable flow mode, focus the first match. |
| `flows on` / `flows off` | Toggle flow-particle mode. |
| `play` / `pause` / `now` | Simulation clock control; `now` jumps to the dataset's regime boundary. |
| `speed 1h` / `speed 6h` / `speed 24h` | Sim-hours per wall-second. |
| `compare <a> vs <b>` | Compare two routes: distance, promised duration, live utilization. |
| `world` / `freight` / `trade` / `commodities` / `network` / `exceptions` | View presets. |
| `follow the load` | Cinematic multimodal demo scenario; `stop` / `exit` ends it. |
| `help` | Print the verb summary. |

## Architecture

The engineering record — the data/render seam, provenance discipline, the
Assertion/Observation/Deviation model, the provider interface, the rendering
pipeline, and the temporal model — lives in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Naming and compatibility

The repository was previously named `PayloadOS-Render-Engine`. The technical
name identifies its visualization responsibility. The local package name
`payload-earth`, browser API `window.payloadEarth`, CSS namespaces, record and
operation IDs, and source values such as `payload:spatial` remain compatible.
A repository rename does not rewrite schema identity, evidence, execution
records, or retained runtime pins.

The surrounding workbench's current project title is **Notations Engineering
Terminal**, with `ciw` retained as its package, command, and contract namespace.
**Geospatial Systems Compiler** is the current title of the former **Payload
Terminal V0**. These title updates do not reclassify a view as authoritative state.

## License

GNU General Public License v3.0 — see [`LICENSE`](LICENSE).
