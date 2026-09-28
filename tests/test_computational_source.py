"""Real local Git, no imported selected source; retained comparisons use CIW math."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import pytest

from ciw import computational_objects as co
from ciw import computational_source as cs
from ciw.computational_view import render_selection
from ciw.control_contracts import bytes_ref, load, observation, save_new
from ciw.core.identities import content_identity
from ciw.net import main
from ciw.operations.runner import seal
from test_computational_objects import specimen

SOURCE = b'''from pathlib import Path
Path("must-not-execute").write_text("NO")

def decorate(fn):
    return fn

class Integrator:
    @decorate
    def step(self, x):
        return helper(x)

def helper(x):
    return x + 1
'''


def git(root, *args, data=None):
    return subprocess.check_output(["git", "-C", str(root), *args], input=data, stderr=subprocess.PIPE).decode().strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "NET contract fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "core.autocrlf", "false")
    (root / "model.py").write_bytes(SOURCE)
    for language in ("rust", "cpp", "julia", "wgsl", "gdscript", "typescript"):
        (root / (language + ".txt")).write_bytes(b"// bounded explicit source\noperation\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "Synthetic committed source fixture")
    return root


def snapshot(repo):
    return cs.capture_git(repo, repository="fixture/selection", revision="HEAD", path="model.py", language="python")


def capture(repo, editable=True, declaration=None):
    return cs.bind_source(snapshot(repo), {"symbol": "Integrator.step", "line": None, "span": None},
                          editable=editable, declaration=declaration)


@pytest.mark.parametrize("path", ["../secret", "/root/key", "a/../b", "a//b", "./a", "a/", "C:/data", r"a\b", ".git/config", "x\ny"])
def test_noncanonical_paths_refuse(path):
    obj = specimen()
    obj["source"]["path"] = path
    with pytest.raises(ValueError):
        co.validate_object(obj)


@pytest.mark.parametrize("value", [0, 1, "false", [], None])
def test_authority_booleans_are_exact(value):
    obj = specimen()
    obj["authority"]["may_execute"] = value
    with pytest.raises(ValueError):
        co.validate_object(obj)


@pytest.mark.parametrize("field", ["digest", "authority", "paths", "authorization", "views", "object"])
def test_tampered_selection_refuses_even_with_recomputed_id(field):
    obj = specimen()
    value = co.select(obj)
    if field == "digest":
        value["selection_id"] = "selection:sha256:" + "0" * 64
    elif field == "authority":
        value["authority"]["may_edit"] = True
    elif field == "paths":
        value["edit_envelope"]["paths"] = ["unrelated.py"]
    elif field == "authorization":
        value["edit_envelope"]["requires_human_or_executor_authorization"] = False
    elif field == "views":
        value["views"] = []
    else:
        value["object_digest"] = "sha256:" + "1" * 64
    if field != "digest":
        value["selection_id"] = "selection:" + co._digest({k: v for k, v in value.items() if k != "selection_id"})
    with pytest.raises(ValueError):
        co.context_package(obj, value)


def test_context_perturbation_detachment_and_reopening():
    obj = specimen()
    views = ["source"]
    selection = co.select(obj, views=views)
    views.append("algebra")
    assert selection["views"] == ["source"]
    context = co.context_package(obj, selection)
    assert co.validate_context(context) == context
    context["direct_context"]["invariants"] = ["forged"]
    context["context_digest"] = co._digest({k: v for k, v in context.items() if k != "context_digest"})
    with pytest.raises(ValueError):
        co.validate_context(context)
    request = co.perturbation_request(obj, dimension="parameter", change={"dt": 0.1})
    assert co.validate_perturbation(obj, request) == request
    request["execute"] = True
    with pytest.raises(ValueError):
        co.validate_perturbation(obj, request)


@pytest.mark.parametrize("left,right", [({"x": [1]}, {"y": [1]}), ({"x": [[1, 2]]}, {"x": [1, 2]}),
    ({"x": 1, "unit": "m"}, {"x": 1, "unit": "s"}), ({"x": True}, {"x": 1}),
    ({"x": None}, {"x": 0}), ({"x": float("inf")}, {"x": 1}),
    ({"x": 10**400}, {"x": 0})])
def test_legacy_comparison_does_not_flatten_unrelated_numbers(left, right):
    with pytest.raises(ValueError):
        co.compare_observations(specimen(), left, right, metrics=["output"])


def test_actual_git_capture_decorator_and_no_execution(repo, monkeypatch):
    monkeypatch.chdir(repo)
    value = capture(repo)
    assert not (repo / "must-not-execute").exists()
    assert value["snapshot"]["revision"] == git(repo, "rev-parse", "HEAD")
    assert value["object"]["source"]["span"] == [8, 10]
    assert value["object"]["mathematics"]["expression"] == "undeclared"
    assert value["object"]["operation_id"] is None
    assert value["syntactic_calls"] == [{"expression": "helper", "line": 10, "resolution": "unresolved"}]
    assert cs.validate_capture(value) == value
    (repo / "model.py").write_bytes(b"dirty worktree never silently captured")
    assert snapshot(repo)["content"].encode() == SOURCE


def test_qualified_symbols_and_innermost_line(repo):
    snap = snapshot(repo)
    index = cs.index_source(snap)
    assert [item["name"] for item in index["symbols"]] == ["decorate", "Integrator", "Integrator.step", "helper"]
    by_line = cs.bind_source(snap, {"symbol": None, "line": 9, "span": None})
    assert by_line["object"]["label"] == "Integrator.step"
    with pytest.raises(ValueError):
        cs.bind_source(snap, {"symbol": "step", "line": None, "span": None})


def test_git_environment_does_not_override_explicit_root(repo, monkeypatch):
    monkeypatch.setenv("GIT_DIR", str(repo / "nonexistent"))
    assert snapshot(repo)["content"].encode() == SOURCE


def test_git_symlink_missing_directory_and_oversized_refuse(repo):
    blob = git(repo, "hash-object", "-w", "--stdin", data=b"model.py")
    git(repo, "update-index", "--add", "--cacheinfo", "120000", blob, "link.py")
    (repo / "large.py").write_bytes(b"#" * (cs.MAX_SOURCE_BYTES + 1))
    git(repo, "add", "large.py")
    git(repo, "commit", "-qm", "Boundaries")
    for path in ("link.py", "large.py", "missing.py", "."):
        with pytest.raises(ValueError):
            cs.capture_git(repo, repository="fixture/repo", revision="HEAD", path=path, language="python")
    with pytest.raises(ValueError):
        cs.capture_git(repo, repository="fixture/repo", revision="no-such-ref", path="model.py", language="python")


@pytest.mark.parametrize("language", ["rust", "cpp", "julia", "wgsl", "gdscript", "typescript"])
def test_polyglot_explicit_spans_not_fake_parsers(repo, language):
    snap = cs.capture_git(repo, repository="fixture/repo", revision="HEAD", path=language + ".txt", language=language)
    value = cs.bind_source(snap, {"symbol": None, "line": None, "span": [1, 2]})
    assert value["object"]["source"]["language"] == language
    assert not value["syntactic_calls"]
    with pytest.raises(ValueError):
        cs.index_source(snap)


@pytest.mark.parametrize("locator", [{"symbol": None, "line": 200, "span": None},
    {"symbol": "missing", "line": None, "span": None}, {"symbol": None, "line": None, "span": [0, 1]},
    {"symbol": None, "line": None, "span": [1, 999]}, {"symbol": "helper", "line": None, "span": [1, 2]},
    {"symbol": None, "line": True, "span": None}])
def test_invalid_locator_refuses(repo, locator):
    with pytest.raises(ValueError):
        cs.bind_source(snapshot(repo), locator)


def test_unicode_crlf_nested_and_ambiguous_symbols(repo):
    raw = 'def duplicate():\r\n    return "α\\u0085"\r\ndef duplicate():\r\n    def nested():\r\n        return "λ"\r\n    return nested()\r\n'.encode()
    (repo / "model.py").write_bytes(raw)
    git(repo, "add", "model.py")
    git(repo, "commit", "-qm", "CRLF and nested symbols")
    snap = snapshot(repo)
    with pytest.raises(ValueError):
        cs.bind_source(snap, {"symbol": "duplicate", "line": None, "span": None})
    value = cs.bind_source(snap, {"symbol": "duplicate", "line": 6, "span": None})
    ctx = cs.source_context(value)
    assert ctx["excerpt"].encode() == b"".join(raw.splitlines(keepends=True)[2:])
    assert ctx["excerpt_sha256"] == bytes_ref(ctx["excerpt"].encode())
    assert cs.validate_source_context(ctx, value) == ctx
    ctx["excerpt"] += "forged"
    seal(ctx)
    with pytest.raises(ValueError):
        cs.validate_source_context(ctx, value)


@pytest.mark.parametrize("field", ["content", "span", "calls", "declaration", "permissions"])
def test_capture_tampering_refuses(repo, field):
    value = capture(repo)
    if field == "content":
        value["snapshot"]["content"] += "\n# forged\n"
        seal(value["snapshot"])
    elif field == "span":
        value["object"]["source"]["span"] = [1, 3]
    elif field == "calls":
        value["syntactic_calls"] = []
    elif field == "declaration":
        value["declaration"]["operation_id"] = "unrelated.v1"
    else:
        value["selection"]["authority"]["may_execute"] = True
    seal(value)
    with pytest.raises(ValueError):
        cs.validate_capture(value)


def test_edit_guard_is_span_bounded_inert_and_not_verification(repo):
    value = capture(repo)
    allowed = SOURCE.replace(b"return helper(x)", b"return helper(x) + 2")
    check = cs.check_edit(value, allowed)
    assert check["status"] == "PASS" and check["applied"] is False and check["verification_id"] is None
    assert cs.check_edit(value, allowed + b"# outside\n")["status"] == "FAIL"
    assert cs.check_edit(value, b"# outside\n" + allowed)["status"] == "FAIL"
    assert cs.check_edit(capture(repo, editable=False), allowed)["status"] == "FAIL"
    assert (repo / "model.py").read_bytes() == SOURCE


def obs(value, **changes):
    kwargs = {"identity": {"model_id": "fixture-model.v1", "entity_id": "x", "execution_id": "fixture-execution"},
        "clock": {"id": "fixture-clock", "time_s": 0}, "frame": "fixture-frame", "quantity": "x", "value": value, "unit": "m",
        "provenance": {"provider": "fixture", "sources": [bytes_ref(b"synthetic")], "semantics": "simulated"}}
    kwargs.update(changes)
    return observation(**kwargs)


@pytest.mark.parametrize("changes,reason", [({"unit": "s"}, "model_entity_quantity_unit_frame_or_clock_mismatch"),
    ({"frame": "other"}, "model_entity_quantity_unit_frame_or_clock_mismatch"),
    ({"quantity": "y"}, "model_entity_quantity_unit_frame_or_clock_mismatch"),
    ({"clock": {"id": "fixture-clock", "time_s": 1}}, "time_grid_mismatch"),
    ({"value": [1.0]}, "shape_mismatch"), ({"value": None}, "missing_sample")])
def test_typed_comparison_reuses_existing_mismatch_rules(repo, changes, reason):
    kwargs = {"value": 1.0, **changes}
    result = cs.compare_series(capture(repo), [obs(1)], [obs(**kwargs)], atol=0)
    assert result["comparison"]["outcome"]["status"] == "INDETERMINATE"
    assert result["comparison"]["outcome"]["reason"] == reason
    assert cs.validate_source_comparison(result, capture(repo)) == result


def test_comparison_pass_fail_tamper_and_identity_separation(repo):
    value = capture(repo)
    left, right = [obs(1.0)], [obs(1.05)]
    passed = cs.compare_series(value, left, right, atol=.1)
    assert passed["comparison"]["outcome"]["status"] == "PASS"
    assert cs.compare_series(value, left, right, atol=.01)["comparison"]["outcome"]["status"] == "FAIL"
    assert passed["verification_id"] is None and passed["verification_status"] == "not_verified"
    passed["comparison"]["outcome"]["metrics"]["max_abs_error"] = 0
    seal(passed["comparison"])
    seal(passed)
    with pytest.raises(ValueError):
        cs.validate_source_comparison(passed, value)


def test_render_is_escaped_script_free_and_offline(repo):
    declared = {"mathematics": {"domain": "<script>alert(1)</script>", "codomain": "state",
        "expression": "f : X -> Y", "units": {}, "assumptions": []}}
    html = render_selection(capture(repo, declaration=declared))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "default-src &#x27;none&#x27;" in html
    assert "src='http" not in html and "src=\"http" not in html
    assert "selected-code" in html and "helper(x)" in html


def test_cli_capture_context_view_perturb_edit_compare_and_no_overwrite(repo, tmp_path, capsys):
    output = tmp_path / "capture.json"
    args = ["object", "capture", "--repo-root", str(repo), "--repository", "fixture/repo", "--revision", "HEAD",
            "--path", "model.py", "--symbol", "Integrator.step", "--editable", "--output", str(output)]
    assert main(args) == 0
    before = output.read_bytes()
    assert main(args) == 1 and output.read_bytes() == before
    context = tmp_path / "context.json"
    assert main(["object", "context", str(output), "--output", str(context)]) == 0
    assert "snapshot" not in load(context) and "excerpt" in load(context)
    view = tmp_path / "view.html"
    assert main(["object", "view", str(output), "--output", str(view)]) == 0
    assert main(["object", "view", str(output), "--output", str(view)]) == 1
    change = tmp_path / "change.json"
    save_new(change, {"dt": {"from": .01, "to": .005}})
    assert main(["object", "perturb", str(output), "--dimension", "parameter", "--change", str(change)]) == 0
    left, right = tmp_path / "left.json", tmp_path / "right.json"
    save_new(left, [obs(1)])
    save_new(right, [obs(2)])
    assert main(["object", "compare", str(output), str(left), str(right), "--atol", "0"]) == 2
    candidate = tmp_path / "candidate.py"
    candidate.write_bytes(SOURCE.replace(b"return helper(x)", b"return helper(x) + 2"))
    assert main(["object", "check-edit", str(output), "--candidate", str(candidate)]) == 0
    assert not (repo / "must-not-execute").exists()


def test_duplicate_json_keys_are_refused_at_cli(repo, tmp_path):
    source = tmp_path / "ambiguous.json"
    source.write_text('{"schema":"x", "schema":"y"}')
    assert main(["object", "inspect", str(source)]) == 1


def test_existing_session_execution_to_selected_source_comparison(tmp_path):
    """Two genuine built-in executions; no new executor or duplicated estimator."""
    import ciw.adapters.oscillator as provider
    from ciw.control_plane import builtin_registry, experiment, run_graph
    from ciw.instruments import make_demo_run
    from ciw.session import Session
    raw = Path(provider.__file__).read_bytes()
    # A separately labelled byte-bound fixture. Git association is not invented.
    snapshot_value = cs._snapshot(raw, "installed-provider-byte-fixture", "0" * 40, "oscillator.py", "python")
    selected = cs.bind_source(snapshot_value, {"symbol": "compute_statistics", "line": None, "span": None},
                              declaration={"operation_id": "statistics.v1"})
    registry = builtin_registry(bind=True)
    session = Session(make_demo_run(), tmp_path / "session", operations=registry.operations)
    graph = experiment("selected-statistics-test", model_id="analytic-damped-oscillator.v1", nodes=[{
        "node_id": "statistics", "operation_id": "statistics.v1", "parameters": {"channel": "q"},
        "inputs": {}, "depends_on": []}])
    projected = []
    for _ in range(2):
        assert run_graph(session, graph, registry)["status"] == "completed"
        result = list(session.results.values())[-1]
        projected.append(observation(identity={"model_id": "analytic-damped-oscillator.v1", "entity_id": "oscillator",
            "execution_id": result["execution_id"]}, clock={"id": "statistics-evaluation", "time_s": 0},
            frame="oscillator-state", quantity="q-mean", value=result["data"]["mean"], unit=result["data"]["unit"],
            provenance={"provider": "ciw.oscillator", "sources": [session.run["evidence_id"], content_identity(result)],
                        "semantics": "simulated"}))
    report = cs.compare_series(selected, [projected[0]], [projected[1]], atol=0)
    assert report["comparison"]["outcome"]["status"] == "PASS"
    assert projected[0]["identity"]["execution_id"] != projected[1]["identity"]["execution_id"]
    assert len(session.results) == len(session.executions) == 2
    workspace = session.save_workspace(tmp_path / "workspace.json")
    reopened = Session.from_workspace(workspace, output_dir=tmp_path / "reopened")
    assert set(reopened.executions) == set(session.executions)
    assert report["verification_id"] is None


def test_unicode_separator_inside_string_does_not_invent_source_lines():
    raw = ('def f():\n    return "a' + chr(0x85) + 'b"\n').encode()
    snap = cs._snapshot(raw, "utf8-fixture", "0" * 40, "sample.py", "python")
    value = cs.bind_source(snap, {"symbol": "f", "line": None, "span": None})
    assert value["object"]["source"]["span"] == [1, 2]
    html = render_selection(value)
    assert '    3  ' not in html
