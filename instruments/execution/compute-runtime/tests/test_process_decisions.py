"""The three process decisions, and the rule that keeps deferrals honest.

Two were settled on 2026-08-27 and one was deliberately left open with an
expiry. What generalizes is the last of those:

  A DEFERRED DECISION IS SAFE ONLY WHILE THE CONDITION THAT MADE IT SAFE
  STILL HOLDS, AND THE CONDITION SHOULD BE CHECKED RATHER THAN
  REMEMBERED.

A carried-forward note does not close when its condition does. It
survives the event silently, which is how four items on that list
reached twenty phases. So a row that declares `deferred_while:` must
also name the check that fires when the condition stops holding, and
this file enforces that.

Note the distinction the field draws: `awaiting_decision` alone means
UNDECIDED, and `deferred_while` means SAFE UNDER A CONDITION. Only the
second needs a trigger. Capability 7-9 is the first kind -- nothing
makes it safe, nobody has chosen -- and demanding a trigger there would
be inventing a condition to satisfy a rule.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

REPO = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = REPO / "architecture" / "invariants.yaml"
BINDING = REPO / "architecture" / "model_binding.yaml"
VERSION = REPO / "core" / "canonical" / "version.py"


def review_record_is_sufficient(lineage: dict) -> bool:
    """The weaker form, as a predicate.

    EXTRACTED FOR THE SAME REASON AS THE LIVENESS CLASSIFIER, and this is
    the fourth time this shape has appeared: the record currently EXISTS
    and the vendors currently ARE disjoint, so an assertion over live
    data alone never exercises the failing branch, and deleting it
    changes nothing observable. A check whose inputs are coincidentally
    uniform tests nothing about the selection.
    """
    if lineage.get("vendor_relationship") != "shared":
        return True  # the obligation does not arise
    record = lineage.get("review_record", "")
    return bool(record) and len(record) > 20


def validator_is_vendor_disjoint(topology: dict) -> bool:
    """The standing constraint, as a predicate."""
    validator = topology["validator"]["vendor"]
    return validator not in {spec["vendor"] for role, spec in topology.items()
                             if role != "validator"}


def _entry(invariant_id):
    registry = yaml.safe_load(REGISTRY.read_text())
    return next(e for e in registry["invariants"] if e["id"] == invariant_id)


# -- builder_check_lineage_recorded: the weaker form, enforced ---------------------------------------


def test_a_shared_vendor_lineage_requires_a_review_record():
    """THE WEAKER FORM. A validator authored by a binding sharing a vendor
    with the lineage it constrains requires a review RECORD; the review
    is not required to be cross-vendor.

    The stronger form makes every enforcement change a two-vendor
    ceremony, which is the condition under which someone eventually adds
    an exception -- leaving a rule that has a hole AND costs the
    ceremony. A rule that survives beats a stricter one that gets holed.
    """
    lineage = yaml.safe_load(BINDING.read_text())["builder_lineage"]
    assert review_record_is_sufficient(lineage), (
        "builder_lineage records a SHARED vendor relationship between the "
        "enforcement code and the lineage it constrains, and carries no "
        "specific review_record. The weaker form is the obligation: record "
        "the review. It is not satisfied by noting that one happened."
    )


def test_the_residual_is_recorded_not_argued_away():
    """A shared-vendor review is not independent review. The record makes
    the exposure auditable; it does not remove it, and the registry has
    to say so or the weakening reads as a resolution."""
    entry = _entry("builder_check_lineage_recorded")
    assert entry["decided"].strip().startswith("2026-08-27")
    assert "not independent review" in entry["residual"]
    assert not entry.get("awaiting_decision"), "decided rows stop being flagged"


# -- cross_vendor_validation: standing, and only over the declaration ---------------------------------


def test_the_validator_role_is_vendor_disjoint_from_the_proposing_lineage():
    """STANDING, not a coincidence of the current deployment.

    This is the only structural check on no_self_validation that is not a
    prompt-boundary fiction. Left as a property the topology happens to
    have, it would be silently lost the first time someone rewired it for
    an unrelated reason.
    """
    topology = yaml.safe_load(BINDING.read_text())["role_bindings"]["intended_topology"]
    assert validator_is_vendor_disjoint(topology), (
        f"the validator vendor also appears in the proposing lineage "
        f"{ {r: s['vendor'] for r, s in topology.items()} } -- the validator "
        f"must remain vendor-independent from what it validates")


def test_the_unenforced_half_is_stated_rather_than_implied():
    """No binding is instantiated, so this binds the DECLARATION and goes
    runtime-live only at instantiation.

    Stated because an intended topology and a live deployment are
    different objects, and reading the first as the second is how a table
    describing nothing gets cited as a satisfied constraint. It is also
    why this row is `partially_enforced` rather than `enforced`.
    """
    bindings = yaml.safe_load(BINDING.read_text())["role_bindings"]
    assert bindings["status"] == "not_instantiated_in_repository"

    entry = _entry("cross_vendor_validation")
    assert entry["status"] == "partially_enforced"
    assert "not_instantiated_in_repository" in entry["the_half_that_is_NOT_enforced"]
    assert entry["and_it_does_not_satisfy_builder_check_lineage"], (
        "the two lineages must be kept apart in writing: one is the runtime "
        "topology, the other is who authored the enforcement code")


# -- multi_writer_write_conflict: undecided, with an expiry ------------------------------------------


def _version_store_implementations() -> list[str]:
    """Classes implementing the VersionStore protocol -- `put` plus a
    version index. The Protocol itself is not an implementation."""
    source = VERSION.read_text()
    found = []
    for match in re.finditer(r"^class\s+(\w+)[^\n]*:\n((?:[ \t]+.*\n|\n)*)", source, re.M):
        name, body = match.group(1), match.group(2)
        if name == "VersionStore" or "Protocol" in match.group(0).split("\n")[0]:
            continue
        if "def put(" in body and "def head(" in body:
            found.append(name)
    return found


def test_the_multi_writer_deferral_expires_when_a_second_writer_exists():
    """THE TRIGGER. The deferral is safe because exactly one writer
    exists -- so that fact is CHECKED, not remembered.

    `InMemoryVersionStore` documents itself as single-writer, in-process,
    append-only and is the only implementation. A second one is the event
    at which a merge policy stops being optional, and a note would have
    survived it silently.
    """
    implementations = _version_store_implementations()
    assert len(implementations) == 1, (
        f"more than one VersionStore implementation exists ({implementations}). "
        "multi_writer_write_conflict was deferred because exactly one writer "
        "did -- that condition no longer holds.\n\n"
        "This is a DECISION, not a defect: choose the merge policy for "
        "concurrent canonical assertions. It changes the identity model, "
        "which is why it was left open while it cost nothing. Deleting this "
        "check does not close it."
    )


def test_the_multi_writer_trigger_fires_when_a_second_writer_is_planted(monkeypatch, tmp_path):
    """ITS OWN REACHABILITY PROOF. A check designed never to fire in the
    state it ships in is the archetype of the shape that rots -- so the
    event is planted and the trigger is required to catch it."""
    import tests.test_process_decisions as module

    planted = tmp_path / "version.py"
    planted.write_text(
        VERSION.read_text()
        + "\n\nclass SecondStore:\n"
          "    def put(self, version): ...\n"
          "    def head(self): ...\n"
    )
    monkeypatch.setattr(module, "VERSION", planted)
    assert len(module._version_store_implementations()) == 2

    with pytest.raises(AssertionError, match="no longer holds"):
        module.test_the_multi_writer_deferral_expires_when_a_second_writer_exists()


# -- the generalization ------------------------------------------------------------------------------


def test_every_conditional_deferral_names_the_check_that_ends_it():
    """THE PATTERN, AS A MECHANISM.

    A deferred decision is safe only while its condition holds. A note
    does not close when the condition does -- it survives the event in
    silence, which is how four rows reached twenty phases. So every row
    declaring `deferred_while:` must name a `trigger_enforced_by:`, that
    file must exist, and it must actually mention the row.

    The last clause matters: a trigger naming a file that says nothing
    about the invariant is the enforcement-claim defect again, and this
    project has now met that defect from both directions.
    """
    registry = yaml.safe_load(REGISTRY.read_text())
    conditional = [e for e in registry["invariants"] if e.get("deferred_while")]
    assert conditional, "the mechanism must have subjects or it is untested"

    for entry in conditional:
        trigger = entry.get("trigger_enforced_by")
        assert trigger, (
            f"{entry['id']} is deferred on a condition and names no check "
            f"that fires when the condition ends -- that is a note again")
        path = REPO / trigger
        assert path.is_file(), f"{entry['id']}: {trigger} does not exist"
        assert entry["id"] in path.read_text(errors="replace"), (
            f"{entry['id']}: {trigger} never mentions it -- a cited file that "
            f"does not name the subject is not evidence for it")


def test_undecided_is_not_the_same_as_conditionally_deferred():
    """`awaiting_decision` alone means UNDECIDED. `deferred_while` means
    SAFE UNDER A CONDITION. Only the second needs a trigger.

    Capability 7-9 is the first kind: nothing makes it safe and nobody
    has chosen. Demanding a trigger there would mean inventing a
    condition to satisfy a rule, which is how a mechanism starts
    generating the evidence it was built to check.
    """
    registry = yaml.safe_load(REGISTRY.read_text())
    awaiting = {e["id"] for e in registry["invariants"] if e.get("awaiting_decision")}
    conditional = {e["id"] for e in registry["invariants"] if e.get("deferred_while")}

    assert conditional < awaiting, "a conditional deferral is still an open decision"
    assert "self_optimization_acceptance_criteria" in awaiting - conditional, (
        "capabilities 7-9 are undecided, not conditionally safe")


def test_both_process_predicates_reject_what_they_are_meant_to_reject():
    """Driven over CONSTRUCTED inputs, because the live ones pass.

    Fourth appearance of this shape in the project, and the fix has been
    the same every time: extract the predicate and cover both outcomes,
    rather than adding cases to the subject and hoping one of them fails.
    """
    # the review-record obligation
    assert review_record_is_sufficient(
        {"vendor_relationship": "shared",
         "review_record": "in-repo test evidence + human review of pushed commits"})
    assert not review_record_is_sufficient(
        {"vendor_relationship": "shared", "review_record": ""}), (
            "a shared lineage with no record must fail")
    assert not review_record_is_sufficient(
        {"vendor_relationship": "shared", "review_record": "reviewed"}), (
            "'reviewed' is noting that one happened, not recording it")
    assert review_record_is_sufficient(
        {"vendor_relationship": "distinct", "review_record": ""}), (
            "the obligation does not arise when the vendors differ")

    # the standing vendor-disjointness constraint
    disjoint = {"builder": {"vendor": "a"}, "scout": {"vendor": "a"},
                "validator": {"vendor": "b"}}
    shared = {"builder": {"vendor": "a"}, "scout": {"vendor": "a"},
              "validator": {"vendor": "a"}}
    assert validator_is_vendor_disjoint(disjoint)
    assert not validator_is_vendor_disjoint(shared), (
        "a validator sharing a vendor with what it validates must fail -- "
        "that is the whole content of the constraint")
