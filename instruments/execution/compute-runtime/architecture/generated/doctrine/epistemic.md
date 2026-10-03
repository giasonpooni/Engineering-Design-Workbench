# Epistemic doctrine (generated -- do not edit; see doctrine_generator.py)

Evidence classes are assigned at ingest and are immutable; the class
is a total, fail-closed function of the declared extraction method.

Classes:
- asserted: a source's claim, carried by extraction from a document
- computed: the result of a declared computation
- derived: inference over other evidence
- measured: a physical measurement by a declared instrument method

Presentation vocabulary maps onto these classes; it never mints:
- computed -> computed
- hypothesized -> derived
- inferred -> derived
- manufactured -> measured
- measured -> measured
- observed -> measured
- predicted -> computed
- reported -> asserted
- simulated -> computed
- validated: NOT a class (status_on_claim)

Write barriers: proposals are not evidence (optimizer output has no
write path into the pool); derived state re-enters only through
acquisition; no operation promotes a class after ingest.
