# Invariant-corpus record

[`validation/invariant-corpus-v1.json`](../validation/invariant-corpus-v1.json)
uses the `invariant-corpus-v1` schema and declares the scope
`computational-integrity-only`. It records separate board/interface/sensor/
installation identities, declared calibration uncertainty, and a reading
coordinate that requires a declared calibration.

Its `cites` field identifies the companion CSE schema repository. This metadata
does not transform the observation into a CSE domain measurement or establish
physical validity. `tests/test_corpus_cite.py` checks the retained schema, scope
and record identifiers.
