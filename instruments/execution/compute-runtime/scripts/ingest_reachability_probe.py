#!/usr/bin/env python3
"""§4.1 reachability proof, run BEFORE any rejection rate is interpreted.

A clean result is ambiguous between a working system and a probe that
did not reach anything. This project has produced enough of the second
that ambiguity is the default reading. So for every gate the ingest
probe claims to exercise, plant a violation on the SAME path live
documents travel and confirm it is refused with the expected invariant
id. A gate not proven reached is reported UNREACHED -- never clean.

THE PATH THIS RUNS. It runs the GATED path
(`structures.ingest.ingest_documents`), and reports the ungated one as
a contrast rather than as the measurement. Until the gates were wired
this probe ran `run_scout` directly and reported 0/3 -- correctly, and
for the whole of that time it was the only honest answer available. Now
that a caller supplies the gates, running the bare path would report
UNREACHED for gates that a real ingest reaches, which is the same
failure in the opposite direction: a probe measuring the caller it
chose rather than the path the vertical uses.

Run: python3 scripts/ingest_reachability_probe.py
"""

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from evidence.pool import EvidencePool                     # noqa: E402
from scout.extraction import DeterministicExtractor        # noqa: E402
from scout.property_extraction import PropertyExtractor    # noqa: E402
from scout.interface import RawDocument                    # noqa: E402
from scout.pipeline import run_scout                       # noqa: E402

#: The gates a chemistry ingest probe would claim to exercise, each with
#: a payload that MUST be refused if the gate is on the ingest path.
#: WHY `PROPERTY:` LINES AND NOT `FACT:`. The first version of these
#: plants used `FACT: property=... value=...`, read by
#: DeterministicExtractor into a FLAT mapping. `assert_property_context`
#: requires `conditions` to be a non-empty MAPPING, which a flat
#: extractor cannot express -- so EVERY plant through it is refused by
#: the context gate first, and no plant can ever isolate the quantity
#: gate behind it. The probe duly reported `quantity_is_typed`
#: UNREACHED, which was a fact about the plant's format and not about
#: the gate's position.
#:
#: That is a MALFORMED plant, the same class as the chemistry probe's
#: first run, and it is now DETECTED rather than relied on: a plant
#: refused under a DIFFERENT invariant id is reported MALFORMED, never
#: UNREACHED. An unreached verdict has to mean the payload arrived and
#: nothing refused it.
GATES = (
    ("no_context_free_property",
     "PROPERTY: melt_viscosity | value=1250 | unit=Pa.s "
     "| uncertainty_kind=absent\n",
     "a property with no method and no conditions",
     True),
    ("quantity_is_typed",
     "PROPERTY: density | method=pycnometry | conditions=T:298 "
     "| value=1.2 | unit=g/cm3\n",
     "a fully contexted property whose quantity has no uncertainty_kind",
     True),
    # MALFORMED PLANT, recorded rather than counted. No document payload
    # can produce an undeclared extraction_method: the extractor declares
    # its own method as a class constant ("regex:kv_v1"), so this plant
    # is structurally incapable of violating the invariant it targets.
    # A plant that cannot reach the semantics is MALFORMED, not SURVIVED
    # -- reporting it as an unreached gate would claim a hole that the
    # architecture does not have.
    ("class_assigned_at_ingest",
     "PROPERTY: tg | method=DSC | conditions=rate:10 | value=350 "
     "| unit=K | uncertainty_kind=absent\n",
     "an observation whose extraction method declares no class",
     False),
)


class _PlantedSource:
    """A source adapter carrying exactly one planted document. The
    violation enters through the ADAPTER, the same door a live document
    uses -- injecting past acquisition would prove nothing."""

    def __init__(self, raw: str):
        self._raw = raw

    def fetch(self):
        return (RawDocument(
            source_name="reachability-probe", source_kind="paper",
            content=self._raw, locator="probe://planted/1",
            retrieval_method="manual_entry",
            retrieved_at="2026-08-26T00:00:00Z"),)


def ingest(raw: str):
    """The SAME path a live document travels: adapter -> source ->
    document -> record -> extraction -> CONTENT GATE -> admission."""
    from structures.ingest import ingest_documents

    pool = EvidencePool()
    return ingest_documents(_PlantedSource(raw), PropertyExtractor(), pool)


def ingest_ungated(raw: str):
    """The same document with NO gate wired -- the contrast, never the
    measurement."""
    pool = EvidencePool()
    return run_scout(_PlantedSource(raw), PropertyExtractor(), pool)


REACHED = "REACHED"
UNREACHED = "UNREACHED"
MALFORMED = "MALFORMED"


def classify(invariant_id, codes, admitted, can_violate):
    """The probe's verdict, as a named predicate rather than a branch
    buried in a print loop.

    EXTRACTED BECAUSE IT COULD NOT BE TESTED WHERE IT WAS. A test can
    assert what the GATE does with a misaimed payload without ever
    touching the classification that reads the result -- the ingredients
    rather than the check, which is the failure this project has now hit
    four times. So the four verdicts are driven directly.

    The distinction that matters is the third one: REFUSED BY ANOTHER
    GATE is not UNREACHED. An unreached verdict has to mean the payload
    arrived and nothing refused it; a payload stopped one gate earlier
    says nothing at all about the gate being probed.
    """
    if not can_violate:
        return MALFORMED, "the plant cannot reach this gate's semantics"
    if invariant_id in codes:
        return REACHED, "refused with its id"
    if codes:
        return MALFORMED, (f"refused earlier by {sorted(codes)}, so this gate "
                           f"was never consulted")
    return UNREACHED, f"admitted={admitted}, nothing refused it"


def main() -> int:
    print("=== INGEST REACHABILITY PROBE ===")
    print("planting one violation per gate, on the GATED acquisition path")
    print("  structures.ingest.ingest_documents -> run_scout(content_gates=...)\n")
    reached, unreached, malformed = [], [], []
    for invariant_id, payload, description, can_violate in GATES:
        findings, failures = ingest(payload)
        codes = {error.code for failure in failures for error in failure.errors}
        outcome, why = classify(invariant_id, codes, len(findings), can_violate)
        {REACHED: reached, UNREACHED: unreached,
         MALFORMED: malformed}[outcome].append(invariant_id)
        print(f"  {invariant_id:28} {outcome} ({why})")
        print(f"     planted: {description}")

    print("\n--- the contrast: the same plants with NO gate wired ---")
    for invariant_id, payload, _description, can_violate in GATES:
        if not can_violate:
            continue
        findings, failures = ingest_ungated(payload)
        print(f"  {invariant_id:28} admitted={len(findings)} "
              f"refusals={len(failures)}  <- what the path did before")

    print(f"\ngates proven reached : {len(reached)}/{len(GATES)}")
    print(f"gates unreached      : {len(unreached)}/{len(GATES)}")
    print(f"plants malformed     : {len(malformed)}/{len(GATES)} "
          f"(reported, never counted as a hole)")
    if unreached:
        print(
            "\nVERDICT: the rejection-rate measurement is NOT interpretable.\n"
            "Every unreached gate would contribute 0 rejections whether the\n"
            "corpus is clean or the gate is simply not on the path. Reporting\n"
            "a rate now would record a probe that reached nothing as a\n"
            "working system. The gates must be wired into the acquisition\n"
            "path before any rate is measured.")
        return 1
    print(
        "\nVERDICT: every gate a plant CAN violate is reached; a rejection\n"
        "rate over these gates is now interpretable. What it is not yet is a\n"
        "rate over real documents -- every candidate counted here was planted\n"
        "to violate a gate, so 100% measures that the plants arrived, not\n"
        "that the world is dirty. The gate this probe cannot speak for stays\n"
        "MALFORMED and stays named.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
