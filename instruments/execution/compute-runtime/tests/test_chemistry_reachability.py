"""Locks on the chemistry reachability probe.

The probe's job is to refuse to manufacture a measurement. Both ways it
could fail at that were hit while writing it, so both are pinned:

  a MALFORMED plant -- the payload trips a DIFFERENT refusal than the one
  aimed at, measuring the plant instead of the gate

  a VACUOUS confirmation -- the executed plant produces no findings, so
  nothing traverses the path, and "no refusal fired" is reported as a
  termination when nothing was tested

The second is the same shape as the acquisition layer's Phase 27
correction: an error running in the direction that makes the metric look
meaningful.
"""

from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scripts.chemistry_reachability import (
    ADMITTED,
    CODES,
    NOT_EXPRESSIBLE,
    REACHABLE,
    REACHABLE_VIA_INGEST,
    STRUCTURALLY_UNREACHABLE,
    classify_liveness,
    confirm_termination_by_execution,
    probe_liveness,
    probe_ingest_reachability,
    probe_reachability,
    termination_verdict,
)
from structures.ingest import GATE_INVARIANTS

ROOT = pathlib.Path(__file__).resolve().parent.parent

REPO = pathlib.Path(__file__).resolve().parent.parent
ARTIFACT = REPO / "architecture" / "chemistry_reachability.yaml"


def test_every_enumerated_code_is_live():
    """Reachability analysis over a gate that does not refuse is analysis
    of nothing. This is the cheap question and it is asked first."""
    probe_liveness()
    dead = [c.id for c in CODES if c.live == "DEAD"]
    assert not dead, f"gates that accepted a violating payload: {dead}"


def test_no_plant_is_malformed():
    """A plant that trips a different refusal measured the plant, not the
    gate. On the first run one did -- the DISTRIBUTION_FIELDS_MISSING
    plant passed an empty mapping and hit a refusal one line earlier. The
    fix was to ADD the code it found (STRUCTURE_STRING_ONLY), not to
    re-aim the plant quietly: a malformed plant is a finding about the
    enumeration."""
    probe_liveness()
    malformed = [(c.id, c.observed) for c in CODES if c.live == "MALFORMED_PLANT"]
    assert not malformed, f"plants that measured themselves: {malformed}"


def test_both_refusals_of_the_two_refusal_guard_are_enumerated():
    """The specific gap the malformed plant exposed, pinned so the
    enumeration cannot silently lose one again."""
    ids = {c.id for c in CODES}
    assert {"STRUCTURE_STRING_ONLY", "DISTRIBUTION_FIELDS_MISSING"} <= ids


def test_an_unreachable_verdict_carries_a_traced_termination():
    """AN UNREACHABLE VERDICT NEEDS A PATH THAT TERMINATES, not an
    absence of anyone finding one. Every non-REACHABLE verdict must name
    the mechanism that stops it."""
    probe_reachability(REPO)
    for code in CODES:
        for entry, verdict in code.entry_verdicts.items():
            if verdict != REACHABLE:
                assert code.blocked_by.get(entry), (
                    f"{code.id}/{entry}: {verdict} with no mechanism named -- "
                    f"that is an absence of a finding, not a finding")


def test_the_executed_confirmation_refuses_a_vacuous_pass():
    """Zero findings is not a termination.

    The first version of the executed plant used a line format the
    shipped extractor does not read. It produced zero findings, zero
    refusals, and the probe called it 'termination confirmed' -- nothing
    had traversed the path. The verdict now requires that something DID
    traverse and arrive admitted.
    """
    result = confirm_termination_by_execution()
    assert result["admitted_findings"] > 0, (
        "the plant must actually land an observation; a document that "
        "produces nothing measures nothing")
    assert result["vacuous"] is False
    assert result["terminated"] is True
    assert result["chemistry_refusals"] == 0


def test_a_plant_that_lands_nothing_is_not_counted_as_terminated():
    """The rule, driven over every combination -- CALLING it rather than
    restating it.

    The first version of this test recomputed the verdict inside itself
    and passed whatever the code did. A test that reimplements its
    subject tests only its own copy, which is why the mutation that
    dropped the `admitted > 0` condition survived it.
    """
    assert termination_verdict(0, 0) == {
        "admitted_findings": 0, "chemistry_refusals": 0,
        "terminated": False, "vacuous": True}, (
            "nothing traversed: not a termination")
    assert termination_verdict(1, 0)["terminated"] is True, (
        "something traversed and no gate fired: the termination, measured")
    assert termination_verdict(1, 1)["terminated"] is False, (
        "a gate fired: the path did NOT terminate, it was refused")
    assert termination_verdict(0, 1)["vacuous"] is True


def test_the_liveness_classifier_reports_a_dead_gate_as_dead():
    """Driven over a CONSTRUCTED dead gate, because the real set has
    none.

    Every one of the twenty codes is LIVE, so the classifier's DEAD arm
    never executes against production inputs and a mutation deleting it
    changed nothing observable. A check whose inputs are coincidentally
    uniform tests nothing about the selection.
    """
    verdict, observed = classify_liveness(
        plant=lambda: "accepted without complaint",
        expect=ValueError, fragment="never reached")
    assert verdict == "DEAD"
    assert "ACCEPTED" in observed


def test_the_liveness_classifier_reports_a_misaimed_plant_as_malformed():
    """Same reason, the other unexercised arm -- both the wrong-message
    and wrong-type cases."""
    wrong_message, observed = classify_liveness(
        plant=lambda: (_ for _ in ()).throw(ValueError("a different refusal")),
        expect=ValueError, fragment="the one I aimed at")
    assert wrong_message == "MALFORMED_PLANT"
    assert "wrong refusal" in observed

    wrong_type, observed = classify_liveness(
        plant=lambda: (_ for _ in ()).throw(TypeError("not even the right family")),
        expect=ValueError, fragment="anything")
    assert wrong_type == "MALFORMED_PLANT"
    assert "TypeError" in observed

    correct, _ = classify_liveness(
        plant=lambda: (_ for _ in ()).throw(ValueError("the aimed-at refusal")),
        expect=ValueError, fragment="aimed-at")
    assert correct == "LIVE", "and the LIVE arm still works"


def test_the_artifact_reports_silences_as_silences_not_as_clean():
    """A probe reporting 'clean' across the set would present silences as
    one number. Since the wiring, MOST codes are reachable -- which makes
    this lock harder, not easier: the ones that are still silent must
    stay visible as their own count rather than being absorbed into a
    reassuring majority.

    The counts are derived from the live verdicts rather than pinned to
    literals, so this cannot be satisfied by editing the artifact."""
    probe_liveness()
    probe_ingest_reachability(ROOT)
    document = yaml.safe_load(ARTIFACT.read_text())
    summary = document["summary"]
    reachable = sum(1 for c in CODES if c.ingest_verdict == REACHABLE_VIA_INGEST)
    silent = sum(1 for c in CODES if c.ingest_verdict == NOT_EXPRESSIBLE)

    assert summary["codes_total"] == len(CODES)
    assert summary["live"] == len(CODES)
    assert summary["reachable_from_any_entry"] == reachable
    assert summary["exercised_by_real_acquisition"] == reachable
    # the silences, counted and NOT folded into the reachable total
    assert summary["not_expressible_as_a_document"] == silent
    assert reachable + silent == len(CODES)
    # a code that ARRIVED and was admitted anyway is a hole, and a
    # different state from one that never arrived
    assert summary["admitted_despite_arriving"] == 0

    rule = document["metric_interpretation"]["rule"]
    assert "REACHABLE" in rule and str(len(CODES)) in rule
    assert document["metric_interpretation"][
        "what_a_clean_set_would_look_like_and_why_this_is_not_it"]
    # and the artifact still carries what it measured BEFORE the wiring,
    # so the 15 is not left standing on nothing
    assert "POSITION" in document["metric_interpretation"]["before_the_wiring"]


def test_the_artifact_carries_the_ingest_measurement_not_the_import_trace():
    """The import trace asked the WRONG DIRECTION and would now print
    STRUCTURALLY_UNREACHABLE with confidence and be wrong. The artifact
    must record the executed measurement as the verdict and the trace as
    a demoted note."""
    probe_ingest_reachability(ROOT)
    document = yaml.safe_load(ARTIFACT.read_text())
    measured = document["measured_through_a_real_ingest"]
    assert measured["attempted"] == measured["refused_and_held"] + measured["admitted"]
    assert measured["rejection_rate"] == 1.0
    assert set(measured["per_invariant"]) <= set(GATE_INVARIANTS)
    assert sum(measured["per_invariant"].values()) == measured["refused_and_held"]
    assert "DIRECTION" in measured["why_the_import_trace_is_no_longer_the_verdict"]

    for entry in document["codes"]:
        # the superseded trace is retained under a name that says so
        assert "acquisition_trace_superseded" in entry
        assert entry["ingest"] in (REACHABLE_VIA_INGEST, NOT_EXPRESSIBLE, ADMITTED)


def test_the_artifact_records_the_alias_correction():
    """Three of five gate ids were renames of rules already declared
    elsewhere. The cost is recorded as a measurement, not a note."""
    document = yaml.safe_load(ARTIFACT.read_text())
    correction = document["the_alias_correction"]
    assert "no_point_identity_for_distributions" in correction["what_happened"]
    assert "58" in correction["measured_cost"] and "61" in correction["measured_cost"]
    assert "ONE id" in correction["rule"]


def test_the_artifact_records_the_two_battery_defects():
    """Found in the instrument that verifies the instrument. Both made it
    report a verdict for work it had not done."""
    document = yaml.safe_load(ARTIFACT.read_text())
    found = [d["found"] for d in document["battery_defects_found"]]
    assert any("does not parse" in f for f in found)
    assert any("mtime" in f for f in found)
    collision = next(d for d in document["battery_defects_found"] if "mtime" in d["found"])
    assert "+8 bytes" in collision["what_happened"]
    # both halves of the fix, not either
    assert "purged" in collision["consequence"]
    assert "mutate_register_checks" in collision["consequence"]


def test_the_artifact_records_its_own_two_corrections():
    """Both failure modes were hit while writing the probe. They are
    recorded in the artifact rather than only fixed, because a probe that
    reports how it was wrong is worth more than one that reports a
    number."""
    document = yaml.safe_load(ARTIFACT.read_text())
    corrections = document["corrections"]
    assert len(corrections) >= 2
    kinds = " ".join(c["found"] for c in corrections).lower()
    assert "malformed" in kinds and "vacuous" in kinds


def test_the_artifact_is_current():
    """Re-derive and compare: a stale measurement record is worse than
    none, because it reads as current."""
    sys.path.insert(0, str(REPO / "architecture" / "exchange"))
    from canonical_yaml import canonical_sha256

    document = yaml.safe_load(ARTIFACT.read_text())
    recorded = (REPO / "architecture" / "chemistry_reachability.sha256").read_text().strip()
    assert recorded == canonical_sha256(document)


# ---------------------------------------------------------------------
# THE BATTERY THAT VERIFIES THE PROBE, VERIFIED.
#
# Two defects were found in it while wiring the gates, and neither was
# visible in its output -- both made it report a confident verdict for
# work it had not done:
#
#   a mutant that does not PARSE can only be "killed" by an import
#   error, which is a fact about the edit, not about the named test
#
#   a mutant is not identified by (mtime, size), and two mutants of one
#   file with the same byte length written in the same second are
#   indistinguishable to CPython's `.pyc` validity check -- so the
#   second run executes the FIRST one's bytecode and prints its result
#   under the second one's label
#
# The second is the sharper one: byte-identity is again what makes the
# thing dangerous, and it produced a stable SURVIVED across repeated
# runs for a mutant that a direct run kills in 0.07s.
# ---------------------------------------------------------------------

import os
import subprocess


def _battery():
    import importlib

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
    return importlib.import_module("mutate_reachability_checks")


def test_every_mutant_in_the_battery_parses():
    """A malformed mutant is scored MALFORMED, never KILLED. This runs
    the same predicate the battery runs, over every mutation it holds."""
    battery = _battery()
    malformed = []
    for label, path, mutate, _target in battery.MUTATIONS:
        source = path.read_text()
        mutated = mutate(source)
        assert mutated != source, f"{label}: the diff reached nothing"
        broken = battery._compiles(path, mutated)
        if broken:
            malformed.append(f"{label}: {broken}")
    assert malformed == []


def test_the_malformed_guard_rejects_a_mutant_that_does_not_parse():
    """Drive the predicate over both branches, in both languages it
    checks -- a guard that returned "" unconditionally would pass a
    battery whose mutants all happen to compile."""
    battery = _battery()
    python = pathlib.Path("x.py")
    assert battery._compiles(python, "a = 1\n") == ""
    assert battery._compiles(python, "def f(:\n") != ""
    document = pathlib.Path("x.yaml")
    assert battery._compiles(document, "a: 1\n") == ""
    assert battery._compiles(document, "a: [1\n") != ""


def test_a_same_size_replacement_is_not_masked_by_a_stale_bytecode_cache():
    """The exact failure, reconstructed: import a module (writing its
    cache), replace it with a DIFFERENT module of the SAME byte length
    and the same mtime, and require a subprocess to observe the second.

    Without the purge and the no-bytecode environment this fails -- it
    is what made the battery report SURVIVED for a mutant it had not
    run."""
    import tempfile

    battery = _battery()
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        module = root / "subject.py"
        first, second = 'VALUE = "AAA"\n', 'VALUE = "BBB"\n'
        assert len(first) == len(second)

        module.write_text(first)
        read = [sys.executable, "-c",
                "import subject; print(subject.VALUE)"]
        assert subprocess.run(read, cwd=root, capture_output=True,
                              text=True).stdout.strip() == "AAA"
        assert list((root / "__pycache__").glob("subject.*.pyc"))

        # same length, and the mtime is forced equal to the first write:
        # both halves of CPython's validity check now match the cache.
        stamp = module.stat().st_mtime
        module.write_text(second)
        os.utime(module, (stamp, stamp))

        battery._purge_cache(module)
        observed = subprocess.run(
            read, cwd=root, capture_output=True, text=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1")).stdout.strip()
        assert observed == "BBB"


def test_the_battery_purges_and_suppresses_bytecode_for_every_run():
    """Both halves, not either: suppressing the write does not
    invalidate an entry an ordinary test run already left on disk."""
    import inspect

    battery = _battery()
    body = inspect.getsource(battery.run_one)
    assert "_purge_cache(path)" in body
    assert 'PYTHONDONTWRITEBYTECODE="1"' in body
    assert "path" in inspect.signature(battery.run_one).parameters
    # and the caller actually passes it -- a default of None would make
    # the purge silently optional.
    assert "run_one(target, path)" in inspect.getsource(battery.main)
