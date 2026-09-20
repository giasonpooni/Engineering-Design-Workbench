# Kernel

This repository owns the schematic IR and eligibility routing.
It does not own A, V, samples, or dispositions.

A fixture A is tagged fixture=true and does not open PLSR.
The adapter in schematics.adapters.jspt wraps jacobian_at against
giasonpooni/Jacobian-Sensitivity-Propagation-Testbed@7399ab03087b27683620b4c57f97b2ac14546c7f.
Missing sensitivity is NOT_CHECKED, not a sample.
RCI digest binding records the supplied digest. The separate record-binding path
validates a supplied measurement record; neither path acquires a physical sample.
