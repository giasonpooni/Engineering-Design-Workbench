"""Molecule: atoms with Cartesian integer coordinates, content-addressed.

THE REPRESENTATION (deliberately minimal, per the vertical's own
overbuild ban): an ordered tuple of atoms, each an element symbol plus
Cartesian coordinates in INTEGER PICOMETERS. Integers make identity a
property instead of a formatting accident -- no float printing, no
rounding convention, no locale.

IDENTITY: `commit(ste.structure.molecule.v1, [canonical bytes])` over

    ste-molecule v1
    convention cartesian-pm
    atom <Element> <x> <y> <z>        (one line per atom, declared order)

Deliberately NOT in it: names/labels, timestamps, hostnames, PIDs,
occurrence numbers, provenance -- a structure is the same structure no
matter when or where it is written down.

CANONICALIZATION -- exactly what determinism required, nothing more
(probed empirically against the kernels this lowers into):

  - atom ORDER is preserved and identity-bearing: the pairwise and Rg
    kernels consume atoms in input order, so reordering is a different
    computation; silently sorting would equate computations the engine
    distinguishes. Physical equivalence (a relabeled H2O is "the same
    molecule") is a DIFFERENT relation from computational identity and
    is not established here.
  - coordinates are exact integers: no precision rule is needed because
    no rounding ever happens inside this type; whoever converts from
    angstrom floats bears the Phase 128 canonicalization burden ONCE,
    at construction.
  - element symbols are validated (capitalized chemical form, e.g. "H",
    "Ar") and never normalized: "h" is refused at construction, not
    silently equated with "H".

WHAT AN IDENTITY DOES NOT CLAIM: that this molecule physically exists,
that these coordinates were measured, or that the geometry is a minimum
of anything. It identifies a DESCRIPTION. (COMPUTATION != MEASUREMENT,
unchanged.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple

from execution.commitments import commit_hex

MOLECULE_TAG = "ste.structure.molecule.v1"

_ELEMENT_FORM = re.compile(r"^[A-Z][a-z]?$")


class StructureError(ValueError):
    """A structure that cannot be represented is refused, not repaired."""


@dataclass(frozen=True)
class Atom:
    """One atom: capitalized element symbol, Cartesian integer pm."""

    element: str
    x: int
    y: int
    z: int

    def __post_init__(self):
        if not _ELEMENT_FORM.match(self.element):
            raise StructureError(
                f"element {self.element!r} is not a capitalized chemical symbol; "
                f"refusing rather than normalizing"
            )
        for coordinate in (self.x, self.y, self.z):
            if not isinstance(coordinate, int) or isinstance(coordinate, bool):
                raise StructureError(
                    f"coordinate {coordinate!r} is not an integer; the "
                    f"float->pm conversion burden belongs to the caller, once"
                )


@dataclass(frozen=True)
class Molecule:
    """An ordered, non-empty atom tuple. See the module docstring for
    the identity contract."""

    atoms: Tuple[Atom, ...]

    def __post_init__(self):
        if not self.atoms:
            raise StructureError("a molecule has at least one atom")

    def canonical_bytes(self) -> bytes:
        lines = ["ste-molecule v1", "convention cartesian-pm"]
        lines += [f"atom {a.element} {a.x} {a.y} {a.z}" for a in self.atoms]
        return ("\n".join(lines) + "\n").encode()

    def identity(self) -> str:
        return commit_hex(MOLECULE_TAG, [self.canonical_bytes()])
