from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.board_morphisms import bind_board, compile_bound_board, validate_binding, validate_bound_compilation
from ciw.control_plane import run_graph
from ciw.core.identities import content_identity
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.representation_morphisms import registry_from_specs
from ciw.session import Session
from ciw.system_board import board_from_spec, compile_board
from test_representation_morphisms import registry, representation_specs, morphism_specs
from test_system_board import board_spec


@pytest.fixture
def specimen():
    concrete, semantic, morphisms = registry()
    spec = board_spec()
    spec["nodes"] = [spec["nodes"][1]]
    spec["edges"] = []
    spec["groups"] = []
    board = board_from_spec(spec)
    assignment = {"binding_id": "spectrum-signature", "node_morphisms": {"spectrum": "signal.periodogram.transform.v1"}}
    return concrete, semantic, morphisms, board, assignment


def test_binding_retains_exact_scientific_refs_and_old_lowering(specimen):
    _, semantic, registry, board, spec = specimen
    binding = bind_board(board, registry, semantic, spec)
    value = compile_bound_board(board, binding, registry, semantic)
    assert value["board_compilation"] == compile_board(board, semantic)
    assert value["registry_ref"] == registry["record_digest"]
    assert value["binding_ref"] == binding["record_digest"]
    assert not value["claims"]["provider_execution"]
    assert not value["claims"]["scientific_payload_validated"]
    assert validate_bound_compilation(value, board, binding, registry, semantic) == value


@pytest.mark.parametrize("assignments", [{}, {"spectrum": "signal.periodogram.transform.v1", "missing": "signal.periodogram.transform.v1"}])
def test_partial_or_extra_coverage_refuses(specimen, assignments):
    _, semantic, registry, board, spec = specimen
    spec["node_morphisms"] = assignments
    with pytest.raises(ValueError, match="every and only"):
        bind_board(board, registry, semantic, spec)


def test_capability_mismatch_refuses(specimen):
    _, semantic, registry, board, spec = specimen
    board["nodes"][0]["semantic_capability"] = "analysis.statistics.v1"
    board = seal(board)
    with pytest.raises(ValueError, match="capabilities differ"):
        bind_board(board, registry, semantic, spec)


def test_undeclared_parameter_refuses(specimen):
    _, semantic, registry, board, spec = specimen
    board["nodes"][0]["parameters"]["undeclared"] = deepcopy(board["nodes"][0]["parameters"]["channel"])
    with pytest.raises(ValueError, match="parameter is not declared"):
        bind_board(seal(board), registry, semantic, spec)


def test_changed_board_and_resealed_metadata_refuse(specimen):
    _, semantic, registry, board, spec = specimen
    binding = bind_board(board, registry, semantic, spec)
    changed = deepcopy(board)
    changed["nodes"][0]["parameters"]["channel"]["value"] = "v"
    with pytest.raises(ValueError, match="exact Board"):
        validate_binding(binding, seal(changed), registry, semantic)
    binding["bound_nodes"]["spectrum"]["parameter_values"]["channel"] = "v"
    with pytest.raises(ValueError, match="derived signatures"):
        validate_binding(seal(binding), board, registry, semantic)


def test_changed_registry_and_compilation_refuse(specimen):
    _, semantic, registry, board, spec = specimen
    binding = bind_board(board, registry, semantic, spec)
    reps = representation_specs()
    reps[0]["notes"] += " altered"
    changed = registry_from_specs(reps, morphism_specs(), semantic)
    with pytest.raises(ValueError, match="registry"):
        validate_binding(binding, board, changed, semantic)
    value = compile_bound_board(board, binding, registry, semantic)
    value["claims"]["preconditions_discharged"] = True
    with pytest.raises(ValueError, match="recomputed lowering"):
        validate_bound_compilation(seal(value), board, binding, registry, semantic)


def test_dataflow_requires_same_scientific_representation_but_dependency_does_not(specimen):
    _, semantic, registry, board, spec = specimen
    other = deepcopy(board["nodes"][0])
    other["node_id"] = "next"
    other["sockets"]["inputs"] = deepcopy(other["sockets"]["outputs"])
    board["nodes"].append(other)
    board["edges"] = [{"edge_id": "flow", "kind": "DATAFLOW", "source_node_id": "spectrum",
                       "target_node_id": "next", "source_socket": "result", "target_socket": "result",
                       "relation": "declared-flow", "metadata": {}}]
    spec["node_morphisms"]["next"] = "signal.periodogram.transform.v1"
    with pytest.raises(ValueError, match="codomain/domain mismatch"):
        bind_board(seal(board), registry, semantic, spec)
    board["edges"][0].update(kind="DEPENDENCY", source_socket=None, target_socket=None)
    # Dependency relates execution, without asserting that the spectrum is a time series.
    assert bind_board(seal(board), registry, semantic, spec)["checked_dataflow_edges"] == []


def test_bound_board_runs_same_real_periodogram_and_retains_source(specimen, tmp_path):
    concrete, semantic, registry, board, spec = specimen
    original = deepcopy(board)
    binding = bind_board(board, registry, semantic, spec)
    bound = compile_bound_board(board, binding, registry, semantic)
    ordinary = compile_board(board, semantic)
    source = make_demo_run()
    data, runtimes = [], []
    for name, compiled in (("bound", bound["board_compilation"]), ("ordinary", ordinary)):
        session = Session(source, tmp_path / name, operations=concrete.operations)
        run = run_graph(session, compiled["semantic_compilation"]["experiment"], concrete)
        assert run["status"] == "completed"
        result = run["nodes"]["spectrum"]["result"]
        data.append(result["data"])
        execution = run["nodes"]["spectrum"]["execution"]
        runtimes.append(execution["runtime"])
        assert execution["evidence_id"] == source["evidence_id"]
    assert data[0] == data[1] and runtimes[0] == runtimes[1]
    assert data[0]["unit"] == "(m)^2/Hz"
    assert data[0]["sample_count"] == source["metadata"]["sample_count"]
    assert content_identity(board) == content_identity(original)


def test_cli_binding_and_compilation(specimen, tmp_path):
    _, _, registry, board, spec = specimen
    for name, value in (("registry", registry), ("board", board), ("spec", spec)):
        (tmp_path / (name + ".json")).write_text(json.dumps(value))
    command = [sys.executable, "-m", "ciw.net", "board"]
    binding, compiled = tmp_path / "binding.json", tmp_path / "compiled.json"
    subprocess.run(command + ["bind-morphisms", str(tmp_path / "board.json"), str(tmp_path / "registry.json"),
                              str(tmp_path / "spec.json"), "--output", str(binding)], check=True)
    subprocess.run(command + ["compile-bound", str(tmp_path / "board.json"), str(tmp_path / "registry.json"),
                              str(binding), "--output", str(compiled)], check=True)
    assert json.loads(compiled.read_text())["schema"] == "ciw.board-morphism-compilation.v1"
