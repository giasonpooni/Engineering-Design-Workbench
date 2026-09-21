import pytest
from types import MappingProxyType
pytest.importorskip("state_estimation_testbed.contracts")
from fdir.exchange import export_result


def arguments():
    return dict(operation_id="operation.v1", execution_ref="execution:one",
        source_revision="0" * 40, created_at="2026-09-20T00:00:00Z",
        input_refs=["evidence:one"], input_payload={"x": 1.0},
        numerical_result={"score": 1.0}, applicability="Synthetic computational diagnostic",
        components=[{"name": "score", "unit": "1", "value": 1.0}],
        covariance={"status": "not_applicable", "variables": ["score"],
            "units": ["1"], "frame": {"id": "diagnostic", "semantics": "arbitrary_model_space"},
            "source_refs": ["evidence:one"], "calibration_refs": [],
            "method": "No uncertainty claimed for this diagnostic"})


@pytest.mark.parametrize("alias", ["execution:one", "operation.v1"])
def test_covariance_sources_cannot_alias_execution_or_operation(alias):
    kwargs = arguments()
    kwargs["covariance"]["source_refs"] = [alias]
    with pytest.raises(ValueError, match="distinct"):
        export_result(**kwargs)


def test_nested_read_only_mapping_is_snapshotted():
    source = {"x": [1.0]}
    kwargs = arguments()
    kwargs["input_payload"] = MappingProxyType({"nested": MappingProxyType(source)})
    artifact = export_result(**kwargs)
    source["x"][0] = 99.0
    assert artifact["computation"]["inputs"] == {"nested": {"x": [1.0]}}
