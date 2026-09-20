# Computational evidence reference

This reference covers implemented derivation and retrieval types. It does not define an organizational roadmap or a new storage authority.

## B. Observation and derivation

An `Observation` records an extraction event over source records. A `DerivedValue` records a computation from observation identifiers, derived-value identifiers or both. The source types and factories are in `evidence/types.py`.

## E. Derivation identity and grounding

A derived value's identity covers its deduplicated, sorted input identifiers, method and content. Confidence and derivation time are annotations. Admission checks that the referenced inputs exist in the pool.

The subjects a derivation is about are recorded separately by `DerivedGrounding`. Reusing a derivation across explicitly declared subjects does not change the underlying derivation identity. Neither object silently resolves conflicting evidence.

## K. Epistemic-status vocabulary

`retrieval/epistemic.py` declares `observed`, `extracted`, `inferred`, `simulated`, `hypothesized`, `predicted` and `validated`.

Its observation classifier returns:

| Extraction method | Status |
| --- | --- |
| `human_transcription` | `observed` |
| Prefix `model:` | `inferred` |
| Prefix `simulation:` | `simulated` |
| Other methods | `extracted` |

The classifier does not return `hypothesized`, `predicted` or `validated`. A vocabulary member's existence is not evidence that an observation has that status.

## Inquiry boundary

`retrieval/seam.py` exposes `InquirySeam(context_id, opened_at)` and `open_inquiry_seam`. This object records which context package was selected and a caller-supplied time. It does not perform computation or implement mutable inquiry state.

## O. Authority boundary

Retrieval returns `RetrievalResult` and `ContextPackage` values without changing evidence or canonical state. A derived result remains a derived result; passing it between packages does not grant it canonical authority. See [Retrieval architecture](RETRIEVAL_ARCHITECTURE.md) and [Evidence-pool architecture](PHASE_14_DATA_POOL_ARCHITECTURE.md) for the implemented contracts.
