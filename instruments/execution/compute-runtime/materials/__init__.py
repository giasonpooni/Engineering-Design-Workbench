"""materials: the first real consumer built ABOVE the frozen SCOUT
evidence/retrieval substrate (commit db44142), not part of it.

Phases 18-26 established, empirically (Phase 24/25/26) rather than by
further design, that the substrate already supports realistic
materials-development questions with zero architectural extension. This
package is the application layer those phases were waiting for -- it
composes existing, unmodified `evidence`/`retrieval` public API into an
answer to one concrete question shape ("what do we know about
<material>'s <property>, and where does the evidence disagree?"). It
introduces no new SCOUT capability, no new identity domain, and no
change to `EvidencePool`, `RetrievalQuery`, `RetrievalResult`,
`ContextPackage`, `InquirySeam`, `DerivedValue`, `DerivedGrounding`,
`TrustGraph`, or provenance semantics.

Dependency direction, one-way only (`tests/test_materials_boundaries.py`):

    materials
        |
        v
    retrieval
        |
        v
    evidence

`evidence`, `retrieval`, `core`, `runtime`, and `scout` have no import
of, and no awareness of, this package -- the substrate remains exactly
as frozen at db44142.
"""
