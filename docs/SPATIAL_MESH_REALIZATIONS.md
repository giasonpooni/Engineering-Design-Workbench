# Spatial and mesh realization adapters V1

This increment applies the representation-realization boundary to two existing
spatial/geometry instruments rather than creating a parallel GIS or geometry
architecture.

It adds two trusted families to the realization registry:

- `geographic-context.v1`
- `mesh-edge-result.v1`

Both reuse their existing domain validators.

## Geographic context realization

The source is the existing retained workbench geographic descriptor whose raw
payload declares `ciw.geographic-context.v1`.

The family delegates to the existing spatial-view projection validator, which
already checks:

- exact source byte SHA-256;
- exact source-descriptor identity;
- source kind and schema;
- OGC:CRS84;
- longitude/latitude axis order;
- degree units;
- explicit UTC time range;
- facility identity and point geometry;
- coordinate bounds;
- retained provenance/evidence references;
- facility validity covering the complete view range;
- one explicit state per facility;
- status and reference-time consistency;
- no undeclared dynamic collections.

The realization adapter then binds the representation to exactly:

```text
quantities = [longitude, latitude]
units      = [deg, deg]
frame      = OGC:CRS84
```

No coordinate transform is performed. No covariance is invented.

The realization retains the geographic source evidence identity because the
underlying retained bytes are already content-addressed.

## Mesh edge-result realization

The source is the existing bounded
`isgt.edge-geodesic-result.v1`.

The family delegates to the existing mesh-result validator. That validator
checks the retained triangular mesh and edge-distance evidence, including:

- mesh/request/result content identities;
- bounded finite vertices and triangles;
- coincident/degenerate/duplicate/nonmanifold conditions;
- triangle quality;
- connected components and boundaries;
- retained edge-path validity;
- edge inequalities and tight predecessor chains;
- reachability;
- lower/upper distance bounds;
- path/distance consistency;
- declared tolerance and authority boundaries.

The realization adapter adds an explicit coordinate binding:

```text
quantities = [x, y, z]
units      = [mesh unit, mesh unit, mesh unit]
frame      = exact mesh-declared frame
```

It retains mesh/result digests, mesh counts, reachability, target distance and
bounds.

The existing mesh provenance currently contains a human-readable source
declaration rather than a CIW evidence content reference. V1 therefore leaves
`evidence_refs=[]` for this family instead of manufacturing a hash and
pretending it authenticates the source.

That distinction is important:

```text
mesh internal content integrity
    !=
external source authentication
```

## Why this matters for the broader Terminal

The same representation substrate can now accommodate:

```text
signals
states
covariance matrices
geographic contexts
piecewise-flat meshes
```

without collapsing their semantics.

This is useful across the emerging NET workloads:

- remote sensing / GIS can bind geographic and later raster/field
  representations to explicit frames;
- manufacturing geometry can bind meshes without promoting them to certified
  metrology;
- simulation can retain mesh topology/results while separating numerical
  evidence from physical validation;
- game/simulation visualization can consume spatial representations without
  inheriting industrial evidence authority;
- later molecular and continuum representations can register their own
  validators rather than overloading a generic spatial object.

## Non-claims

The geographic adapter does not:

- transform CRS;
- infer missing locations;
- interpolate trajectories;
- perform sensor fusion;
- authenticate physical facilities.

The mesh adapter does not:

- run a mesh generator;
- repair geometry;
- solve continuous geodesics;
- certify floating-point error bounds;
- establish metrology or physical accuracy.

Neither adapter executes a provider, mutates canonical state or admits state.

## Qualification

The dedicated suite exercises both new families and reruns:

- native geographic-context tests;
- native mesh-contract tests;
- all three PR #99 realization families;
- evidence-bound expansion;
- finite preservation;
- Board/morphism binding;
- representation-aware Needle;
- System Board and parameter programs;
- semantic compilation;
- covariance and thermal regression contracts.

The spatial adapters remain additions to the existing realization registry,
not replacements for their domain validators.

## Next representation families

The next scientifically meaningful families are not more generic spatial JSON.
They are structured fields and observations:

1. calibrated observation / observation stream;
2. raster or gridded spatial field with CRS, resolution and nodata semantics;
3. estimated spatial field with covariance/correlation model;
4. molecular configuration/trajectory with units, periodic cell and topology;
5. continuum mesh/field pair with discretization and conservation metadata.

Those can now be added one family at a time under the same realization
boundary.
