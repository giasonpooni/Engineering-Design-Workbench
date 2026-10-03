from schematics import Status, decide, quadratic_drag, run
from schematics.adapters.rci import bind_record

COMPLETE = {
    "board": "LILYGO-T-Display-S3",
    "interface": "i2c-displacement",
    "instrument": "lvdt-12mm",
    "installation": "bench-fixture-A",
    "quality": {"acquisition": "sample received", "timing": "device clock at readout", "calibration": "applicable", "inference": "not run"},
    "rci_digest": "sha256-field-fixture",
}


def test_incomplete_chain_refused():
    event = bind_record(quadratic_drag(), "ySensor", {"board": "x"})
    assert event.result is Status.REFUSED


def test_good_flag_refused():
    event = bind_record(quadratic_drag(), "ySensor", {**COMPLETE, "quality": "GOOD"})
    assert event.result is Status.REFUSED


def test_promote_to_state_refused():
    event = bind_record(quadratic_drag(), "ySensor", {**COMPLETE, "promote_to_state": True})
    assert event.result is Status.REFUSED


def test_inference_on_record_refused():
    rec = {**COMPLETE, "quality": {**COMPLETE["quality"], "inference": "observer updated"}}
    assert bind_record(quadratic_drag(), "ySensor", rec).result is Status.REFUSED


def test_complete_record_binds():
    sch = quadratic_drag()
    assert bind_record(sch, "ySensor", COMPLETE).result is Status.SAMPLED
    assert sch.node("ySensor").get("board") == "LILYGO-T-Display-S3"
    assert [d for d in decide(sch) if d.tool == "rci.bind"][0].status is Status.ELIGIBLE


def test_agent_record_does_not_invent_state():
    report = run(quadratic_drag(), rci_record=COMPLETE)
    assert report.schematic.node("ySensor").kind.value == "measurement"
    assert report.schematic.node("x").kind.value == "variable"
