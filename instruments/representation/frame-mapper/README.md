<div align="center">

# Geospatial Systems Compiler (GSC)

### Notation Systems — data, modelling, and visualization for physical systems.

**State · Variation · Invariance**

[![Next.js](https://img.shields.io/badge/Next.js-16-black?style=for-the-badge&logo=next.js)](https://nextjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![MapLibre](https://img.shields.io/badge/MapLibre_GL-GPU_Rendered-396CB2?style=for-the-badge)](https://maplibre.org)
[![License](https://img.shields.io/badge/License-GPLv3-D4AF37?style=for-the-badge)](LICENSE)

Explore observations, compare results, and inspect how they were produced.

</div>

## Overview

**Geospatial Systems Compiler (GSC)** is the current project identity for the
former **Payload Terminal V0**, the browser-interface foundation for **Notation
Systems**. Its target is a provenance-aware visualization system that transforms
supplied physical-system records and computed results into synchronized spatial,
temporal, relational, and interactive representations. This is representation
compilation, not evidence admission, scientific execution, or verification.

The existing application is part of Notation Systems' computational
instrumentation and evidence infrastructure for industrial and cyber-physical
systems. It currently contains a map-led physical-economy application with
commodity analytics and freight workflows.

The development direction is a **separately maintained Notation Systems
homepage and read-only explorer**, combining the strongest presentation and
provider-boundary components of this project and Geospatial State Visualization.
It connects to existing evidence services and the engineering workbench through
explicit interfaces. Freight remains a worked application, not the definition
of the whole company. Scientific methods and specialist domain models stay with
their respective instruments.

**Status on this branch:** the existing Next.js application is implemented.
The unified representation compiler, company homepage separation, ESM projection
adapter, Geospatial State Visualization integration, and workbench handoff below
remain **integration targets**, not capabilities delivered by this README update.
The running interface and application metadata have not been rebranded by this
documentation change.

## What is already in this repository

| Area | Existing application |
| --- | --- |
| Browser interface | Next.js, MapLibre maps, search, panels, layer controls, and temporal inspection. |
| Physical-economy records | Entities, observations, flows, capacities, dependencies, provenance, and source-known time. |
| Commodity analytics | Copper and aluminium examples; concentration, flow dependencies, candidate bottlenecks, source disagreements, and acquisition/snapshot fallback. |
| Freight records | Append-only entries, lane residuals with minimum-trial requirements, carrier vetting, and exceptions. |
| Freight operations | Persistent intake, alternatives, authorization, assignment, dispatch evidence, tracking, and settlement; an exception-first `/operations` workspace. |
| Supporting sources | Routing, maritime reference, weather, market data, and conditional organisational-infrastructure attribution. Availability depends on the source and configuration. |
| Checks | Vitest tests, source and route policy checks, and checks over outward-facing product descriptions. |

The existing application includes local domain state, analytics, and
write-capable freight APIs. **The proposed read-only boundary applies to the
new homepage/explorer; it is not a claim that every existing route is read-only.**
Those workflows must remain explicitly separated from any public demonstration.
This document neither removes them nor migrates their records into ESM.

Implementation details remain in
[`docs/PHYSICAL_ECONOMY.md`](docs/PHYSICAL_ECONOMY.md) and
[`docs/ARCHITECTURE_LEDGER.md`](docs/ARCHITECTURE_LEDGER.md).

## The Notation Systems experience

The organizing object should be an **investigation**: a question connected to
specific data, assumptions, model configurations, runs, and results.

```text
Inspect data → Understand the model and assumptions
             → Open a recorded result or continue in the workbench
             → Compare cases → Trace the supporting evidence
```

The browser presents this context; it should not recreate the existing
workbench's experiment editor, execution history, or instrument implementations.

| Principle | Intended user action |
| --- | --- |
| **State** | Inspect a record, field, or estimate at a declared time, with its units, source, and observed/computed status. |
| **Variation** | Compare a baseline with a changed input, parameter, model version, or sensor configuration. |
| **Invariance** | Inspect model-specific constraints, conservation checks, frame consistency, tolerances, and failures supplied by the instrument. |

These are design targets, not a claim that a general scientific comparison
workspace already exists here. Controls must distinguish **changing a view**,
**selecting a precomputed result**, and **requesting a new computation**.

Data, model descriptions, recorded experiments, views, comparisons, and evidence
should be navigable parts of the same investigation. A table, plot, map, globe,
graph, or local 3D scene is a different way to inspect a result—not a different
source of truth. Geography is one view, not the universal container for every
scientific or industrial problem.

## Responsibility in the stack

**Separate application, integrated information and workflow.** Keep GSC outside
ESM and connect it through narrow interfaces rather than merging it into ESM,
duplicating the workbench, or offering only a generic homepage link.

| Component | Responsibility |
| --- | --- |
| **Geospatial Systems Compiler (GSC)** | Company presentation, navigation, local selection, representation compilation, view configuration, and inspection of explicitly supplied records and results. The broader compiler is an integration target. |
| [Evidence and State Management (ESM)](https://github.com/giasonpooni/Evidence-and-State-Management) | Retain and govern evidence, versioned state, admission, and release. |
| [Notations Engineering Terminal (CIW)](https://github.com/giasonpooni/Notations-Engineering-Terminal) | The existing workbench: instrument sessions, adapters, configuration, inspection, and replay; `ciw` remains its runtime identity. |
| [Scientific Computation Runtime](https://github.com/giasonpooni/Scientific-Computation-Runtime) and specialist instruments | Declared computation, numerical methods, result contracts, and diagnostics. |
| [Geospatial State Visualization (GSV)](https://github.com/giasonpooni/Geospatial-State-Visualization) | Existing read-only geographic client and source of globe/provider-boundary components for the GSC integration. |

The following is the **target integration**, not the current deployment:

```text
Explicitly published demonstration artifacts
                     │
                     ▼
       GEOSPATIAL SYSTEMS COMPILER / NOTATION SYSTEMS WEB
              Homepage · Explorer · Inspectors
                     │
          ┌──────────┴───────────────────┐
          │                              │
   Read/projection adapter       Contextual links first;
          │                      authenticated adapter later
          ▼                              ▼
         ESM                 Notations Engineering Terminal
 Evidence and released state     Existing CIW sessions and replay
                                         │
                                         ▼
                                Runtime and instruments

       Maps, GSV, plots, and tables present returned data.
       Displaying a result does not admit it or authorize execution.
```

ESM is not the route for camera movements or a general solver-dispatch service.
The web application should retain references and replaceable view caches, not
create a second canonical corpus or competing execution ledger.

GSV's documented standalone implementation uses a deterministic synthetic
provider. Its presence elsewhere in the stack does not mean it is embedded on
this branch or connected to live data. Integration must explicitly map supported
records to its provider contract; an ESM response is not automatically a GSV
`WorldSnapshot`. Do not copy private implementation code or datasets into this
public repository as an integration shortcut.

## Homepage, explorer, and workbench

| Experience | Intended boundary |
| --- | --- |
| **Public homepage** | Explain Notation Systems and demonstrate one investigation using deliberately published artifacts. No credentials for private stores or workbench execution; explanatory content must not require a running scientific backend. |
| **Read-only explorer** | Inspect exact permitted releases and results, preserve identity and time selection, and open their supporting records. Public access is limited to deliberately published material. |
| **Notations Engineering Terminal** | Continue investigations, configure supported instruments, execute, and replay through the existing CIW workbench rather than a duplicate application built here. Private project access is a deployment permission, not a repository title. |

Retention, admission, release, and public publication are different decisions.
A record held in ESM is not automatically suitable for the homepage. Recorded
instrument results and candidate evidence must not be presented as admitted
state; candidate review must retain its `UNADMITTED` status where applicable.

Contextual links should open an exact supporting record, release, recorded run,
or workbench session where the destination supports it. Carry only necessary
identifiers and view context—not credentials or embedded private records. The
destination must still authorize access. A link is navigation, not permission.

## Integration sequence

### 1. One released dataset, two synchronized views

Extract reusable navigation, panels, selection, and temporal controls from the
existing application. Preserve the freight experience separately while adding
the company homepage and explorer. Update company-level metadata alongside the
future interface work, rather than changing only visible branding.

Build one read-only ESM adapter around the existing projection contract:

```text
Exact release → Explicit record and time selection → Validated projection
                                                    ├── Table
                                                    └── Geographic view
```

Preserve release and snapshot bindings, source references, units, coordinate
basis, event-time window, and knowledge cutoff. Keep fixture or synthetic
responses labelled as such. Unsupported records remain unsupported; missing
geometry must not become invented coordinates.

For GSV, establish provider injection, container-relative sizing, selection and
time synchronization, and a complete mount/resize/dispose lifecycle before
embedding it as a panel. Begin with bounded snapshots and recorded outputs;
streaming is a later requirement, not a prerequisite for the first integration.

### 2. Recorded results, comparisons, and workbench handoff

Open supported recorded results through the workbench's result/session boundary.
Keep that adapter separate from ESM's released-record projection and any
candidate-evidence review path.

A comparison should state what changed, what stayed fixed, which outputs differ,
and what limits the comparison. Preserve exact dataset, model, run, baseline,
record, and time references when switching views. Covariance, residuals,
sensitivity, and constraint diagnostics come from the relevant instrument;
the viewer must not invent uncertainty propagation or infer independence.

Start with contextual links into existing sessions and runs. Do not duplicate
session management or replay machinery simply to make the frontend look complete.

### 3. Authenticated operations only when required

Add a workbench adapter only for a demonstrated workflow. The browser may request
a supported operation; the existing backend remains responsible for permitting,
executing, and recording it. Keep view commands and computation commands distinct.
Public demonstrations remain on released data and recorded results unless a
separately bounded public computation is deliberately provided.

### First integration acceptance criteria

- Switching views preserves the selected record, release, run, and time context; an unsupported view says so.
- Invalid source or snapshot bindings are rejected; missing values, geometry, and unavailable results remain explicit rather than becoming zeros or fabricated data.
- Comparisons declare their baseline, changed inputs, units, frames, and limitations; unsupported conversions and uncertainty calculations are refused.
- Public requests cannot obtain internal records or invoke private operations, and publication is never inferred from retention alone.
- Synthetic data, recorded runs, connected adapters, and validation evidence are labelled separately. A generated template is not an executed or validated experiment.

Initial demonstration targets are **geographic state replay**, **state estimation
and uncertainty**, and **geometry and sensitivity**. These are proposed
end-to-end integrations, not a list of finished capabilities. Complete the first
inspectable path before adding more feeds, industries, or renderers.

<!-- collection-policy:begin -->
## Collection policy

Payload is being built for a firm that will hold carrier, driver and customer
personal information. What the application is allowed to collect is therefore
part of its design, not a footnote to it.

**Prohibited, and removed from this tree:** username enumeration across
platforms, breach-corpus lookup by email address, infostealer credential
corpora, phone-number research, and host or port scanning. These were present
in the upstream project this fork began from. They are deleted — code, routes,
UI and client libraries — rather than disabled or feature-flagged, because a
feature-flagged breach lookup is still a breach lookup in the tree and still
in the image.

**Conditional, and permitted only with the condition written down:** WHOIS,
DNS, IP intelligence, certificate transparency, BGP/ASN and MAC-prefix
lookup. Each states the same constraint in its own source —
*organisational infrastructure attribution only; never used to profile a
person*. A conditional permission with the condition left implicit is an
unconditional permission.

**Permitted:** sanctions screening of counterparty **organisations, vessels
and aircraft**. The person path is not served, and is filtered out of every
result set rather than merely omitted from the schema allowlist.

Three checks hold this in place, and they run in CI:

- the **source registry** refuses to register a source that yields
  natural-person data;
- the **route-surface gate**
  ([`routeSurfacePolicy.test.ts`](src/lib/economy/routeSurfacePolicy.test.ts))
  classifies every route under `src/app/api/**`, fails on an unclassified
  one, and scans every route's source for a prohibited capability regardless
  of how it is labelled;
- the **shipped-description gate** fails if this README advertises a
  prohibited capability — the description is an artifact and drifts from
  policy like any other.

Registration was never the only door.
<!-- collection-policy:end -->

## Run the existing application

These commands start the current Payload application, not the proposed
Notation Systems homepage or an integrated scientific workbench. Use Node.js 22
for consistency with the repository's container build.

```bash
git clone https://github.com/giasonpooni/Geospatial-Systems-Compiler.git
cd Geospatial-Systems-Compiler
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

```bash
npm test          # Vitest, including the policy gates
npx tsc --noEmit  # Type checking
npm run build    # Production build
```

For a README-only change, the relevant shipped-description checks are in:

```bash
npm test -- src/lib/economy/routeSurfacePolicy.test.ts
```

### Docker / self-hosting

Create an optional `.env` with the supported settings below. The current Compose
file expects an external network named `umami_default`; provision it first if
it does not already exist.

```bash
docker network inspect umami_default >/dev/null 2>&1 || docker network create umami_default
docker compose up -d --build
```

The image uses a multi-stage `node:22-alpine` standalone build and a non-root
application user. The container listens on `3000`; `PAYLOAD_PORT` controls the
published host port. Compose provisions a persistent freight-journal volume.
See [DOCKER.md](DOCKER.md) for additional deployment details; some inherited
naming and setup references there still need alignment with this repository.

### Environment and freight operations

Some existing data paths use public, keyless sources; others need credentials
or return unavailable results. Keyless does not guarantee live availability.
Private freight commands require their own configuration and are not part of
the proposed public explorer.

Use the following settings as needed in `.env`. The checked-in
[`.env.example`](.env.example) also contains legacy entries and comments; it is
not a declaration that all of those inherited capabilities are supported.

```env
# Published host port; container always listens on 3000
PAYLOAD_PORT=3000

# Force source snapshot fallback, visible in provenance
PAYLOAD_DISABLE_LIVE=

# Leave the operations token empty to disable the private operations API
PAYLOAD_OPERATIONS_TOKEN=
PAYLOAD_OPERATIONS_LOG=

# Carrier authority/status and weekly diesel benchmark
FMCSA_WEB_KEY=
EIA_API_KEY=
PAYLOAD_FREIGHT_SOURCE_TIMEOUT_MS=10000

# Outbound carrier adapter and authenticated inbound carrier events
PAYLOAD_CARRIER_DISPATCH_URL=
PAYLOAD_CARRIER_DISPATCH_TOKEN=
PAYLOAD_CARRIER_DISPATCH_PROVIDER=carrier-webhook
PAYLOAD_CARRIER_DISPATCH_TIMEOUT_MS=10000
PAYLOAD_CARRIER_WEBHOOK_SECRET=
PAYLOAD_CARRIER_COMMUNICATIONS_LOG=
```

`GET /api/freight/operations` reads current load-operation projections;
`POST /api/freight/operations` advances intake, alternatives, authorization,
assignment, dispatch evidence, and settlement outcome capture.
`GET /api/freight/control-tower` joins these records to tender delivery,
acknowledgements, tracking freshness, delivery windows, and settlement state.
The `/operations` workspace refreshes that private view every 30 seconds and
keeps its bearer credential only in the active browser tab's memory.

`GET /api/freight/sources?usdot=<number>&carrierId=<internal-id>&includeDiesel=1`
pulls FMCSA identity/authority/out-of-service evidence and the EIA weekly U.S.
diesel benchmark. It returns an `authorizationCarrier` object but leaves cargo
insurance expiry and limit null: missing coverage never becomes clearance.

`POST /api/freight/communications` delivers the journal-derived tender to the
configured carrier adapter with a stable `Idempotency-Key`; its corresponding
`GET` exposes delivery and carrier-event projections. These private routes
require `Authorization: Bearer <PAYLOAD_OPERATIONS_TOKEN>`.

The carrier adapter must return JSON containing `receiptId` and optionally
`acceptedAt`. It receives only the selected carrier rate and sanitized load
facts—not the shipper target rate or source-message identity. Carriers post
acknowledgements and tracking updates to `/api/freight/carrier-events`, signed
as `HMAC-SHA256(timestamp + "." + rawBody)` using
`PAYLOAD_CARRIER_WEBHOOK_SECRET` (at least 32 random bytes). Run both journals
on persistent, backed-up storage with one application writer.

FMCSA and EIA keys stay server-side and are not included in evidence identifiers
or source errors. Partial upstream failure returns a typed source refusal, not
an inferred compliance pass. Do not expose operational credentials in public
site configuration, demonstration artifacts, or navigation links.

> **Compatibility:** existing `PAYLOAD_*` settings and Payload identifiers
> remain in use. The documented `OSIRIS_*` migration aliases are temporary;
> the existing compatibility window ends after `v0.2.0`. This README change
> does not rename packages, environment variables, routes, or retained records.
>
> `SCANNER_URL` and `SCANNER_KEY` refer to a removed backend. Do not configure
> them even where inherited setup examples still contain those entries.

## Technology and implementation references

| Layer | Technology |
| --- | --- |
| Application | Next.js 16 App Router, React, TypeScript 5 |
| Map | MapLibre GL JS / WebGL |
| Interface | Framer Motion, Lucide React |
| Tests | Vitest |

See the [physical-economy design](docs/PHYSICAL_ECONOMY.md),
[architecture ledger](docs/ARCHITECTURE_LEDGER.md),
[deployment guide](DOCKER.md), and [security policy](SECURITY.md).
Cross-repository links above describe component responsibilities; they do not
establish that an adapter is connected or a service is publicly deployed.

## Project title and compatibility

Use **Geospatial Systems Compiler (GSC)** and
`giasonpooni/Geospatial-Systems-Compiler` for the current project and new links.
**Payload Terminal V0** remains the historical application title. The prior
`notationsystems/Payload-Terminal-V0` and `giasonpooni/Payload-Terminal-V0`
locations are historical references, not separate systems. The existing package,
route, schema, environment, evidence and runtime identities are unchanged.

## Origin and license

This project began as a fork of
[simplifaisoul/osiris](https://github.com/simplifaisoul/osiris), an open-source
situational-awareness dashboard, and retains its map and rendering foundation.
It was subsequently developed around provenance-preserving physical-economy
records and freight workflows. Those remain the starting application as the
repository is repositioned within Notation Systems.

The upstream project is MIT-licensed; its permissive grant and retained notice
continue to apply to inherited code. This project as a whole is distributed
under the **GNU General Public License v3.0**—see [LICENSE](LICENSE).
This documentation update does not change the license.
