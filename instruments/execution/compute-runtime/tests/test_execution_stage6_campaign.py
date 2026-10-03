"""Stage 6 locks -- few, high-value, each answering one campaign question.

The full campaign (sweep + SP1 + GROMACS + failures) lives in
scripts/stage6_campaign.py and is run for real; these tests lock the
properties that must survive refactoring, using the cheap subset
(native + Nexus).
"""

from __future__ import annotations

import pathlib

import pytest

from campaign.driver import CampaignPoint, make_campaign_pool, run_campaign
from execution.engine import default_cli_path, run_specification
from execution.proving import (
    default_nexus_heat_guest_elf_path,
    default_nexus_host_path,
    proved_runner,
)
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR,
    ExecutionSpecification,
    encode_heat_input,
)
from operations.trace import FAILED, REJECTED, SUCCEEDED, OperationTrace

pytestmark = pytest.mark.skipif(
    not default_cli_path().exists(),
    reason="execution engine binary not built; environment gap, not an architectural pass",
)

SPEC_A = ExecutionSpecification(
    HEAT_DIFFUSION_DESCRIPTOR, b"", encode_heat_input(50, [0, 700_000, 1_000_000, 700_000, 0, 0])
)
SPEC_B = ExecutionSpecification(
    HEAT_DIFFUSION_DESCRIPTOR, b"", encode_heat_input(50, [0, 700_000, 1_000_001, 700_000, 0, 0])
)


def _peak(candidate, result):
    finals = [int.from_bytes(result.output[a:a + 8], "little", signed=True)
              for a in range(0, len(result.output), 8)]
    return {"property": candidate.property, "value": max(finals), "unit": "fixed_point_mk"}


def test_central_experiment_three_runs_one_evidence_then_one_changed_input():
    """Target G verbatim: A, A, A, B -> 4 occurrences, 2 specification
    identities, 2 unique evidence ids -- repetition inflates the
    operation ledger and NOT the evidence ledger, in ONE shared pool."""
    points = (
        [CampaignPoint("rod-A", "peak_temperature", SPEC_A, _peak)] * 3
        + [CampaignPoint("rod-B", "peak_temperature", SPEC_B, _peak)]
    )
    pool, doc = make_campaign_pool(["rod-A", "rod-B"])
    trace = OperationTrace()
    report = run_campaign(pool, doc.id, trace, points)

    assert report.executions == 4 and report.failures == 0
    assert len({p.spec.identity() for p in points}) == 2
    assert len(report.observation_ids) == 4, "every success admitted"
    assert report.unique_evidence == 2, "three runs of A collapsed to ONE evidence id"
    assert report.observation_ids[0] == report.observation_ids[1] == report.observation_ids[2]
    assert report.observation_ids[3] != report.observation_ids[0]
    assert len(trace.occurrences()) == 4, "the operation ledger kept all four"
    assert all(trace.state_of(o.occurrence) == SUCCEEDED for o in trace.occurrences())


@pytest.mark.skipif(
    not (default_nexus_host_path().exists() and default_nexus_heat_guest_elf_path().exists()),
    reason="nexus artifacts not built; environment gap",
)
def test_backend_substitution_in_one_shared_pool(tmp_path):
    """Target E inside a single campaign pool with a REAL proof: the
    unproved run and the Nexus-proved run of one specification admit the
    SAME observation id; only the warrant (a proof artifact on disk)
    distinguishes them, and the trace holds two occurrences."""
    nexus = proved_runner(tmp_path, host_path=default_nexus_host_path(),
                          elf_path=default_nexus_heat_guest_elf_path())
    points = [
        CampaignPoint("rod-A", "peak_temperature", SPEC_A, _peak),
        CampaignPoint("rod-A", "peak_temperature", SPEC_A, _peak,
                      runner=nexus, label="nexus"),
    ]
    pool, doc = make_campaign_pool(["rod-A"])
    trace = OperationTrace()
    report = run_campaign(pool, doc.id, trace, points)

    assert report.failures == 0
    assert report.unique_evidence == 1, "the warrant is not part of the evidence"
    assert len(trace.occurrences()) == 2
    assert any(p.name.startswith("proof-") for p in tmp_path.iterdir()), (
        "the proved run left a real proof artifact"
    )


def test_failure_campaign_leaves_exactly_the_right_traces(tmp_path):
    """Target F: execution failure, verification failure (a lying
    engine caught by recomputation), downstream rejection, malformed
    interpretation -- interleaved with one success. The campaign
    continues through all of them; only the success admits evidence;
    the ledger states separate operation failure from downstream
    rejection."""
    honest = run_specification(SPEC_A)
    tampered = honest.computation_identity[:-1] + (
        "0" if honest.computation_identity[-1] != "0" else "1")
    lying = tmp_path / "lying-engine"
    lying.write_text(
        "#!/bin/sh\ncat > /dev/null\nprintf 'ste-execution-result v1\\n'\n"
        f"printf 'spec {honest.specification_identity}\\n'\n"
        f"printf 'program {honest.program_identity}\\n'\n"
        f"printf 'input {honest.input_identity}\\n'\n"
        "printf 'occurrence 0\\nstatus completed\\nexit_code 0\\n'\n"
        f"printf 'output {honest.output.hex()}\\n'\n"
        f"printf 'output_id {honest.output_identity}\\n'\n"
        f"printf 'computation {tampered}\\n'\n")
    lying.chmod(0o755)

    points = [
        CampaignPoint("rod-x1", "peak_temperature",
                      ExecutionSpecification(HEAT_DIFFUSION_DESCRIPTOR, b"", b"bad"),
                      _peak, label="fail-execution"),
        CampaignPoint("rod-x2", "peak_temperature", SPEC_A, _peak,
                      runner=lambda s: run_specification(s, cli_path=lying),
                      label="fail-verification"),
        CampaignPoint("rod-A", "peak_temperature", SPEC_A, _peak),  # the success
        CampaignPoint("rod-x3", "peak_temperature", SPEC_A,
                      lambda c, r: {"property": "wrong_property", "value": 1, "unit": "x"},
                      label="fail-rejected"),
        CampaignPoint("rod-x4", "peak_temperature", SPEC_A,
                      lambda c, r: (_ for _ in ()).throw(ValueError("malformed output read")),
                      label="fail-malformed"),
    ]
    pool, doc = make_campaign_pool(["rod-A", "rod-x1", "rod-x2", "rod-x3", "rod-x4"])
    trace = OperationTrace()
    report = run_campaign(pool, doc.id, trace, points)

    assert report.successes == 1 and report.failures == 4
    assert report.unique_evidence == 1, "only the success admitted evidence"
    states = [trace.state_of(o.occurrence) for o in trace.occurrences()]
    assert states.count(SUCCEEDED) == 1
    assert states.count(REJECTED) == 1, "downstream rejection stays distinct"
    assert states.count(FAILED) == 3, "execution+verification+malformed are operation failures"
    kinds = " ".join(report.failure_kinds)
    assert "EngineIdentityMismatch" in kinds, "the verification failure is named as one"
