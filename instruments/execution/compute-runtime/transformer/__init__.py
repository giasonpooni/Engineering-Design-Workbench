"""The Transformer Engine: scientific state transformation and model
computation -- and nothing else.

    CANONICAL SCIENTIFIC STATE  (structures/, evidence -- not owned here)
             |
    TransformerRepresentation   (typed tokens; a computational
             |                   projection, never a replacement)
    tensor encoding
             |
    model computation           (AttentionModel -> ExecutionSpecification)
             |
    STE EXECUTION CONTRACT      (the unchanged engine boundary)
             |
    ExecutionResult -> Prediction
             |
    validation / admissibility  (the existing epistemic barriers)

The Transformer Engine is NOT the EvidencePool, the canonical-state
authority, the trust authority, the acquisition system, the proof
authority, or a second provenance system. A Prediction is a
computational result -- it is not evidence, and no write path from this
package into the pool exists (the architecture-sync minting-seam
ratchet enforces that mechanically).
"""
