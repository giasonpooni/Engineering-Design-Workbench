"""Read-only evidence indexing. Synthetic fixtures are not native-engine claims."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
from unittest.mock import patch
import uuid

import pytest

from ciw.control_contracts import MAX_BYTES, bytes_ref, save_new
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.session import Session
from ciw.simulation_cli import demo
from ciw.simulation_campaign import reference_demo
from ciw.simulation_control import SimulationControl, completed, open_workspace
from ciw.simulation_records import observer
from ciw.simulation_reference import ReferenceMotion, PROVIDER_ID
from ciw.simulation_timeline import build, collect, derive, inspect_bundle
from ciw.simulation_timeline_cli import main
from ciw.simulation_timeline_view import render
from test_simulation_capture import lab as capture_lab, call_capture


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    root = tmp_path_factory.mktemp("timeline-reference")
    demo(root / "replay")
    reference_demo(root / "campaign")
    return root


def source_path(reference):
    return reference / "replay/workspace.json"


def indexed(path, reports=()):
    inputs, files = collect(workspaces=[path], reports=reports)
    return derive(inputs, files)


def test_existing_campaign_and_replay_are_linked_not_reexecuted(reference, tmp_path):
    source = source_path(reference)
    before = source.read_bytes()
    with patch("subprocess.Popen", side_effect=AssertionError("no process")), \
         patch.object(ReferenceMotion, "__init__", side_effect=AssertionError("no provider")), \
         patch.object(SimulationControl, "__init__", side_effect=AssertionError("no controller")):
        summary = build(tmp_path / "timeline", workspaces=[source], reports=[reference / "replay/replay.json"])
        checked = inspect_bundle(tmp_path / "timeline")
    assert source.read_bytes() == before
    assert summary["unique_executions"] == summary["unique_results"] == 32
    assert checked["summary"] == summary and checked["provider_executed"] is False
    t = read(tmp_path / "timeline/timeline.json")
    assert t["analyses"][0]["summary"]["status"] == "PASS"
    assert sum(link["relation"] == "restored_from" for link in t["links"]) == 2
    assert t["summary"]["instance_count"] == 3 and not t["history_gaps"]
    assert t["verification_id"] is None and t["verification_status"] == "not_verified"
    html = (tmp_path / "timeline/index.html").read_text(encoding="utf-8")
    assert "snapshot_b64" not in html and "configuration_ref" not in html
    assert "connect-src 'none'" in html and "unsafe-eval" not in html


def test_campaign_outcomes_keep_fail_meaning(reference):
    t = indexed(reference / "campaign/workspace.json", [reference / "campaign/campaign.json"])
    assert t["summary"]["unique_executions"] == 44
    assert t["analyses"][0]["summary"]["status"] == "completed"
    assert [o["outcome"]["status"] for o in t["analyses"][0]["outcomes"]] == ["FAIL"] * 3


def test_duplicate_inputs_are_not_new_occurrences(reference, tmp_path):
    a = source_path(reference)
    value = read(a); value["view_settings"] = {"duplicate_snapshot": True}
    b = tmp_path / "second.json"; write(b, value)
    x, xf = collect(workspaces=[a, a, b])
    y, yf = collect(workspaces=[b, a])
    assert x == y and xf == yf
    t = derive(x, xf)
    assert t == derive(y, yf)
    assert t["summary"]["deduplicated_execution_copies"] == 32
    assert t["summary"]["unique_executions"] == 32


def test_conflicting_valid_occurrence_copies_refuse(reference, tmp_path):
    value = read(source_path(reference))
    ex = value["executions"][0]
    ex["created_at"] = "2026-09-01T00:00:00+00:00"; seal(ex)
    result = next(r for r in value["results"] if r["execution_id"] == ex["execution_id"])
    result["created_at"] = ex["created_at"]; seal(result)
    altered = tmp_path / "conflict.json"; write(altered, value)
    with pytest.raises(ValueError, match="Conflicting retained execution"):
        build(tmp_path / "no-output", workspaces=[source_path(reference), altered])
    assert not (tmp_path / "no-output").exists()


def test_samples_remain_identical_and_delayed(reference):
    original = read(source_path(reference))
    t = indexed(source_path(reference))
    observed = [e for e in t["entries"] if e["kind"] == "observation"]
    for e in observed:
        r = next(r for r in original["results"] if r["result_id"] == e["result_id"])
        assert e["samples"] == r["data"]["observations"]["samples"]
    delayed = next(e for e in observed if e["observer"]["kind"] == "embodied_agent")
    assert delayed["available_at"]["time_s"] == 6
    assert delayed["samples"][-1]["clock"]["time_s"] == 4
    assert delayed["samples"][0]["identity"]["execution_id"] is None


def test_missing_step_is_unknown_not_a_filled_edge(reference, tmp_path):
    value = read(source_path(reference))
    removed = next(r for r in value["results"] if r["parameters"]["action"] == "step")
    value["results"].remove(removed)
    value["executions"] = [e for e in value["executions"] if e["execution_id"] != removed["execution_id"]]
    path = tmp_path / "gap.json"; write(path, value)
    t = indexed(path)
    assert t["summary"]["history_status"] == "INDETERMINATE"
    assert any(g["reason"] == "history_gap" for g in t["history_gaps"])
    assert not any(removed["execution_id"] in (l["source"], l["target"]) for l in t["links"])


def test_absent_checkpoint_occurrence_is_reported(reference, tmp_path):
    value = read(source_path(reference))
    removed = next(r for r in value["results"] if r["parameters"]["action"] == "checkpoint")
    value["results"].remove(removed)
    value["executions"] = [e for e in value["executions"] if e["execution_id"] != removed["execution_id"]]
    path = tmp_path / "gap.json"; write(path, value)
    t = indexed(path)
    assert sum(g["reason"] == "checkpoint_occurrence_not_selected" for g in t["history_gaps"]) == 2


def test_adjacent_binding_corruption_rejected_after_resealing(reference, tmp_path):
    value = read(source_path(reference))
    r = next(r for r in value["results"] if r["parameters"]["action"] == "step")
    r["data"]["before"]["state_ref"] = "sha256:" + "f" * 64
    seal(r["data"]["before"]); seal(r["data"]); seal(r)
    path = tmp_path / "contradiction.json"; write(path, value)
    with pytest.raises(ValueError, match="Contradictory adjacent"):
        indexed(path)


def test_ambiguous_instance_revisions_rejected(reference, tmp_path):
    value = read(source_path(reference))
    r, e = deepcopy(value["results"][0]), deepcopy(value["executions"][0])
    eid, rid = "execution-" + uuid.uuid4().hex, "result-" + uuid.uuid4().hex
    r.update(execution_id=eid, result_id=rid); e.update(execution_id=eid, result_id=rid)
    seal(r); seal(e); value["results"].append(r); value["executions"].append(e)
    path = tmp_path / "ambiguous.json"; write(path, value)
    with pytest.raises(ValueError, match="Ambiguous instance"):
        indexed(path)


def test_timestamp_order_does_not_override_causal_links(reference, tmp_path):
    value = read(source_path(reference))
    r = next(r for r in value["results"] if r["parameters"]["action"] == "step")
    e = next(e for e in value["executions"] if e["execution_id"] == r["execution_id"])
    r["created_at"] = e["created_at"] = "2000-01-01T00:00:00+00:00"; seal(r); seal(e)
    path = tmp_path / "clock.json"; write(path, value)
    t = indexed(path); order = {e["execution_id"]: i for i, e in enumerate(t["entries"])}
    assert t["summary"]["wall_clock_reversed_links"] >= 1
    assert all(order[l["source"]] < order[l["target"]] for l in t["links"])


def test_refusal_has_attempted_not_fabricated_world_identity(tmp_path):
    session = Session(make_demo_run(), tmp_path / "source")
    control = SimulationControl(session)
    world = control.attach(ReferenceMotion(), provider_id=PROVIDER_ID, experiment_id="refusal")
    completed(world.command("start"))
    request = world.request("step", dt=1); request["expected"]["owner_id"] = "wrong"
    receipt = control.submit(request)
    assert receipt["payload"]["status"] == "refused"
    path = tmp_path / "source.json"; session.save_workspace(path)
    t = indexed(path); refusal = next(e for e in t["entries"] if e["kind"] == "refusal")
    assert refusal["result_id"] is None and refusal["world_after"] is None and refusal["owner_id"] is None
    assert refusal["instance_id"] is None and refusal["requested_instance_id"] == world.instance_id


def test_capture_links_bytes_and_source_without_executing(capture_lab, tmp_path):
    directory = tmp_path / "capture"
    result = call_capture(capture_lab, directory)
    with patch("subprocess.Popen", side_effect=AssertionError("no renderer")):
        summary = build(tmp_path / "timeline", captures=[directory])
        inspected = inspect_bundle(tmp_path / "timeline")
    assert summary["unique_executions"] == 2 and summary["checked_images"] == 1
    assert inspected["summary"] == summary
    t = read(tmp_path / "timeline/timeline.json")
    c = next(e for e in t["entries"] if e["kind"] == "capture")
    assert c["image"]["bytes_checked"] is True and c["execution_id"] == result["execution_id"]
    assert t["links"] == [{"source": result["data"]["source_result"]["execution_id"], "target": result["execution_id"], "relation": "captured_from"}]


def test_capture_metadata_alone_does_not_claim_image_bytes(capture_lab, tmp_path):
    directory = tmp_path / "capture"; call_capture(capture_lab, directory)
    t = indexed(directory / "workspace.json")
    c = next(e for e in t["entries"] if e["kind"] == "capture")
    assert c["image"]["bytes_checked"] is False and c["image"]["asset"] is None
    assert t["summary"]["checked_images"] == 0


def test_corrupted_png_refuses_before_output(capture_lab, tmp_path):
    directory = tmp_path / "capture"; call_capture(capture_lab, directory)
    image = next((directory / "images").glob("*.png")); image.write_bytes(b"not a PNG")
    with pytest.raises(ValueError): build(tmp_path / "no-output", captures=[directory])
    assert not (tmp_path / "no-output").exists()


@pytest.mark.parametrize("mode", ["html", "index", "manifest-authority", "input-path", "source-bytes"])
def test_bundle_tampering_cannot_be_fixed_by_manifest_rehash(reference, tmp_path, mode):
    directory = tmp_path / "timeline"; build(directory, workspaces=[source_path(reference)])
    manifest = read(directory / "manifest.json")
    if mode == "html":
        p = directory / "index.html"; p.write_text("<h1>Altered</h1>")
        manifest["files"]["index.html"] = bytes_ref(p.read_bytes())
    elif mode == "index":
        p = directory / "timeline.json"; value = read(p); value["summary"]["unique_executions"] = 999; seal(value); write(p, value)
        manifest["files"]["timeline.json"] = bytes_ref(p.read_bytes())
    elif mode == "manifest-authority": manifest["verification_status"] = "verified"
    elif mode == "input-path": manifest["inputs"]["workspaces"] = ["../outside.json"]
    else:
        path = manifest["inputs"]["workspaces"][0]; (directory / path).write_bytes(b"{}")
        manifest["files"][path] = bytes_ref(b"{}")
    seal(manifest); write(directory / "manifest.json", manifest)
    with pytest.raises(ValueError): inspect_bundle(directory)


def test_report_with_absent_occurrences_refuses_preflight(reference, tmp_path):
    with pytest.raises(ValueError, match="absent or changed"):
        build(tmp_path / "no-output", workspaces=[source_path(reference)], reports=[reference / "campaign/campaign.json"])
    assert not (tmp_path / "no-output").exists()


def test_resealed_report_verdict_is_recomputed(reference, tmp_path):
    value = read(reference / "replay/replay.json"); value["outcome"]["status"] = "FAIL"; seal(value)
    path = tmp_path / "bad-replay.json"; write(path, value)
    with pytest.raises(ValueError): build(tmp_path / "no-output", workspaces=[source_path(reference)], reports=[path])
    assert not (tmp_path / "no-output").exists()


def test_create_only_and_manifest_hash(reference, tmp_path):
    directory = tmp_path / "timeline"; build(directory, workspaces=[source_path(reference)])
    original = (directory / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError): build(directory, workspaces=[source_path(reference)])
    assert (directory / "manifest.json").read_bytes() == original
    assert inspect_bundle(directory, expected_manifest_sha256=bytes_ref(original))["status"] == "retained_timeline_checked"
    with pytest.raises(ValueError, match="digest mismatch"):
        inspect_bundle(directory, expected_manifest_sha256="sha256:" + "0" * 64)


def test_incomplete_publication_has_no_manifest(reference, tmp_path):
    original_open = Path.open
    def failing_open(path, *args, **kwargs):
        if path.name == "index.html" and args and args[0] == "xb": raise OSError("injected storage failure")
        return original_open(path, *args, **kwargs)
    with patch.object(Path, "open", failing_open), pytest.raises(OSError):
        build(tmp_path / "partial", workspaces=[source_path(reference)])
    assert not (tmp_path / "partial/manifest.json").exists()


@pytest.mark.parametrize("case", ["missing", "oversized", "duplicate-key", "v3", "unsupported-report", "too-many"])
def test_invalid_inputs_refuse_without_output(reference, tmp_path, case):
    source = tmp_path / "source.json"
    if case == "oversized": source.write_bytes(b" " * (MAX_BYTES + 1))
    elif case == "duplicate-key": source.write_text('{"workspace_version":2,"workspace_version":1}')
    elif case == "v3": value=read(source_path(reference));value["workspace_version"]=3;write(source,value)
    elif case == "unsupported-report": source.write_text('{"schema":"unknown.v1"}')
    kwargs = {"workspaces": [source]}
    if case == "too-many": kwargs = {"workspaces": [source_path(reference)] * 17}
    if case == "unsupported-report": kwargs = {"workspaces": [source_path(reference)], "reports": [source]}
    with pytest.raises((ValueError, OSError)):
        build(tmp_path / "no-output", **kwargs)
    assert not (tmp_path / "no-output").exists()


def test_empty_session_is_explicit_not_a_completed_simulation(tmp_path):
    s=Session(make_demo_run(),tmp_path/'source');s.save_workspace(tmp_path/'source.json')
    t=indexed(tmp_path/'source.json')
    assert t['entries']==[] and t['summary']['history_status']=='no_indexed_simulation_history'


def test_script_terminators_are_inert(reference):
    inputs, files = collect(workspaces=[source_path(reference)])
    t = derive(inputs, files)
    t["entries"][0]["action"] = '</script><img src="https://invalid.example" onerror="alert(1)">'
    seal(t)
    html = render(t, files)
    assert '</script><img' not in html
    assert r'\u003c/script\u003e' in html
    assert html.count('<script') == 2


def test_cli_dispatch_and_invalid_status(reference, tmp_path, capsys):
    from ciw.net import main as net_main
    directory = tmp_path/'cli'
    assert net_main(['simulation','timeline','build','--workspace',str(source_path(reference)),'--output-dir',str(directory)])==0
    assert main(['inspect',str(directory)])==0
    assert main(['inspect',str(tmp_path/'missing')])==1
    assert 'refused' in capsys.readouterr().err


def test_unrelated_source_recordings_are_not_silently_joined(reference, tmp_path):
    # Different recording identity, same scientific content: neither run nor
    # evidence identity is rewritten to force an unrelated Session join.
    run=make_demo_run()
    run['run_id']='run-other-recording'
    from ciw.core.identities import evidence_id
    run['evidence_id']=evidence_id(run)
    session=Session(run,tmp_path/'other')
    session.save_workspace(tmp_path/'other.json')
    with pytest.raises(ValueError,match='exact source recording'):
        build(tmp_path/'no-output',workspaces=[source_path(reference),tmp_path/'other.json'])
    assert not (tmp_path/'no-output').exists()


def test_changed_restore_source_reference_refuses(reference, tmp_path):
    value=read(source_path(reference))
    r=next(r for r in value['results'] if r['parameters']['action']=='restore')
    r['data']['request']['arguments']['source_result_ref']='sha256:'+'a'*64
    r['parameters']=deepcopy(r['data']['request'])
    e=next(e for e in value['executions'] if e['execution_id']==r['execution_id'])
    e['parameters']=deepcopy(r['parameters'])
    seal(r['data']);seal(r);seal(e)
    path=tmp_path/'bad-restore.json';write(path,value)
    with pytest.raises(ValueError,match='checkpoint occurrence contradicts'):
        indexed(path)


def test_clock_namespace_cannot_change_within_instance(reference,tmp_path):
    value=read(source_path(reference))
    r=next(r for r in value['results'] if r['parameters']['action']=='step')
    for key in ('before','after'):
        r['data'][key]['provider']['clock']['id']='other-clock'
        seal(r['data'][key])
    seal(r['data']);seal(r)
    path=tmp_path/'clock-namespace.json';write(path,value)
    with pytest.raises(ValueError,match='clock identity changed'):
        indexed(path)


def test_selected_source_is_frozen_before_later_mutation(reference,tmp_path):
    source=tmp_path/'source.json';source.write_bytes(source_path(reference).read_bytes())
    import ciw.simulation_timeline as module
    original=module.read_bounded
    def changed(path,*args):
        data=original(path,*args)
        if Path(path)==source: source.write_text('{}')
        return data
    with patch.object(module,'read_bounded',changed):
        summary=build(tmp_path/'timeline',workspaces=[source])
    assert source.read_text()=='{}' and summary['unique_executions']==32
    assert inspect_bundle(tmp_path/'timeline')['summary']==summary


def test_aggregate_budget_is_enforced_before_output(reference,tmp_path):
    import ciw.simulation_timeline as module
    with patch.object(module,'MAX_TOTAL',1), pytest.raises(ValueError,match='aggregate byte budget'):
        build(tmp_path/'no-output',workspaces=[source_path(reference)])
    assert not (tmp_path/'no-output').exists()


def test_generic_existing_operations_keep_their_own_identity(tmp_path):
    session=Session(make_demo_run(),tmp_path/'source')
    r=completed(session.handle({'protocol_version':1,'request_id':'statistics','type':'operation.execute',
        'payload':{'operation_id':'statistics.v1','parameters':{}}}))
    session.save_workspace(tmp_path/'source.json')
    t=indexed(tmp_path/'source.json');e=t['entries'][0]
    assert e['kind']=='operation' and e['operation_id']=='statistics.v1'
    assert e['result_id']==r['result_id'] and e['world_after'] is None and e['samples']==[]
