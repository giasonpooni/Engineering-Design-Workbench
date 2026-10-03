"""The operator CLI preserves create-only inputs and honest retained outcomes."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ciw import leakage_cli, leakage_workflow
from ciw.adapters.protocol import AdapterRefusal
from ciw.leakage_contract import AUTHORITY, MAX_BYTES, example_request, validate_request
from ciw.net import main as net_main


@pytest.fixture(scope="module")
def native_backend():
    configured = os.environ.get("CIW_LEAKAGE_PROVIDER_CHECKOUT")
    if not configured or not Path(configured).exists():
        pytest.skip("CIW_LEAKAGE_PROVIDER_CHECKOUT must name an existing FSRT checkout")
    from ciw.leakage_native import NativeLeakageBackend
    return NativeLeakageBackend(Path(configured))


@pytest.fixture(scope="module")
def retained(native_backend, tmp_path_factory):
    directory = tmp_path_factory.mktemp("leakage-cli") / "run"
    result = leakage_workflow.run(example_request(), directory, backend=native_backend)
    assert result["status"] == "PASS", result
    return directory


def _json_output(capsys, code):
    captured = capsys.readouterr()
    text = captured.out if code in (0, 2) else captured.err
    assert text, captured
    return json.loads(text)


def _files(directory):
    return {str(p.relative_to(directory)): p.read_bytes()
            for p in directory.rglob("*") if p.is_file()}


@pytest.mark.parametrize("basis,unit", [("volume", "m3"), ("mass", "kg")])
def test_nested_example_is_create_only_and_preserves_declared_support(tmp_path, capsys, basis, unit):
    path = tmp_path / "request.json"
    code = net_main(["polymer", "leakage", "example", "--basis", basis, "--output", str(path)])
    assert code == 0 and _json_output(capsys, code)["status"] == "created"
    request = validate_request(json.loads(path.read_text()))
    assert request["unit"] == unit
    assert all(c["support"] == "integrated_total" for c in request["channels"])
    before = path.read_bytes()
    code = net_main(["polymer", "leakage", "example", "--basis", basis, "--output", str(path)])
    assert code == 1 and _json_output(capsys, code)["status"] == "REFUSE"
    assert path.read_bytes() == before


def test_nested_help_exposes_explicit_provider_and_parent_run_directory(capsys):
    with pytest.raises(SystemExit) as completed:
        net_main(["polymer", "leakage", "run", "--help"])
    assert completed.value.code == 0
    text = capsys.readouterr().out
    assert "--provider-checkout" in text and "--polymer-workspace" in text
    assert "directory" in text and "workspace.json" in text


@pytest.mark.parametrize("challenge", ["duplicate", "nonfinite", "oversize", "symlink", "authority", "rate_support"])
def test_bad_request_refuses_before_loading_provider_or_creating_output(tmp_path, capsys, monkeypatch, challenge):
    request = tmp_path / "input.json"
    if challenge == "duplicate":
        request.write_text('{"schema":"a","schema":"b"}')
    elif challenge == "nonfinite":
        request.write_text('{"value":Infinity}')
    elif challenge == "oversize":
        with request.open("wb") as stream:
            stream.truncate(MAX_BYTES + 1)
    elif challenge == "symlink":
        target = tmp_path / "target.json"
        target.write_text(json.dumps(example_request()))
        request.symlink_to(target)
    else:
        value = example_request()
        if challenge == "authority":
            value["authority"] = {"hardware_actuation": "permitted"}
        else:
            value["channels"][0]["support"] = "rate"
        request.write_text(json.dumps(value))
    def forbidden(*args, **kwargs):
        pytest.fail("Malformed request reached native provider construction")
    monkeypatch.setattr(leakage_cli, "_backend", forbidden)
    destination = tmp_path / "output"
    code = net_main(["polymer", "leakage", "run", str(request), "--output-dir", str(destination),
        "--provider-checkout", str(tmp_path / "unused")])
    assert code == 1 and _json_output(capsys, code)["status"] == "REFUSE"
    assert not destination.exists()


def test_missing_provider_checkout_reports_structured_refusal(tmp_path, capsys):
    code = net_main(["polymer", "leakage", "doctor", "--provider-checkout", str(tmp_path / "missing")])
    assert code == 1
    result = _json_output(capsys, code)
    assert result["status"] == "REFUSE" and result["reason"]


def test_run_requires_explicit_provider_selection_before_reading_request(tmp_path, capsys):
    with pytest.raises(SystemExit) as refused:
        net_main(["polymer", "leakage", "run", str(tmp_path / "request"), "--output-dir", str(tmp_path / "run")])
    assert refused.value.code == 2
    assert "--provider-checkout" in capsys.readouterr().err
    assert not (tmp_path / "run").exists()


@pytest.mark.integration
class TestNativeOperatorCommands:
    def test_readonly_commands_and_create_only_fresh_receipt(self, retained, tmp_path, capsys, monkeypatch):
        before = _files(retained)
        def forbidden(*args, **kwargs):
            pytest.fail("Read-only CLI command constructed a native provider")
        monkeypatch.setattr(leakage_cli, "_backend", forbidden)
        code = net_main(["polymer", "leakage", "inspect", str(retained)])
        assert code == 0
        inspection = _json_output(capsys, code)
        assert inspection["status"] == inspection["numerical_audit_status"] == "PASS"
        assert inspection["balance_status"] == "UNACCOUNTED_LOSS"
        receipt = tmp_path / "fresh.json"
        code = net_main(["polymer", "leakage", "verify", str(retained), "--output", str(receipt)])
        assert code == 0
        fresh = _json_output(capsys, code)
        assert fresh == json.loads(receipt.read_text())
        assert fresh["verification_id"] != inspection["verification"]["verification_id"]
        assert fresh["fresh_numerical_verification"] is True and fresh["authority"] == AUTHORITY
        receipt_before = receipt.read_bytes()
        code = net_main(["polymer", "leakage", "verify", str(retained), "--output", str(receipt)])
        assert code == 1 and _json_output(capsys, code)["status"] == "REFUSE"
        assert receipt.read_bytes() == receipt_before
        output = tmp_path / "export"
        code = net_main(["polymer", "leakage", "export", str(retained), "--output-dir", str(output)])
        assert code == 0
        assert _json_output(capsys, code)["status"] == "created"
        assert (output / "workspace.json").read_bytes() == before["workspace.json"]
        assert _files(retained) == before

    def test_refused_native_outcome_uses_nonzero_exit_and_retains_attempt(self, native_backend, tmp_path, capsys, monkeypatch):
        request = tmp_path / "request.json"
        request.write_text(json.dumps(example_request()))
        def refuse(*args, **kwargs):
            raise AdapterRefusal("TEST_NATIVE_REFUSAL", "Declared covariance unsupported")
        monkeypatch.setattr(native_backend, "calculate", refuse)
        monkeypatch.setattr(leakage_cli, "_backend", lambda args: native_backend)
        output = tmp_path / "refused"
        code = net_main(["polymer", "leakage", "run", str(request), "--output-dir", str(output),
            "--provider-checkout", str(tmp_path / "operator-selected")])
        assert code == 2
        result = _json_output(capsys, code)
        assert result["status"] == "REFUSE" and result["balance_status"] == "NOT_AVAILABLE"
        workspace = json.loads((output / "workspace.json").read_text())
        assert len(workspace["executions"]) == 1 and workspace["results"] == []
        assert workspace["executions"][0]["refusal"]["code"] == "TEST_NATIVE_REFUSAL"

    def test_doctor_checks_selected_runtime_and_qualify_executes_both_bases(self, native_backend, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(leakage_cli, "_backend", lambda args: native_backend)
        provider = str(tmp_path / "operator-selected")
        code = net_main(["polymer", "leakage", "doctor", "--provider-checkout", provider])
        assert code == 0
        doctor = _json_output(capsys, code)
        assert doctor["status"] == "PASS" and all(doctor["checks"].values())
        assert doctor["authority"] == AUTHORITY
        output = tmp_path / "qualification"
        code = net_main(["polymer", "leakage", "qualify", "--output-dir", str(output), "--provider-checkout", provider])
        assert code == 0
        report = _json_output(capsys, code)
        assert report["status"] == "PASS" and all(c["passed"] for c in report["checks"])
        assert report == json.loads((output / "qualification.json").read_text())
        for basis in ("volume", "mass"):
            assert (output / basis / "workspace.json").is_file()
            assert (output / (basis + "-replay") / "workspace.json").is_file()
            assert (output / (basis + "-report") / "balance.csv").is_file()

    def test_actual_nested_python_entrypoint_run_inspect_verify_replay(self, native_backend, tmp_path):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PYTHONPATH=str(root / "src"), PYTHONDONTWRITEBYTECODE="1")
        def call(*args):
            response = subprocess.run([sys.executable, "-m", "ciw.net", "polymer", "leakage", *map(str, args)],
                cwd=root, env=env, capture_output=True, text=True, timeout=60)
            assert response.returncode == 0, response.stderr or response.stdout
            return json.loads(response.stdout)
        request = tmp_path / "mass.json"
        call("example", "--basis", "mass", "--output", request)
        checkout = os.environ["CIW_LEAKAGE_PROVIDER_CHECKOUT"]
        run_dir = tmp_path / "run"
        initial = call("run", request, "--output-dir", run_dir, "--provider-checkout", checkout)
        assert initial["basis"] == "mass" and initial["balance_status"] == "UNACCOUNTED_LOSS"
        assert call("inspect", run_dir) == initial
        fresh = call("verify", run_dir, "--output", tmp_path / "fresh.json")
        assert fresh["status"] == "PASS" and fresh["verification_id"] != initial["verification"]["verification_id"]
        repeated = call("replay", run_dir, "--output-dir", tmp_path / "replay", "--provider-checkout", checkout)
        assert repeated["evidence_id"] == initial["evidence_id"]
        assert {r["execution_id"] for r in initial["occurrences"]}.isdisjoint(r["execution_id"] for r in repeated["occurrences"])
