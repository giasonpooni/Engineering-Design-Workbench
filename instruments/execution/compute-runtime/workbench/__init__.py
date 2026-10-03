"""The interactive interface layer above `experiment/` -- Phase 68.
`workbench -> experiment -> materials -> evidence/retrieval`, never the
reverse; `materials/` remains completely unaware that an interactive
interface exists (nothing here is imported by anything beneath it, and
this package changed no file outside itself). See `workbench.cli` and
`workbench.interaction` for the actual implementation, and
`docs/EXPERIMENT_ARCHITECTURE.md` for the boundary this package sits
on top of without altering."""
