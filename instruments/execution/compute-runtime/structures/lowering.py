"""Deterministic lowering: STRUCTURE -> ExecutionSpecification.

This is the vertical's whole insertion point into the substrate: a pure
function from a content-addressed structure to the content-addressed
computation request the EXISTING engine executes. Nothing here runs,
proves, records, or admits anything.

    Molecule --lower--> ExecutionSpecification --(unchanged machinery)-->
        execution, proofs, warrants, evidence

THE TRUST BOUNDARY, stated exactly: a proof downstream binds the BYTES
the guest consumed -- that is, what the lowering PUT into the input
payload -- never the structure object itself. So:

  - `molecule_to_pairwise_spec` lowers coordinates only (the pairwise
    kernel is element-blind). A pairwise proof binds the geometry and
    NOTHING about element identity: two molecules differing only in an
    element lower to the SAME pairwise input, and the structural
    identities differing is a fact about the structure ledger, not
    about that proof.
  - `molecule_to_rg_spec` lowers (mass, x, y, z) where mass is the
    element's integer atomic mass -- element identity participates in
    the consumed bytes, so an element change moves the input
    commitment. The mass table below is therefore part of the lowering
    convention: CALLER-DECLARED science, recorded here once.

An unknown element is REFUSED (`LoweringError`), never guessed.

MORPHO (recorded decision, per the vertical's Part VIII): the question
"can a structure lower into an existing ExecutionSpecification without
a parallel execution architecture?" is answered YES by this module
directly -- the lowering is a total, deterministic, ~20-line function
per kernel, and the repository's `morpho` compiler pipeline
(lexer/parser/IR for its own source language) would add a language
between two byte formats that already agree. Morpho becomes justified
at this boundary when a structural transformation NEEDS a program
representation (parameterized generation, symbolic manipulation), not
for fixed-format encoding; that need has not yet appeared in a real
workload, so no Morpho stage is inserted here.
"""

from __future__ import annotations

from execution.specification import (
    CRYSTAL_LATTICE_DESCRIPTOR,
    PAIRWISE_ENERGY_DESCRIPTOR,
    RADIUS_OF_GYRATION_DESCRIPTOR,
    ExecutionSpecification,
    encode_crystal_input,
    encode_positions,
    encode_rg_input,
)
from structures.crystal import CrystalStructure
from structures.molecule import Molecule

#: Integer atomic masses (amu) -- the lowering convention for the Rg
#: kernel's mass field. Deliberately integers (the kernel's arithmetic
#: is integer); deliberately small (exactly the elements real workloads
#: here use; extending the table is a recorded change, not a guess).
ELEMENT_MASSES = {
    "H": 1,
    "C": 12,
    "N": 14,
    "O": 16,
    "S": 32,
    "Ar": 40,
}


class LoweringError(ValueError):
    """A structure this lowering cannot honestly represent is refused."""


def molecule_to_pairwise_spec(molecule: Molecule) -> ExecutionSpecification:
    """Coordinates only -- see the module docstring for exactly what a
    proof of this specification does and does not bind."""
    positions = [(a.x, a.y, a.z) for a in molecule.atoms]
    return ExecutionSpecification(
        PAIRWISE_ENERGY_DESCRIPTOR, b"", encode_positions(positions)
    )


def molecule_to_rg_spec(molecule: Molecule) -> ExecutionSpecification:
    """(mass, x, y, z) per atom -- element identity enters the consumed
    bytes through the mass table above."""
    atoms = []
    for atom in molecule.atoms:
        mass = ELEMENT_MASSES.get(atom.element)
        if mass is None:
            raise LoweringError(
                f"no recorded integer mass for element {atom.element!r}; "
                f"refusing rather than guessing"
            )
        atoms.append((mass, atom.x, atom.y, atom.z))
    return ExecutionSpecification(RADIUS_OF_GYRATION_DESCRIPTOR, b"", encode_rg_input(atoms))


def crystal_to_lattice_spec(crystal: CrystalStructure) -> ExecutionSpecification:
    """Lattice rows (pm) + fractional sites (millionths), exactly the
    crystal kernel's input convention. Element symbols do not enter
    this kernel's consumed bytes (volume and neighbour distances are
    element-blind); they remain structural-ledger facts."""
    return ExecutionSpecification(
        CRYSTAL_LATTICE_DESCRIPTOR,
        b"",
        encode_crystal_input(
            [tuple(row) for row in crystal.lattice],
            [(s.fx, s.fy, s.fz) for s in crystal.sites],
        ),
    )
