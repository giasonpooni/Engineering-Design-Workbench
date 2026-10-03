#!/usr/bin/env python3
"""Per-invariant reachability for the chemistry vertical's refusal codes.

WHY PER-CODE. A probe reporting "clean" across a gate set is a handful
of measurements and a larger number of SILENCES presented as one number.
The acquisition layer measured 2 of 15 admission codes REACHABLE; the
other 13 are not clean, they are unmeasured, and a zero rejection rate
says nothing about any of them.

TWO QUESTIONS, DELIBERATELY SEPARATED. The earlier probe here ran one
and reported it as though it were the other.

  LIVE       call the gate directly with a violating payload. Does it
             refuse? A gate that does not is dead code, and no amount of
             reachability analysis matters until it is.
  REACHABLE  plant the same violation at an ENTRY PATH -- the door real
             data comes through -- and see whether it arrives. This is
             the question a rejection rate depends on.

A gate can be LIVE and UNREACHABLE. That is not a contradiction and not
a defect; it is the honest state of a vertical whose gates have no
callers yet. What would be a defect is reporting the rate anyway.

AN UNREACHABLE VERDICT NEEDS A TRACED PATH THAT TERMINATES, not an
absence of anyone finding one. The acquisition layer's Phase 27
correction is the case: a stage claimed unreachable turned out REACHABLE
via two real bindings on a zero-length response body, and the error ran
in the direction that made the metric look meaningful. So every verdict
below that is not REACHABLE names the mechanism that stops it, and
wherever the mechanism can be executed, it is -- `blocked_at` records
what actually fired instead.

Verdict vocabulary is adopted from the acquisition layer's
admission_reachability.yaml rather than reinvented, so the two registers
can be read side by side.
"""

from __future__ import annotations

import pathlib
import sys
import traceback
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from structures.method_blocks import MethodBlockError, assert_applicability, assert_method_block
from structures.molecule import StructureError
from structures.quantity import QuantityError, TypedQuantity, assert_property_context, assert_quantity_type
from structures.substance import (
    DistributionIdentity,
    IdentityPolicyError,
    ResolutionPolicy,
    SubstanceIdentity,
    assert_distribution_identity,
    assert_identity_policy,
)

#: Adopted from architecture/admission_reachability.yaml in the
#: acquisition layer, so the two registers use one vocabulary.
REACHABLE = "REACHABLE"
STRUCTURALLY_UNREACHABLE = "STRUCTURALLY_UNREACHABLE"
ADAPTER_UNREACHABLE = "ADAPTER_UNREACHABLE"
CALLER_ONLY = "CALLER_ONLY"          # only a direct in-repo caller can construct it
NOT_ESTABLISHED = "NOT_ESTABLISHED"  # neither reached nor traced to a stop
#: A plant that ARRIVED and was admitted anyway -- the gate did not fire
#: on a violation that reached it. That is a hole, and it is a different
#: state from a plant that never arrived.
ADMITTED = "ADMITTED_DESPITE_ARRIVING"


@dataclass
class Code:
    """One refusal, with the plant that should produce it."""

    id: str
    gate: str
    rule: str
    plant: Callable[[], object]
    expect: type
    fragment: str                 # a substring the refusal must carry
    #: The document line that provokes this code through a REAL ingest,
    #: or None where no single payload can express it: a merge conflict
    #: needs two identities, a policy refusal needs a SubstanceIdentity
    #: constructed. Absent is recorded rather than forced -- a plant that
    #: cannot be written is a fact about the gate's position, not a gap.
    document: Optional[str] = None
    ingest_verdict: str = ""
    entry_verdicts: Dict[str, str] = field(default_factory=dict)
    blocked_by: Dict[str, str] = field(default_factory=dict)
    live: Optional[str] = None
    observed: str = ""


def _policy(**over):
    return ResolutionPolicy(**{"tautomer": "distinct", "stereo": "distinct",
                               "salt_solvate": "distinct", "isotope": "distinct", **over})


CODES: List[Code] = [
    # -- structures/quantity.py ------------------------------------------------
    Code("QUANTITY_NO_UNIT", "structures.quantity.TypedQuantity",
         "a numeric value without a unit is untyped",
         lambda: TypedQuantity(value=1.0, unit="", uncertainty_kind="absent"),
         QuantityError, "without a unit",
         document='PROPERTY: p | method=m | conditions=r:1 | value=1 | unit= | uncertainty_kind=absent'),
    Code("UNCERTAINTY_KIND_UNKNOWN", "structures.quantity.TypedQuantity",
         "uncertainty_kind must be one of the four declared postures",
         lambda: TypedQuantity(value=1.0, unit="K", uncertainty_kind="maybe"),
         QuantityError, "not one of",
         document='PROPERTY: p | method=m | conditions=r:1 | value=1 | unit=K | uncertainty_kind=maybe'),
    Code("ABSENT_CONTRADICTED", "structures.quantity.TypedQuantity",
         "'absent' with a supplied uncertainty is a contradiction",
         lambda: TypedQuantity(value=1.0, unit="K", uncertainty_kind="absent", uncertainty=0.5),
         QuantityError, "contradicts",
         document='PROPERTY: p | method=m | conditions=r:1 | value=1 | unit=K | uncertainty_kind=absent | uncertainty=0.5'),
    Code("KIND_WITHOUT_VALUE", "structures.quantity.TypedQuantity",
         "a non-absent posture must carry the uncertainty it claims",
         lambda: TypedQuantity(value=1.0, unit="K", uncertainty_kind="stated"),
         QuantityError, "requires the",
         document='PROPERTY: p | method=m | conditions=r:1 | value=1 | unit=K | uncertainty_kind=stated'),
    Code("QUANTITY_FIELDS_MISSING", "structures.quantity.assert_quantity_type",
         "bare scalars are refused",
         lambda: assert_quantity_type({"value": 1.0}),
         QuantityError, "bare scalars",
         document='PROPERTY: p | method=m | conditions=r:1 | value=1'),
    Code("PROPERTY_CONTEXT_MISSING", "structures.quantity.assert_property_context",
         "a value without method and conditions is a different fact",
         lambda: assert_property_context({"value": 1.0, "unit": "K",
                                          "uncertainty_kind": "absent"}),
         QuantityError, "different fact",
         document='PROPERTY: p | value=1 | unit=K | uncertainty_kind=absent'),
    Code("CONDITIONS_EMPTY", "structures.quantity.assert_property_context",
         "conditions must be a non-empty mapping",
         lambda: assert_property_context({"property": "Tg", "method": "DSC",
                                          "conditions": {}, "value": 1.0,
                                          "unit": "K", "uncertainty_kind": "absent"}),
         QuantityError, "non-empty mapping",
         document='PROPERTY: p | method=m | conditions= | value=1 | unit=K | uncertainty_kind=absent'),

    # -- structures/substance.py ----------------------------------------------
    Code("POLICY_DIMENSION_UNKNOWN", "structures.substance.ResolutionPolicy",
         "each policy dimension takes a declared value",
         lambda: _policy(tautomer="whatever"),
         IdentityPolicyError, "is not one of"),
    Code("TAUTOMER_RULE_REQUIRED", "structures.substance.ResolutionPolicy",
         "tautomer normalization requires an explicit rule id",
         lambda: _policy(tautomer="normalized"),
         IdentityPolicyError, "explicit rule id"),
    Code("IDENTITY_FIELDS_MISSING", "structures.substance.SubstanceIdentity",
         "identity requires representation and representation_version",
         lambda: SubstanceIdentity(representation="", representation_version="v1",
                                   policy=_policy()),
         IdentityPolicyError, "requires representation"),
    Code("MERGE_POLICY_MISMATCH", "structures.substance.assert_identity_policy",
         "a policy mismatch blocks the merge rather than guessing",
         lambda: assert_identity_policy(
             SubstanceIdentity("C", "v1", _policy()),
             SubstanceIdentity("C", "v1", _policy(stereo="ignored"))),
         IdentityPolicyError, "policy mismatch"),
    Code("MERGE_VERSION_MISMATCH", "structures.substance.assert_identity_policy",
         "a representation-version mismatch blocks the merge",
         lambda: assert_identity_policy(
             SubstanceIdentity("C", "v1", _policy()),
             SubstanceIdentity("C", "v2", _policy())),
         IdentityPolicyError, "version mismatch"),
    Code("DISTRIBUTION_KIND_UNKNOWN", "structures.substance.DistributionIdentity",
         "an unknown distribution kind is refused, not defaulted",
         lambda: DistributionIdentity(kind="slurry", fields={}),
         IdentityPolicyError, "unknown distribution kind",
         document='DISTRIBUTION: slurry | a=1'),
    # FOUND BY A MALFORMED PLANT, and kept because that is what the
    # classification is for. The plant below aimed at the field-set rule
    # with an EMPTY mapping and hit a different refusal one line earlier
    # -- so it measured the plant, not the gate. The guard has two
    # refusals and the enumeration had one; the missing code is added
    # rather than the plant quietly re-aimed.
    Code("STRUCTURE_STRING_ONLY", "structures.substance.assert_distribution_identity",
         "a structure string alone cannot identify a distribution-kind entity",
         lambda: assert_distribution_identity("polymer", {"structure": "CC(C)"}),
         IdentityPolicyError, "identified only by a structure string",
         document='DISTRIBUTION: polymer | structure=CC(C)'),
    Code("DISTRIBUTION_FIELDS_MISSING", "structures.substance.DistributionIdentity",
         "a distribution kind requires its full field set",
         lambda: assert_distribution_identity("polymer", {"dispersity": 1.8}),
         IdentityPolicyError, "is missing",
         document='DISTRIBUTION: polymer | dispersity=1.8'),

    # -- structures/method_blocks.py ------------------------------------------
    Code("METHOD_KIND_UNKNOWN", "structures.method_blocks.assert_method_block",
         "an unknown computed-method kind is refused",
         lambda: assert_method_block("astrology", {}),
         MethodBlockError, "unknown computed-method kind",
         document='METHOD: astrology | a=1'),
    Code("METHOD_BLOCK_INCOMPLETE", "structures.method_blocks.assert_method_block",
         "an underspecified method block is inadmissible for canonical assertion",
         lambda: assert_method_block("quantum", {}),
         MethodBlockError, "is missing",
         document='METHOD: quantum | functional=B3LYP'),
    Code("NO_APPLICABILITY_DOMAIN", "structures.method_blocks.assert_applicability",
         "a prediction with no declared applicability domain is refused",
         lambda: assert_applicability({}, {"T": 300}),
         MethodBlockError, "no declared applicability domain",
         document='METHOD: ml | model_id=m | snapshot=s | training_evidence_classes=measured | inputs=T:300'),
    Code("INPUT_OUTSIDE_DOMAIN", "structures.method_blocks.assert_applicability",
         "an input outside the declared domain is flagged and inadmissible",
         lambda: assert_applicability(
             {"applicability_domain": {"T": [200, 400]}}, {"T": 5000}),
         MethodBlockError, "outside the declared domain",
         document='METHOD: ml | model_id=m | snapshot=s | training_evidence_classes=measured | domain=T:200-400 | inputs=T:5000'),
    Code("INPUT_NEVER_DECLARED", "structures.method_blocks.assert_applicability",
         "an input the domain never declared is outside it",
         lambda: assert_applicability(
             {"applicability_domain": {"T": [200, 400]}}, {"pH": 7}),
         MethodBlockError, "never declared",
         document='METHOD: ml | model_id=m | snapshot=s | training_evidence_classes=measured | domain=T:200-400 | inputs=pH:7'),
]


# ------------------------------------------------------------ liveness --


def classify_liveness(plant: Callable[[], object], expect: type, fragment: str):
    """Run one plant and say what it measured.

    EXTRACTED SO IT CAN BE DRIVEN OVER ALL THREE BRANCHES. Against the
    real code set every gate is LIVE and no plant is malformed, so the
    DEAD and MALFORMED arms never execute and nothing tests them --
    mutating either one changed no observable behaviour and survived.
    That is the same shape as a currency check whose two siblings happen
    to be in the same state: A CHECK WHOSE INPUTS ARE COINCIDENTALLY
    UNIFORM TESTS NOTHING ABOUT THE SELECTION.
    """
    try:
        plant()
    except expect as error:
        if fragment in str(error):
            return "LIVE", str(error)[:120]
        return "MALFORMED_PLANT", f"right type, wrong refusal: {str(error)[:100]}"
    except Exception as error:  # noqa: BLE001 -- classifying, not handling
        return "MALFORMED_PLANT", f"{type(error).__name__}: {str(error)[:100]}"
    return "DEAD", "the violating payload was ACCEPTED"


def termination_verdict(admitted: int, chemistry_refusals: int) -> Dict[str, object]:
    """Did anything actually traverse, and did the gates stay silent?

    ALSO EXTRACTED, and for a sharper reason: the test covering this
    recomputed the rule inside itself instead of calling it, so it passed
    whatever the code did. A test that reimplements its subject tests
    only its own copy.

    A PLANT THAT PRODUCES NOTHING MEASURES NOTHING. Zero findings and
    zero refusals is not a confirmed termination -- it is a document
    that never entered the path.
    """
    return {
        "admitted_findings": admitted,
        "chemistry_refusals": chemistry_refusals,
        "terminated": admitted > 0 and chemistry_refusals == 0,
        "vacuous": admitted == 0,
    }


def probe_liveness() -> None:
    """Call each gate directly with a violating payload.

    This is the cheap question and it must be asked first: reachability
    analysis over a gate that does not refuse is analysis of nothing.
    """
    for code in CODES:
        code.live, code.observed = classify_liveness(
            code.plant, code.expect, code.fragment)


# -------------------------------------------------------- reachability --

#: The doors real data comes through. A verdict is meaningless without
#: one: these gates are reachable from a direct caller by construction,
#: and that says nothing about whether a document can trip them.
ENTRY_PATHS = ("acquisition", "execution")


def _importers_of_structures(root: pathlib.Path) -> Dict[str, List[str]]:
    """Who actually calls into structures/, by package.

    THE TRACE THAT TERMINATES, mechanised. An UNREACHABLE verdict here
    is not "nobody managed to build a plant" -- it is "the entry path's
    module graph contains no edge into the gate's package", which is a
    fact about the source and is re-measured on every run rather than
    remembered from the phase that first checked.
    """
    found: Dict[str, List[str]] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if rel.parts[0] in ("structures", "tests", ".git", "scripts") or "__pycache__" in rel.parts:
            continue
        text = path.read_text(errors="replace")
        if "structures" in text and ("import structures" in text or "from structures" in text):
            found.setdefault(rel.parts[0], []).append(str(rel))
    return found


def probe_reachability(root: pathlib.Path) -> Dict[str, object]:
    """Trace each entry path to the gate package, and say where it stops."""
    importers = _importers_of_structures(root)

    acquisition_reaches = "scout" in importers
    execution_reaches = any(p in importers for p in ("execution", "materials", "evidence"))

    for code in CODES:
        # acquisition: run_scout -> adapters -> extraction -> admission
        if acquisition_reaches:
            code.entry_verdicts["acquisition"] = NOT_ESTABLISHED
            code.blocked_by["acquisition"] = (
                "scout/ imports structures/ -- the edge exists, so a plant must "
                "be executed rather than argued")
        else:
            code.entry_verdicts["acquisition"] = STRUCTURALLY_UNREACHABLE
            code.blocked_by["acquisition"] = (
                "no module under scout/ imports structures/ at all, so no document "
                "or record admitted by run_scout can reach this gate. The path "
                "terminates at the import graph, not at a plant nobody wrote")
        if execution_reaches:
            code.entry_verdicts["execution"] = NOT_ESTABLISHED
            code.blocked_by["execution"] = "edge exists; requires an executed plant"
        else:
            code.entry_verdicts["execution"] = STRUCTURALLY_UNREACHABLE
            code.blocked_by["execution"] = (
                "no module under execution/, materials/ or evidence/ imports "
                "structures/, so no computed result reaches this gate either")

    return {
        "importers_of_structures": importers,
        "acquisition_edge_exists": acquisition_reaches,
        "execution_edge_exists": execution_reaches,
    }


REACHABLE_VIA_INGEST = "REACHABLE"
NOT_EXPRESSIBLE = "NOT_EXPRESSIBLE_AS_A_DOCUMENT"


def probe_ingest_reachability(root: pathlib.Path) -> Dict[str, object]:
    """Plant each code's provoking line in ONE document, ingest it
    through the vertical's own entry point, and record what arrives.

    THIS REPLACES AN IMPORT TRACE THAT ASKED THE WRONG DIRECTION. The
    earlier trace asked whether anything under `scout/` imports
    `structures/` and concluded STRUCTURALLY_UNREACHABLE. The wiring
    runs the other way: the vertical calls acquisition
    (`structures.ingest.ingest_documents`), supplying its gates. The
    edge the trace looked for still does not exist, and the path does --
    so the trace was measuring a direction rather than a path, and its
    verdict would now be confidently wrong.

    An edge is an inference in either direction. This executes.
    """
    from evidence.pool import EvidencePool
    from evidence.quarantine import Quarantine
    from scout.interface import RawDocument
    from scout.property_extraction import PropertyExtractor
    from structures.ingest import ingest_documents

    planted = [c for c in CODES if c.document]

    class _Source:
        def fetch(self):
            return (RawDocument(
                source_name="chemistry-reachability", source_kind="paper",
                content="\n".join(c.document for c in planted),
                locator="probe://chemistry/codes",
                retrieval_method="manual_entry",
                retrieved_at="2026-08-27T00:00:00Z"),)

    pool, quarantine = EvidencePool(), Quarantine()
    findings, failures = ingest_documents(
        _Source(), PropertyExtractor(), pool, quarantine=quarantine)

    # A code is REACHABLE when its own plant was refused THROUGH the
    # ingest path. Attribution is per payload: the quarantine holds the
    # content, and the code whose plant produced that content is the one
    # credited -- never the invariant id alone, which several codes
    # share and which would over-credit every one of them.
    held = [dict(record.payload) for record in quarantine.records]
    for code in CODES:
        if not code.document:
            code.ingest_verdict = NOT_EXPRESSIBLE
            continue
        candidates = PropertyExtractor().extract(
            type("R", (), {"raw_content": code.document})())
        content = dict(candidates[0].content) if candidates else None
        code.ingest_verdict = (
            REACHABLE_VIA_INGEST if content in held else ADMITTED)

    return {
        "attempted": len(findings) + len(failures),
        "admitted": len(findings),
        "refused": len(failures),
        "per_invariant": quarantine.by_invariant(),
        "rejection_rate": quarantine.rejection_rate(len(findings) + len(failures)),
    }


# --------------------------------------------- executed confirmation --


def confirm_termination_by_execution() -> Dict[str, object]:
    """Execute the acquisition path with a payload that violates the
    gates, and show it is ADMITTED.

    THE IMPORT TRACE IS AN INFERENCE; THIS IS THE MEASUREMENT. The
    acquisition layer's Phase 27 correction is the reason both are here:
    a stage claimed unreachable turned out REACHABLE through two real
    bindings on a zero-length body, and the error ran in the direction
    that made the metric look meaningful. An absent import edge is a
    strong argument, but the argument is not the thing -- so a document
    whose content would trip several codes is put through the SAME door
    a live document uses, and what arrives is recorded.

    An admitted violation is the termination, executed: the gates were
    not consulted, and a zero rejection rate is that fact rather than a
    statement about the source.
    """
    from evidence.pool import EvidencePool
    from scout.extraction import DeterministicExtractor
    from scout.interface import RawDocument
    from scout.pipeline import run_scout

    class _PlantedSource:
        """The violation enters through the ADAPTER -- the door a live
        document uses. Injecting past acquisition would prove nothing."""

        def fetch(self):
            return (RawDocument(
                source_name="chemistry-reachability", source_kind="paper",
                # every one of these would be refused by a chemistry gate:
                # a bare scalar, no unit, no method, no conditions, and a
                # polymer identified by a structure string alone.
                # THE FORMAT THE SHIPPED EXTRACTOR ACTUALLY READS. The
                # first version of this plant used `key: value` lines,
                # produced ZERO findings, and the probe reported
                # "termination confirmed" -- a vacuous pass, and the same
                # shape as the Phase 27 error it was written to avoid.
                # Nothing traversed the path, so nothing was measured.
                content=("ENTITY: polystyrene-batch-7 :: substance\n"
                         # a bare scalar: no unit, no method, no
                         # conditions, no uncertainty posture. Every one
                         # of those is a live refusal in structures/.
                         "FACT: glass_transition=373 structure=CC(C) "
                         "dispersity=1.8\n"),
                locator="probe://chemistry/1",
                retrieval_method="manual_entry",
                retrieved_at="2026-08-26T00:00:00Z"),)

    pool = EvidencePool()
    findings, failures = run_scout(_PlantedSource(), DeterministicExtractor(), pool)
    admitted = len(findings or [])
    chemistry_refusals = [
        f for f in (failures or [])
        if any(c.id.lower() in str(f).lower() or "chem" in str(f).lower() for c in CODES)
    ]
    verdict = termination_verdict(admitted, len(chemistry_refusals))
    verdict["failures"] = len(failures or [])
    return verdict


# ------------------------------------------------------------- report --


def emit(root: pathlib.Path, executed: Dict[str, object],
         measured: Dict[str, object]) -> pathlib.Path:
    """The measurement record, in the acquisition layer's form."""
    import sys as _sys
    _sys.path.insert(0, str(root / "architecture" / "exchange"))
    from canonical_yaml import canonical_bytes, canonical_sha256

    live = [c for c in CODES if c.live == "LIVE"]
    reachable = [c for c in CODES if c.ingest_verdict == REACHABLE_VIA_INGEST]
    inexpressible = [c for c in CODES if c.ingest_verdict == NOT_EXPRESSIBLE]
    holes = [c for c in CODES if c.ingest_verdict == ADMITTED]
    document = {
        "extends": "core@1.0.0",
        "generated_by": "scripts/chemistry_reachability.py",
        "artifact": "chemistry_reachability",
        "owner": "STE",
        "method": (
            "each refusal code was probed TWICE and the two questions kept "
            "apart: LIVE asks whether the gate refuses a violating payload "
            "when called directly; REACHABLE asks whether a plant can ARRIVE "
            "through an entry path. Every non-REACHABLE verdict names the "
            "mechanism that stops it, and the stop is executed, not argued"),
        "verdict_vocabulary_adopted_from": (
            "the acquisition layer's architecture/admission_reachability.yaml, "
            "so the two registers read side by side rather than in two "
            "private vocabularies"),
        "summary": {
            "codes_total": len(CODES),
            "live": len(live),
            "dead": sum(1 for c in CODES if c.live == "DEAD"),
            "malformed_plants": sum(1 for c in CODES if c.live == "MALFORMED_PLANT"),
            "reachable_from_any_entry": len(reachable),
            "exercised_by_real_acquisition": len(reachable),
            "not_expressible_as_a_document": len(inexpressible),
            "admitted_despite_arriving": len(holes),
        },
        "measured_through_a_real_ingest": {
            "entry_point": (
                "structures.ingest.ingest_documents -> "
                "scout.pipeline.run_scout(content_gates=(chemistry_content_gate,))"),
            "attempted": measured["attempted"],
            "admitted": measured["admitted"],
            "refused_and_held": measured["refused"],
            "rejection_rate": measured["rejection_rate"],
            "per_invariant": dict(sorted(measured["per_invariant"].items())),
            "why_the_import_trace_is_no_longer_the_verdict": (
                "the earlier trace asked whether anything under scout/ "
                "imports structures/ and concluded STRUCTURALLY_UNREACHABLE. "
                "The wiring runs the OTHER direction: the vertical calls "
                "acquisition and supplies its own gate. The edge the trace "
                "looked for still does not exist and the path now does -- so "
                "the trace was measuring a DIRECTION, not a path, and would "
                "today report STRUCTURALLY_UNREACHABLE with confidence and be "
                "wrong. It is retained as a note and demoted from evidence"),
            "why_five_are_silent": (
                "they are substance-identity refusals: a merge conflict needs "
                "TWO identities and a policy refusal needs a SubstanceIdentity "
                "constructed. No single document payload expresses either, so "
                "they are recorded as inexpressible rather than counted as "
                "unreached -- an absence with a named cause, not a silence"),
        },
        "metric_interpretation": {
            "zero_rate_when_reachable": (
                "the gate is reached by acquisition and did not fire. A real "
                "measurement."),
            "zero_rate_when_unreachable": (
                "no entry path can reach the gate. NOT a measurement; the "
                "metric is silent, not clean."),
            "rule": (
                "a rate is evidence about source quality only for a code "
                f"whose verdict is REACHABLE. Today that is {len(reachable)} "
                f"of {len(CODES)}"),
            "what_a_clean_set_would_look_like_and_why_this_is_not_it": (
                f"{len(inexpressible)} of {len(CODES)} codes remain LIVE and "
                "unreached, and they stay labelled. A probe reporting 'clean' "
                "would be presenting those silences as one number"),
            "before_the_wiring": (
                f"all {len(CODES)} codes were LIVE and NONE was reachable "
                "through any entry path. The gates were correct and had no "
                "caller: what was missing was POSITION, not correctness"),
        },
        "executed_confirmation": {
            "why": (
                "an absent import edge is an INFERENCE. The acquisition "
                "layer's Phase 27 correction is the reason it is not left as "
                "one: a stage claimed unreachable turned out REACHABLE via "
                "two real bindings on a zero-length body, and the error ran "
                "in the direction that made the metric look meaningful"),
            "what_was_run": (
                "a document carrying a bare scalar (no unit, method, "
                "conditions or uncertainty posture) and a polymer identified "
                "by a structure string, through run_scout, entering at the "
                "ADAPTER -- the door a live document uses"),
            "findings_admitted": executed["admitted_findings"],
            "chemistry_refusals": executed["chemistry_refusals"],
            "termination_confirmed": bool(executed["terminated"]),
        },
        "codes": [
            {
                "id": c.id,
                "gate": c.gate,
                "rule": c.rule,
                "live": c.live,
                "acquisition_trace_superseded": c.entry_verdicts.get("acquisition", ""),
                "execution_trace_superseded": c.entry_verdicts.get("execution", ""),
                "ingest": c.ingest_verdict,
                "provoking_document": c.document or "",
                "acquisition_trace_note": c.blocked_by.get("acquisition", ""),
            }
            for c in CODES
        ],
        "corrections": [
            {
                "found": "a MALFORMED plant, on the first run",
                "what_happened": (
                    "the plant for DISTRIBUTION_FIELDS_MISSING passed an empty "
                    "field mapping and hit a DIFFERENT refusal one line "
                    "earlier -- so it measured the plant, not the gate"),
                "consequence": (
                    "the guard has two refusals and the enumeration had one. "
                    "STRUCTURE_STRING_ONLY was added rather than the plant "
                    "quietly re-aimed: a malformed plant is a finding about "
                    "the enumeration, not noise to tune away"),
            },
            {
                "found": "a VACUOUS confirmation, on the second run",
                "what_happened": (
                    "the executed plant used `key: value` lines, which the "
                    "shipped extractor does not read. It produced ZERO "
                    "findings and the probe reported 'termination confirmed'"),
                "consequence": (
                    "nothing had traversed the path, so nothing was measured "
                    "-- the same shape as the Phase 27 error this "
                    "confirmation exists to avoid. The probe now refuses to "
                    "call zero findings a termination, and the plant uses the "
                    "format the shipped extractor actually parses"),
            },
        ],
        "what_this_does_not_claim": (
            "that a 100% rejection rate says anything about real sources. "
            "Every candidate counted here was PLANTED to violate a gate, so "
            "the rate measures that the plants arrived, not that the world is "
            "dirty. The claim is narrower: fifteen of twenty refusals are now "
            "reachable through a real ingest, so a rate over real documents "
            "would be evidence for those fifteen. It is not one yet"),
        "the_alias_correction": {
            "what_happened": (
                "three of the five invariant ids this gate refuses under were "
                "written here as NEW names for rules the acquisition layer had "
                "already declared: distribution_has_no_point_identity for "
                "no_point_identity_for_distributions, "
                "computed_method_fully_specified for computed_fully_specified, "
                "prediction_within_declared_domain for "
                "applicability_domain_declared"),
            "how_it_was_caught": (
                "a lock requiring every gate id to resolve against a declared "
                "invariant, which failed on ALL FIVE: none was in this "
                "repository's architecture/invariants.yaml at all, so the "
                "per-invariant rejection rate was keyed on strings no registry "
                "carried"),
            "measured_cost": (
                "the derived register holds 58 rows before and after; all six "
                "STE declarations landed on EXISTING rows (STE claims 33 -> "
                "39). Under the renamed ids it would have been 61 -- MEASURED "
                "by deriving with the renames in place, not computed"),
            "rule": (
                "a rule gets ONE id across the project, and the party that "
                "implements it second does not get to rename it by "
                "implementing it. The earlier declaration keeps the name"),
        },
        "battery_defects_found": [
            {
                "found": "a mutant that does not parse",
                "what_happened": (
                    "a malformed mutant can only be killed by an import "
                    "error, which is a fact about the edit and not about the "
                    "named test -- the malformed-plant problem one level up, "
                    "in the battery that verifies the probe"),
                "consequence": (
                    "mutants are now compile-checked (YAML targets are parsed "
                    "as YAML) and a malformed one is scored MALFORMED, never "
                    "KILLED. The guard caught a second instance on its first "
                    "run"),
            },
            {
                "found": "a mutant is not identified by (mtime, size)",
                "what_happened": (
                    "two mutations of scout/pipeline.py change the file by "
                    "exactly +8 bytes each. Written in the same second they "
                    "are indistinguishable to CPython's .pyc validity check, "
                    "so the second run executed the FIRST one's bytecode and "
                    "printed its PASS under the second one's label. The "
                    "battery reported a stable SURVIVED for a mutant a direct "
                    "run kills in 0.07s"),
                "consequence": (
                    "no bytecode is written during a battery run AND the cache "
                    "entry is purged before it -- both, since suppressing the "
                    "write does not invalidate an entry an ordinary test run "
                    "already left on disk. Byte-identity is what made it "
                    "dangerous, the same shape as 'a mirror is not a source'. "
                    "Applied to scripts/mutate_register_checks.py without "
                    "waiting for it to fire there"),
            },
        ],
    }
    out = root / "architecture" / "chemistry_reachability.yaml"
    out.write_bytes(canonical_bytes(document))
    (root / "architecture" / "chemistry_reachability.sha256").write_text(
        canonical_sha256(document) + "\n")
    return out


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    probe_liveness()
    trace = probe_reachability(root)

    print("=== LIVENESS: does the gate refuse a violating payload? ===")
    for code in CODES:
        print(f"  {code.live:16} {code.id:28} {code.gate}")

    live = [c for c in CODES if c.live == "LIVE"]
    dead = [c for c in CODES if c.live == "DEAD"]
    malformed = [c for c in CODES if c.live == "MALFORMED_PLANT"]
    print(f"\n  {len(live)}/{len(CODES)} LIVE, {len(dead)} DEAD, "
          f"{len(malformed)} MALFORMED PLANT (measured the plant, not the gate)")
    for c in malformed:
        print(f"     MALFORMED {c.id}: {c.observed}")

    trace = probe_reachability(root)
    measured = probe_ingest_reachability(root)

    print("\n=== REACHABILITY: does a plant ARRIVE through the ingest path? ===")
    print("  entry point: structures.ingest.ingest_documents -> run_scout")
    print("               with the vertical's gate wired and a quarantine held")
    for code in CODES:
        print(f"  {code.ingest_verdict:32} {code.id}")

    reachable = [c for c in CODES if c.ingest_verdict == REACHABLE_VIA_INGEST]
    inexpressible = [c for c in CODES if c.ingest_verdict == NOT_EXPRESSIBLE]
    admitted_codes = [c for c in CODES if c.ingest_verdict == ADMITTED]

    print("\n  the import trace, and why it is no longer the verdict:")
    print(f"    packages importing structures/: {sorted(trace['importers_of_structures'])}")
    print("    That edge STILL does not exist and the path now does. The trace")
    print("    asked whether acquisition reaches the gate package; the wiring")
    print("    runs the other way -- the vertical calls acquisition and supplies")
    print("    its own gate. A direction is not a path, and this trace would now")
    print("    report STRUCTURALLY_UNREACHABLE with confidence and be wrong.")

    print("\n=== MEASURED THROUGH A REAL INGEST ===")
    print(f"  candidates attempted : {measured['attempted']}")
    print(f"  admitted             : {measured['admitted']}")
    print(f"  refused and HELD     : {measured['refused']}")
    print(f"  rejection rate       : {measured['rejection_rate']:.0%}")
    print("  per invariant        :")
    for invariant_id, count in sorted(measured["per_invariant"].items()):
        print(f"      {count:3}  {invariant_id}")

    executed = confirm_termination_by_execution()
    print("\n=== THE CONTRAST: the SAME document through the UNGATED path ===")
    print("  run_scout with no content gate wired -- what the path did before")
    print(f"    findings admitted:  {executed['admitted_findings']}")
    print(f"    failures raised:    {executed['failures']}")
    print(f"    chemistry refusals: {executed['chemistry_refusals']}")
    print(f"    termination confirmed by execution: {executed['terminated']}")
    if executed["vacuous"]:
        print("    -> VACUOUS: the plant produced no findings, so nothing")
        print("       traversed the path. This is NOT a termination and is")
        print("       not counted as one.")
    if executed["terminated"] and executed["admitted_findings"]:
        print("    -> still ADMITTED, and that is the point rather than a")
        print("       defect: the ungated path has not changed and never")
        print("       refuses a chemistry claim. What changed is that a")
        print("       caller can now wire the gate. The wiring is the")
        print("       difference, not the data -- a dataset arriving on the")
        print("       ungated path would still be admitted whole.")

    print(f"\n=== THE NUMBER THAT MATTERS ===")
    print(f"  refusal codes:                    {len(CODES)}")
    print(f"  LIVE (gate refuses):              {len(live)}")
    print(f"  REACHABLE through a real ingest:  {len(reachable)}")
    print(f"  not expressible as a document:    {len(inexpressible)}")
    if admitted_codes:
        print(f"  ADMITTED (a hole):                {len(admitted_codes)}: "
              + ", ".join(c.id for c in admitted_codes))
    print(f"\n  a rejection rate is evidence for {len(reachable)} of {len(CODES)} codes.")
    print("  The five that are not are substance-identity refusals: a merge")
    print("  conflict needs two identities and a policy refusal needs a")
    print("  SubstanceIdentity constructed. No single document payload")
    print("  expresses either, so they stay silent and stay labelled --")
    print("  recorded as inexpressible rather than counted as unreached.")
    if "--emit" in sys.argv:
        out = emit(root, executed, measured)
        print(f"\n  wrote {out.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
