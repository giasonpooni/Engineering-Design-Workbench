"""ExperimentalMethod: an explicit, structured representation of WHICH
measurement or validation TECHNIQUE an experimental design is asking to
perform -- distinct from `ActionCandidate.action_class` (Phase 37),
which names only a generic evidence-acquisition DOMAIN
("measurement:repeat", "model_validation:context", ...) and carries no
information about whether a measurement is a tensile test, DMA, DSC,
rheology, spectroscopy, or microscopy.

Before this module was written, every upstream structure was inspected
for anything that could justify a method concept: `ActionCandidate`,
`EvidenceRequirement`, and `materials.program`'s process association all
carry identity/context data, but nothing that names a measurement
TECHNIQUE. The one directly relevant precedent already in the frozen
SCOUT substrate is `evidence.types.DerivedValue.method: str` -- an open,
prefix-convention string (e.g. "model:A") already used to name which
technique PRODUCED a derived value. `ExperimentalMethod.kind` below
follows that exact convention (an open string, never a closed enum) for
the same reason: SCOUT itself never closed this vocabulary, so this
application-layer concept should not either.

Only two fields are justified by that inspection: `kind` (which
technique) and `parameters` (an open, method-specific settings mapping
the caller supplies -- e.g. strain rate for a tensile test, oscillation
frequency for DMA). A third candidate field, "method version/protocol
identity" (e.g. "ASTM D638"), was explicitly investigated and NOT given
its own field: nothing in the existing architecture distinguishes a
protocol reference as structurally different from any other
caller-supplied method setting, so it is expressible as an ordinary
`parameters` key (e.g. `{"protocol": "ASTM D638"}`) rather than a
fabricated new dimension. Instrument, operator, laboratory, cost, and
duration were investigated and excluded for the same reason -- no
existing structure justifies them as part of a METHOD, and this module
does not fabricate domain semantics no upstream data supports.

Identity: a method IS a reusable, referenceable concept -- the same
method (e.g. "DMA at 1Hz, 3C/min ramp") can legitimately be specified
for more than one design entry, and two independently-specified,
content-identical methods should converge on one identity rather than
being silently treated as different -- exactly the discipline every
SCOUT evidence type already establishes for its own `make_*` factory.
`make_experimental_method` therefore content-hashes `kind` +
`parameters` using the existing `evidence.identity.content_hash`; no
new hashing system is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional

from evidence.identity import content_hash


@dataclass(frozen=True)
class ExperimentalMethod:
    """`kind` is an open string (e.g. "tensile_test", "DMA", "DSC",
    "rheology", "spectroscopy", "microscopy") -- never inferred from
    `property` or `action_class`, since nothing in the existing
    architecture maps a property to the technique that would measure
    it; `kind` must always be supplied by the caller. `parameters` is
    an open, unschematized mapping, mirroring
    `Observation.content`/`Criterion.context`/`DerivedValue.content`'s
    own established discipline."""

    id: str
    kind: str
    parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        if not self.kind:
            raise ValueError("ExperimentalMethod.kind must not be empty")


def make_experimental_method(kind: str, parameters: Optional[Mapping[str, object]] = None) -> ExperimentalMethod:
    """The only supported way to construct an ExperimentalMethod --
    mirrors every `make_*` factory in `evidence/types.py`: id is always
    derived from content, never supplied by the caller."""
    parameters = parameters or {}
    method_id = content_hash({"kind": kind, "parameters": dict(sorted(parameters.items()))})
    return ExperimentalMethod(id=method_id, kind=kind, parameters=parameters)
