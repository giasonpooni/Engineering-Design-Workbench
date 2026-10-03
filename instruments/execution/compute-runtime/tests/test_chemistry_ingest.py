"""Locks on the chemistry gates' WIRING to the acquisition path.

The gates were correct, tested, and had no caller: twenty refusal codes,
twenty LIVE, zero reachable. Correctness was never the thing that was
missing -- POSITION was. So these tests pin the position, and each one
fails in a way that would have been invisible before the wiring existed:

  the extension point is OPT-IN     -- every existing caller of run_scout
                                       keeps its exact prior behaviour
  a refusal is VISIBLE              -- stage "content_gate", the invariant
                                       ids on the errors
  a refusal is RETAINED             -- quarantine_not_discard: the payload
                                       survives with its failing ids
  a refusal is ATTRIBUTED           -- to the ONE invariant that refused,
                                       because the metric is per invariant
                                       and a wrong filing is a wrong rate
                                       under a right total
  a non-claim passes UNTOUCHED      -- the gate governs claims of a kind,
                                       not every document through the door
  there is NO FORCE PATH            -- nothing admits a candidate the gate
                                       refused

The last one is the one worth stating plainly: a gate that can be
bypassed by an argument is a default, and a rejection rate over a
default measures the caller.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from evidence.pool import EvidencePool
from evidence.quarantine import Quarantine
from scout.extraction import DeterministicExtractor
from scout.interface import RawDocument
from scout.pipeline import run_scout
from scout.property_extraction import PropertyExtractor
from structures.ingest import (
    APPLICABILITY,
    DISTRIBUTION_IDENTITY,
    GATE_INVARIANTS,
    METHOD_BLOCK,
    PROPERTY_CONTEXT,
    QUANTITY_TYPED,
    chemistry_content_gate,
    ingest_documents,
)

# A property line that satisfies every quantity and context gate.
CLEAN = ("PROPERTY: glass_transition | method=DSC | conditions=heating_rate:10 "
         "| value=373 | unit=K | uncertainty_kind=absent")
# The same claim with the unit removed: a bare scalar.
NO_UNIT = ("PROPERTY: glass_transition | method=DSC | conditions=heating_rate:10 "
           "| value=373 | unit= | uncertainty_kind=absent")
# The same claim with no method and no conditions: context-free.
NO_CONTEXT = "PROPERTY: glass_transition | value=373 | unit=K | uncertainty_kind=absent"


def _source(*lines: str):
    class _S:
        def fetch(self):
            return (RawDocument(
                source_name="ingest-lock", source_kind="paper",
                content="\n".join(lines), locator="test://chemistry/1",
                retrieval_method="manual_entry",
                retrieved_at="2026-08-29T00:00:00Z"),)
    return _S()


# ------------------------------------------------- the extension point --


def test_run_scout_without_gates_is_unchanged():
    """The parameter defaults to the prior behaviour EXACTLY. If this
    ever fails, wiring one vertical changed every other caller."""
    findings, failures = run_scout(_source(NO_UNIT), PropertyExtractor(), EvidencePool())
    assert len(findings) == 1
    assert failures == ()


def test_run_scout_without_gates_holds_nothing():
    """No gate means no quarantine writes -- not even an empty record."""
    quarantine = Quarantine()
    run_scout(_source(NO_UNIT), PropertyExtractor(), EvidencePool(),
              quarantine=quarantine)
    assert quarantine.records == []


def test_the_same_document_is_refused_once_gated():
    """The contrast is the whole point: identical bytes, identical
    extractor, identical pool -- only the gate differs."""
    ungated, _ = run_scout(_source(NO_UNIT), PropertyExtractor(), EvidencePool())
    gated, failures = ingest_documents(_source(NO_UNIT), PropertyExtractor(), EvidencePool())
    assert len(ungated) == 1
    assert gated == ()
    assert len(failures) == 1


# ------------------------------------------------------ visible refusal --


def test_refusal_names_its_stage():
    _, failures = ingest_documents(_source(NO_UNIT), PropertyExtractor(), EvidencePool())
    assert [f.stage for f in failures] == ["content_gate"]


def test_refusal_carries_the_invariant_id():
    """The invariant id travels on the error, not just a message. A
    refusal that only says "rejected" cannot be counted per invariant."""
    _, failures = ingest_documents(_source(NO_UNIT), PropertyExtractor(), EvidencePool())
    codes = {error.code for f in failures for error in f.errors}
    assert codes == {QUANTITY_TYPED}


# ----------------------------------------------------- retained refusal --


def test_quarantine_retains_the_payload():
    """quarantine_not_discard. The rejected content is recoverable, so a
    repair can re-enter through normal ingest."""
    quarantine = Quarantine()
    ingest_documents(_source(NO_UNIT), PropertyExtractor(), EvidencePool(),
                     quarantine=quarantine)
    assert len(quarantine.records) == 1
    assert quarantine.records[0].payload["property"] == "glass_transition"


def test_quarantine_records_the_source_record():
    """A held payload without its origin cannot be traced back to the
    document that carried it."""
    quarantine = Quarantine()
    ingest_documents(_source(NO_UNIT), PropertyExtractor(), EvidencePool(),
                     quarantine=quarantine)
    assert quarantine.records[0].source_ref


def test_nothing_is_lost_between_admitted_and_refused():
    """Attempted == admitted + refused. A gate that DROPPED would
    satisfy the letter of the refusal and destroy the metric: the
    denominator would shrink with the numerator."""
    findings, failures = ingest_documents(
        _source(CLEAN, NO_UNIT, NO_CONTEXT), PropertyExtractor(), EvidencePool())
    assert len(findings) == 1
    assert len(failures) == 2


def test_rejection_rate_is_computed_over_what_arrived():
    quarantine = Quarantine()
    findings, failures = ingest_documents(
        _source(CLEAN, NO_UNIT, NO_CONTEXT), PropertyExtractor(), EvidencePool(),
        quarantine=quarantine)
    assert quarantine.rejection_rate(len(findings) + len(failures)) == pytest.approx(2 / 3)


# -------------------------------------------------- attributed refusal --


def test_a_quantity_refusal_is_not_filed_under_the_property_invariant():
    """`assert_property_context` delegates to the quantity gate, so ONE
    call refuses for two different reasons. Filing them together leaves
    the total right and both rates wrong."""
    assert chemistry_content_gate({
        "property": "glass_transition", "method": "DSC",
        "conditions": {"heating_rate": 10}, "value": 373, "unit": "",
        "uncertainty_kind": "absent",
    }) == (QUANTITY_TYPED,)


def test_a_context_refusal_is_not_filed_under_the_quantity_invariant():
    assert chemistry_content_gate({
        "property": "glass_transition", "value": 373, "unit": "K",
        "uncertainty_kind": "absent",
    }) == (PROPERTY_CONTEXT,)


def test_the_two_attributions_are_distinguished_by_the_refusal_itself():
    """Not by which key is missing -- the gate cannot know that. Drive
    both branches of the discriminator over constructed messages, so a
    predicate that returned a constant is killed."""
    from structures.ingest import _quantity_or_property

    assert _quantity_or_property("value 373 without a unit") == QUANTITY_TYPED
    assert _quantity_or_property("uncertainty_kind 'maybe' is not one of") == QUANTITY_TYPED
    assert _quantity_or_property("a property with no method") == PROPERTY_CONTEXT
    assert _quantity_or_property("") == PROPERTY_CONTEXT


# ------------------------------------------------------------- routing --


def test_a_non_chemistry_candidate_passes_untouched():
    """The gate governs claims of a KIND. A gate that refused everything
    it did not recognise would make one vertical a filter on the whole
    corpus."""
    assert chemistry_content_gate({"headline": "a paper about polymers"}) == ()


def test_an_unrecognised_document_still_ingests_through_the_gated_path():
    findings, failures = ingest_documents(
        _source("ENTITY: polystyrene :: substance", "FACT: colour=white"),
        DeterministicExtractor(), EvidencePool())
    assert len(findings) >= 1
    assert failures == ()


def test_an_empty_distribution_kind_is_not_a_distribution_claim():
    """A declaration key present but empty is an absent declaration, not
    a malformed one -- otherwise every payload carrying the key for
    another reason is refused."""
    assert chemistry_content_gate({"distribution_kind": ""}) == ()


def test_a_non_mapping_method_block_is_not_a_method_claim():
    assert chemistry_content_gate({"method_block": "quantum"}) == ()


# ------------------------------------------------------ no force path --


def test_no_argument_admits_a_refused_candidate():
    """There is no force flag, and adding one would show up here: the
    gate's tuple is the decision, and the pipeline has no branch that
    consults anything else once it is non-empty."""
    import inspect

    from scout import pipeline

    body = inspect.getsource(pipeline.run_scout)
    assert "if failing:" in body
    # the ONLY thing that follows a non-empty gate result is retention
    # plus `continue` -- never a conditional admission.
    after = body.split("if failing:", 1)[1].split("continue", 1)[0]
    assert "put_observation" not in after


def test_a_refused_candidate_never_reaches_the_pool():
    pool = EvidencePool()
    ingest_documents(_source(NO_UNIT), PropertyExtractor(), pool)
    assert pool.all_observations() == ()


# ------------------------------------------- all five gates are reached --


def test_every_gate_invariant_is_reachable_through_one_ingest():
    """The measurement the wiring exists to make possible. Five gates,
    five reached, through the vertical's own entry point -- not by
    calling the assertions directly, which is what LIVE already proved."""
    quarantine = Quarantine()
    ingest_documents(
        _source(
            NO_UNIT,
            NO_CONTEXT,
            "DISTRIBUTION: polymer | Mn=3251",
            "METHOD: quantum | functional=B3LYP",
            "METHOD: quantum | method=DFT | functional=B3LYP "
            "| basis_set=6-31G* | solvation_model=none | convergence=1e-8 "
            "| domain=T:200-400 | inputs=T:900",
        ),
        PropertyExtractor(), EvidencePool(), quarantine=quarantine)
    assert set(quarantine.by_invariant()) == set(GATE_INVARIANTS)


def test_the_five_ids_are_the_verticals_own_invariants():
    """Not free-form strings. If an id here drifts from
    architecture/invariants.yaml, the per-invariant rate names something
    the register does not carry."""
    import yaml

    root = pathlib.Path(__file__).resolve().parent.parent
    declared = {
        entry["id"]
        for entry in yaml.safe_load((root / "architecture" / "invariants.yaml").read_text())["invariants"]
    }
    assert set(GATE_INVARIANTS) <= declared


def test_applicability_runs_only_on_a_well_formed_block():
    """Order matters: a malformed block cannot be checked for domain, so
    a refusal must be attributed to METHOD_BLOCK alone. Reporting both
    would double-count one defect across two invariants."""
    failing = chemistry_content_gate({
        "method_block_kind": "quantum",
        "method_block": {"functional": "B3LYP"},
        "method_inputs": {"T": 900},
    })
    assert failing == (METHOD_BLOCK,)
    assert APPLICABILITY not in failing


def test_a_distribution_without_its_field_set_is_refused():
    assert chemistry_content_gate({
        "distribution_kind": "polymer", "distribution_fields": {"Mn": 3251},
    }) == (DISTRIBUTION_IDENTITY,)


# ---------------------------------------------------------------------
# THE THREE-GATE INGEST PROBE (scripts/ingest_reachability_probe.py).
#
# It carried `0/3 gates proven reached` for several phases and was
# right to. Once the gates were wired it kept reporting UNREACHED, for
# two reasons that had nothing to do with reachability -- and both ran
# in the direction that made the probe look vindicated:
#
#   its plants used a FLAT extractor, and `conditions` must be a
#   non-empty MAPPING, so every plant was refused by the context gate
#   first and none could isolate the quantity gate behind it
#
#   it could not tell "nothing refused it" from "something else refused
#   it one gate earlier"
#
# It had no test at all, which is how both survived. It has one now.
# ---------------------------------------------------------------------


def _probe():
    import importlib

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
    return importlib.import_module("ingest_reachability_probe")


def test_the_three_gate_probe_reaches_both_gates_a_plant_can_violate():
    probe = _probe()
    assert probe.main() == 0


def test_each_plant_isolates_the_gate_it_names():
    """The defect that hid for phases: a plant refused by a DIFFERENT
    gate proves nothing about the one it targets. Every violable plant
    must be refused under its OWN id and no other."""
    probe = _probe()
    for invariant_id, payload, _description, can_violate in probe.GATES:
        if not can_violate:
            continue
        _findings, failures = probe.ingest(payload)
        codes = {error.code for failure in failures for error in failure.errors}
        assert codes == {invariant_id}, (
            f"{invariant_id}: refused under {sorted(codes)} instead")


def test_a_plant_refused_by_another_gate_is_malformed_not_unreached():
    """An UNREACHED verdict has to mean the payload ARRIVED and nothing
    refused it. All four verdicts driven over CONSTRUCTED inputs -- the
    first version of this test asserted what the GATE did with a
    misaimed payload and never touched the classification that reads the
    result, so a mutant that deleted the malformed branch survived it.
    Ingredients are not the check."""
    probe = _probe()

    assert probe.classify("quantity_is_typed", {"quantity_is_typed"}, 0, True)[0] == "REACHED"
    # refused, but ONE GATE EARLIER: says nothing about this gate
    assert probe.classify("quantity_is_typed", {"no_context_free_property"}, 0, True)[0] == "MALFORMED"
    # arrived and nothing refused it: the only thing UNREACHED may mean
    assert probe.classify("quantity_is_typed", set(), 1, True)[0] == "UNREACHED"
    # a plant that structurally cannot violate the invariant it targets
    assert probe.classify("class_assigned_at_ingest", set(), 1, False)[0] == "MALFORMED"
    # and the misaimed verdict names what stopped it, so the finding is
    # actionable rather than a label
    _outcome, why = probe.classify("quantity_is_typed", {"no_context_free_property"}, 0, True)
    assert "no_context_free_property" in why


def test_the_probe_still_refuses_to_call_this_a_rate_over_real_documents():
    """Every candidate it counts was planted to violate a gate. A 100%
    refusal measures that the plants arrived, not that the world is
    dirty -- and the probe says so in its own verdict."""
    import inspect

    probe = _probe()
    verdict = inspect.getsource(probe.main)
    assert "not\\nthat the world is dirty" in verdict or "world is dirty" in verdict
    assert "planted" in verdict


def test_the_flat_extractor_still_cannot_express_a_valid_context():
    """The reason the plants had to change format, pinned so it is a
    measured constraint rather than a remembered one. If a flat
    extractor ever could express `conditions`, this fails and the
    comment above it is stale."""
    from scout.extraction import DeterministicExtractor

    findings, failures = ingest_documents(
        _source("FACT: property=density method=pycnometry conditions=T298 "
                "value=1.2 unit=g/cm3 uncertainty_kind=absent"),
        DeterministicExtractor(), EvidencePool())
    assert findings == ()
    codes = {error.code for f in failures for error in f.errors}
    assert codes == {PROPERTY_CONTEXT}


# ---------------------------------------------------------------------
# THE VERTICAL CONTRACT'S DECLARED POSITION.
#
# Before the wiring, architecture/verticals/chemistry/vertical.yaml named
# a gate set with NO DECLARED POSITION -- which is exactly the defect the
# per-code probe went on to measure. A contract naming what a vertical
# refuses without naming WHERE it refuses it is describing an intention.
#
# So the declaration is now checked against the code rather than trusted:
# every id it claims reachable must be one the gate can actually emit,
# and the entry point it names must exist and be the one that wires them.
# ---------------------------------------------------------------------

CONTRACT = pathlib.Path(__file__).resolve().parent.parent / "architecture" / "verticals" / "chemistry" / "vertical.yaml"


def _contract():
    import yaml

    return yaml.safe_load(CONTRACT.read_text())["ingest"]


def test_the_contract_names_an_entry_point_that_exists_and_wires_the_gates():
    import importlib
    import inspect

    module_name, _, attribute = _contract()["entry_point"].rpartition(".")
    entry = getattr(importlib.import_module(module_name), attribute)
    assert callable(entry)
    assert "content_gates=(chemistry_content_gate,)" in inspect.getsource(entry)


def test_the_contract_claims_exactly_the_gates_the_code_can_emit():
    """Not a subset either way. A contract claiming a gate the code
    cannot emit is an overclaim; one omitting a gate the code does emit
    hides a refusal from anyone reading the contract."""
    assert set(_contract()["gates_reachable_through_this_path"]) == set(GATE_INVARIANTS)


def test_the_gate_that_is_live_but_unreachable_is_named_and_kept_apart():
    """LIVE is not REACHABLE, and the contract must not flatten them --
    that distinction is the whole finding this phase rests on."""
    contract = _contract()
    unreachable = contract["gate_LIVE_but_not_reachable_here"]
    assert set(unreachable) == {"identity_policy_declared"}
    assert "NOT_EXPRESSIBLE" in unreachable["identity_policy_declared"]
    # and it is NOT also claimed as reachable
    assert not set(unreachable) & set(contract["gates_reachable_through_this_path"])


def test_the_contracts_declared_direction_matches_the_import_graph():
    """The contract says the vertical calls acquisition and that nothing
    under scout/ imports structures/. If that edge ever appears, the
    generic path has taken on a domain dependency and the contract's
    stated direction is false."""
    import ast

    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for path in (root / "scout").rglob("*.py"):
        # PARSED, not grepped. The first version of this searched the
        # file text and caught pipeline.py's DOCSTRING, which names
        # structures/ingest.py to explain why the coupling lives there.
        # A prose reference is not a dependency, and a check that cannot
        # tell them apart would forbid documenting the boundary it
        # exists to protect.
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name.split(".")[0] == "structures" for name in names):
                offenders.append(path.relative_to(root))
    assert offenders == [], f"scout/ now imports structures/: {offenders}"


def test_the_contract_points_at_the_measurement_and_the_locks():
    contract = _contract()
    root = pathlib.Path(__file__).resolve().parent.parent
    assert (root / contract["measured"]).exists()
    assert (root / contract["locks"]).exists()
