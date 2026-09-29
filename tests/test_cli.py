import json

import pytest

from tbrt.cli import main, reconcile_payload


def payload():
    return {
        "source_frame": {
            "clock_id": "synthetic-sensor/clock-1",
            "time_scale": "device-monotonic",
            "unit": "s",
        },
        "reference_frame": {
            "clock_id": "synthetic-reference/clock-1",
            "time_scale": "reference-monotonic",
            "unit": "s",
        },
        "observation": {
            "device_time": 1003.0,
            "evidence_id": "synthetic-observation-0001",
        },
        "model": {
            "model_id": "synthetic-affine-map-0001",
            "device_origin": 1000.0,
            "reference_origin": 200.0,
            "skew": 1.00002,
            "offset": 0.0003,
            "valid_device_interval": [1000.0, 1010.0],
            "synchronization_evidence_ids": ["synthetic-sync-exchange-0001"],
        },
        "joint_covariance": [
            [1e-6, 0.0, 0.0],
            [0.0, 1e-10, 0.0],
            [0.0, 0.0, 4e-6],
        ],
    }


def test_reconcile_payload_exposes_product_boundary():
    result = reconcile_payload(payload())
    assert result["operation_id"] == "tbrt.affine-clock-reconcile.v1"
    assert result["reference_origin"] == 200.0
    assert result["event_time"] == pytest.approx(203.00036)
    assert result["standard_uncertainty"] > 0


def test_cli_emits_json(tmp_path, capsys):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(payload()), encoding="utf-8")
    assert main([str(source), "--compact"]) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["model"]["model_id"] == "synthetic-affine-map-0001"


def test_cli_fails_closed_on_out_of_domain_timestamp(tmp_path, capsys):
    invalid = payload()
    invalid["observation"]["device_time"] = 999.0
    source = tmp_path / "input.json"
    source.write_text(json.dumps(invalid), encoding="utf-8")
    assert main([str(source)]) == 2
    assert "outside model applicability" in capsys.readouterr().err
