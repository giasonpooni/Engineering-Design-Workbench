"""Host conformance: integrity under failure, not a live display."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from instrument_chain.bench import Session, run_bidirectional_pass
from instrument_chain.calibration import apply_calibration
from instrument_chain.manifest import SCHEMA, loads, load_assembly
from instrument_chain.observation import AcquisitionStatus, CalibrationStatus, acquire_or_unavailable
from instrument_chain.receiver import receive, replay
from instrument_chain.transport import Outbox, deliver

DECL = Path(__file__).resolve().parents[1] / "declarations" / "assembly_v1.toml"


@pytest.fixture
def assembly():
    return load_assembly(DECL)


def test_declaration_refuses_unknown_key():
    raw = DECL.read_text()
    with pytest.raises(ValueError, match="unknown"):
        loads(raw + "\nextra = 1\n")


def test_declaration_refuses_wrong_schema():
    raw = DECL.read_text().replace(SCHEMA, "rci-assembly-v0")
    with pytest.raises(ValueError, match="schema"):
        loads(raw)


def test_linear_conversion_is_declared(assembly):
    assert apply_calibration(1000.0, assembly.calibration) == pytest.approx(10.0)


def test_silent_source_must_declare_sigma(assembly):
    assert assembly.calibration.sigma == pytest.approx(0.02)
    assert assembly.calibration.sigma_unit == "mm"
    assert "silent" in assembly.calibration.sigma_reason.lower()


def test_missing_sigma_is_refused():
    raw = DECL.read_text().replace("sigma = 0.02\n", "")
    with pytest.raises(ValueError, match="sigma"):
        loads(raw)


def test_disconnect_does_not_manufacture_zero(assembly):
    session = Session(assembly, "sess-disconnect")
    session.connected = False
    obs = session.step(raw=100.0)
    assert obs.raw is None
    assert obs.indicated is None
    assert obs.quality.acquisition is AcquisitionStatus.UNAVAILABLE
    assert obs.quality.calibration is CalibrationStatus.NONE


def test_overrange_is_not_a_good_reading(assembly):
    obs = acquire_or_unavailable(
        assembly=assembly,
        session_id="s",
        sequence=1,
        device_ticks=1,
        raw=10_000.0,
    )
    assert obs.indicated is None
    assert obs.quality.acquisition is AcquisitionStatus.OVERRANGE
    assert obs.quality.calibration is CalibrationStatus.UNSUPPORTED_RANGE


def test_retransmit_keeps_observation_identity(assembly, tmp_path):
    log = tmp_path / "log.jsonl"
    session = Session(assembly, "sess-retry", outbox=Outbox())
    obs = session.step(200.0)
    first = deliver(session.outbox, obs)
    receive(log, obs, first)
    second = deliver(session.outbox, obs, retry=True)
    receive(log, obs, second)
    rows = replay(log)
    assert len(rows) == 1
    assert rows[0]["observation_id"] == obs.observation_id
    assert first.observation_id == second.observation_id
    assert first.packet_id != second.packet_id
    assert second.attempt == 2
    assert len(rows[0]["delivery_history"]) == 2


def test_restart_starts_new_session_without_reusing_ids(assembly):
    a = Session(assembly, "boot-1")
    b = Session(assembly, "boot-2")
    oa = a.step(100.0)
    ob = b.step(100.0)
    assert oa.session_id != ob.session_id
    assert oa.observation_id != ob.observation_id
    assert oa.sequence == ob.sequence == 1


def test_calibration_change_does_not_rewrite_history(assembly, tmp_path):
    log = tmp_path / "log.jsonl"
    session = Session(assembly, "sess-cal", outbox=Outbox())
    old = session.step(1000.0)
    receive(log, old, deliver(session.outbox, old))
    new_cal = replace(assembly.calibration, id="linear-v2", theta=(0.012, 0.0))
    session = session.with_calibration(new_cal)
    new = session.step(1000.0)
    receive(log, new, deliver(session.outbox, new))
    rows = replay(log)
    assert rows[0]["calibration_id"] == "linear-v1"
    assert rows[0]["indicated"] == pytest.approx(10.0)
    assert rows[1]["calibration_id"] == "linear-v2"
    assert rows[1]["indicated"] == pytest.approx(12.0)
    assert rows[0]["observation_id"] != rows[1]["observation_id"]


def test_units_change_preserves_physical_result(assembly):
    mm = apply_calibration(1000.0, assembly.calibration)
    um_cal = replace(
        assembly.calibration,
        id="linear-v1-um",
        output_unit="um",
        theta=(10.0, 0.0),
    )
    um = apply_calibration(1000.0, um_cal)
    assert mm * 1000.0 == pytest.approx(um)


def test_network_interrupt_still_records_locally(assembly, tmp_path):
    log = tmp_path / "local.jsonl"
    session = Session(assembly, "sess-offline", outbox=Outbox())
    obs = session.step(400.0)
    delivery = deliver(session.outbox, obs, retry=False)
    delivery.acknowledged = False
    delivery.admitted = False
    receive(log, obs, delivery)
    rows = replay(log)
    assert len(rows) == 1
    assert rows[0]["delivery"]["acknowledged"] is False
    assert rows[0]["indicated"] == pytest.approx(4.0)


def test_bidirectional_pass_is_replayable(assembly, tmp_path):
    log = tmp_path / "bench.jsonl"
    session = Session(assembly, "sess-bench", outbox=Outbox())
    raws = [0.0, 200.0, 400.0, 600.0, 400.0, 200.0, 0.0]
    records = run_bidirectional_pass(session, raws, log)
    assert [r.indicated for r in records] == [0.0, 2.0, 4.0, 6.0, 4.0, 2.0, 0.0]
    replayed = replay(log)
    assert [row["observation_id"] for row in replayed] == [r.observation_id for r in records]
    assert all(row["quality"]["inference"] == "not_run" for row in replayed)


def test_move_sensor_requires_new_installation_id(assembly):
    moved = replace(assembly.installation, id="bench-stand-02", mount="relocated fixture")
    assert moved.id != assembly.installation.id
    assert assembly.instrument.id == "displacement-head-01"
