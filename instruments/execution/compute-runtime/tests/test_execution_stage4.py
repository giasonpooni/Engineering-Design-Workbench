"""STE Stage 4 -- does the substrate generalize beyond the argon pair?

Three materially different scientific workloads through the SAME
contract (ExecutionSpecification -> engine -> ExecutionResult ->
OperationTrace -> optional ProofBackend), with zero workload-specific
leakage into the substrate:

  A1/E  GROMACS MD trajectory      (external process; 8-atom argon,
                                    200 steps, per-frame energy series)
  A2    1-D heat diffusion         (new provable kernel: explicit
                                    finite-difference PDE -- a
                                    time-stepped stencil, structurally
                                    unlike pairwise accumulation)
  A3    GROMACS energy minimization (structured input: perturbed
                                    lattice; structured output:
                                    convergence series + minimized
                                    structure)

Every test answers one architectural question; none is a permutation.
GROMACS tests skip without a gmx binary; proving tests skip without the
built guests -- always as environment gaps, never as passes.
"""

from __future__ import annotations

import functools
import os
import pathlib
import shutil

import pytest

from execution.engine import default_cli_path, run_specification
from execution.gromacs import (
    GROMACS_MINIMIZATION_HEADER,
    GROMACS_TRAJECTORY_HEADER,
    gmx_version_line,
    gromacs_program_descriptor,
    run_gromacs_minimization_specification,
    run_gromacs_trajectory_specification,
)
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR,
    PAIRWISE_ENERGY_DESCRIPTOR,
    ExecutionSpecification,
    encode_heat_input,
)

REPO = pathlib.Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    not default_cli_path().exists(),
    reason="execution engine binary not built; environment gap, not an architectural pass",
)


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
needs_gmx = pytest.mark.skipif(GMX is None, reason="no gmx binary; environment gap")

TOPOLOGY_8AR = b"""[ defaults ]
1 2 yes 0.5 0.5

[ atomtypes ]
Ar 18 39.948 0.0 A 0.3401 0.978638

[ moleculetype ]
AR 1

[ atoms ]
1 Ar 1 AR AR 1 0.0 39.948

[ system ]
Argon octet
[ molecules ]
AR 8
"""


def _gro_octet(perturb: float = 0.0) -> bytes:
    corners = [(a, b, c) for a in (0, 1) for b in (0, 1) for c in (0, 1)]
    lines = ["Argon octet", "    8"]
    for i, (dx, dy, dz) in enumerate(corners, 1):
        x = 1.0 + dx * 0.5 + (perturb if i == 1 else 0.0)
        lines.append(f"{i:>5}AR     AR{i:>5}{x:8.3f}{1.0 + dy * 0.5:8.3f}{1.0 + dz * 0.5:8.3f}")
    lines.append("   3.00000   3.00000   3.00000")
    return ("\n".join(lines) + "\n").encode()


MDP_TRAJECTORY = b"""integrator = md
nsteps = 200
dt = 0.002
nstenergy = 20
cutoff-scheme = Verlet
coulombtype = Cut-off
vdwtype = Cut-off
rlist = 1.0
rcoulomb = 1.0
rvdw = 1.0
gen-vel = no
"""

MDP_MINIMIZATION = b"""integrator = steep
nsteps = 100
emtol = 1.0
emstep = 0.01
cutoff-scheme = Verlet
coulombtype = Cut-off
vdwtype = Cut-off
rlist = 1.0
rcoulomb = 1.0
rvdw = 1.0
"""


def _heat_spec(steps=500, values=(0, 800_000, 1_000_000, 800_000, 0, 0, 0, 0)):
    return ExecutionSpecification(
        program=HEAT_DIFFUSION_DESCRIPTOR,
        configuration=b"",
        input_payload=encode_heat_input(steps, list(values)),
    )


# =====================================================================
# A2 -- the heat kernel through the unchanged contract
# =====================================================================


def test_heat_contract_and_identities():
    """One run answers Target B for the kernel route: a structurally
    different computation (time-stepped stencil) needed NO substrate
    change -- same specification type, same engine, same identities."""
    first = run_specification(_heat_spec())
    second = run_specification(_heat_spec())
    assert first.status == "completed" and first.exit_code == 0
    # same specification twice -> same identity; two processes -> one computation
    assert first.specification_identity == second.specification_identity
    assert first.computation_identity == second.computation_identity
    # changed input -> changed identities
    hotter = run_specification(_heat_spec(values=(0, 900_000, 1_000_000, 800_000, 0, 0, 0, 0)))
    assert hotter.input_identity != first.input_identity
    assert hotter.computation_identity != first.computation_identity
    # changed configuration dimension (steps live in input for this
    # kernel; the CONFIGURATION field separation is pinned elsewhere) --
    # changed step count is a changed computation:
    longer = run_specification(_heat_spec(steps=1000))
    assert longer.computation_identity != first.computation_identity
    # different program, same substrate: kernel identities never collide
    assert first.program_identity != run_specification(
        ExecutionSpecification(PAIRWISE_ENERGY_DESCRIPTOR, b"", b"")
    ).program_identity


def test_heat_failure_admits_nothing_downstream():
    result = run_specification(
        ExecutionSpecification(HEAT_DIFFUSION_DESCRIPTOR, b"", b"short")
    )
    assert result.status == "halted" and result.exit_code == 2
    assert result.output is None and result.computation_identity is None


def test_heat_through_the_seam_evidence_invariant_and_rejection_distinct(tmp_path):
    """Target C's two ledger properties for the new kernel, in one loop
    harness: (1) two complete loops admit ONE observation id; (2) an
    interpret function whose content the admission boundary refuses
    leaves the operation SUCCEEDED-then-REJECTED -- the dispatch
    happened; what failed was downstream, and the ledgers say so."""
    from evidence.admission import admit_document, admit_referent
    from evidence.pool import EvidencePool
    from evidence.types import make_document, make_referent, make_source
    from execution.dispatcher import SpecificationDispatcher
    from experiment.policy import ExperimentPolicy
    from experiment.session import make_experiment_session
    from experiment.step import run_experiment_step
    from materials.candidates import generate_candidates
    from materials.decision import make_criterion
    from materials.information import InformationValueEstimate
    from materials.iteration import reevaluate_program
    from materials.optimization import OptimizationPolicy
    from materials.program import make_material_program_query
    from materials.selection import SelectionPolicy
    from materials.utility import ExperimentUtilityInput
    from operations.trace import REJECTED, SUCCEEDED, OperationTrace
    from retrieval.engine import DeterministicRetrievalEngine

    def _session():
        pool = EvidencePool()
        source = make_source(kind="computational_campaign", name="STE-heat")
        pool.put_source(source)
        doc = make_document(
            source_id=source.id, raw_content="heat session",
            retrieval_method="manual_entry", retrieved_at="2026-08-25T00:00:00Z",
        )
        admit_document(pool, doc)
        pool.put_document(doc)
        for key, kind in (("process-heat-cell", "process"), ("formulation-rod", "formulation")):
            referent = make_referent(natural_key=key, kind=kind)
            admit_referent(pool, referent)
            pool.put_referent(referent)
        engine = DeterministicRetrievalEngine()
        query = make_material_program_query(
            ["formulation-rod"], "process-heat-cell", ("peak_temperature",)
        )
        iteration = reevaluate_program(
            pool, engine, query, (make_criterion("peak_temperature", "<=", 1_000_000),)
        )
        return pool, make_experiment_session(pool, engine, iteration, document_id=doc.id)

    policy = ExperimentPolicy(
        selection_policy=SelectionPolicy(
            allowed_action_classes=None, allow_already_represented_context=True,
            allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
        ),
        optimization_policy=OptimizationPolicy(
            max_candidates=1, allowed_action_classes=None, allow_indeterminate_utility=True
        ),
        utility_input_source=lambda e: (
            ExperimentUtilityInput(benefit=e.estimate, cost=1.0)
            if isinstance(e, InformationValueEstimate) and e.estimate is not None
            else ExperimentUtilityInput(benefit=1.0, cost=1.0)
        ),
    )

    def _peak(candidate, result):
        finals = [
            int.from_bytes(result.output[at:at + 8], "little", signed=True)
            for at in range(0, len(result.output), 8)
        ]
        return {"property": candidate.property, "value": max(finals), "unit": "fixed_point_mk"}

    # (1) evidence invariance across two complete loops.
    steps = []
    for _ in range(2):
        pool, session = _session()
        dispatcher = SpecificationDispatcher(
            spec_for=lambda c: _heat_spec(), interpret=_peak,
            extracted_at="2026-08-25T00:00:00Z",
        )
        candidates = generate_candidates(session.iteration.specification)
        steps.append(run_experiment_step(
            session, candidates, dispatcher, policy, confidence=1.0, trace=OperationTrace()
        ))
    assert steps[0].observation.id == steps[1].observation.id

    # (2) downstream rejection stays distinct from operation failure.
    pool, session = _session()
    wrong = SpecificationDispatcher(
        spec_for=lambda c: _heat_spec(),
        interpret=lambda c, r: {"property": "not_the_requested_property", "value": 1, "unit": "x"},
        extracted_at="2026-08-25T00:00:00Z",
    )
    trace = OperationTrace()
    candidates = generate_candidates(session.iteration.specification)
    rod = make_referent(natural_key="formulation-rod", kind="formulation")
    observations_before = len(pool.observations_about(rod.id))
    with pytest.raises(Exception):
        run_experiment_step(session, candidates, wrong, policy, confidence=1.0, trace=trace)
    # Phase 44's boundary, observed live: the raw Record IS admitted (the
    # dispatch happened; its transcript is structural bookkeeping), while
    # the SEMANTIC fact is refused -- no Observation entered.
    assert len(pool.observations_about(rod.id)) == observations_before, (
        "no semantic fact was admitted"
    )
    states = [t.to_state for t in trace.transitions_of(0)]
    assert SUCCEEDED in states and states[-1] == REJECTED, (
        "the dispatch SUCCEEDED; the refusal was downstream, and the ledger keeps them distinct"
    )


# =====================================================================
# A1 / Target E -- GROMACS MD trajectory
# =====================================================================


@needs_gmx
def test_gromacs_trajectory_workload():
    """A real MD trajectory through the unchanged contract: simulation
    state actually evolves (the energy series is non-constant), repeat
    runs are byte-identical, and every Target E dimension is carried:
    executable identity (version line in the program), input (.gro
    initial state), configuration (.mdp with integrator/dt/nsteps),
    output (per-frame series), occurrence (per-invocation), verification
    status (unproved external process -- stated, not implied)."""
    version = gmx_version_line(GMX)
    spec = ExecutionSpecification(
        gromacs_program_descriptor(version, TOPOLOGY_8AR, GROMACS_TRAJECTORY_HEADER),
        MDP_TRAJECTORY,
        _gro_octet(),
    )
    first = run_gromacs_trajectory_specification(spec, GMX)
    second = run_gromacs_trajectory_specification(spec, GMX)
    assert first.status == "completed"
    assert first.output.startswith(b"gmx-energy-series kJ/mol\n")
    frames = first.output.decode().splitlines()[1:]
    assert len(frames) >= 10, "a trajectory, not a point"
    energies = [float(line.split()[1]) for line in frames]
    assert len(set(energies)) > 1, "simulation state evolved"
    assert first.output == second.output and (
        first.computation_identity == second.computation_identity
    )
    assert version.encode() in spec.program, "executable identity rides in the program"
    # changed initial state -> changed identities
    moved = ExecutionSpecification(spec.program, spec.configuration, _gro_octet(perturb=0.05))
    third = run_gromacs_trajectory_specification(moved, GMX)
    assert third.input_identity != first.input_identity
    assert third.computation_identity != first.computation_identity
    # changed configuration -> changed specification identity
    shorter = ExecutionSpecification(
        spec.program, MDP_TRAJECTORY.replace(b"nsteps = 200", b"nsteps = 100"), _gro_octet()
    )
    assert shorter.identity() != spec.identity()


# =====================================================================
# A3 -- GROMACS energy minimization
# =====================================================================


@needs_gmx
def test_gromacs_minimization_workload():
    """Structured input (a perturbed lattice), structured output
    (convergence series + minimized structure), real optimization (the
    final energy is materially below the initial), deterministic on
    repeat -- and a DIFFERENT program identity from the trajectory
    workload over the identical topology, because output semantics are
    part of what a program is."""
    version = gmx_version_line(GMX)
    spec = ExecutionSpecification(
        gromacs_program_descriptor(version, TOPOLOGY_8AR, GROMACS_MINIMIZATION_HEADER),
        MDP_MINIMIZATION,
        _gro_octet(perturb=0.12),
    )
    first = run_gromacs_minimization_specification(spec, GMX)
    second = run_gromacs_minimization_specification(spec, GMX)
    assert first.status == "completed"
    assert first.output == second.output
    series, structure = first.output.split(b"\n[minimized-structure]\n")
    energies = [float(line.split()[1]) for line in series.decode().splitlines()[2:]]
    assert energies[-1] < energies[0] - 5.0, "the lattice actually relaxed"
    assert structure.splitlines()[0].strip() == b"8", "the minimized structure came back"

    trajectory_program = gromacs_program_descriptor(
        version, TOPOLOGY_8AR, GROMACS_TRAJECTORY_HEADER
    )
    assert ExecutionSpecification(trajectory_program, b"", b"").program_identity() != (
        ExecutionSpecification(spec.program, b"", b"").program_identity()
    )


@needs_gmx
def test_gromacs_workload_outside_the_proof_envelope_is_refused():
    """Target D's honesty clause: no guest implements a GROMACS
    descriptor, so the proving layer refuses -- an explicit refusal,
    never a pretended verification."""
    from execution.proving import ProvedRunError, prove_and_verify

    version = gmx_version_line(GMX)
    spec = ExecutionSpecification(
        gromacs_program_descriptor(version, TOPOLOGY_8AR, GROMACS_TRAJECTORY_HEADER),
        MDP_TRAJECTORY,
        _gro_octet(),
    )
    with pytest.raises(ProvedRunError, match="capability envelope"):
        prove_and_verify(spec, pathlib.Path("/tmp/never.proof"))


# =====================================================================
# Target D -- the new workload across both real proof backends
# =====================================================================

from execution.proving import (  # noqa: E402
    default_guest_elf_path,
    default_heat_guest_elf_path,
    default_host_path,
    default_nexus_guest_elf_path,
    default_nexus_heat_guest_elf_path,
    default_nexus_host_path,
    prove_and_verify,
)

_PROVING_READY = all(
    p.exists()
    for p in (
        default_host_path(), default_heat_guest_elf_path(),
        default_nexus_host_path(), default_nexus_heat_guest_elf_path(),
    )
)
needs_proving = pytest.mark.skipif(
    not _PROVING_READY, reason="heat guests or hosts not built; environment gap"
)

#: A small instance for proving (proof cost scales with cycles).
_HEAT_PROVING_SPEC = functools.partial(
    _heat_spec, steps=50, values=(0, 700_000, 1_000_000, 700_000, 0, 0)
)


@needs_proving
def test_heat_is_proven_by_both_backends_one_statement(tmp_path):
    """The stage's decisive Target D fact: the NEW workload crosses BOTH
    real proof backends -- one specification, one computation identity,
    two warrants. Different proof backend != different scientific fact,
    demonstrated on a workload that did not exist when the backends were
    built (neither adapter changed for it: only new guests around the
    same kernel crate and the same io layout)."""
    spec = _HEAT_PROVING_SPEC()
    sp1 = prove_and_verify(
        spec, tmp_path / "heat.sp1.proof",
        host_path=default_host_path(), elf_path=default_heat_guest_elf_path(),
    )
    nexus = prove_and_verify(
        spec, tmp_path / "heat.nexus.proof",
        host_path=default_nexus_host_path(), elf_path=default_nexus_heat_guest_elf_path(),
    )
    assert sp1.execution.computation_identity == nexus.execution.computation_identity
    assert sp1.execution.output == nexus.execution.output
    assert (sp1.backend_name, nexus.backend_name) == ("sp1-cpu", "nexus-stwo")
    assert sp1.proof_identity != nexus.proof_identity


@needs_proving
def test_program_binding_refusal_and_its_exact_trust_boundary(tmp_path):
    """This test originally asserted that verifying a heat proof under a
    falsely-REGISTERED pairwise binding would fail -- and the first run
    FALSIFIED that: it verified. That is not a bug; it is the declared
    binding boundary (stated since stage 2) located precisely. The
    registration IS the declaration "this ELF implements that
    descriptor"; a verifier cannot catch a false declaration, because
    catching it is exactly what the declaration exists to stand in for.

    So this test now pins BOTH truths:

      1. the attributable refusal that DOES exist: an EXPECTATION naming
         a different program than the registration fails as
         ProgramMismatch;
      2. the discovered boundary: a false REGISTRATION at the raw CLI
         seam verifies -- the caller of that seam is the registrar, and
         registrar honesty is trusted there. The Python driver is not
         exposed: it always registers spec.program itself and
         cross-checks the guest's output against the native kernel, so a
         wrong ELF for a spec is caught as a commitment mismatch."""
    import subprocess

    spec = _HEAT_PROVING_SPEC()
    native = run_specification(spec)
    proof = tmp_path / "heat.nexus.proof"
    prove_and_verify(
        spec, proof,
        host_path=default_nexus_host_path(), elf_path=default_nexus_heat_guest_elf_path(),
    )
    heat_descriptor = tmp_path / "heat-descriptor.bin"
    heat_descriptor.write_bytes(HEAT_DIFFUSION_DESCRIPTOR)
    pairwise_descriptor = tmp_path / "pairwise-descriptor.bin"
    pairwise_descriptor.write_bytes(PAIRWISE_ENERGY_DESCRIPTOR)

    def _verify(register: pathlib.Path, expect: str) -> str:
        proc = subprocess.run(
            [
                str(default_nexus_host_path()), "verify",
                str(default_nexus_heat_guest_elf_path()), str(register), str(proof),
                expect, spec.input_payload.hex(), native.output.hex(), "0",
            ],
            capture_output=True, timeout=600,
        )
        assert proc.returncode == 0, proc.stderr.decode()
        return proc.stdout.decode()

    # (1) True registration, foreign expectation: attributably refused.
    mismatched = _verify(heat_descriptor, str(pairwise_descriptor))
    assert "outcome failed" in mismatched and "ProgramMismatch" in mismatched, mismatched

    # (2) False registration, matching expectation: VERIFIES -- the
    # declared-binding boundary, pinned so it can never be mistaken for
    # a checked property. (If this ever starts failing, the binding
    # became verifiable and the docs must be rewritten, not this test.)
    falsely_registered = _verify(pairwise_descriptor, "registered")
    assert "outcome verified" in falsely_registered, falsely_registered

    # And the Python driver's mitigation: a wrong ELF for a spec is
    # caught by the native cross-check, not trusted.
    from execution.proving import ProvedRunError

    pairwise_spec = ExecutionSpecification(
        PAIRWISE_ENERGY_DESCRIPTOR, b"",
        __import__("execution.specification", fromlist=["encode_positions"]).encode_positions(
            [(0, 0, 0), (5, 0, 0)]
        ),
    )
    with pytest.raises(ProvedRunError):
        prove_and_verify(
            pairwise_spec, tmp_path / "mismatched.proof",
            host_path=default_nexus_host_path(),
            elf_path=default_nexus_heat_guest_elf_path(),  # wrong guest for this spec
        )
