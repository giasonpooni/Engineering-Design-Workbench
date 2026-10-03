"""The GROMACS single-point-energy workload -- a REAL scientific
computation through the STE identity discipline, audited live.

Skips (with the reason stated as an environment gap, never an
architectural pass) when no `gmx`/`gmx_d` binary is reachable via
STE_GMX_BIN or PATH. In the development environment the binary is built
from the `notationsystems/gromacs` fork: double precision, SIMD off.
"""

from __future__ import annotations

import os
import pathlib
import shutil

import pytest

from execution.gromacs import (
    FAULT_GROMPP,
    gmx_version_line,
    gromacs_program_descriptor,
    run_gromacs_specification,
)
from execution.specification import ExecutionSpecification

def _find_gmx():
    candidate = os.environ.get("STE_GMX_BIN")
    if candidate and pathlib.Path(candidate).exists():
        return pathlib.Path(candidate)
    for name in ("gmx_d", "gmx"):
        found = shutil.which(name)
        if found:
            return pathlib.Path(found)
    return None

GMX = _find_gmx()
pytestmark = pytest.mark.skipif(
    GMX is None,
    reason="no gmx binary (set STE_GMX_BIN); environment gap, not an architectural pass",
)

TOPOLOGY = b"""[ defaults ]
1 2 yes 0.5 0.5

[ atomtypes ]
Ar 18 39.948 0.0 A 0.3401 0.978638

[ moleculetype ]
AR 1

[ atoms ]
1 Ar 1 AR AR 1 0.0 39.948

[ system ]
Argon pair

[ molecules ]
AR 2
"""

MDP = b"""integrator = md
nsteps = 0
cutoff-scheme = Verlet
coulombtype = Cut-off
vdwtype = Cut-off
rlist = 1.0
rcoulomb = 1.0
rvdw = 1.0
"""

def _gro(x2: float) -> bytes:
    return (
        "Argon pair\n    2\n"
        "    1AR     AR    1   1.000   1.000   1.000\n"
        f"    2AR     AR    2   {x2:.3f}   1.000   1.000\n"
        "   3.00000   3.00000   3.00000\n"
    ).encode()

def _spec(x2: float = 1.4) -> ExecutionSpecification:
    descriptor = gromacs_program_descriptor(gmx_version_line(GMX), TOPOLOGY)
    return ExecutionSpecification(program=descriptor, configuration=MDP, input_payload=_gro(x2))

def test_real_workload_completes_with_a_physical_shaped_result():
    result = run_gromacs_specification(_spec(), GMX)
    assert result.status == "completed"
    assert result.output is not None and result.output.startswith(b"potential_kj_per_mol ")
    # 0.4 nm separation with argon LJ (sigma=0.3401) is in the attractive
    # well: the potential must be negative. A sign check is a semantic
    # check on the WORKLOAD, not on the substrate.
    assert float(result.output.split()[1]) < 0.0
    assert result.computation_identity is not None

def test_repeat_determinism_same_binary_same_machine():
    """Two full grompp->mdrun->energy pipelines, two fresh workdirs: the
    energy TEXT and therefore every identity must agree. This is the
    claimed determinism scope (same binary, same machine) exercised, and
    nothing broader is claimed."""
    first = run_gromacs_specification(_spec(), GMX)
    second = run_gromacs_specification(_spec(), GMX)
    assert first.output == second.output
    assert first.computation_identity == second.computation_identity

def test_geometry_change_changes_input_and_computation_identity():
    near = run_gromacs_specification(_spec(1.38), GMX)
    far = run_gromacs_specification(_spec(1.80), GMX)
    assert near.input_identity != far.input_identity
    assert near.program_identity == far.program_identity
    assert near.output != far.output
    assert near.computation_identity != far.computation_identity

def test_engine_version_is_part_of_the_program():
    a = gromacs_program_descriptor("GROMACS version 2026.0", TOPOLOGY)
    b = gromacs_program_descriptor("GROMACS version 2026.1", TOPOLOGY)
    sa = ExecutionSpecification(a, MDP, _gro(1.4))
    sb = ExecutionSpecification(b, MDP, _gro(1.4))
    assert sa.program_identity() != sb.program_identity()

def test_broken_topology_halts_at_grompp_with_no_output():
    descriptor = gromacs_program_descriptor(gmx_version_line(GMX), b"[ defaults\nbroken")
    spec = ExecutionSpecification(descriptor, MDP, _gro(1.4))
    result = run_gromacs_specification(spec, GMX)
    assert result.status == "halted"
    assert result.exit_code == FAULT_GROMPP
    assert result.output is None and result.computation_identity is None
