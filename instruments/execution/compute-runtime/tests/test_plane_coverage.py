"""Locks on the measurement of the plane architecture.

A SPECIFICATION IS A CLAIM ABOUT A TREE, and a document describing a
system reads exactly the same whether the system exists or not. This is
the only thing that tells them apart, so it must keep measuring rather
than restating a number someone wrote once.
"""

from __future__ import annotations

import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "architecture"))

from architecture import plane_coverage as pc

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "architecture" / "exchange" / "plane_coverage.yaml"


def test_the_gap_is_measured_not_transcribed():
    """Recomputed from the tree. If a concept lands, the number moves."""
    result = pc.coverage()
    assert result["present"], "nothing present would mean the matcher is broken"
    assert result["absent"], "nothing absent would mean the spec is fully built"

    # DERIVED FRESH. Reading the committed artifact tests the artifact; a
    # mutation to the code that produces it leaves the snapshot alone and
    # survives. To test what produces it, produce it.
    document = pc.document()
    assert document["summary"]["present"] == len(result["present"])
    assert document["summary"]["absent"] == len(result["absent"])
    # and the committed bytes agree with what the deriver just said
    assert yaml.safe_load(ARTIFACT.read_text())["summary"] == document["summary"]


def test_every_named_concept_lands_in_exactly_one_side():
    """A concept counted twice, or dropped, makes the ratio meaningless
    -- the same denominator discipline the rejection rate needs."""
    result = pc.coverage()
    named = {c for concepts in pc.NAMED.values() for c in concepts}
    named |= set(pc.LOAD_BEARING)
    assert set(result["present"]) | set(result["absent"]) == named
    assert not (set(result["present"]) & set(result["absent"]))


def test_the_unenforceable_ones_are_separated_from_the_merely_unbuilt():
    """Flattening them into `40 missing` loses the distinction that
    matters: most absences are work not yet done, and these are claims
    the architecture cannot currently keep."""
    document = pc.document()
    unenforceable = document["unenforceable_today"]
    assert "tenant" in unenforceable, (
        "if a tenant concept has landed, the three tenant-bound planes are "
        "enforceable and this artifact should say so")
    assert set(unenforceable) <= set(document["absent"])
    finding = document["the_finding"]["unenforceable_rather_than_merely_unbuilt"]
    assert "isolated while isolating nothing" in finding


def test_the_matcher_states_which_direction_it_fails_in():
    """Matching by name over-reports the gap rather than the coverage.
    A weakness that is stated is a bound; one that is not is a bug."""
    document = yaml.safe_load(ARTIFACT.read_text())
    assert "LOWER" in document["method"] and "UPPER" in document["method"]
    assert "matched by name" in document["what_this_does_not_claim"]


def test_a_concept_that_exists_is_found_and_one_that_does_not_is_not():
    """Both directions driven, so a matcher returning a constant is
    killed. `canonical` is in all three apparatuses; a nonsense token is
    in none."""
    result = pc.coverage()
    assert "canonical" in result["present"]
    assert sorted(result["present"]["canonical"]) == ["DAQ", "SCL", "STE"]
    # A NAMED CONCEPT THAT IS ABSENT. `tenant` is only in LOAD_BEARING and
    # never passes through the matcher at all, so asserting on it left the
    # negative direction untested and a matcher returning a constant
    # survived. `federation` is named by the specification and matched.
    named = {c for concepts in pc.NAMED.values() for c in concepts}
    assert "federation" in named
    assert "federation" in result["absent"]


def test_the_artifact_is_a_fixed_point():
    sys.path.insert(0, str(ROOT / "architecture" / "exchange"))
    from canonical_yaml import canonical_bytes

    assert canonical_bytes(pc.document()) == ARTIFACT.read_bytes()


def test_the_artifact_records_what_was_built_instead():
    """The envelope is the one part buildable before the absent
    concepts. Saying so keeps the artifact from reading as a complaint."""
    document = yaml.safe_load(ARTIFACT.read_text())
    built = document["the_finding"]["what_was_built_instead"]
    assert "api/envelope.py" in built
    assert "no third construction" in built
    assert "does not authenticate" in built or "authorise" in built
