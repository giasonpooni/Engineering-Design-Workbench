# Arrow IPC / Parquet observation interchange

This optional adapter addresses one narrow interoperability problem: moving a
retained homogeneous scalar observation stream into a standard columnar
representation without replacing NET's canonical JSON evidence contracts.

Apache Arrow defines a multi-language in-memory columnar format and IPC formats;
Parquet is a complementary durable columnar storage format. V1 uses PyArrow
25.0.1 as the qualified Python implementation.

## Scope

V1 accepts:

- one validated `ciw.observation-stream.v1`;
- 1..65,536 observations;
- one model/entity/execution/provider/quantity/unit/frame/clock/semantics descriptor;
- explicit Python Float64 time and scalar value fields;
- per-row provenance source references;
- no per-observation uncertainty artifact.

It refuses vectors, integer-to-float coercion, missing values, uncertainty,
descriptor drift and implicit unit/frame/clock conversions.

The resulting table contains only:

```text
time_s: Float64
value: Float64
sources: List<Utf8>
observation_digest: Utf8
```

The shared descriptor and original stream digest live in Arrow schema metadata.

## Exact NET reconstruction

On import, NET reconstructs each original observation using the ordinary
`observation(...)` contract and requires every reconstructed observation digest
and the final stream digest to equal the identities embedded in the columnar
representation and sidecar artifact.

Thus the supported guarantee is:

```text
NET observation stream
    -> Arrow IPC / Parquet representation
    -> NET observation stream
    == original NET content identity
```

for this qualified profile.

That does **not** mean Arrow/Parquet becomes canonical evidence. The sidecar is an
ordinary `ciw.artifact.v1` with `canonical_evidence: false`.

## Security/resource boundary

V1 limits source/output bytes to 8 MiB and rows to 65,536. Parquet metadata is
checked for row count and a 64 MiB uncompressed row-group budget before reading
the full table. The decoded table is also bounded.

These checks reduce accidental/resource abuse but are not a complete hostile-file
sandbox or proof of every Arrow parser path.

## Commands

Install the optional profile:

```sh
python -m pip install '.[columnar]'
```

Export:

```sh
net columnar export observations.json --format ipc \
  --output observations.arrow --artifact observations.arrow.json \
  --experiment-id inspection-001
```

Round-trip:

```sh
net columnar import observations.arrow --format ipc \
  --artifact observations.arrow.json --output restored.json
```

Parquet uses the same commands with `--format parquet`.

No Flight/gRPC service, shared-memory coordinator, Plasma store, external data
lake, or automatic network transfer is installed by this increment. Those require
separate deployment/security contracts.
