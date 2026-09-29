"""Contract tests use a labelled test-double game, not historical/native evidence.

The separate qualification script exercises the exact real 1792 checkout.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from ciw import production_reconstruction as r


@pytest.fixture
def game(tmp_path, monkeypatch):
    root = tmp_path / "test-double-game"
    path = root / r.SOURCE_PATH
    path.parent.mkdir(parents=True)
    baseline = {"schema": "1792.gujranwala-reconstruction.v1", "year": 1792,
        "sources": [{"id": "explicit-unit-fixture-not-history"}], "routes": ["protected"],
        "features": [{"id": "stall", "kind": "stall", "position": [1, 0, 2], "size": [4, 3, 2], "collision": False},
                     {"id": "arcade", "kind": "arcade", "position": [3, 0, 2], "size": [8, 3, 2], "bays": 4}]}
    path.write_text(json.dumps(baseline), encoding="utf-8")
    checker = root / r.VALIDATOR_PATH
    checker.parent.mkdir()
    code = b'def validate(value):\n    if value["features"][0]["position"][0] < 0:\n        raise ValueError("test-double blocked route")\n'
    checker.write_bytes(code)
    monkeypatch.setattr(r, "VALIDATOR_SHA256", r.sha(code))
    return root


@pytest.fixture
def packet(game):
    return r.prepare(game, "unit-task", {"stall": ["position", "size"], "arcade": ["bays"]})


def reply(packet, x=2):
    return r.proposal(packet, "unit-worker-not-an-LLM", [{"feature_id": "stall", "field": "position", "value": [x, 0, 2]}])


def batch(packet, *, repair=True):
    attempts = [reply(packet, -1)] + ([reply(packet, 2)] if repair else [])
    return {"schema": r.BATCH, "jobs": [
        {"job_id": "primary", "proposals": attempts, "depends_on": []},
        {"job_id": "dependent", "proposals": [reply(packet, 3)], "depends_on": ["primary"]},
        {"job_id": "independent", "proposals": [reply(packet, 4)], "depends_on": []}]}


def reseal(packet):
    packet["packet_sha256"] = r.sha(r.encode({k:v for k,v in packet.items() if k != "packet_sha256"}))


def test_exact_source_and_no_mutation(packet, game):
    original = deepcopy(packet)
    candidate = r.compose(packet, reply(packet))
    before = r.parse(packet["baseline_utf8"].encode())
    after = r.parse(candidate["candidate_utf8"].encode())
    assert after["sources"] == before["sources"] and after["routes"] == before["routes"]
    assert after["features"][0]["position"] == [2, 0, 2]
    after["features"][0]["position"] = before["features"][0]["position"]
    assert after == before and packet == original
    assert r.read_regular(game / r.SOURCE_PATH).decode() == packet["baseline_utf8"]
    assert candidate["authority"]["verification_id"] is None
    assert candidate["authority"]["game_integration"] == "not_performed"


@pytest.mark.parametrize("field", ["sources", "claims", "routes", "collision", "year", "earliest_year", "id", "kind", "claim_ids", "schema", "__class__", "../x"])
def test_forbidden_fields(packet, field):
    value = reply(packet)
    value["edits"][0]["field"] = field
    with pytest.raises(ValueError):
        r.compose(packet, value)


@pytest.mark.parametrize("value", [None, True, "x", [], [1, 2], [1, 2, 3, 4], [True, 0, 1], [float("nan"), 0, 1], [float("inf"), 0, 1], [501, 0, 1], ["1", 0, 1], {"x": 1}])
def test_bad_vectors(packet, value):
    proposal = reply(packet)
    proposal["edits"][0]["value"] = value
    with pytest.raises(ValueError):
        r.compose(packet, proposal)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, 13, None, "2"])
def test_bad_bays(packet, value):
    with pytest.raises(ValueError):
        r.proposal(packet, "worker", [{"feature_id": "arcade", "field": "bays", "value": value}])


@pytest.mark.parametrize("value", [[0, 1, 1], [-1, 1, 1]])
def test_nonpositive_size(packet, value):
    with pytest.raises(ValueError):
        r.proposal(packet, "worker", [{"feature_id": "stall", "field": "size", "value": value}])


@pytest.mark.parametrize("edit", ["empty", "duplicate", "extra", "foreign", "worker-path", "too-many"])
def test_bad_replies(packet, edit):
    proposal = reply(packet)
    if edit == "empty": proposal["edits"] = []
    if edit == "duplicate": proposal["edits"] *= 2
    if edit == "extra": proposal["approved"] = True
    if edit == "foreign": proposal["packet_sha256"] = "sha256:" + "0" * 64
    if edit == "worker-path": proposal["worker_label"] = "../../worker"
    if edit == "too-many": proposal["edits"] *= 17
    with pytest.raises(ValueError):
        r.compose(packet, proposal)


@pytest.mark.parametrize("edit", ["digest", "source", "authority", "validator", "path", "allow-field", "unknown-feature", "budget", "duplicate-field", "bays-on-stall"])
def test_bad_packets(packet, edit):
    if edit == "digest": packet["packet_sha256"] = "bad"
    if edit == "source": packet["baseline_utf8"] += " "
    if edit == "authority": packet["authority"]["publication"] = "approved"
    if edit == "validator": packet["validator_sha256"] = "sha256:" + "0" * 64
    if edit == "path": packet["source_path"] = "../secret"
    if edit == "allow-field": packet["allowed_fields"]["stall"] = ["collision"]
    if edit == "unknown-feature": packet["allowed_fields"]["unknown"] = ["size"]
    if edit == "budget": packet["max_edits"] = True
    if edit == "duplicate-field": packet["allowed_fields"]["stall"] = ["size", "size"]
    if edit == "bays-on-stall": packet["allowed_fields"]["stall"] = ["bays"]
    if edit != "digest": reseal(packet)
    with pytest.raises(ValueError):
        r.validate_packet(packet)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'{} '*30000, b'{"x":Infinity}'])
def test_bad_json(raw):
    with pytest.raises(ValueError): r.parse(raw)


def test_deterministic_candidates_and_detached_worker(packet):
    expected = reply(packet)
    def worker(value):
        value["allowed_fields"].clear()
        return deepcopy(expected)
    before = deepcopy(packet)
    assert r.request_proposal(packet, worker) == expected and packet == before
    assert r.compose(packet, expected) == r.compose(packet, expected)


def test_worker_cannot_rewrite_gate(packet):
    def worker(value):
        value["allowed_fields"]["stall"] = ["collision"]
        return {"schema": r.PROPOSAL, "packet_sha256": value["packet_sha256"], "worker_label": "bad-worker",
                "edits": [{"feature_id": "stall", "field": "collision", "value": True}]}
    with pytest.raises(ValueError): r.request_proposal(packet, worker)


def test_checker_pin_before_execution(game, tmp_path):
    marker = tmp_path / "must-not-exist"
    (game / r.VALIDATOR_PATH).write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
    with pytest.raises(ValueError): r.GameValidator(game)
    assert not marker.exists()


def test_checker_drift(game):
    validator = r.GameValidator(game)
    (game / r.VALIDATOR_PATH).write_bytes(b'changed')
    with pytest.raises(ValueError): validator.runtime_identity()


def test_gate_checks_are_not_producer_claims(game, packet):
    validator = r.GameValidator(game)
    assert validator.check(r.parse(r.compose(packet, reply(packet, -1))["candidate_utf8"].encode()))["status"] == "FAIL"
    assert validator.check(r.parse(r.compose(packet, reply(packet, 2))["candidate_utf8"].encode()))["status"] == "PASS"


def test_no_overwrite_and_symlink_rejection(tmp_path, monkeypatch):
    path = tmp_path / "x.json"
    r.save_new(path, {"x": 1})
    with pytest.raises(FileExistsError): r.save_new(path, {"x": 2})
    before = path.read_bytes()
    monkeypatch.setattr(Path, "is_symlink", lambda p: p == path)
    with pytest.raises(ValueError): r.load(path)
    assert path.read_bytes() == before


def test_session_repair_blocking_inspection_and_exact_export(game, packet, tmp_path, monkeypatch):
    root = tmp_path / "campaign"
    report = r.run_batch(packet, batch(packet), game, root)
    assert report["status"] == "completed" and report["attempt_count"] == 4
    assert report["execution_count"] == 4 and report["result_count"] == 4
    files = {str(p):p.read_bytes() for p in root.rglob("*") if p.is_file()}
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Inspection started a process"))
    checked = r.inspect(root, game)
    assert checked["fresh_execution"] is False and checked["integrity"] == "checked"
    export = r.export_candidate(root, game, "primary", tmp_path / "export")
    value = json.loads((tmp_path / "export" / export["file"]).read_text())
    assert value["features"][0]["position"][0] == 2  # Not the last/dependent/independent result.
    assert files == {str(p):p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_session_failure_blocks_descendant_but_not_independent(game, packet, tmp_path):
    root = tmp_path / "campaign"
    report = r.run_batch(packet, batch(packet, repair=False), game, root)
    assert report["status"] == "incomplete" and report["attempt_count"] == 2
    assert report["jobs"]["primary"]["status"] == "rejected"
    assert report["jobs"]["dependent"]["status"] == "blocked"
    assert report["jobs"]["independent"]["status"] == "accepted"
    assert r.inspect(root, game)["status"] == "incomplete"
    with pytest.raises(ValueError): r.export_candidate(root, game, "primary", tmp_path / "export")
    assert not (tmp_path / "export").exists()


@pytest.mark.parametrize("fault", ["stale-baseline", "bad-last-alternative", "budget", "cycle"])
def test_session_preflight_has_no_partial_execution(game, packet, tmp_path, fault):
    root = tmp_path / "must-not-exist"
    work = batch(packet)
    kwargs = {}
    if fault == "stale-baseline": (game / r.SOURCE_PATH).write_text('{}')
    if fault == "bad-last-alternative": work["jobs"][-1]["proposals"][0]["edits"][0]["field"] = "collision"
    if fault == "budget": kwargs["max_operations"] = 1
    if fault == "cycle": work["jobs"][0]["depends_on"] = ["dependent"]
    with pytest.raises(ValueError): r.run_batch(packet, work, game, root, **kwargs)
    assert not root.exists()


def test_session_cli_entrypoint(game, packet, tmp_path):
    from ciw.production_reconstruction_cli import main
    packet_path, proposal_path = tmp_path / 'packet.json', tmp_path / 'proposal.json'
    r.save_new(packet_path, packet); r.save_new(proposal_path, reply(packet))
    root = tmp_path / 'cli-campaign'
    assert main(['run', '--packet', str(packet_path), '--proposal', str(proposal_path), '--game-root', str(game), '--output-dir', str(root)]) == 0
    assert main(['inspect', str(root), '--game-root', str(game)]) == 0
