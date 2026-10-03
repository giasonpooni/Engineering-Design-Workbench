"""Mandatory public CSR campaign through installed NET scientific commands.

No provider fixtures/fallbacks. A missing checkout or evidence destination fails.
Uses the existing independently coded test oracle with its unchanged tolerances.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ciw import scientific, curved_path_study as study
from ciw.control_plane import ParameterSpace, Interval
from ciw.geodesic_reference import GeodesicReferenceWorkflow, PINS
from ciw.instruments import make_demo_run
from ciw.session import Session
from test_geodesic_reference import _assert_curved_oracle

ROOT = Path(__file__).resolve().parents[1]
KIND = "curved-path-transfer"
LIMITS = {"max_abs_lateral": .01, "max_abs_heading": .01, "units": {"length": "m", "angle": "radian"}}


def forbidden(*args, **kwargs):
    raise AssertionError("Native provider called during read-only inspection/preflight")


@pytest.fixture(scope="module")
def campaign():
    assert os.environ.get("CIW_CSG_REPO"), "A genuine pinned public CSR checkout is required"
    assert os.environ.get("CIW_SCIENTIFIC_OUT"), "Retained evidence destination is required"
    root = Path(os.environ["CIW_SCIENTIFIC_OUT"])
    root.mkdir(parents=True, exist_ok=False)
    repositories = {"csg": Path(os.environ["CIW_CSG_REPO"]).resolve(strict=True)}
    raw = (ROOT / "examples/curved-path-study/baseline.json").read_bytes()
    seed = Session(make_demo_run(), root / "seed")
    seed_path = seed.save_workspace(root / "seed/workspace.json")
    source = root / "baseline.json"
    source.write_bytes(raw)
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    def cli(*args):
        call = subprocess.run([sys.executable, "-I", "-m", "ciw.net", "science", *map(str, args), "--json"],
                              cwd=root, env=env, capture_output=True, text=True, timeout=240)
        assert call.returncode == 0, call.stdout + call.stderr
        return json.loads(call.stdout)
    first = cli("run", "--workspace", seed_path, "--kind", KIND, "--source", source,
                "--label", "declared synthetic CSR baseline", "--binding", "csg=" + str(repositories["csg"]),
                "--output-dir", root / "executed")
    with scientific.open_workspace(root / "executed/workspace.json") as session:
        native = session.workbench.get_bundle(first["bundle_id"])
    replayed = cli("replay", "--workspace", root / "executed/workspace.json", "--bundle", first["bundle_id"],
                   "--binding", "csg=" + str(repositories["csg"]), "--output-dir", root / "replayed")
    with scientific.open_workspace(root / "replayed/workspace.json") as session:
        native_replay = session.workbench.get_bundle(replayed["bundle"]["bundle_id"])
    experiment = cli("study", "--workspace", root / "executed/workspace.json", "--bundle", first["bundle_id"],
        "--binding", "csg=" + str(repositories["csg"]), "--output-dir", root / "study",
        "--headings", ".001", "-.001", "--sample-index", "4", "--max-lateral", ".01", "--max-heading", ".01",
        "--length-unit", "m", "--study-id", "net-scientific-native")
    return root, repositories, first, native, replayed, native_replay, experiment, cli


def test_actual_pinned_csr_execution_and_original_oracle(campaign):
    root, repositories, first, native, *_ = campaign
    runtime = native["runtimes"]["csg"]
    assert runtime["revision"] == PINS[KIND]["revision"]
    assert runtime["source_tree"] == PINS[KIND]["source_tree"]
    step = native["steps"][0]
    _assert_curved_oracle(step["request"], step["result"]["data"])
    assert native["verification"]["outcome"] == "passed"
    assert native["verification"]["independent"] is False
    assert native["verification"]["reproduction"]["execution_id"] != step["execution_id"]
    assert native["verification"]["authority"]["state_admission"] == "not_performed"


def test_actual_replay_has_fresh_occurrences(campaign):
    _, _, _, native, replayed, fresh, *_ = campaign
    a, b = native["steps"][0], fresh["steps"][0]
    assert a["execution_id"] != b["execution_id"]
    assert a["result_id"] != b["result_id"]
    assert a["numerical_result_id"] == b["numerical_result_id"]
    assert replayed["replay_receipt"]["numerical_match"] is True
    _assert_curved_oracle(b["request"], b["result"]["data"])


def test_parameter_space_reaches_original_study_and_full_covariance(campaign):
    root, _, _, _, _, _, experiment, _ = campaign
    assert experiment["schema"] == "ciw.curved-path-study.v1"
    assert len(experiment["candidates"]) == 2
    assert experiment["authority"]["state_admission"] == "not_performed"
    with scientific.open_workspace(root / "study/workspace.json") as session:
        assert study.load_study(root / "study/study.json", session.workbench) == experiment
        for row in experiment["candidates"]:
            native = session.workbench.get_bundle(row["references"]["bundle_id"])
            step = native["steps"][0]
            _assert_curved_oracle(step["request"], step["result"]["data"])
            assert step["result"]["data"]["propagated_covariance"][0][0][1] == 1e-7
        assert len(session.workbench.list_bundles()) == 3


def test_native_inspection_is_provider_free_and_non_overwriting(campaign, monkeypatch):
    root, _, first, _, _, _, experiment, _ = campaign
    source = root / "study/workspace.json"
    before = source.read_bytes()
    monkeypatch.setattr(GeodesicReferenceWorkflow, "_step", forbidden)
    monkeypatch.setattr(GeodesicReferenceWorkflow, "create_session", forbidden)
    monkeypatch.setattr(GeodesicReferenceWorkflow, "_adapters", forbidden)
    with scientific.open_workspace(source) as session:
        assert len(scientific.inspect(session)["bundles"]) == 3
        assert study.inspect_study(session.workbench, experiment) == experiment
        view = scientific.inspect(session, bundle_id=first["bundle_id"])
        assert view
    assert before == source.read_bytes()


@pytest.mark.parametrize("case", ["units", "validity", "sample"])
def test_bad_study_preflight_does_not_probe_or_execute(campaign, monkeypatch, case):
    root, _, first, *_ = campaign
    space = ParameterSpace({"initial_heading_radian": Interval(-.1, .1, "radian")})
    limits = deepcopy(LIMITS)
    if case == "units": limits["units"]["length"] = "mm"
    request = scientific.heading_request(first["bundle_id"], space, [.1 if case == "validity" else .001],
        sample_index=127 if case == "sample" else 4, limits=limits, study_id="deliberately-invalid")
    monkeypatch.setattr(GeodesicReferenceWorkflow, "_adapters", forbidden)
    with scientific.open_workspace(root / "executed/workspace.json") as session:
        before = session.workbench.serialize()
        with pytest.raises(ValueError):
            scientific.heading_study(session, request, repositories={"csg": root})
        assert session.workbench.serialize() == before


def test_installed_cli_reads_study_and_original_context_unchanged(campaign):
    root, _, _, _, _, _, experiment, cli = campaign
    assert cli("inspect", "--workspace", root / "study/workspace.json", "--study", root / "study/study.json") == experiment
    with scientific.open_workspace(root / "seed/workspace.json") as original, scientific.open_workspace(root / "study/workspace.json") as result:
        assert original.run == result.run
        assert not original.workbench.list_bundles()
        assert not result.executions  # preserve native records without duplicate ordinary wrappers


@pytest.fixture(scope="module")
def replayed_study(campaign):
    root, _, _, _, _, _, original, cli = campaign
    result = cli("replay-study", "--workspace", root / "study/workspace.json",
        "--study", root / "study/study.json", "--binding", "csg=" + str(campaign[1]["csg"]),
        "--output-dir", root / "study-replayed")
    return result


def test_whole_study_replay_uses_original_native_occurrences(campaign, replayed_study):
    root, _, _, _, _, _, original, _ = campaign
    assert replayed_study["replay_of"] == original["study_digest"]
    assert replayed_study["authority"] == original["authority"]
    with scientific.open_workspace(root / "study-replayed/workspace.json") as session:
        for old, new in zip([original["baseline"], *original["candidates"]],
                            [replayed_study["baseline"], *replayed_study["candidates"]]):
            for field in ("bundle_id", "execution_id", "result_id", "verification_id"):
                assert old["references"][field] != new["references"][field]
            assert old["references"]["numerical_result_id"] == new["references"]["numerical_result_id"]
            native = session.workbench.get_bundle(new["references"]["bundle_id"])
            assert len(native["replay_receipts"]) == 1
            _assert_curved_oracle(native["steps"][0]["request"], native["steps"][0]["result"]["data"])
        assert len(session.workbench.list_bundles()) == 6


def test_whole_study_replay_reopens_without_provider(campaign, replayed_study, monkeypatch):
    root = campaign[0]
    monkeypatch.setattr(GeodesicReferenceWorkflow, "_adapters", forbidden)
    monkeypatch.setattr(GeodesicReferenceWorkflow, "create_session", forbidden)
    monkeypatch.setattr(GeodesicReferenceWorkflow, "replay_session", forbidden)
    with scientific.open_workspace(root / "study-replayed/workspace.json") as session:
        assert study.load_study(root / "study-replayed/study.json", session.workbench) == replayed_study
    # Its original source is not extended in place.
    with scientific.open_workspace(root / "study/workspace.json") as original:
        assert len(original.workbench.list_bundles()) == 3


def test_replay_study_corruption_is_refused_before_binding(campaign, monkeypatch, capsys):
    from ciw.scientific_cli import main
    root = campaign[0]
    bad = root / "corrupt-study.json"
    raw = json.loads((root / "study/study.json").read_bytes())
    raw["request"]["sample_index"] = 127
    from ciw.telemetry import canonical, digest
    raw["study_digest"] = digest({k: v for k, v in raw.items() if k != "study_digest"})
    bad.write_bytes(canonical(raw))
    monkeypatch.setattr(GeodesicReferenceWorkflow, "_adapters", forbidden)
    assert main(["replay-study", "--workspace", str(root / "study/workspace.json"), "--study", str(bad),
        "--binding", "csg=" + str(root / "not-a-provider"), "--output-dir", str(root / "refused-study"), "--json"]) == 1
    assert not (root / "refused-study/study.json").exists()
    assert json.loads(capsys.readouterr().err)["status"] == "refused"
