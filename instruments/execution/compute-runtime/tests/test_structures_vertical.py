"""Structural vertical locks -- structures are content-addressed
DESCRIPTIONS that lower into the unchanged execution substrate.

Proof budget: 1 real Nexus proof (water's pairwise statement,
manufactured once and reused); everything else is proof-free -- the
native engine runs in milliseconds.
"""

from __future__ import annotations

import pathlib

import pytest

from execution.engine import default_cli_path, run_specification
from execution.proving import (
    ProvedRunError,
    default_nexus_host_path,
    prove_and_verify_result,
)
from structures.crystal import CrystalSite, CrystalStructure
from structures.library import FCC_ARGON, METHANE, ROCK_SALT, WATER
from structures.lowering import (
    LoweringError,
    crystal_to_lattice_spec,
    molecule_to_pairwise_spec,
    molecule_to_rg_spec,
)
from structures.molecule import Atom, Molecule, StructureError

pytestmark = pytest.mark.skipif(
    not default_cli_path().exists(),
    reason="execution engine not built; environment gap",
)


# -- structural identity ------------------------------------------------------------------------------


def test_molecule_identity_is_content_and_only_content():
    assert WATER.identity() == Molecule(WATER.atoms).identity(), "deterministic"
    moved = Molecule((WATER.atoms[0], Atom("H", 77, 0, 59), WATER.atoms[2]))
    relabeled = Molecule((Atom("S", 0, 0, 0),) + WATER.atoms[1:])
    reordered = Molecule((WATER.atoms[1], WATER.atoms[0], WATER.atoms[2]))
    identities = {WATER.identity(), moved.identity(), relabeled.identity(),
                  reordered.identity()}
    assert len(identities) == 4, (
        "coordinate, element, and order changes are all identity changes")


def test_structures_are_refused_not_repaired():
    with pytest.raises(StructureError):
        Atom("h", 0, 0, 0)  # not normalized to "H"
    with pytest.raises(StructureError):
        Atom("H", 0.5, 0, 0)  # the float->pm burden is the caller's
    with pytest.raises(StructureError):
        Molecule(())
    with pytest.raises(StructureError):
        CrystalSite("Ar", 1_000_000, 0, 0)  # not wrapped into the cell
    with pytest.raises(StructureError):
        CrystalStructure(((1, 0, 0), (0, 1, 0)), (CrystalSite("Ar", 0, 0, 0),))


def test_crystal_identity_distinct_from_molecular_identity():
    strained = CrystalStructure(
        lattice=((527, 0, 0), (0, 526, 0), (0, 0, 526)), sites=FCC_ARGON.sites)
    assert FCC_ARGON.identity() != strained.identity(), "lattice is identity"
    assert FCC_ARGON.identity() != ROCK_SALT.identity()
    # different tags: a crystal identity can never collide with a
    # molecule identity even over crafted content
    assert not any(m.identity() == c.identity()
                   for m in (WATER, METHANE) for c in (FCC_ARGON, ROCK_SALT))


# -- lowering: the one insertion point ---------------------------------------------------------------


def test_lowering_is_deterministic_and_refuses_unknown_elements():
    assert (molecule_to_pairwise_spec(WATER).identity()
            == molecule_to_pairwise_spec(WATER).identity())
    assert (crystal_to_lattice_spec(FCC_ARGON).identity()
            == crystal_to_lattice_spec(FCC_ARGON).identity())
    with pytest.raises(LoweringError):
        molecule_to_rg_spec(Molecule((Atom("Xe", 0, 0, 0),)))  # no recorded mass


def test_element_blindness_is_a_fact_about_the_kernel_not_the_ledger():
    """The pairwise kernel consumes coordinates only: an element change
    moves the STRUCTURAL identity but not the pairwise input commitment
    -- a pairwise proof binds geometry, nothing else. The Rg kernel
    consumes masses, so the SAME element change moves its input
    commitment. This is the trust boundary, executable."""
    sulfur_water = Molecule((Atom("S", 0, 0, 0),) + WATER.atoms[1:])
    assert sulfur_water.identity() != WATER.identity()
    assert (molecule_to_pairwise_spec(sulfur_water).identity()
            == molecule_to_pairwise_spec(WATER).identity()), (
        "pairwise: element-blind, same statement")
    assert (molecule_to_rg_spec(sulfur_water).identity()
            != molecule_to_rg_spec(WATER).identity()), (
        "rg: the mass is consumed, different statement")


def test_structural_tamper_moves_the_computation_identity():
    moved = Molecule((WATER.atoms[0], Atom("H", 77, 0, 59), WATER.atoms[2]))
    assert (molecule_to_pairwise_spec(moved).identity()
            != molecule_to_pairwise_spec(WATER).identity())
    assert (molecule_to_pairwise_spec(moved).input_identity()
            != molecule_to_pairwise_spec(WATER).input_identity())
    strained = CrystalStructure(
        lattice=((527, 0, 0), (0, 526, 0), (0, 0, 526)), sites=FCC_ARGON.sites)
    assert (crystal_to_lattice_spec(strained).identity()
            != crystal_to_lattice_spec(FCC_ARGON).identity())


# -- real structures execute through the unchanged engine --------------------------------------------


def test_water_and_methane_execute_natively():
    for molecule in (WATER, METHANE):
        pairwise = run_specification(molecule_to_pairwise_spec(molecule))
        rg = run_specification(molecule_to_rg_spec(molecule))
        assert pairwise.status == "completed" and rg.status == "completed"
    # methane's Rg2, recomputed independently in integer arithmetic:
    # com = (12*0 + 4*1*63*[signs])/16 = 0 per axis (symmetric), so
    # rg2 = sum(m*|r|^2)/16 = (4 * 1 * 3*63^2) / 16
    rg = run_specification(molecule_to_rg_spec(METHANE))
    expected = (4 * 3 * 63 * 63) // 16
    assert int.from_bytes(rg.output, "little", signed=True) == expected


def test_fcc_argon_and_rock_salt_execute_with_exact_lattice_arithmetic():
    out = run_specification(crystal_to_lattice_spec(FCC_ARGON))
    assert out.status == "completed"
    volume = int.from_bytes(out.output[:16], "little", signed=True)
    mind2 = int.from_bytes(out.output[16:], "little", signed=True)
    assert volume == 526 ** 3, "V = |det L| exactly"
    assert mind2 == 526 ** 2 // 2, "FCC nearest neighbour a/sqrt(2)"

    salt = run_specification(crystal_to_lattice_spec(ROCK_SALT))
    mind2 = int.from_bytes(salt.output[16:], "little", signed=True)
    assert mind2 == (564 // 2) ** 2, "B1 nearest neighbour a/2 (Na-Cl)"


def test_periodicity_is_semantic_a_single_site_still_has_neighbours():
    lonely = CrystalStructure(
        lattice=((100, 0, 0), (0, 200, 0), (0, 0, 300)),
        sites=(CrystalSite("Ar", 0, 0, 0),))
    out = run_specification(crystal_to_lattice_spec(lonely))
    mind2 = int.from_bytes(out.output[16:], "little", signed=True)
    assert mind2 == 100 * 100, "its own image one cell over"
    # while a single-ATOM molecule has no pairs at all
    single = run_specification(
        molecule_to_pairwise_spec(Molecule((Atom("Ar", 0, 0, 0),))))
    assert int.from_bytes(single.output, "little", signed=True) == 0


# -- the proof boundary ------------------------------------------------------------------------------


def test_unproven_kernels_are_refused_attributably(tmp_path):
    """No guest is registered for the Rg or crystal kernels: the stage-5
    gate refuses to prove them with ANY artifact -- an explicit refusal,
    never a silent skip or a false warrant."""
    nexus_host = default_nexus_host_path()
    if not nexus_host.exists():
        pytest.skip("nexus not built; environment gap")
    from tests.test_execution_stage8_warrant_cache import NEXUS_ELF

    spec = molecule_to_rg_spec(WATER)
    native = run_specification(spec)
    with pytest.raises(ProvedRunError, match="no built guest is registered"):
        prove_and_verify_result(native, spec, tmp_path / "p.bin", nexus_host, NEXUS_ELF)


# -- the GROMACS bridge ------------------------------------------------------------------------------


def _find_gmx():
    import os
    import pathlib
    import shutil

    candidate = os.environ.get("STE_GMX_BIN")
    if candidate and pathlib.Path(candidate).exists():
        return pathlib.Path(candidate)
    for name in ("gmx_d", "gmx"):
        found = shutil.which(name)
        if found:
            return pathlib.Path(found)
    return None


def test_gromacs_consumes_the_structure_through_the_existing_boundary():
    """A real argon-trimer Molecule lowers to deterministic .gro bytes
    and runs through the UNCHANGED external GROMACS workload; moving one
    atom moves the specification identity. No claim travels from any
    structural proof to this execution -- it is externally executed
    computation with the stage-1 trust posture, unchanged."""
    gmx = _find_gmx()
    if gmx is None:
        pytest.skip("no gmx binary (set STE_GMX_BIN); environment gap")
    from execution.gromacs import (
        gmx_version_line,
        gromacs_program_descriptor,
        run_gromacs_specification,
    )
    from execution.specification import ExecutionSpecification
    from structures.gromacs_bridge import argon_topology, molecule_to_gro
    from structures.molecule import Atom, Molecule

    trimer = Molecule((Atom("Ar", 0, 0, 0), Atom("Ar", 380, 0, 0),
                       Atom("Ar", 190, 329, 0)))
    moved = Molecule((Atom("Ar", 0, 0, 0), Atom("Ar", 381, 0, 0),
                      Atom("Ar", 190, 329, 0)))
    box = (3000, 3000, 3000)
    mdp = (b"integrator = md\nnsteps = 0\ncutoff-scheme = Verlet\n"
           b"coulombtype = Cut-off\nvdwtype = Cut-off\n"
           b"rlist = 1.0\nrcoulomb = 1.0\nrvdw = 1.0\n")
    descriptor = gromacs_program_descriptor(gmx_version_line(gmx), argon_topology(3))

    def spec_for(molecule):
        return ExecutionSpecification(
            program=descriptor, configuration=mdp,
            input_payload=molecule_to_gro(molecule, box))

    # the bridge is deterministic, and structural tamper moves the spec
    assert molecule_to_gro(trimer, box) == molecule_to_gro(trimer, box)
    assert spec_for(trimer).identity() != spec_for(moved).identity()

    result = run_gromacs_specification(spec_for(trimer), gmx)
    assert result.status == "completed"
    assert result.output.startswith(b"potential_kj_per_mol ")


# -- molecular proofs and warrant reuse --------------------------------------------------------------


def test_water_pairwise_statement_proves_reuses_and_tamper_misses(tmp_path):
    """The full chain on a REAL molecule with an instrumented host:
    water's pairwise statement proves once on Nexus (through the
    existing reproducible pairwise guest); a repeat of the identical
    structure HITS and re-verifies without proving; a moved atom is a
    different statement -- a cache MISS, structurally; and corrupting
    the stored proof makes the hit FAIL verification. One structure,
    three ledgers, none collapsed."""
    from campaign.warrant_cache import WarrantCache, statement_key
    from execution.proving import (
        prove_and_verify_result,
        verify_existing_proof,
    )
    from tests.test_execution_stage8_warrant_cache import _instrumented_nexus

    nexus_host = default_nexus_host_path()
    pairwise_elf = (pathlib.Path(__file__).resolve().parent.parent
                    / "zk" / "artifacts" / "nexus-pairwise.elf")
    if not (nexus_host.exists() and pairwise_elf.exists()):
        pytest.skip("nexus pairwise guest not built; environment gap")

    shim, log = _instrumented_nexus(tmp_path)
    cache = WarrantCache(tmp_path / "cache")
    spec = molecule_to_pairwise_spec(WATER)
    native = run_specification(spec)

    # manufacture once, store
    proved = prove_and_verify_result(native, spec, tmp_path / "w.bin", shim, pairwise_elf)
    key = statement_key("nexus", pairwise_elf, spec)
    cache.store(key, pathlib.Path(proved.proof_path).read_bytes(), "nexus", spec.identity())

    # the identical structure -> the identical statement -> HIT, re-verified
    again = molecule_to_pairwise_spec(Molecule(WATER.atoms))
    assert statement_key("nexus", pairwise_elf, again) == key
    hit = cache.lookup(key)
    fields = verify_existing_proof(run_specification(again), again,
                                   hit.proof_path, shim, pairwise_elf)
    assert fields["outcome"] == "verified"
    calls = log.read_text().split()
    assert calls.count("prove") == 1 and calls.count("verify") >= 2

    # structural tamper -> different statement -> MISS (the old warrant
    # stays valid for its own statement only)
    moved = Molecule((WATER.atoms[0], Atom("H", 77, 0, 59), WATER.atoms[2]))
    assert cache.lookup(
        statement_key("nexus", pairwise_elf, molecule_to_pairwise_spec(moved))) is None

    # corrupted warrant -> hit still goes to the verifier, and FAILS
    raw = bytearray(hit.proof_path.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    hit.proof_path.write_bytes(bytes(raw))
    fields = verify_existing_proof(native, spec, hit.proof_path, shim, pairwise_elf)
    assert fields["outcome"] == "failed"
