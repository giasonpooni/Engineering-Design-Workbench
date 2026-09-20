# Invariant corpus fixture

[validation/invariant-corpus-v1.json](../validation/invariant-corpus-v1.json)
uses the `invariant-corpus-v1` schema and cites
`giasonpooni/Construction-State-Estimator-for-BIM` as its source.
Its claim scope is computational integrity only.

The fixture records a chain-rule numeric result and a declared tangent
coordinate. [tests/test_corpus_cite.py](../tests/test_corpus_cite.py) checks the
schema, claim scope, numeric pin, and presence of the tangent declaration.
