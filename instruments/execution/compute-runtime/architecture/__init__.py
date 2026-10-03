"""The canonical architecture layer: structured sources, executable
gates, and generated projections.

    invariants.yaml / evidence_class.yaml / model_binding.yaml /
    vocabulary_map.yaml / verticals/*/vertical.yaml   -- canonical
    doctrine_generator.py                             -- projection
    conformance.py                                    -- the gates
    snapshot_verification.py / retention.py           -- hosted-binding
                                                         boundaries

The repository is the source of truth for implementation state; these
YAML artifacts are the source of truth for structured architecture;
generated doctrine is a projection and never a source.
"""
