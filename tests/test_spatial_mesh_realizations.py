from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.control_plane import builtin_registry
from ciw.operations.runner import seal
from ciw.representation_morphisms import registry_from_specs
from ciw.representation_realizations import (
    adapter_registry_from_specs,
    realize,
    validate_realization,
)
from ciw.semantic_capabilities import builtin_semantic_registry
from test_geometry_mesh_contract import result as mesh_result, reseal_result
from test_representation_morphisms import morphism_specs, representation_specs, scale
from test_spatial_view import retained as retained_geographic


def spatial_representation_specs():
    return [
        {
            "representation_id": "spatial.geographic.context.v1",
            "role": "SPATIAL",
            "source_state_type": "retained-geographic-context",
            "schema_id": "ciw.geographic-context.v1",
            "quantity_semantics": "declared facility longitude and latitude coordinates",
            "unit_semantics": "degrees",
            "frame_semantics": "OGC CRS84 longitude-latitude",
            "time_semantics": "declared constant states over inclusive retained time range",
            "scale": scale("facility geographic context"),
            "uncertainty_semantics": "no covariance supplied by geographic-context V1",
            "equivalence_contract": "EXACT",
            "preserved_queries": ["facility-location", "facility-status-at-reference-time"],
            "supported_interventions": [],
            "recovery_route": None,
            "provenance_refs": [],
            "notes": "Read-only retained geographic context.",
        },
        {
            "representation_id": "geometry.mesh.edge-result.v1",
            "role": "SPATIAL",
            "source_state_type": "retained-piecewise-flat-mesh-result",
            "schema_id": "isgt.edge-geodesic-result.v1",
            "quantity_semantics": "triangular mesh and retained edge-constrained distance result",
            "unit_semantics": "mesh-declared linear units",
            "frame_semantics": "mesh-declared Cartesian frame",
            "time_semantics": "static retained geometry",
            "scale": scale("piecewise-flat mesh"),
            "uncertainty_semantics": "no stochastic uncertainty model declared",
            "equivalence_contract": "TASK_SPECIFIC",
            "preserved_queries": ["mesh-topology", "edge-path-distance", "reachability", "distance-bounds"],
            "supported_interventions": [],
            "recovery_route": None,
            "provenance_refs": [],
            "notes": "Edge-constrained mesh result; not a continuous geodesic solver.",
        },
    ]


def spatial_registry():
    concrete = builtin_registry(bind=True)
    semantic = builtin_semantic_registry(concrete)
    morphisms = registry_from_specs(
        representation_specs() + spatial_representation_specs(),
        morphism_specs(),
        semantic,
    )
    specs = [
        {
            "adapter_id": "realizer.geographic-context.v1",
            "representation_id": "spatial.geographic.context.v1",
            "validator_id": "geographic-context.v1",
            "binding": {
                "quantity_ids": ["longitude", "latitude"],
                "units": ["deg", "deg"],
                "frame": "OGC:CRS84",
                "uncertainty_required": False,
            },
            "notes": "Retained CRS84 facility context.",
        },
        {
            "adapter_id": "realizer.mesh-edge-result.v1",
            "representation_id": "geometry.mesh.edge-result.v1",
            "validator_id": "mesh-edge-result.v1",
            "binding": {
                "quantity_ids": ["x", "y", "z"],
                "units": ["m", "m", "m"],
                "frame": "declared Cartesian axes",
                "uncertainty_required": False,
            },
            "notes": "Validated piecewise-flat mesh edge result.",
        },
    ]
    adapters = adapter_registry_from_specs(morphisms, semantic, specs)
    return semantic, morphisms, adapters, specs


def test_spatial_registry_adds_two_domain_validators_without_execution():
    _, _, adapters, _ = spatial_registry()
    assert set(adapters["adapters"]) == {
        "realizer.geographic-context.v1",
        "realizer.mesh-edge-result.v1",
    }
    assert adapters["adapters"]["realizer.geographic-context.v1"]["source_schema"] == "ciw.geographic-context.v1"
    assert adapters["adapters"]["realizer.mesh-edge-result.v1"]["source_schema"] == "isgt.edge-geodesic-result.v1"
    assert adapters["claims"]["provider_execution"] is False


def test_geographic_context_realization_reuses_native_descriptor_and_frame_checks():
    semantic, morphisms, adapters, _ = spatial_registry()
    source = retained_geographic()
    value = realize(adapters, morphisms, semantic, source, {
        "realization_id": "ontario-geographic-context",
        "adapter_id": "realizer.geographic-context.v1",
        "selector": {},
        "notes": "",
    })
    view = value["realized_view"]
    assert view["quantity_ids"] == ["longitude", "latitude"]
    assert view["units"] == ["deg", "deg"]
    assert view["frame"] == "OGC:CRS84"
    assert view["state_policy"] == "declared_constant_over_inclusive_time_range"
    assert view["authority"]["coordinate_transform"] == "not_performed"
    assert value["evidence_refs"] == [source["evidence_id"]]
    assert validate_realization(value, adapters, morphisms, semantic, source) == value


def test_geographic_context_refuses_substituted_descriptor_evidence():
    semantic, morphisms, adapters, _ = spatial_registry()
    source = retained_geographic()
    source["evidence_id"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="evidence byte identity mismatch"):
        realize(adapters, morphisms, semantic, source, {
            "realization_id": "bad-geography",
            "adapter_id": "realizer.geographic-context.v1",
            "selector": {},
            "notes": "",
        })


def test_geographic_context_refuses_wrong_adapter_frame():
    semantic, morphisms, adapters, specs = spatial_registry()
    bad_specs = deepcopy(specs)
    bad_specs[0]["binding"]["frame"] = "EPSG:3857"
    bad = adapter_registry_from_specs(morphisms, semantic, bad_specs)
    with pytest.raises(ValueError, match="coordinate frame differs"):
        realize(bad, morphisms, semantic, retained_geographic(), {
            "realization_id": "wrong-frame",
            "adapter_id": "realizer.geographic-context.v1",
            "selector": {},
            "notes": "",
        })


def test_geographic_context_adapter_cannot_claim_invented_uncertainty():
    semantic, morphisms, _, specs = spatial_registry()
    bad = deepcopy(specs)
    bad[0]["binding"]["uncertainty_required"] = True
    with pytest.raises(ValueError, match="does not invent uncertainty"):
        adapter_registry_from_specs(morphisms, semantic, bad)


def test_mesh_realization_reuses_full_topology_path_and_bound_validator():
    semantic, morphisms, adapters, _ = spatial_registry()
    artifact = mesh_result()
    value = realize(adapters, morphisms, semantic, artifact, {
        "realization_id": "unit-square-edge-result",
        "adapter_id": "realizer.mesh-edge-result.v1",
        "selector": {},
        "notes": "",
    })
    view = value["realized_view"]
    assert view["quantity_ids"] == ["x", "y", "z"]
    assert view["units"] == ["m", "m", "m"]
    assert view["frame"] == "declared Cartesian axes"
    assert view["vertex_count"] == 4
    assert view["triangle_count"] == 2
    assert view["component_count"] == 1
    assert view["reachable"] is True
    assert view["target_distance"] == 2.0
    assert view["claim_scope"] == "edge_constrained_upper_bound_on_declared_piecewise_flat_mesh"
    assert value["evidence_refs"] == []
    assert value["claims"]["empirical_truth_established"] is False


def test_mesh_realization_does_not_turn_source_description_into_fake_content_evidence():
    semantic, morphisms, adapters, _ = spatial_registry()
    artifact = mesh_result()
    artifact["request"]["mesh"]["provenance"]["source"] = "human-readable declaration only"
    # Changing request content invalidates the retained request/result digests.
    with pytest.raises(ValueError):
        realize(adapters, morphisms, semantic, artifact, {
            "realization_id": "unresealed-mesh",
            "adapter_id": "realizer.mesh-edge-result.v1",
            "selector": {},
            "notes": "",
        })


def test_mesh_realization_refuses_resealed_bad_path_evidence():
    semantic, morphisms, adapters, _ = spatial_registry()
    artifact = mesh_result()
    artifact["solution"]["target_path"] = [0, 2]
    reseal_result(artifact)
    with pytest.raises(ValueError, match="leaves the declared edge graph"):
        realize(adapters, morphisms, semantic, artifact, {
            "realization_id": "bad-path",
            "adapter_id": "realizer.mesh-edge-result.v1",
            "selector": {},
            "notes": "",
        })


def test_mesh_realization_refuses_binding_frame_or_unit_mismatch():
    semantic, morphisms, _, specs = spatial_registry()
    for field, value, message in (
        ("frame", "machine-frame", "coordinate frame differs"),
        ("units", ["mm", "mm", "mm"], "coordinate units differ"),
    ):
        changed = deepcopy(specs)
        changed[1]["binding"][field] = value
        adapters = adapter_registry_from_specs(morphisms, semantic, changed)
        with pytest.raises(ValueError, match=message):
            realize(adapters, morphisms, semantic, mesh_result(), {
                "realization_id": "mesh-binding-mismatch",
                "adapter_id": "realizer.mesh-edge-result.v1",
                "selector": {},
                "notes": "",
            })


def test_mesh_adapter_cannot_claim_invented_uncertainty():
    semantic, morphisms, _, specs = spatial_registry()
    bad = deepcopy(specs)
    bad[1]["binding"]["uncertainty_required"] = True
    with pytest.raises(ValueError, match="does not invent uncertainty"):
        adapter_registry_from_specs(morphisms, semantic, bad)


def test_resealed_fake_spatial_realization_is_recomputed():
    semantic, morphisms, adapters, _ = spatial_registry()
    source = retained_geographic()
    value = realize(adapters, morphisms, semantic, source, {
        "realization_id": "geography",
        "adapter_id": "realizer.geographic-context.v1",
        "selector": {},
        "notes": "",
    })
    value["realized_view"]["frame"] = "invented-frame"
    with pytest.raises(ValueError, match="exact family validation"):
        validate_realization(seal(value), adapters, morphisms, semantic, source)


def test_cli_realizes_geographic_context_through_existing_realization_surface(tmp_path):
    semantic, morphisms, adapters, specs = spatial_registry()
    source = retained_geographic()
    for name, value in (
        ("morphisms", morphisms),
        ("adapter-spec", {"adapters": specs}),
        ("source", source),
        ("realization-spec", {
            "realization_id": "geography-cli",
            "adapter_id": "realizer.geographic-context.v1",
            "selector": {},
            "notes": "",
        }),
    ):
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    command = [sys.executable, "-m", "ciw.net", "realization"]
    registry_path = tmp_path / "adapters.json"
    realization_path = tmp_path / "realization.json"
    subprocess.run(command + [
        "create-registry", str(tmp_path / "morphisms.json"),
        str(tmp_path / "adapter-spec.json"), "--output", str(registry_path)], check=True)
    subprocess.run(command + [
        "realize", str(registry_path), str(tmp_path / "morphisms.json"),
        str(tmp_path / "source.json"), str(tmp_path / "realization-spec.json"),
        "--output", str(realization_path)], check=True)
    assert json.loads(registry_path.read_text())["record_digest"] == adapters["record_digest"]
    retained = json.loads(realization_path.read_text())
    assert retained["representation_id"] == "spatial.geographic.context.v1"
    assert retained["realized_view"]["frame"] == "OGC:CRS84"
