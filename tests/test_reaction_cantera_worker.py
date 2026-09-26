"""Genuine Cantera provider checks for the bounded reaction-a-to-b profile."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
from typing import Any

import pytest

from ciw.reaction_contract import MODEL, PROFILE, SEMANTICS, check_output


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "runtimes" / "cantera-reaction" / "worker.py"


def payload() -> dict[str, Any]:
    return {
        "model": MODEL,
        "species_order": ["A", "B"],
        "initial_concentration_mol_m3": [2.0, 0.5],
        "rate_constant_s_inv": 0.5,
        "temperature_k": 300.0,
        "volume_m3": 0.001,
        "time_s": [0.0, 0.03, 0.4, 1.0, 3.0],
        "solver": {"reltol": 1e-9, "abstol_mol_m3": 1e-11, "max_steps": 100000},
    }


def request(request_id: str, value: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": "ciw.native-interop-request.v1",
        "request_id": request_id,
        "parent_execution_id": "cantera-test-execution",
        "profile": PROFILE,
        "arithmetic": "binary64",
        "semantics": deepcopy(SEMANTICS),
        "payload": deepcopy(payload() if value is None else value),
    }


def frame(value: dict[str, Any]) -> bytes:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return struct.pack(">I", len(raw)) + raw


def frames(raw: bytes) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(raw):
        assert len(raw) - cursor >= 4
        count = struct.unpack(">I", raw[cursor : cursor + 4])[0]
        cursor += 4
        assert 1 <= count <= 4 * 1024 * 1024
        assert len(raw) - cursor >= count
        result.append(json.loads(raw[cursor : cursor + count]))
        cursor += count
    assert cursor == len(raw)
    return result


def qualified_python() -> Path:
    value = os.environ.get("CIW_TEST_REACTION_CANTERA")
    if not value:
        if os.environ.get("CIW_REACTION_REQUIRE_CANTERA") == "1":
            pytest.fail("CIW_TEST_REACTION_CANTERA is required but unset")
        pytest.skip("set CIW_TEST_REACTION_CANTERA to run the qualified Cantera worker")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"qualified Cantera Python is missing: {path}")
    return path


def run_worker(requests: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    python = qualified_python()
    input_bytes = frame({"schema": "ciw.native-interop-handshake-request.v1", "request_id": "hello"})
    input_bytes += b"".join(frame(value) for value in requests)
    completed = subprocess.run(
        [str(python), "-I", "-u", str(WORKER)],
        cwd=str(ROOT),
        input=input_bytes,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(
            f"Cantera worker exited {completed.returncode}: "
            f"{completed.stderr.decode('utf-8', 'replace')[-2000:]}"
        )
    output = frames(completed.stdout)
    assert len(output) == len(requests) + 1
    return output[0], output[1:]


def run_raw(raw: bytes) -> subprocess.CompletedProcess[bytes]:
    python = qualified_python()
    return subprocess.run(
        [str(python), "-I", "-u", str(WORKER)],
        cwd=str(ROOT),
        input=raw,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_genuine_cantera_trajectory_rates_and_identity():
    hello, responses = run_worker([request("run-1")])
    identity = hello["identity"]
    assert hello["schema"] == "ciw.native-interop-handshake-response.v1"
    assert hello["status"] == "ok"
    assert hello["profiles"] == [PROFILE]
    assert identity["schema"] == "ciw.reaction-cantera-identity.v1"
    assert identity["python_version"] == "3.12.14"
    assert identity["platform"] == "win-amd64"
    assert identity["packages"] == {
        "cantera": "3.2.0",
        "numpy": "2.5.3",
        "ruamel.yaml": "0.19.1",
        "typing-extensions": "4.16.0",
    }
    assert all(
        isinstance(identity[name], str) and identity[name].startswith("sha256:")
        for name in (
            "worker_sha256",
            "requirements_sha256",
            "extension_sha256",
            "package_files_sha256",
        )
    )
    assert identity["worker_sha256"] == "sha256:" + hashlib.sha256(WORKER.read_bytes()).hexdigest()
    response = responses[0]
    assert response["status"] == "ok"
    assert response["profile"] == PROFILE
    data = response["data"]
    assert set(data) == {
        "model",
        "species_order",
        "time_s",
        "concentration_mol_m3",
        "production_rate_mol_m3_s",
        "mechanism",
        "solver",
    }
    assert data["species_order"] == payload()["species_order"]
    assert data["time_s"] == payload()["time_s"]
    assert data["mechanism"]["format"] == "cantera-yaml-v1"
    mechanism = bytes.fromhex(data["mechanism"]["bytes_hex"])
    assert mechanism.startswith(b"units:\n")
    assert b"equation: A => B\n" in mechanism
    assert data["mechanism"]["sha256"] == "sha256:" + hashlib.sha256(mechanism).hexdigest()
    assert data["solver"] == {
        "algorithm": "Cantera.CVODES",
        "retcode": "Success",
        **payload()["solver"],
    }
    checked = check_output(
        {
            "schema": "ciw.native-interop-source.v1",
            "experiment_id": "cantera-test",
            "provider": "cantera",
            "profile": PROFILE,
            "arithmetic": "binary64",
            "semantics": deepcopy(SEMANTICS),
            "payload": payload(),
            "configuration": {
                "atol": 2e-8,
                "rtol": 2e-8,
                "qp_kkt_atol": 2e-6,
                "covariance_status": "not_applicable",
                "calibration": "not_applicable",
            },
            "upstream": None,
        },
        data,
    )
    assert checked["outcome"] == "passed"
    assert checked["metrics"]["trajectory_max_abs_mol_m3"] < 2e-8
    assert checked["metrics"]["rate_law_max_abs_mol_m3_s"] < 2e-8


def test_worker_response_persistence_reopen_and_replay_are_byte_stable(tmp_path):
    _hello, responses = run_worker([request("run-a"), request("run-b")])
    first, replay = (response["data"] for response in responses)
    saved = tmp_path / "cantera-result.json"
    saved.write_text(json.dumps(first, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    reopened = json.loads(saved.read_text(encoding="utf-8"))
    assert reopened == replay


def test_species_permutation_is_preserved_by_native_engine():
    swapped = payload()
    swapped["species_order"] = ["B", "A"]
    swapped["initial_concentration_mol_m3"] = [0.5, 2.0]
    _hello, responses = run_worker([request("swapped", swapped)])
    response = responses[0]
    assert response["status"] == "ok"
    data = response["data"]
    assert data["species_order"] == ["B", "A"]
    assert data["concentration_mol_m3"][0] == pytest.approx([0.5, 2.0], abs=2e-8)
    assert data["production_rate_mol_m3_s"][0] == pytest.approx([1.0, -1.0], abs=2e-8)


def test_zero_rate_constant_is_a_native_success_with_zero_rates():
    zero = payload()
    zero["rate_constant_s_inv"] = 0.0
    _hello, responses = run_worker([request("zero-rate", zero)])
    response = responses[0]
    assert response["status"] == "ok"
    data = response["data"]
    for row in data["concentration_mol_m3"]:
        assert row == pytest.approx([2.0, 0.5], abs=2e-8)
    for row in data["production_rate_mol_m3_s"]:
        assert row == pytest.approx([0.0, 0.0], abs=2e-12)


def test_duplicate_stale_occurrence_is_refused_in_a_b_a_sequence():
    _hello, responses = run_worker([request("A"), request("B"), request("A")])
    assert [response["status"] for response in responses] == ["ok", "ok", "refused"]
    assert responses[2]["refusal"]["code"] == "INVALID_REQUEST"


def test_transport_accepts_slash_and_full_160_character_identifiers():
    valid = request("x" * 159 + "/")
    valid["parent_execution_id"] = "parent/path"
    _hello, responses = run_worker([valid])
    assert responses[0]["status"] == "ok"


def test_transport_refuses_identifier_longer_than_160_characters():
    invalid = request("x" * 161)
    _hello, responses = run_worker([invalid])
    assert responses[0]["status"] == "refused"
    assert responses[0]["refusal"]["code"] == "INVALID_REQUEST"


def test_duplicate_json_key_frame_fails_closed_with_bounded_timeout():
    handshake = frame({"schema": "ciw.native-interop-handshake-request.v1", "request_id": "hello"})
    malformed = b'{"schema":"ciw.native-interop-request.v1","request_id":"x","request_id":"x"}'
    completed = run_raw(handshake + struct.pack(">I", len(malformed)) + malformed)
    assert completed.returncode != 0
    assert b"duplicate JSON key" in completed.stderr


def test_oversized_frame_fails_closed_with_bounded_timeout():
    handshake = frame({"schema": "ciw.native-interop-handshake-request.v1", "request_id": "hello"})
    oversized = struct.pack(">I", 1024 * 1024 + 1)
    completed = run_raw(handshake + oversized)
    assert completed.returncode != 0
    assert b"oversized frame" in completed.stderr


@pytest.mark.parametrize(
    "mutation",
    ("negative_concentration", "wrong_semantics", "unknown_payload_field", "too_few_steps"),
)
def test_invalid_or_unqualified_requests_are_refused(mutation):
    value = payload()
    envelope = request("refuse-" + mutation, value)
    if mutation == "negative_concentration":
        value["initial_concentration_mol_m3"] = [-1.0, 2.0]
        envelope = request("refuse-negative", value)
    elif mutation == "wrong_semantics":
        envelope["semantics"]["concentration_unit"] = "kmol/m^3"
    elif mutation == "unknown_payload_field":
        value["mechanism"] = "caller-supplied code is never accepted"
        envelope = request("refuse-mechanism", value)
    else:
        value["time_s"] = [0.0, 10.0]
        value["solver"]["max_steps"] = 1
        envelope = request("refuse-steps", value)
    _hello, responses = run_worker([envelope])
    response = responses[0]
    assert response["status"] == "refused"
    assert response["refusal"]["code"] in {"INVALID_REQUEST", "NUMERICAL_FAILURE"}
