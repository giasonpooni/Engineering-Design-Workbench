"""Explicit polymer profiles reuse NET typed graphs and MCP transport."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ciw.agent_api import encode, parse
from ciw.agent_mcp import Server, VERSIONS, demo_config, from_profile, polymer_config
from ciw.control_plane import plan_graph
from ciw.net import main as net_main
from ciw.operations.registry import default_registry
from ciw.polymer_contract import AUTHORITY
from ciw.polymer_workflow import ASSESS, COPILOT, SIMULATE, VERIFY, OPERATIONS, capability_registry


def _workspace(path):
    return parse(path.read_bytes())


@pytest.mark.parametrize("process", ["injection_molding", "extrusion_blow_molding"])
def test_polymer_profile_executes_complete_typed_graph_and_fresh_replay(tmp_path, process):
    path = polymer_config(tmp_path / "profile", process)
    original_inputs = {name: (path.parent / name).read_bytes()
                       for name in ("request.json", "source.json", "experiment.json", "profile.json")}
    graph = parse(original_inputs["experiment.json"])
    assert plan_graph(graph, capability_registry()) == ["assessment", "copilot", "simulation", "verification"]
    host = from_profile(path, instrument="polymer")
    catalog = host.call("net_capabilities", {})
    assert set(catalog["catalog"]["operations"]) == OPERATIONS
    assert catalog["catalog"]["authorizes_execution"] is False
    assert all(item["bound"] and item["agent_execution_enabled"]
               for item in catalog["catalog"]["operations"].values())
    first = host.call("net_execute", {"source": "source", "graph": "baseline", "attempt": "first"})
    assert first["status"] == "completed", first
    retained = _workspace(path.parent / "agent-output" / "first" / "workspace.json")
    assert len(retained["results"]) == len(retained["executions"]) == 4
    results = {item["operation_id"]: item for item in retained["results"]}
    assert results[ASSESS]["data"]["process"] == process
    assert results[VERIFY]["data"]["report"]["status"] == "PASS"
    assert all(item["data"]["authority"] == AUTHORITY for item in results.values())
    for operation in (COPILOT, VERIFY):
        assert results[operation]["parameters"]["assessment"] == results[ASSESS]
        assert results[operation]["data"]["assessment_result_id"] == results[ASSESS]["result_id"]
    retried = host.call("net_execute", {"source": "source", "graph": "baseline", "attempt": "first"})
    assert retried["reused_response"] is True
    assert retried["execution_ids"] == first["execution_ids"]
    replay = host.call("net_replay", {"original_attempt": "first", "new_attempt": "second"})
    assert replay["status"] == "completed", replay
    assert set(replay["execution_ids"]).isdisjoint(first["execution_ids"])
    assert set(replay["result_ids"]).isdisjoint(first["result_ids"])
    replayed = _workspace(path.parent / "agent-output" / "second" / "workspace.json")
    second_results = {item["operation_id"]: item for item in replayed["results"]}
    assert replayed["run"]["evidence_id"] == retained["run"]["evidence_id"]
    assert second_results[ASSESS]["data"] == results[ASSESS]["data"]
    assert second_results[VERIFY]["data"]["verification_id"] != results[VERIFY]["data"]["verification_id"]
    assert original_inputs == {name: (path.parent / name).read_bytes() for name in original_inputs}


def test_polymer_profile_requires_explicit_selector_and_does_not_change_builtin_profile(tmp_path):
    polymer = polymer_config(tmp_path / "polymer")
    with pytest.raises(ValueError, match="not advertised"):
        from_profile(polymer)
    builtin = from_profile(demo_config(tmp_path / "builtin"))
    assert set(builtin.capabilities()["catalog"]["operations"]) == {"statistics.v1", "spectrum.periodogram.v1"}
    assert not OPERATIONS.intersection(item["operation_id"] for item in default_registry().describe())
    value = parse(polymer.read_bytes())
    value["instrument"] = "polymer"
    polymer.write_bytes(encode(value))
    with pytest.raises(ValueError, match="contract fields"):
        from_profile(polymer, instrument="polymer")


@pytest.mark.parametrize("instrument", ["module.provider", "", "Polymer", None])
def test_profile_cannot_select_arbitrary_provider_import(tmp_path, instrument):
    with pytest.raises(ValueError, match="fixed operator-selected instrument"):
        from_profile(tmp_path / "not-read.json", instrument=instrument)


@pytest.mark.parametrize("allow", [[], [ASSESS]])
def test_polymer_advertisement_does_not_grant_other_graph_operations(tmp_path, monkeypatch, allow):
    from ciw import polymer_workflow

    profile = polymer_config(tmp_path / "profile")
    value = parse(profile.read_bytes())
    value["allow_operations"] = allow
    profile.write_bytes(encode(value))

    def forbidden(*args, **kwargs):
        pytest.fail("A missing grant dispatched a polymer calculation")

    for name in ("_assess", "_copilot", "_simulate", "_verify"):
        monkeypatch.setattr(polymer_workflow, name, forbidden)
    host = from_profile(profile, instrument="polymer")
    catalog = host.capabilities()["catalog"]["operations"]
    assert set(catalog) == OPERATIONS
    assert all(item["bound"] == bool(allow) for item in catalog.values())
    assert {operation for operation, item in catalog.items() if item["agent_execution_enabled"]} == set(allow)
    with pytest.raises(ValueError, match="not enabled"):
        host.call("net_execute", {"source": "source", "graph": "baseline", "attempt": "denied"})
    assert host.capabilities()["execution_budget"]["used"] == 0
    assert list((profile.parent / "agent-output").iterdir()) == []


def test_dependent_graph_requires_an_exact_typed_assessment_edge(tmp_path):
    profile = polymer_config(tmp_path / "profile")
    graph = parse((profile.parent / "experiment.json").read_bytes())
    registry = capability_registry()
    candidate = deepcopy(graph)
    candidate["nodes"][1]["inputs"] = {}
    from ciw.operations.runner import seal
    seal(candidate)
    with pytest.raises(ValueError, match="contract fields"):
        plan_graph(candidate, registry)
    candidate = deepcopy(graph)
    candidate["nodes"][1]["inputs"]["assessment"]["port"] = "imagined_assessment"
    seal(candidate)
    with pytest.raises(ValueError, match="port schema"):
        plan_graph(candidate, registry)


def test_polymer_mcp_stdio_launch_handles_full_graph_and_retry(tmp_path):
    profile = polymer_config(tmp_path / "profile")
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": VERSIONS[0], "capabilities": {},
            "clientInfo": {"name": "polymer-contract-test", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "net_capabilities", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "net_execute", "arguments": {"source": "source", "graph": "baseline", "attempt": "first"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "net_execute", "arguments": {"source": "source", "graph": "baseline", "attempt": "first"}}},
    ]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run([sys.executable, "-m", "ciw.agent_mcp", "serve", "--instrument", "polymer",
                             "--profile", str(profile)],
        input=b"\n".join(encode(message) for message in messages)+b"\n",
        capture_output=True, timeout=30, env=environment)
    assert result.returncode == 0, result.stderr.decode()
    responses = {message["id"]: message for message in map(json.loads, result.stdout.splitlines())}
    assert set(responses) == {1, 2, 3, 4}
    assert set(responses[2]["result"]["structuredContent"]["catalog"]["operations"]) == OPERATIONS
    first = responses[3]["result"]
    assert first["isError"] is False
    assert first["structuredContent"]["status"] == "completed"
    assert len(first["structuredContent"]["execution_ids"]) == 4
    assert responses[4]["result"]["structuredContent"]["reused_response"] is True
    assert (responses[4]["result"]["structuredContent"]["execution_ids"]
            == first["structuredContent"]["execution_ids"])
    retained = _workspace(profile.parent / "agent-output" / "first" / "workspace.json")
    assert len(retained["results"]) == len(retained["executions"]) == 4


def test_net_help_advertises_polymer_without_execution(capsys):
    with pytest.raises(SystemExit) as exc:
        net_main(["--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "polymer" in output and "molding cycles" in output


def test_polymer_profile_creation_never_executes_and_is_create_only(tmp_path, monkeypatch):
    from ciw import polymer_workflow

    def forbidden(*args, **kwargs):
        pytest.fail("Profile generation executed a provider")

    for name in ("_assess", "_copilot", "_simulate", "_verify", "runtime_identity"):
        monkeypatch.setattr(polymer_workflow, name, forbidden)
    root = tmp_path / "profile"
    path = polymer_config(root)
    assert path.is_file()
    assert not (root / "agent-output").exists()
    before = {item.name: item.read_bytes() for item in root.iterdir()}
    with pytest.raises(FileExistsError):
        polymer_config(root)
    assert before == {item.name: item.read_bytes() for item in root.iterdir()}


def test_polymer_profile_cli_creates_selected_process(tmp_path, capsys):
    from ciw.agent_mcp import main

    root = tmp_path / "profile"
    assert main(["polymer-config", "--process", "extrusion_blow_molding", "--output-dir", str(root)]) == 0
    assert Path(capsys.readouterr().out.strip()) == root / "profile.json"
    assert parse((root / "request.json").read_bytes())["process"] == "extrusion_blow_molding"
