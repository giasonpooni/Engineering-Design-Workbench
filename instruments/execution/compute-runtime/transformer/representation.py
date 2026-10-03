"""TransformerRepresentation: canonical scientific state, projected to
typed tokens.

The representation is DISTINGUISHABLE from everything around it: its
identity (`ste.transformer.representation.v1`) commits to the token
semantics and values -- it is not the molecule's structural identity
(which commits to the description), not the specification identity
(which commits to program+config+input), and not any evidence identity.
The tensor encoding below it is a pure computational projection of this
representation into the attention kernel's integer token matrix.

The first encoder consumes the EXISTING canonical molecular
representation (structures.Molecule) and the EXISTING element->mass
convention (structures.lowering.ELEMENT_MASSES) -- no duplicate schema,
no prose input: structured state in, typed tokens out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from execution.commitments import commit_hex
from structures.lowering import ELEMENT_MASSES, LoweringError
from structures.molecule import Molecule

REPRESENTATION_TAG = "ste.transformer.representation.v1"

#: token layout for molecular state: (mass, x, y, z) -- d = 4
MOLECULE_TOKEN_DIM = 4


@dataclass(frozen=True)
class TransformerRepresentation:
    """A typed token sequence: n tokens of d integer features, with the
    declared feature semantics carried alongside the values."""

    feature_semantics: Tuple[str, ...]
    tokens: Tuple[Tuple[int, ...], ...]

    def __post_init__(self):
        d = len(self.feature_semantics)
        if d == 0 or not self.tokens:
            raise ValueError("a representation has at least one token and one feature")
        if any(len(row) != d for row in self.tokens):
            raise ValueError("every token carries exactly the declared features")

    @property
    def d(self) -> int:
        return len(self.feature_semantics)

    def identity(self) -> str:
        canonical = ";".join(self.feature_semantics) + "|" + "|".join(
            ",".join(str(v) for v in row) for row in self.tokens)
        return commit_hex(REPRESENTATION_TAG, [canonical.encode()])

    def tensor(self) -> Tuple[Tuple[int, ...], ...]:
        """The computational projection: the integer token matrix the
        kernel consumes. Deliberately trivial here -- the point is the
        BOUNDARY (representation identity vs tensor bytes), not a
        framework."""
        return self.tokens


def molecule_representation(molecule: Molecule) -> TransformerRepresentation:
    """Canonical molecular state -> per-atom tokens (mass, x, y, z).
    Unknown elements are refused (the lowering convention's rule),
    never guessed."""
    tokens = []
    for atom in molecule.atoms:
        mass = ELEMENT_MASSES.get(atom.element)
        if mass is None:
            raise LoweringError(
                f"no recorded integer mass for element {atom.element!r}; "
                f"refusing rather than guessing"
            )
        tokens.append((mass, atom.x, atom.y, atom.z))
    return TransformerRepresentation(
        feature_semantics=("mass_amu", "x_pm", "y_pm", "z_pm"),
        tokens=tuple(tokens),
    )
