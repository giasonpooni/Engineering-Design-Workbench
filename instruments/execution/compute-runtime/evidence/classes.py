"""Evidence classes: the four immutable ingest classes, derived --
fail-closed -- from the declaration every observation already carries.

The architecture sync's two priority-zero write barriers land here and
in the tests that exercise this module:

    class_assigned_at_ingest   -- the class is a total function of
                                  `extraction_method`, which is declared
                                  at ingest and is PART OF the
                                  observation's content-addressed
                                  identity. There is no promotion path
                                  because there is no mutation path: a
                                  different class means a different
                                  extraction_method means a DIFFERENT
                                  OBSERVATION. This module adds no
                                  field and widens no schema; it makes
                                  the classing that was already implicit
                                  in the declaration explicit and
                                  refusable.

    proposals_are_not_evidence -- enforced structurally elsewhere (an
                                  `ActionCandidate` is not an admissible
                                  type and no optimizer module holds a
                                  pool write; locked by tests), and
                                  named here so the class vocabulary has
                                  one home.

THE FOUR CLASSES (`evidence_class.yaml` is the registry entry; this is
the executable form):

    measured   a physical measurement by a declared instrument method.
               NO production ingest path currently mints this class in
               this repository -- the external-engine and kernel paths are
               simulations and declare `simulation:` -- and that gap is
               a recorded fact, not an accident: COMPUTATION !=
               MEASUREMENT is this codebase's founding boundary.
    asserted   a source's claim, carried by extraction from a document
               (human transcription, rule, or model -- a model-extracted
               claim is still the DOCUMENT's claim).
    computed   the result of a declared computation (native kernels,
               external engines, any `simulation:` dispatch).
    derived    inference over other evidence (fits, DerivedValue).

An extraction method whose class this map does not know is REFUSED --
never guessed, never defaulted.
"""

from __future__ import annotations

EVIDENCE_CLASSES = ("measured", "asserted", "computed", "derived")


class EvidenceClassError(ValueError):
    """An extraction method with no declared class is refused."""


#: Prefix -> class. Order matters only for readability; prefixes are
#: disjoint. Extending this map is a recorded change to
#: `architecture/evidence_class.yaml`, not a local convenience.
_PREFIX_CLASSES = (
    ("measurement:", "measured"),
    ("simulation:", "computed"),
    ("model:", "asserted"),
    ("regex:", "asserted"),
    ("fixture:", "asserted"),
    ("fit:", "derived"),
)

_EXACT_CLASSES = {
    "human_transcription": "asserted",
    "OCR": "asserted",
}


def class_of(extraction_method: str) -> str:
    """The evidence class the ingest declaration assigns -- total over
    the declared vocabulary, fail-closed outside it."""
    exact = _EXACT_CLASSES.get(extraction_method)
    if exact is not None:
        return exact
    for prefix, evidence_class in _PREFIX_CLASSES:
        if extraction_method.startswith(prefix):
            return evidence_class
    raise EvidenceClassError(
        f"extraction_method {extraction_method!r} declares no known evidence "
        f"class; refusing to guess (declare it in evidence/classes.py and "
        f"architecture/evidence_class.yaml, or use a declared prefix)"
    )
