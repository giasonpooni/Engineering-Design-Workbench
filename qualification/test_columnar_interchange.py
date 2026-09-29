from copy import deepcopy

import pytest

from ciw.columnar import decode, encode, export_file, import_file, QUALIFIED_PYARROW
from ciw.control_contracts import observation, record, save_new
from ciw.core.covariance import create_covariance_artifact


def source_ref(char):
    return "sha256:" + char * 64


def stream(*, vector=False, integer_value=False):
    rows = []
    base = (1.25, 1.5, 1.75, 2.0)
    for index, value in enumerate(base):
        supplied = ([float(value), float(value) + 0.1] if vector
                    else int(value) if integer_value and index == 0
                    else float(value))
        rows.append(observation(
            identity={"model_id": "model-1", "entity_id": "bearing-04", "execution_id": None},
            clock={"id": "rig-clock", "time_s": float(index) * 0.25},
            frame="machine-frame",
            quantity="vibration",
            value=supplied,
            unit="m/s^2",
            provenance={
                "provider": "fixture.sensor",
                "sources": [source_ref(str(index + 1))],
                "semantics": "observed",
            },
            uncertainty=None,
        ))
    return record("observation-stream", observations=rows)


def stream_with_uncertainty():
    covariance = create_covariance_artifact(
        matrix=[[0.04]],
        quantity_ids=["vibration"],
        units=["m/s^2"],
        frame="machine-frame",
        reference_values=[1.25],
        method="fixture",
        basis={"kind": "observation", "id": "bearing-04-vibration"},
        provenance={
            "provider": "fixture.sensor",
            "source_evidence_ids": [source_ref("a")],
            "source_covariance_ids": [],
        },
        assumptions=["fixture covariance"],
    )
    row = observation(
        identity={"model_id": "model-1", "entity_id": "bearing-04", "execution_id": None},
        clock={"id": "rig-clock", "time_s": 0.0},
        frame="machine-frame",
        quantity="vibration",
        value=1.25,
        unit="m/s^2",
        provenance={
            "provider": "fixture.sensor",
            "sources": [source_ref("1")],
            "semantics": "observed",
        },
        uncertainty=covariance,
    )
    return record("observation-stream", observations=[row])


@pytest.mark.parametrize("format", ["ipc", "parquet"])
def test_exact_roundtrip_preserves_net_record_identity(format):
    original = stream()
    payload, artifact = encode(original, format=format, experiment_id="columnar-roundtrip")
    restored = decode(payload, artifact, format=format)
    assert restored == original
    assert restored["record_digest"] == original["record_digest"]
    assert artifact["metadata"]["canonical_evidence"] is False
    assert artifact["metadata"]["pyarrow_version"] == QUALIFIED_PYARROW


@pytest.mark.parametrize("format", ["ipc", "parquet"])
def test_file_cli_seam_uses_create_only_artifact_and_reconstructs(format, tmp_path):
    original = stream()
    source = tmp_path / "stream.json"
    payload = tmp_path / ("stream.arrow" if format == "ipc" else "stream.parquet")
    sidecar = tmp_path / "artifact.json"
    restored = tmp_path / "restored.json"
    save_new(source, original)
    exported = export_file(source, format=format, output=payload,
                           artifact_path=sidecar, experiment_id="file-roundtrip")
    decoded = import_file(payload, format=format, artifact_path=sidecar, output=restored)
    assert decoded == original
    assert exported["metadata"]["source_stream_record_digest"] == original["record_digest"]
    with pytest.raises(FileExistsError):
        export_file(source, format=format, output=payload,
                    artifact_path=tmp_path / "new-artifact.json", experiment_id="again")


@pytest.mark.parametrize("bad", ["vector", "integer"])
def test_non_scalar_float64_values_refuse_without_coercion(bad):
    original = stream(vector=bad == "vector", integer_value=bad == "integer")
    with pytest.raises(ValueError, match="Float64"):
        encode(original, format="ipc", experiment_id=bad)


def test_uncertainty_refuses_instead_of_being_dropped():
    with pytest.raises(ValueError, match="uncertainty"):
        encode(stream_with_uncertainty(), format="ipc", experiment_id="uncertainty")


@pytest.mark.parametrize("format", ["ipc", "parquet"])
def test_payload_or_sidecar_tamper_refuses(format):
    original = stream()
    payload, artifact = encode(original, format=format, experiment_id="tamper")
    broken = bytearray(payload)
    broken[-1] ^= 1
    with pytest.raises(ValueError):
        decode(bytes(broken), artifact, format=format)
    wrong = deepcopy(artifact)
    wrong["metadata"]["source_stream_record_digest"] = source_ref("f")
    with pytest.raises(ValueError):
        decode(payload, wrong, format=format)


def test_wrong_format_refuses():
    payload, artifact = encode(stream(), format="ipc", experiment_id="wrong-format")
    with pytest.raises(ValueError):
        decode(payload, artifact, format="parquet")
