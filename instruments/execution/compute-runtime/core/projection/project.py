"""State projection (§13).

Primitive 5's role is NOT estimation -- it is a pure, deterministic
projection of a frozen canonical Version. `project_state` performs no
inference, no I/O, no wall-clock reads, and no randomness. Given the same
Version, it always returns an equal ProjectedState (I6, I7).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Tuple

from core.canonical.state import EdgeRecord, Field
from core.canonical.version import Version, VersionId


@dataclass(frozen=True)
class ProjectedState:
    source_version: VersionId
    schema_version: str
    fields: Mapping[str, Field]
    edges: Tuple[EdgeRecord, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        object.__setattr__(self, "edges", tuple(self.edges))


def restore_projection(store, version_id: VersionId, config) -> ProjectedState:
    """§19 deterministic replay contract:

        restore_projection(store, v.id, config) == project_state(v)

    for the same v.id, regardless of how much time has passed or how
    many other versions have since been created, PROVIDED
    config.compiler_version matches what was pinned when v was compiled.
    Because VersionId is content-addressed (§4) and project_state is pure
    (§13), this follows structurally -- `config` is accepted for call-site
    symmetry with the compiler stage, not consulted by this function's
    body."""
    version = store.get(version_id)
    return project_state(version)


def project_state(version: Version) -> ProjectedState:
    """Pure. Precondition: `version` is already a frozen, immutable
    Version. Postcondition: the returned ProjectedState shares no mutable
    references with `version.state` -- Field/EdgeRecord instances are
    themselves immutable, and the containing mapping/tuple are freshly
    copied, so mutating call sites (impossible on frozen types, but
    defended against regardless) can never reach back into `version`."""
    return ProjectedState(
        source_version=version.id,
        schema_version=version.schema_version,
        fields=dict(version.state.fields),
        edges=tuple(version.state.edges),
    )
