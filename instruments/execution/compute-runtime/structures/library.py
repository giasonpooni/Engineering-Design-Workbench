"""Real structures, with their representation conventions recorded.

These are DESCRIPTIONS with recorded sources, not measurements: the
identities commit to the description; nothing here claims a physical
sample existed (COMPUTATION != MEASUREMENT, unchanged).

Conventions used throughout: Cartesian INTEGER PICOMETERS for
molecules; integer-pm lattice rows + millionth fractional sites for
crystals. Geometry sources are standard textbook equilibrium values,
rounded ONCE, here, to integer pm -- this file is where the Phase 128
canonicalization burden for these structures was paid, and the
sub-picometer rounding (<1%) is part of each recorded description.
"""

from __future__ import annotations

from structures.crystal import CrystalSite, CrystalStructure
from structures.molecule import Atom, Molecule

#: Water: O-H bond 95.7 pm, H-O-H angle 104.5 degrees. O at the origin,
#: molecule in the xz-plane, C2 axis along +z: H at
#: (+/- 95.7*sin(52.25 deg), 0, 95.7*cos(52.25 deg)) -> (+/-76, 0, 59) pm.
WATER = Molecule((
    Atom("O", 0, 0, 0),
    Atom("H", 76, 0, 59),
    Atom("H", -76, 0, 59),
))

#: Methane: C-H bond 108.7 pm, ideal tetrahedron along cube diagonals:
#: H at (+-d, +-d, +-d) with d = 108.7/sqrt(3) -> 63 pm.
METHANE = Molecule((
    Atom("C", 0, 0, 0),
    Atom("H", 63, 63, 63),
    Atom("H", 63, -63, -63),
    Atom("H", -63, 63, -63),
    Atom("H", -63, -63, 63),
))

#: FCC argon: cubic cell a = 526 pm (5.26 angstrom, exact in pm), the
#: four FCC sites.
FCC_ARGON = CrystalStructure(
    lattice=((526, 0, 0), (0, 526, 0), (0, 0, 526)),
    sites=(
        CrystalSite("Ar", 0, 0, 0),
        CrystalSite("Ar", 500_000, 500_000, 0),
        CrystalSite("Ar", 500_000, 0, 500_000),
        CrystalSite("Ar", 0, 500_000, 500_000),
    ),
)

#: Rock salt NaCl: cubic a = 564 pm; Na on the FCC sites, Cl offset to
#: the octahedral holes -- the standard B1 arrangement.
ROCK_SALT = CrystalStructure(
    lattice=((564, 0, 0), (0, 564, 0), (0, 0, 564)),
    sites=(
        CrystalSite("Na", 0, 0, 0),
        CrystalSite("Na", 500_000, 500_000, 0),
        CrystalSite("Na", 500_000, 0, 500_000),
        CrystalSite("Na", 0, 500_000, 500_000),
        CrystalSite("Cl", 500_000, 0, 0),
        CrystalSite("Cl", 0, 500_000, 0),
        CrystalSite("Cl", 0, 0, 500_000),
        CrystalSite("Cl", 500_000, 500_000, 500_000),
    ),
)
