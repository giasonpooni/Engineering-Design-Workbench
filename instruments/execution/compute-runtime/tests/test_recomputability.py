"""Locks on the measurement of this apparatus's own claim.

`architecture/apparatus.yaml` used to say a computed result "can be
recomputed by the party reading it". That is true of one path and weaker
on the other, and the sentence did not distinguish them -- an overclaim
in a SELF-DECLARATION, which is the kind this repository has the least
excuse for, since a self-declaration is the one thing no other party can
check for you.

The probe ATTEMPTS the recomputation rather than describing it. These
pin that it keeps attempting, that both grades stay reachable, and that
the declaration stays corrected.
"""

from __future__ import annotations

import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "architecture"))

from architecture import recomputability as rc

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "architecture" / "exchange" / "recomputability.yaml"
DECLARATION = ROOT / "architecture" / "apparatus.yaml"


def test_every_probe_actually_attempts_a_recomputation():
    """A grade asserted without an attempt is the thing this artifact
    exists to replace. `attempted` separates `tried and failed` from
    `not tried`."""
    results = rc.probe()
    assert results
    assert all(r.attempted for r in results)
    assert all(r.succeeded is not None for r in results)


def test_the_execution_path_is_self_contained_and_demonstrably_so():
    """It carries the PROGRAM, so a reader rebuilding from a SERIALISED
    record gets the same identity -- and dropping the program does not.

    The negative half is what makes this a demonstration. Without it the
    check was a tautology (an object rebuilt from its own attributes
    equals itself) and a mutant replacing the comparison with `True`
    survived it."""
    execution = next(r for r in rc.probe() if "ExecutionSpecification" in r.record_kind)
    assert execution.grade == rc.SELF_CONTAINED
    assert execution.succeeded is True
    assert "program" in execution.carries
    assert "load-bearing rather than merely present" in execution.detail


def test_the_execution_demonstration_can_fail_and_does_on_a_hollow_record():
    """THE DISCRIMINATING INPUT. Asserting only that the demonstration
    succeeds cannot tell a working mechanism from a constant -- three
    mutants that hardcoded True survived exactly that. An empty program
    still rebuilds, but removing it no longer changes the identity, so
    nothing in the record is carrying the computation."""
    assert rc.demonstrate_execution(b"\x00a-real-program") is True
    assert rc.demonstrate_execution(b"") is False


def test_the_program_is_load_bearing_in_the_records_identity():
    """Driven here too, directly: a SELF_CONTAINED grade resting on a
    field the identity ignores would be resting on nothing."""
    from execution.specification import ExecutionSpecification

    full = ExecutionSpecification(program=b"P", configuration=b"c", input_payload=b"i")
    stripped = ExecutionSpecification(program=b"", configuration=b"c", input_payload=b"i")
    assert full.identity() != stripped.identity()


def test_the_derivation_path_names_its_method_and_the_attempt_fails():
    """The honest half. The demonstration must FAIL and be recorded as
    failing -- a probe that reported success here would be describing a
    system that does not exist."""
    derived = next(r for r in rc.probe() if "DerivedValue" in r.record_kind)
    assert derived.grade == rc.NAMES_ITS_METHOD
    assert derived.succeeded is False, (
        "if a reader can now resolve a DerivedValue's method from the record "
        "alone, the grade is wrong and the declaration should be re-widened")
    assert "method" in derived.carries
    assert "STRING" in derived.detail


def test_both_grades_are_reachable_so_the_distinction_is_not_decorative():
    """A probe reporting one grade for everything distinguishes
    nothing -- and would read as a clean result."""
    grades = {r.grade for r in rc.probe()}
    assert rc.SELF_CONTAINED in grades
    assert rc.NAMES_ITS_METHOD in grades


def test_the_declaration_no_longer_claims_recomputation_unconditionally():
    """The correction, pinned. If the unqualified sentence comes back,
    this fails."""
    declaration = yaml.safe_load(DECLARATION.read_text())
    half = declaration["supplies_which_half_of_the_company_claim"]
    assert "carries what it was computed from" in half
    assert "recomputed by the party reading it" not in half, (
        "the unqualified claim is back in the self-declaration")


def test_the_declaration_states_both_paths_and_points_at_the_measurement():
    declaration = yaml.safe_load(DECLARATION.read_text())
    section = declaration["recomputability"]
    assert section["measured_by"] == "architecture/recomputability.py"
    assert (ROOT / section["record"]).exists()
    assert "SELF_CONTAINED" in section["execution_path"]
    assert "NAMES_ITS_METHOD" in section["derivation_path"]
    assert "not the same as self-sufficient" in section["the_distinction"]


def test_closing_the_gap_is_recorded_as_a_decision_not_a_todo():
    """Carrying a method digest changes what a DerivedValue IS, which is
    a core-schema change under bend_protocol. Recorded as a decision so
    it cannot be closed by someone who thinks it is a chore."""
    declaration = yaml.safe_load(DECLARATION.read_text())
    closing = declaration["recomputability"]["what_would_close_it"]
    assert "bend_protocol" in closing
    assert "decision rather than a measurement" in closing


def test_the_artifact_is_a_fixed_point():
    sys.path.insert(0, str(ROOT / "architecture" / "exchange"))
    from canonical_yaml import canonical_bytes

    assert canonical_bytes(rc.document()) == ARTIFACT.read_bytes()


def test_the_artifact_does_not_claim_a_self_contained_record_is_correct():
    """An identity, not a warrant. It says a reader can run the
    computation again, not that it was the right one to run."""
    document = yaml.safe_load(ARTIFACT.read_text())
    assert "not that the computation was the right one" in \
        document["what_this_does_not_claim"]
    assert "identity, not a warrant" in document["what_this_does_not_claim"]


def test_the_record_survives_the_encoding_boundary_a_reader_crosses():
    """A record reaches a reader as bytes in a document, so the
    demonstration goes through one. Handing the constructor the very
    attributes it was built from cannot fail -- that version was a
    tautology, and the mutant replacing its comparison with True was
    EQUIVALENT to it, which is the clearest possible statement that the
    step tested nothing."""
    import inspect

    body = inspect.getsource(rc.demonstrate_execution)
    assert ".hex()" in body and "bytes.fromhex" in body, (
        "the round trip must cross an encoding boundary, or it is an "
        "object being compared with itself")
    assert rc.demonstrate_execution(b"\x00\xff a program with high bytes") is True
