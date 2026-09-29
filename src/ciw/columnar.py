"""Optional Arrow IPC / Parquet representation for retained scalar observations.

This is a representation/interchange adapter, not canonical evidence storage.
PyArrow is imported only when encoding/decoding is requested. V1 deliberately
supports one homogeneous scalar Float64 observation stream with no uncertainty
artifact so exact NET record identity can be reconstructed without coercion.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile

from .control_checks import inspect_record
from .control_contracts import MAX_BYTES, MAX_SAMPLES, artifact, load, record, save_new, validate_artifact
from .core.identities import canonical_json

QUALIFIED_PYARROW = "25.0.1"
FORMATS = {
    "ipc": "application/vnd.apache.arrow.file",
    "parquet": "application/vnd.apache.parquet",
}
SCHEMA = "ciw.observation-columnar.v1"
ARTIFACT_SCHEMA = "ciw.columnar-observation-artifact.v1"


def _arrow():
    try:
        import pyarrow as pa
        import pyarrow.ipc as ipc
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ValueError("Columnar interchange requires the optional pyarrow dependency") from exc
    if pa.__version__ != QUALIFIED_PYARROW:
        raise ValueError(
            f"Columnar profile is qualified for PyArrow {QUALIFIED_PYARROW}, got {pa.__version__}")
    return pa, ipc, pq


def _stream_descriptor(stream: dict) -> tuple[dict, list[dict]]:
    inspected = inspect_record(stream)
    if inspected["schema"] != "ciw.observation-stream.v1":
        raise ValueError("Columnar interchange requires a retained observation stream")
    observations = stream["observations"]
    if not observations:
        raise ValueError("Columnar V1 requires a nonempty observation stream")
    if len(observations) > MAX_SAMPLES:
        raise ValueError("Observation stream exceeds row budget")
    first = observations[0]
    identity = first["identity"]
    descriptor = {
        "schema": SCHEMA,
        "source_record_digest": stream["record_digest"],
        "model_id": identity["model_id"],
        "entity_id": identity["entity_id"],
        "execution_id": identity["execution_id"],
        "clock_id": first["clock"]["id"],
        "frame": first["frame"],
        "quantity": first["quantity"],
        "unit": first["unit"],
        "provider": first["provenance"]["provider"],
        "semantics": first["provenance"]["semantics"],
        "row_count": len(observations),
        "time_type": "float64",
        "value_type": "float64",
        "uncertainty": "not_supported_in_v1",
    }
    for item in observations:
        if item["uncertainty"] is not None:
            raise ValueError("Columnar V1 refuses observation uncertainty rather than dropping it")
        if type(item["clock"]["time_s"]) is not float or type(item["value"]) is not float:
            raise ValueError("Columnar V1 requires explicit Float64 time/value to preserve JSON identity")
        current = {
            "model_id": item["identity"]["model_id"],
            "entity_id": item["identity"]["entity_id"],
            "execution_id": item["identity"]["execution_id"],
            "clock_id": item["clock"]["id"],
            "frame": item["frame"],
            "quantity": item["quantity"],
            "unit": item["unit"],
            "provider": item["provenance"]["provider"],
            "semantics": item["provenance"]["semantics"],
        }
        if current != {key: descriptor[key] for key in current}:
            raise ValueError("Columnar V1 requires one homogeneous observation descriptor")
    return descriptor, observations


def _table(stream: dict):
    pa, _, _ = _arrow()
    descriptor, observations = _stream_descriptor(stream)
    metadata = {b"ciw": canonical_json(descriptor).encode("utf-8")}
    schema = pa.schema([
        pa.field("time_s", pa.float64(), nullable=False),
        pa.field("value", pa.float64(), nullable=False),
        pa.field("sources", pa.list_(pa.string()), nullable=False),
        pa.field("observation_digest", pa.string(), nullable=False),
    ], metadata=metadata)
    return pa.Table.from_arrays([
        pa.array([item["clock"]["time_s"] for item in observations], type=pa.float64()),
        pa.array([item["value"] for item in observations], type=pa.float64()),
        pa.array([item["provenance"]["sources"] for item in observations],
                 type=pa.list_(pa.string())),
        pa.array([item["record_digest"] for item in observations], type=pa.string()),
    ], schema=schema)


def encode(stream: dict, *, format: str, experiment_id: str) -> tuple[bytes, dict]:
    if format not in FORMATS:
        raise ValueError("Columnar format must be ipc or parquet")
    pa, ipc, pq = _arrow()
    table = _table(stream)
    sink = pa.BufferOutputStream()
    if format == "ipc":
        with ipc.new_file(sink, table.schema) as writer:
            writer.write_table(table)
    else:
        pq.write_table(table, sink, compression="NONE", use_dictionary=False,
                       write_statistics=True, version="2.6")
    payload = sink.getvalue().to_pybytes()
    if not payload or len(payload) > MAX_BYTES:
        raise ValueError("Encoded columnar artifact exceeds 8 MiB profile")
    value = artifact(
        payload,
        media_type=FORMATS[format],
        producer="ciw.columnar-interchange.v1",
        experiment_id=experiment_id,
        metadata={
            "schema": ARTIFACT_SCHEMA,
            "format": format,
            "source_stream_record_digest": stream["record_digest"],
            "canonical_evidence": False,
            "pyarrow_version": QUALIFIED_PYARROW,
            "row_count": table.num_rows,
        },
    )
    return payload, value


def _metadata(table) -> dict:
    raw = (table.schema.metadata or {}).get(b"ciw")
    if raw is None or len(raw) > 65536:
        raise ValueError("Missing/bounded CIW schema metadata")
    value = json.loads(raw.decode("utf-8"))
    expected = {
        "schema", "source_record_digest", "model_id", "entity_id", "execution_id",
        "clock_id", "frame", "quantity", "unit", "provider", "semantics",
        "row_count", "time_type", "value_type", "uncertainty",
    }
    if type(value) is not dict or set(value) != expected or value["schema"] != SCHEMA:
        raise ValueError("Unsupported columnar schema metadata")
    if value["time_type"] != "float64" or value["value_type"] != "float64":
        raise ValueError("Unsupported numeric column type")
    if value["uncertainty"] != "not_supported_in_v1":
        raise ValueError("Unexpected uncertainty claim")
    return value


def decode(payload: bytes, artifact_record: dict, *, format: str) -> dict:
    if type(payload) is not bytes or not payload or len(payload) > MAX_BYTES:
        raise ValueError("Columnar payload exceeds byte budget or is empty")
    if format not in FORMATS:
        raise ValueError("Columnar format must be ipc or parquet")
    validate_artifact(artifact_record, payload)
    metadata = artifact_record["metadata"]
    expected_metadata = {
        "schema", "format", "source_stream_record_digest",
        "canonical_evidence", "pyarrow_version", "row_count",
    }
    if (type(metadata) is not dict or set(metadata) != expected_metadata
            or metadata["schema"] != ARTIFACT_SCHEMA
            or metadata["format"] != format
            or metadata["canonical_evidence"] is not False
            or metadata["pyarrow_version"] != QUALIFIED_PYARROW):
        raise ValueError("Artifact metadata differs from qualified columnar profile")
    if artifact_record["media_type"] != FORMATS[format] or artifact_record["producer"] != "ciw.columnar-interchange.v1":
        raise ValueError("Artifact media/producer mismatch")

    pa, ipc, pq = _arrow()
    source = pa.BufferReader(payload)
    if format == "ipc":
        reader = ipc.open_file(source)
        table = reader.read_all()
    else:
        parquet = pq.ParquetFile(source)
        if parquet.metadata.num_rows > MAX_SAMPLES:
            raise ValueError("Parquet row count exceeds profile before table materialization")
        if sum(parquet.metadata.row_group(i).total_byte_size
               for i in range(parquet.metadata.num_row_groups)) > 64 * 1024 * 1024:
            raise ValueError("Parquet uncompressed row groups exceed profile")
        table = parquet.read()

    descriptor = _metadata(table)
    if table.num_rows != descriptor["row_count"] or table.num_rows != metadata["row_count"]:
        raise ValueError("Columnar row count contradicts metadata")
    if not 1 <= table.num_rows <= MAX_SAMPLES or table.nbytes > 64 * 1024 * 1024:
        raise ValueError("Decoded table exceeds row/memory profile")
    expected_fields = [
        ("time_s", pa.float64()), ("value", pa.float64()),
        ("sources", pa.list_(pa.string())), ("observation_digest", pa.string()),
    ]
    if [(field.name, field.type) for field in table.schema] != expected_fields:
        raise ValueError("Columnar fields/types differ from qualified schema")
    if any(table.column(name).null_count for name, _ in expected_fields):
        raise ValueError("Columnar V1 refuses null values")

    from .control_contracts import observation
    observations = []
    times = table.column("time_s").to_pylist()
    values = table.column("value").to_pylist()
    sources = table.column("sources").to_pylist()
    digests = table.column("observation_digest").to_pylist()
    for time_s, value, refs, expected_digest in zip(times, values, sources, digests):
        item = observation(
            identity={
                "model_id": descriptor["model_id"],
                "entity_id": descriptor["entity_id"],
                "execution_id": descriptor["execution_id"],
            },
            clock={"id": descriptor["clock_id"], "time_s": time_s},
            frame=descriptor["frame"],
            quantity=descriptor["quantity"],
            value=value,
            unit=descriptor["unit"],
            provenance={
                "provider": descriptor["provider"],
                "sources": refs,
                "semantics": descriptor["semantics"],
            },
            uncertainty=None,
        )
        if item["record_digest"] != expected_digest:
            raise ValueError("Columnar row does not reconstruct original observation identity")
        observations.append(item)
    stream = record("observation-stream", observations=observations)
    inspect_record(stream)
    if (stream["record_digest"] != descriptor["source_record_digest"]
            or stream["record_digest"] != metadata["source_stream_record_digest"]):
        raise ValueError("Columnar representation does not reconstruct source stream identity")
    return stream


def read_payload(path: Path) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Columnar source must be a regular file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Columnar source exceeds 8 MiB profile or is empty")
    return raw


def save_bytes_new(path: Path, payload: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".net-columnar-", dir=path.parent) as directory:
        staged = Path(directory) / "payload"
        with staged.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, path)


def export_file(stream_path: Path, *, format: str, output: Path,
                artifact_path: Path, experiment_id: str) -> dict:
    stream = load(stream_path)
    payload, artifact_record = encode(stream, format=format, experiment_id=experiment_id)
    save_bytes_new(output, payload)
    save_new(artifact_path, artifact_record)
    return artifact_record


def import_file(payload_path: Path, *, format: str, artifact_path: Path,
                output: Path) -> dict:
    payload = read_payload(payload_path)
    artifact_record = load(artifact_path)
    stream = decode(payload, artifact_record, format=format)
    save_new(output, stream)
    return stream
