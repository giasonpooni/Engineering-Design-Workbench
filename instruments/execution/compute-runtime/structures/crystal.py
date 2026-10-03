"""CrystalStructure: a periodic lattice with fractional sites.

A crystal is SEMANTICALLY periodic -- its nearest neighbour may be a
copy of one of its own atoms one cell over -- so it is a distinct type
with a distinct identity domain, not a molecule with extra fields. The
crystal kernel makes the difference executable: a single-site crystal
still has neighbours; a single-atom molecule has none.

THE REPRESENTATION: three integer lattice row vectors in picometers
(an explicit 3x3 matrix, row-major: a, b, c) plus an ordered tuple of
sites, each an element symbol with FRACTIONAL coordinates in integer
millionths of the corresponding lattice vector.

IDENTITY: `commit(ste.structure.crystal.v1, [canonical bytes])` over

    ste-crystal v1
    convention fractional-millionths lattice-pm row-major
    lattice <ax> <ay> <az> <bx> <by> <bz> <cx> <cy> <cz>
    site <Element> <fx> <fy> <fz>       (one line per site, declared order)

The same canonicalization decisions as `Molecule`, for the same probed
reasons: site order preserved (the kernel consumes it), integers exact,
element symbols validated never normalized, and no names, timestamps,
hosts, PIDs or occurrences anywhere near the identity. Lattice ROW
ORDER (a, b, c) is identity-bearing: swapping rows permutes the matrix
the kernel consumes.

An identity claims a DESCRIPTION, never that a physical crystal exists
or was measured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from execution.commitments import commit_hex
from structures.molecule import _ELEMENT_FORM, StructureError

CRYSTAL_TAG = "ste.structure.crystal.v1"


@dataclass(frozen=True)
class CrystalSite:
    """One site: capitalized element symbol, fractional integer
    millionths (each in [0, 1000000))."""

    element: str
    fx: int
    fy: int
    fz: int

    def __post_init__(self):
        if not _ELEMENT_FORM.match(self.element):
            raise StructureError(
                f"element {self.element!r} is not a capitalized chemical symbol"
            )
        for fraction in (self.fx, self.fy, self.fz):
            if not isinstance(fraction, int) or isinstance(fraction, bool):
                raise StructureError(f"fraction {fraction!r} is not an integer")
            if not 0 <= fraction < 1_000_000:
                raise StructureError(
                    f"fraction {fraction} is outside [0, 1000000); reduce into "
                    f"the cell explicitly -- this type does not wrap silently"
                )


@dataclass(frozen=True)
class CrystalStructure:
    """Three integer lattice rows (pm) and a non-empty site tuple."""

    lattice: Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]
    sites: Tuple[CrystalSite, ...]

    def __post_init__(self):
        if len(self.lattice) != 3 or any(len(row) != 3 for row in self.lattice):
            raise StructureError("the lattice is three integer row vectors")
        for row in self.lattice:
            for component in row:
                if not isinstance(component, int) or isinstance(component, bool):
                    raise StructureError(f"lattice component {component!r} is not an integer")
        if not self.sites:
            raise StructureError("a crystal has at least one site")

    def canonical_bytes(self) -> bytes:
        flat = " ".join(str(c) for row in self.lattice for c in row)
        lines = [
            "ste-crystal v1",
            "convention fractional-millionths lattice-pm row-major",
            f"lattice {flat}",
        ]
        lines += [f"site {s.element} {s.fx} {s.fy} {s.fz}" for s in self.sites]
        return ("\n".join(lines) + "\n").encode()

    def identity(self) -> str:
        return commit_hex(CRYSTAL_TAG, [self.canonical_bytes()])
