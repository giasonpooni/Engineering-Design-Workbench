"""Retrieval: the boundary between persistent evidence and temporary
computation.

    Evidence (evidence/) -> Trust Graph (evidence.trust_graph)
        -> RetrievalQuery -> RetrievalEngine -> RetrievalResult
        -> ContextPackage -> (future) InquiryState

Everything in this package is read-only with respect to `evidence/` and
`core/canonical`: nothing here ever calls `pool.put_*`, ever imports
`core.canonical.validation`, or ever constructs a `CanonicalState`/
`Version`. See `docs/RETRIEVAL_ARCHITECTURE.md` and
`tests/test_retrieval_boundaries.py`.
"""
