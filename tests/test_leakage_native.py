"""Contract boundaries and genuine pinned-provider conservation regressions."""
from copy import deepcopy
import math
import json
import os
from pathlib import Path

import numpy as np
import pytest

from ciw.adapters.protocol import AdapterRefusal
from ciw.leakage_contract import (AUTHORITY, MAX_BYTES, MAX_RAW_SIZE, example_request, load_file,
                                 raw_order, raw_readings, save_file, validate_request)
from ciw.leakage_native import NativeLeakageBackend, PIN, SOURCE_TREE, check_runtime, kernel_profile
from ciw.operations.runner import digest


@pytest.fixture(scope="module")
def native():
    path = Path(os.environ.get("CIW_LEAKAGE_PROVIDER_CHECKOUT",
                               "/dev/shm/polymer-leakage-provider-c53383586a0d"))
    if not path.is_dir():
        pytest.skip("Exact operator-provisioned FSRT checkout is unavailable")
    # This constructor verifies the original Git identity and every source byte;
    # no fake HEAD, native double, or source-trust override is used.
    return NativeLeakageBackend(path)


def operator(request, cumulative=False):
    n, m = len(request["edges_s"]) - 1, len(request["channels"])
    H = np.zeros((n, n + 1 + n * m))
    for i in range(n):
        H[i, i], H[i, i + 1] = -1, 1
        for j, channel in enumerate(request["channels"]):
            H[i, n + 1 + i * m + j] = -1 if channel["direction"] == "in" else 1
    return np.cumsum(H, axis=0) if cumulative else H


@pytest.mark.parametrize("basis", ["volume", "mass"])
def test_example_is_detached_and_has_explicit_full_covariance(basis):
    request = example_request(basis)
    other = validate_request(request)
    other["inventory"]["readings"][0]["value"] = 123
    assert request["inventory"]["readings"][0]["value"] == 10
    assert request["covariance"]["raw_order"] == raw_order(request)
    assert len(request["covariance"]["matrix"]) == len(raw_order(request)) <= MAX_RAW_SIZE
    assert request["unit"] == ("m3" if basis == "volume" else "kg")


@pytest.mark.parametrize("field,value", [("value", True), ("value", math.nan), ("value", math.inf),
                                         ("value", -1), ("value", 2**53 + 1), ("time_s", True)])
def test_invalid_reading_numbers(field, value):
    request = example_request()
    request["inventory"]["readings"][0][field] = value
    with pytest.raises(ValueError):
        validate_request(request)


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(basis="mass"),
    lambda r: r.update(unit="litre"),
    lambda r: r.update(process="compression_molding"),
    lambda r: r.update(source_kind="retained_observations"),
    lambda r: r["inventory"].update(support="mean"),
    lambda r: r["channels"][0].update(support="mean"),
    lambda r: r["channels"][0].update(unit="kg"),
    lambda r: r["channels"][0].update(purpose="unknown"),
    lambda r: r["channels"][0].update(direction="both"),
    lambda r: r["channels"][1].update(channel_id="feed"),
    lambda r: r["channels"][0]["readings"][0].update(end_s=2.6),
    lambda r: r["inventory"]["readings"][0].update(clock_ref=digest({"wrong_clock": 1})),
    lambda r: r["clock"].update(support_policy="uncertain_labels"),
    lambda r: r["edges_s"].__setitem__(1, 0),
    lambda r: r["edges_s"].__setitem__(-1, 11),
    lambda r: r["inventory"]["readings"].pop(),
    lambda r: r["covariance"].update(matrix=None),
    lambda r: r["covariance"].update(matrix=[1.0] * 13),
    lambda r: r["covariance"]["raw_order"].reverse(),
    lambda r: r["covariance"].update(independent=True),
    lambda r: r["covariance"]["matrix"][0].__setitem__(0, True),
    lambda r: r["covariance"]["matrix"][0].__setitem__(1, .01),
    lambda r: r["decision_policy"].update(coverage_factor=0),
    lambda r: r["decision_policy"].update(loss_threshold=-1),
    lambda r: r.update(python_executable="/untrusted/evidence/path"),
])
def test_unsupported_contract_boundaries(mutation):
    request = example_request()
    mutation(request)
    with pytest.raises(ValueError):
        validate_request(request)


def test_exactly_indefinite_small_block_is_not_repaired():
    request = example_request()
    P = request["covariance"]["matrix"]
    P[0][0] = P[1][1] = 1.0
    P[0][1] = P[1][0] = math.nextafter(1.0, math.inf)
    with pytest.raises(ValueError, match="positive semidefinite"):
        validate_request(request)


def test_zero_variance_requires_zero_cross_covariance():
    request = example_request()
    P = request["covariance"]["matrix"]
    P[0][0] = 0
    P[0][1] = P[1][0] = 1e-9
    with pytest.raises(ValueError, match="zero variance"):
        validate_request(request)


def resized_request(intervals, channels):
    r = example_request()
    edges = [10 * i / intervals for i in range(intervals + 1)]
    r["edges_s"] = edges
    base = deepcopy(r["inventory"]["readings"][0])
    r["inventory"]["readings"] = [{**deepcopy(base), "time_s": t} for t in edges]
    prototype = deepcopy(r["channels"][0])
    r["channels"] = []
    for j in range(channels):
        channel = deepcopy(prototype)
        channel["channel_id"] = f"channel{j}"
        row = deepcopy(channel["readings"][0])
        channel["readings"] = [{**deepcopy(row), "start_s": a, "end_s": b} for a, b in zip(edges, edges[1:])]
        r["channels"].append(channel)
    order = raw_order(r)
    r["covariance"]["raw_order"] = order
    r["covariance"]["matrix"] = [[1e-6 if i == j else 0 for j in range(len(order))] for i in range(len(order))]
    return r


def test_profile_size_bounds():
    validate_request(resized_request(16, 2))
    validate_request(resized_request(15, 3))  # 61 raw readings
    with pytest.raises(ValueError, match="64 raw"):
        validate_request(resized_request(16, 3))  # 65 raw readings
    with pytest.raises(ValueError, match="1..16"):
        validate_request(resized_request(17, 2))


def test_strict_file_round_trip_is_compact_create_only(tmp_path):
    request = resized_request(15, 3)
    path = tmp_path / "request.json"
    save_file(path, request)
    assert len(path.read_bytes()) <= MAX_BYTES
    assert path.read_bytes().endswith(b"\n")
    assert b"\n" not in path.read_bytes()[:-1]
    assert load_file(path) == request
    with pytest.raises(FileExistsError):
        save_file(path, request)


@pytest.mark.parametrize("replacement", ['1e-400', 'NaN', 'Infinity', 'true'])
def test_strict_file_refuses_nonzero_underflow_nonfinite_bool(tmp_path, replacement):
    request = example_request()
    raw = json.dumps(request).replace('"value": 10.0', '"value": ' + replacement, 1)
    path = tmp_path / "invalid.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        load_file(path)


def test_strict_file_refuses_duplicates_links_nonregular_and_oversize(tmp_path):
    path = tmp_path / "request.json"
    path.write_text('{"schema":"duplicate","schema":"ciw.leakage-request.v1"}')
    with pytest.raises(ValueError):
        load_file(path)
    path.unlink()
    save_file(path, example_request())
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        load_file(link)
    with pytest.raises(ValueError):
        load_file(tmp_path)
    path.write_bytes(b" " * (MAX_BYTES + 1))
    with pytest.raises(ValueError):
        load_file(path)


@pytest.mark.integration
@pytest.mark.parametrize("basis", ["volume", "mass"])
def test_real_native_residual_covariance_and_canceled_lineage(native, basis):
    request = example_request(basis)
    original = deepcopy(request)
    result = native.calculate(request)
    assert request == original
    assert result["request_ref"] == digest(request)
    assert result["runtime"]["revision"] == PIN
    assert result["runtime"]["source_tree"] == SOURCE_TREE
    assert result["kernel"] == kernel_profile(basis)
    assert result["authority"] == AUTHORITY
    assert result["raw"]["covariance"] == request["covariance"]["matrix"]
    y = np.array([row["value"] for row in raw_readings(request)])
    P = np.array(request["covariance"]["matrix"])
    for label in ("interval", "cumulative"):
        H = operator(request, label == "cumulative")
        assert np.array_equal(result[label]["operator"], H)
        np.testing.assert_allclose(result[label]["residual"], H @ y, rtol=0, atol=3e-15)
        np.testing.assert_allclose(result[label]["covariance"], H @ P @ H.T, rtol=2e-15, atol=0)
    np.testing.assert_allclose(result["interval"]["residual"], [-.05] * 4, atol=3e-15)
    np.testing.assert_allclose(result["cumulative"]["residual"], [-.05, -.10, -.15, -.20], atol=3e-15)
    intermediate_ref = request["inventory"]["readings"][1]["evidence_refs"][0]
    assert intermediate_ref in result["interval"]["evidence_refs"][1]
    assert intermediate_ref not in result["cumulative"]["evidence_refs"][-1]
    assert result["interval"]["covariance"][0][1] == -1e-4


@pytest.mark.integration
@pytest.mark.parametrize("basis", ["volume", "mass"])
def test_real_native_shared_transfer_covariance_is_retained(native, basis):
    request = example_request(basis)
    P = np.array(request["covariance"]["matrix"])
    shared = np.zeros(len(P))
    shared[5::2] = 1
    P += 3e-6 * np.outer(shared, shared)
    request["covariance"]["matrix"] = P.tolist()
    result = native.calculate(request)
    H = operator(request, True)
    np.testing.assert_allclose(result["cumulative"]["covariance"], H @ P @ H.T, rtol=2e-15)
    assert result["interval"]["covariance"][0][2] == pytest.approx(3e-6)
    assert result["cumulative"]["covariance"][-1][-1] == pytest.approx(.000208 + 16 * 3e-6)


@pytest.mark.integration
def test_real_native_balanced_transfers_stay_unprojected(native):
    request = example_request("mass")
    for i, row in enumerate(request["inventory"]["readings"]):
        row["value"] = 10 + .2 * i
    result = native.calculate(request)
    np.testing.assert_allclose(result["interval"]["residual"], 0, atol=3e-15)
    assert result["raw"]["values"][:5] == [row["value"] for row in request["inventory"]["readings"]]
    assert "projection" not in result


@pytest.mark.integration
def test_real_native_mass_refuses_singular_and_ill_conditioned_covariance(native):
    for diagonal in (0.0, 1e-20):
        request = example_request("mass")
        P = request["covariance"]["matrix"]
        for i in range(len(P)):
            P[i][i] = 1e-4 if i == 0 else diagonal
        validate_request(request)
        with pytest.raises(AdapterRefusal, match="positive definite"):
            native.calculate(request)


@pytest.mark.integration
def test_real_native_volume_allows_declared_exact_zero_covariance(native):
    request = example_request()
    size = len(raw_order(request))
    request["covariance"]["matrix"] = [[0.0] * size for _ in range(size)]
    result = native.calculate(request)
    assert result["interval"]["covariance"] == [[0.0] * 4 for _ in range(4)]
    assert result["cumulative"]["covariance"] == [[0.0] * 4 for _ in range(4)]


@pytest.mark.integration
def test_real_native_subnormal_source_covariance_changes_are_refused(native):
    request = example_request()
    request["covariance"]["matrix"][0][0] = math.nextafter(0.0, 1.0)
    validate_request(request)
    with pytest.raises(AdapterRefusal, match="preserve the declared raw covariance"):
        native.calculate(request)


@pytest.mark.integration
def test_retained_runtime_validation_never_executes_evidence_paths(native):
    runtime = native.runtime_identity()
    check_runtime(runtime)
    runtime["repository_root"] = "/unavailable/retained/declaration"
    runtime["python_executable"] = "/unavailable/retained/python"
    check_runtime(runtime)  # structure only; no filesystem execution
    for key, value in [("revision", "0" * 40), ("source_tree", "0" * 40), ("source_root", "."),
                       ("python_sha256", "0" * 40), ("python_version", "3.11.0")]:
        changed = deepcopy(runtime)
        changed[key] = value
        with pytest.raises(ValueError):
            check_runtime(changed)
