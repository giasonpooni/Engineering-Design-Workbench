"""Game-specific reopen validation must finish before any destination publication."""
from copy import deepcopy

import pytest

from ciw import game_workflow as g
from ciw.control_contracts import load, save_new
from ciw.operations.runner import seal
from test_game_session import FixtureBinding


def baseline(root):
    binding = FixtureBinding()
    _, source = g.run_case(g.courier_scenario(), binding, root / "baseline")
    return binding, source, root / "baseline/workspace.json"


def altered_workspace(root):
    _, _, original = baseline(root)
    value = load(original)
    audit = next(r for r in value["results"] if r["operation_id"] == g.AUDIT_OP)
    audit["data"]["status"] = "FAIL"
    seal(audit)
    # Structure, execution bindings and hashes remain valid. The scoped
    # retained-data check must detect the false derived outcome before writes.
    path = root / "false-outcome.json"
    save_new(path, value)
    return path, audit["result_id"]


def test_resealed_false_check_cannot_create_destination(tmp_path):
    source, _ = altered_workspace(tmp_path)
    target = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="contradicts"):
        g.open_saved(source, target)
    assert not target.exists()


def test_resealed_false_check_cannot_overwrite_existing_destination(tmp_path):
    source, result_id = altered_workspace(tmp_path)
    target = tmp_path / "existing"
    target.mkdir()
    marker = target / (result_id + ".json")
    marker.write_bytes(b"existing unrelated bytes must survive refusal")
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    with pytest.raises(ValueError, match="contradicts"):
        g.open_saved(source, target)
    assert {p.name: p.read_bytes() for p in target.iterdir()} == before


def test_wrong_reproduction_runtime_cannot_publish_output(tmp_path):
    _, source, path = baseline(tmp_path)
    binding = FixtureBinding()
    binding.identity["different_build"] = True
    target = tmp_path / "wrong-runtime"
    with pytest.raises(ValueError, match="runtime identity"):
        g.extend_case(path, binding, target, source_execution_id=source["execution_id"], reproduce=True)
    assert binding.calls == 0
    assert not target.exists()


def test_wrong_capture_selection_cannot_publish_output(tmp_path):
    _, _, path = baseline(tmp_path)
    binding = FixtureBinding()
    target = tmp_path / "wrong-selection"
    with pytest.raises(ValueError, match="Select a completed"):
        g.extend_case(path, binding, target, source_execution_id="not-a-capture", reproduce=False)
    assert binding.calls == 0
    assert not target.exists()


def test_malformed_reproduction_source_cannot_create_output(tmp_path):
    source = tmp_path / "corrupt.json"
    source.write_text("{broken", encoding="utf-8")
    binding = FixtureBinding()
    target = tmp_path / "bad-input"
    with pytest.raises(ValueError):
        g.extend_case(source, binding, target, source_execution_id="not-a-capture", reproduce=True)
    assert binding.calls == 0
    assert not target.exists()


def test_valid_reopen_preserves_all_retained_records(tmp_path):
    _, _, path = baseline(tmp_path)
    before = deepcopy(load(path))
    target = tmp_path / "valid-reopen"
    restored = g.open_saved(path, target)
    assert list(restored.results.values()) == before["results"]
    assert list(restored.executions.values()) == before["executions"]
    assert target.is_dir()
