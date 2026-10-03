from copy import deepcopy
import json

import pytest

from ciw.adapters.protocol import InstrumentManifest
from ciw.agent_mcp import Server
from ciw.control_plane import CapabilityRegistry, Port, builtin_registry
from ciw.operations.registry import Operation
from ciw.semantic_capabilities import (
    ComparisonWitness,
    EngineLowering,
    SemanticHost,
    SemanticMorphism,
    SemanticRegistry,
    builtin_semantic_registry,
    compile_graph,
)
from ciw.semantic_cli import demo_graph


def runtime(name):
    return {"provider": name, "version": "1"}


def bind(registry, operation_id, identity):
    registry.bind(Operation(operation_id, "analysis", lambda run, parameters: {},
                            lambda: deepcopy(identity)))


def synthetic_registry():
    concrete = CapabilityRegistry()
    manifest = InstrumentManifest(
        instrument_id="test.semantic", version="1", role="operation_provider",
        inputs=("run.v1",), outputs=("ciw.operation-result.v1",),
        units={}, frames=(), sampling={"mode": "explicit"},
        normalization={"mode": "none"},
        supported_operations=("produce.v1", "consume.v1", "view.v1", "produce_alt.v1"),
        determinism={"claim": "fixture"}, tolerance_policy={"policy": "fixture"},
        calibration_requirements={"status": "not_applicable"})
    identity = runtime("test.semantic")
    artifact = Port("ciw.artifact.v1", unit="m", frame="fixture").to_dict()
    result = Port("ciw.operation-result.v1").to_dict()
    concrete.advertise(
        manifest, runtime=identity,
        capabilities={
            "produce.v1": ["fixture.produce"],
            "produce_alt.v1": ["fixture.produce"],
            "consume.v1": ["fixture.consume"],
            "view.v1": ["fixture.view"],
        },
        inputs={"consume.v1": {"artifact": artifact}},
        outputs={
            "produce.v1": {"artifact": {"type": artifact, "path": ["data", "artifact"]}},
            "produce_alt.v1": {"artifact": {"type": artifact, "path": ["data", "artifact"]}},
            "consume.v1": {"result": {"type": result, "path": []}},
            "view.v1": {"result": {"type": result, "path": []}},
        })
    for op in manifest.supported_operations:
        bind(concrete, op, identity)

    semantic = SemanticRegistry(concrete)
    semantic.declare(SemanticMorphism(
        "geometry.compile.v1", "compute", {},
        {"artifact": artifact}, effects=("write:candidate-artifact",)))
    semantic.declare(SemanticMorphism(
        "geometry.inspect.v1", "representation", {},
        {"result": result}, effects=("read:candidate-artifact",)))
    semantic.declare(SemanticMorphism(
        "artifact.consume.v1", "compute", {"artifact": artifact},
        {"result": result}, effects=("read:candidate-artifact",)))
    semantic.implement(EngineLowering(
        "geometry.compile.v1", "produce.v1", "cpp.reference", "cpp",
        "native_edge", "headless", ("cpu",), 20))
    semantic.implement(EngineLowering(
        "geometry.compile.v1", "produce_alt.v1", "rust.alternative", "rust",
        "systems", "headless", ("cpu",), 30))
    semantic.implement(EngineLowering(
        "geometry.inspect.v1", "view.v1", "pyvista.fixture", "python",
        "orchestration", "interactive", ("cpu",), 10))
    semantic.implement(EngineLowering(
        "artifact.consume.v1", "consume.v1", "python.consumer", "python",
        "orchestration", "headless", ("cpu",), 10))
    return concrete, semantic, artifact, result


def graph():
    return {
        "schema": "ciw.semantic-work-graph.v1",
        "graph_id": "typed-geometry",
        "mandate": "Compile and consume a typed geometry artifact.",
        "model_id": "fixture-model",
        "nodes": [
            {"node_id": "compile", "capability": "geometry.compile.v1",
             "parameters": {}, "inputs": {}, "depends_on": [],
             "resources": ["cpu"], "acceptance": {"required": True}, "inspection": False},
            {"node_id": "consume", "capability": "artifact.consume.v1",
             "parameters": {}, "inputs": {"artifact": {"node_id": "compile", "port": "artifact"}},
             "depends_on": [], "resources": ["cpu"],
             "acceptance": {"required": True}, "inspection": False},
        ],
    }


def rpc(server, request_id, method, params):
    return server.handle(json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    ).encode())


def initialized_server(host):
    server = Server(host)
    response = rpc(server, 1, "initialize",
                   {"protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": {"name": "semantic-test", "version": "1"}})
    assert response["result"]["protocolVersion"] == "2025-11-25"
    assert server.handle(b'{"jsonrpc":"2.0","method":"notifications/initialized"}') is None
    return server


def test_builtin_semantic_demo_lowers_to_original_experiment():
    concrete = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(concrete)
    receipt = compile_graph(demo_graph(), semantic)
    assert receipt["schema"] == "ciw.semantic-compilation.v1"
    assert receipt["experiment"]["schema"] == "ciw.experiment.v1"
    assert [node["operation_id"] for node in receipt["experiment"]["nodes"]] == [
        "statistics.v1", "spectrum.periodogram.v1"]
    assert receipt["authorizes_execution"] is False
    assert all(row["execution_mode"] == "headless"
               for row in receipt["resolutions"].values())


def test_agent_names_capabilities_not_engines():
    _, semantic, _, _ = synthetic_registry()
    value = graph()
    value["nodes"][0]["engine_id"] = "cpp.reference"
    with pytest.raises(ValueError, match="Unexpected|missing"):
        compile_graph(value, semantic)


def test_operator_priority_selects_headless_engine():
    _, semantic, _, _ = synthetic_registry()
    receipt = compile_graph(graph(), semantic)
    resolution = receipt["resolutions"]["compile"]
    assert resolution["engine_id"] == "cpp.reference"
    assert resolution["runtime_family"] == "cpp"
    assert resolution["execution_profile"] == "native_edge"
    assert resolution["agent_selected_engine"] is False


def test_typed_connection_compiles_and_preserves_edge():
    _, semantic, _, _ = synthetic_registry()
    receipt = compile_graph(graph(), semantic)
    consumer = receipt["experiment"]["nodes"][1]
    assert consumer["inputs"]["artifact"] == {"node_id": "compile", "port": "artifact"}


def test_semantic_lowering_must_preserve_port_objects():
    concrete, _, _, result = synthetic_registry()
    semantic = SemanticRegistry(concrete)
    semantic.declare(SemanticMorphism(
        "bad.mapping.v1", "compute", {}, {"result": result}))
    with pytest.raises(ValueError, match="preserve"):
        semantic.implement(EngineLowering(
            "bad.mapping.v1", "produce.v1", "bad", "cpp",
            "native_edge", "headless"))


def test_semantic_edge_refuses_unit_or_frame_mismatch():
    _, semantic, _, _ = synthetic_registry()
    value = graph()
    semantic._morphisms["artifact.consume.v1"]["inputs"]["artifact"]["unit"] = "kg"
    with pytest.raises(ValueError, match="port mismatch"):
        compile_graph(value, semantic)


def test_representation_is_explicit_and_demand_driven():
    _, semantic, _, _ = synthetic_registry()
    with pytest.raises(ValueError, match="inspection"):
        semantic.resolve("geometry.inspect.v1", required_resources=["cpu"],
                         inspection_requested=False)
    resolved = semantic.resolve("geometry.inspect.v1", required_resources=["cpu"],
                                inspection_requested=True)
    assert resolved["execution_mode"] == "interactive"
    assert resolved["inspection_requested"] is True


def test_compute_cannot_fall_back_to_interactive_lowering():
    concrete, _, _, result = synthetic_registry()
    semantic = SemanticRegistry(concrete)
    semantic.declare(SemanticMorphism("compute.only.v1", "compute", {}, {"result": result}))
    semantic.implement(EngineLowering(
        "compute.only.v1", "view.v1", "interactive-only", "python",
        "orchestration", "interactive", ("cpu",)))
    with pytest.raises(ValueError, match="No explicitly bound"):
        semantic.resolve("compute.only.v1", required_resources=["cpu"])


def test_unbound_concrete_operation_cannot_resolve():
    concrete = builtin_registry(bind=False)
    semantic = builtin_semantic_registry(concrete)
    with pytest.raises(ValueError, match="No explicitly bound"):
        semantic.resolve("analysis.statistics.v1", required_resources=["cpu"])


def test_resource_requirements_are_operator_checked():
    _, semantic, _, _ = synthetic_registry()
    with pytest.raises(ValueError, match="No explicitly bound"):
        semantic.resolve("geometry.compile.v1", required_resources=["cuda"])


@pytest.mark.parametrize("profile", [
    "orchestration", "scientific", "coordination", "systems",
    "native_edge", "hardware", "external",
])
def test_execution_profiles_are_metadata_not_language_restrictions(profile):
    concrete = builtin_registry(bind=True)
    semantic = SemanticRegistry(concrete)
    result = Port("ciw.operation-result.v1").to_dict()
    semantic.declare(SemanticMorphism("analysis.generic.v1", "compute", {}, {"result": result}))
    semantic.implement(EngineLowering(
        "analysis.generic.v1", "statistics.v1", "runtime." + profile,
        "any-runtime-family", profile, "headless"))
    assert semantic.resolve("analysis.generic.v1")["execution_profile"] == profile


def test_unknown_execution_profile_refuses():
    with pytest.raises(ValueError, match="profile"):
        EngineLowering("analysis.x.v1", "statistics.v1", "engine", "python",
                       "magic", "headless").to_dict()


def test_finite_cross_engine_comparison_is_not_called_naturality():
    _, semantic, _, _ = synthetic_registry()
    semantic.retain_witness(ComparisonWitness(
        "geometry.compile.v1", "cpp.reference", "rust.alternative",
        "strict-numeric", "evidence:comparison-001"))
    row = semantic.catalog()["comparison_witnesses"][0]
    assert row["claim"] == "finite_comparison_witness_not_naturality_proof"


def test_catalog_is_descriptive_not_execution_authority():
    _, semantic, _, _ = synthetic_registry()
    catalog = semantic.catalog()
    assert catalog["authorizes_execution"] is False
    assert catalog["headless_default"] is True
    assert catalog["visualization_policy"] == "demand_driven"


@pytest.mark.parametrize("fault", ["cycle", "missing", "duplicate", "wrong_schema"])
def test_invalid_semantic_graph_refuses_before_lowering(fault):
    _, semantic, _, _ = synthetic_registry()
    value = graph()
    if fault == "cycle":
        value["nodes"][0]["depends_on"] = ["consume"]
    elif fault == "missing":
        value["nodes"][0]["depends_on"] = ["absent"]
    elif fault == "duplicate":
        value["nodes"][1]["node_id"] = "compile"
    else:
        value["schema"] = "other"
    with pytest.raises(ValueError):
        compile_graph(value, semantic)


def test_mcp_semantic_host_exposes_only_catalog_and_compile():
    _, semantic, _, _ = synthetic_registry()
    server = initialized_server(SemanticHost(semantic))
    listed = rpc(server, 2, "tools/list", {})
    names = {row["name"] for row in listed["result"]["tools"]}
    assert names == {"net_semantic_catalog", "net_semantic_compile"}
    assert not any(token in name for name in names
                   for token in ("execute", "shell", "release", "render"))


def test_mcp_compile_returns_data_only_lowering():
    _, semantic, _, _ = synthetic_registry()
    server = initialized_server(SemanticHost(semantic))
    response = rpc(server, 2, "tools/call",
                   {"name": "net_semantic_compile", "arguments": {"graph": graph()}})
    result = response["result"]["structuredContent"]
    assert result["schema"] == "ciw.semantic-compilation.v1"
    assert result["authorizes_execution"] is False
    assert result["resolutions"]["compile"]["agent_selected_engine"] is False


def test_mcp_unknown_engine_selection_field_refuses():
    _, semantic, _, _ = synthetic_registry()
    server = initialized_server(SemanticHost(semantic))
    value = graph()
    value["nodes"][0]["engine"] = "cpp.reference"
    response = rpc(server, 2, "tools/call",
                   {"name": "net_semantic_compile", "arguments": {"graph": value}})
    assert response["result"]["isError"] is True
    assert response["result"]["structuredContent"]["status"] == "refused"
