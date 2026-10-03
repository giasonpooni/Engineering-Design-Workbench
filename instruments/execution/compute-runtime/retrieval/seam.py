"""The InquiryState seam -- deliberately the smallest possible boundary
marker, not an implementation.

`docs/RETRIEVAL_ARCHITECTURE.md` and this phase's own instructions are
explicit: do NOT fully implement InquiryState yet. What follows is only
enough to give a future InquiryState something concrete to attach to --
a reference to which ContextPackage it was opened from, and when. It
holds no mutable slots, no hypothesis/derived-value storage, and no
computation of any kind, because none of that has a settled design yet
(`docs/COMPUTATIONAL_COMMONS.md`'s own InquiryState section is explicitly
conceptual, not implemented).

    ContextPackage  = selected persistent reality (this package)
    InquiryState    = a temporary computational world built FROM that
                       reality (future phase; NOT this dataclass)

`InquirySeam` is not InquiryState. It is the seam between the two --
proof the two concepts are already distinguishable in code, without
committing to InquiryState's eventual shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from retrieval.context import ContextPackage


@dataclass(frozen=True)
class InquirySeam:
    context_id: str
    opened_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock


def open_inquiry_seam(context: ContextPackage, opened_at: str) -> InquirySeam:
    """The only operation this seam supports: recording that a
    ContextPackage was handed off toward computation. It creates no
    mutable state, performs no computation, and is not itself
    InquiryState -- see module docstring."""
    return InquirySeam(context_id=context.id, opened_at=opened_at)
