"""GROMACS bridge: STRUCTURE -> deterministic .gro bytes -> the existing
external-execution boundary.

The path (and its trust level, stated exactly):

    Molecule --molecule_to_gro--> .gro bytes --> ExecutionSpecification
        (program = gmx version line + topology, configuration = .mdp,
         input = the .gro)  --> run_gromacs_specification (unchanged)

Everything downstream is the stage-1/4 GROMACS machinery with its
documented trust posture: an EXTERNALLY EXECUTED computation whose
identities are computed by our module from bytes it holds -- weaker
than the Rust engine, far weaker than a zkVM proof. NOTHING about
proving the structural kernels transfers here: a proof of a molecule's
pairwise or Rg statement says NOTHING about what GROMACS computed over
the same structure. The two share only the structure's identity, in the
structural ledger.

DETERMINISM of the bridge itself: integer picometers convert exactly to
the .gro's 3-decimal nanometers (1 pm = 0.001 nm, so %.3f is lossless),
and the structure's origin maps to the box centre by integer shift --
same molecule, same box, same bytes, always.
"""

from __future__ import annotations

from structures.molecule import Molecule

#: The recorded argon force-field convention for structural GROMACS
#: workloads here -- byte-compatible with the stage-1 fixture (LJ argon,
#: sigma 0.3401 nm, epsilon 0.978638 kJ/mol), parameterized only by the
#: molecule count line. CALLER-DECLARED science, recorded once.
_ARGON_TOPOLOGY_TEMPLATE = """[ defaults ]
1 2 yes 0.5 0.5

[ atomtypes ]
Ar 18 39.948 0.0 A 0.3401 0.978638

[ moleculetype ]
AR 1

[ atoms ]
1 Ar 1 AR AR 1 0.0 39.948

[ system ]
Argon cluster

[ molecules ]
AR {count}
"""


def argon_topology(count: int) -> bytes:
    """The argon topology for a `count`-atom cluster."""
    return _ARGON_TOPOLOGY_TEMPLATE.format(count=count).encode()


def molecule_to_gro(molecule: Molecule, box_pm: tuple[int, int, int],
                    title: str = "STE structure") -> bytes:
    """Deterministic .gro bytes for `molecule` in a rectangular box of
    integer-pm edges, the structure's origin at the box centre.

    Formatting is the fixed-width .gro convention
    (%5d%-5s%5s%5d%8.3f%8.3f%8.3f); every float printed is an exact
    multiple of 0.001, so no rounding decision is hidden in here."""
    lines = [title, f"{len(molecule.atoms):5d}"]
    for index, atom in enumerate(molecule.atoms, start=1):
        name = atom.element.upper()
        shifted = (atom.x + box_pm[0] // 2, atom.y + box_pm[1] // 2,
                   atom.z + box_pm[2] // 2)
        coords = "".join(f"{pm / 1000:8.3f}" for pm in shifted)
        lines.append(f"{index:5d}{name:<5s}{name:>5s}{index:5d}{coords}")
    lines.append("".join(f"{edge / 1000:10.5f}" for edge in box_pm))
    return ("\n".join(lines) + "\n").encode()
