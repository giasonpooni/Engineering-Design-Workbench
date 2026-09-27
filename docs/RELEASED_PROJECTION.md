# Released-record inspection

The `embed.html` entry extends GSV with a read-only consumer of ESM's existing
`payload.projection.v1`. It is separate from the synthetic demo and the CIW
`SpatialDataProvider`. Records are not converted to facilities: the ESM response
does not supply the operational state required by `WorldStore`.

## Implemented path

Terminal's server requests one operator-configured `PUBLIC_RULING` fixture
projection with exact release, manifest, source-snapshot, selection and time
bindings. It checks the complete projection digest against an independently
configured pin. Its browser sends that projection to this entry via a bounded,
origin/source/channel-checked `notation.gsv-inspection.v1` view message.
GSV repeats the checks before replacing the active view.

The embed uses the existing `Engine`, graticule and geographic coordinate
convention. It renders declared WGS84 POINT positions; polygons and extents
remain in the host evidence inspector. Their coordinates are checked, but no
centroid, facility, trajectory or operational state is invented. Every position
source remains distinct. The scene is a spherical display, not a geodetic
measurement engine; marker size and graticule are presentation, not uncertainty.

`Engine(canvas, viewport)` provides container-relative sizing, `resize()`,
`stop()`, removable frame callbacks and idempotent `dispose()`. Omitting the
viewport preserves the existing standalone application's window sizing.
Scene geometry and materials remain caller-owned and are disposed by the embed.
The existing synthetic and CIW boot paths are not replaced.

## Bridge

Start Vite with `npm run dev -- --host 127.0.0.1`. The companion Terminal uses
`NOTATION_GSV_EMBED_URL=http://127.0.0.1:5173/embed.html`. Production deployments
use an explicit HTTPS embed URL on a separately controlled viewer origin.

The host supplies its origin and a random per-mount channel in the fragment.
No source endpoint, executable command, token or credential is accepted through
the bridge. Supported messages are `ready`, `load`, `loaded`, `select`,
`selected` and `refused`. Selection messages are bound to the active projection
digest. A failing or superseded load cannot replace a valid active projection.

The embed never contacts ESM. The channel prevents stale-window/message mixing;
it is not user authentication. Parent origin and `event.source` are checked,
and `postMessage` never uses a wildcard destination. Deployment administrators
must control the configured origins and set appropriate frame/CSP restrictions.

## Preserved meanings

- Fixed `knownAt` and `validAt` are not a live clock. A time change requires a new
  ESM projection. No local temporal interpolation is offered.
- The source's `engine: CesiumJS` is retained as a routing hint. The embed
  explicitly identifies its actual renderer as GSV / Three.js.
- Missing geometry, units and uncertainty do not become zero.
- `fixture_only: true` remains visible. A content digest establishes consistency
  with a selected pin, not authenticity, physical accuracy, rights or admission.
- No execution, verification or canonical-admission identity is manufactured.

## Verification

`npm run build` runs native seam, provenance, tests, types and Vite compilation,
including the new entry. `node --test tests/released-projection.test.mjs` runs
consumer-contract tests using a hand-authored fixture, not exported private ESM
records. The companion Terminal carries a hash-pinned mirror of the consumer
validator to prevent the two deployments from silently accepting different data.

The new CI job also exercises the bridge and repeated mount/dispose in Chromium.
A passing contract test alone does not establish a live ESM deployment or a
completed browser check. Read the actual CI results for the tested revision.
