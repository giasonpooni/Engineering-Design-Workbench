"""Stage 2 -- the SP1 proved path, audited live with REAL proofs.

Every test in this file that touches a proof uses a genuine SP1 core
proof generated on this machine's CPU by the real prover. There is no
mock prover reachable from the adapter, and nothing in this file
constructs a verification outcome by hand.

Skipped (reason stated as an environment gap, never as a pass) when the
sp1-host binary or the guest ELF is not built.

Proving is expensive, so the file generates ONE proof (module-scoped)
and asks every tamper question against it -- tampering is a property of
VERIFICATION, not of proving, so one honest proof supports all of them:

    altered input      -> Failed(InputMismatch)
    altered program    -> Failed(ProgramMismatch)
    altered output     -> Failed(OutputMismatch)
    altered exit code  -> Failed(ExitCodeMismatch)
    corrupted proof    -> Failed(InvalidProof | Malformed)
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

from execution.proving import (
    ProvedRunError,
    default_guest_elf_path,
    default_host_path,
    prove_and_verify,
)
from execution.specification import (
    PAIRWISE_ENERGY_DESCRIPTOR,
    ExecutionSpecification,
    encode_positions,
)

HOST = default_host_path()
ELF = default_guest_elf_path()

pytestmark = pytest.mark.skipif(
    not (HOST.exists() and ELF.exists()),
    reason="sp1-host or guest ELF not built (zk/ workspace + succinct toolchain); "
    "environment gap, not an architectural pass",
)

#: The argon-pair geometry the GROMACS Target D workload evaluated
#: ((1.0,1.0,1.0) and (1.4,1.0,1.0) nm), scaled x1000 onto the kernel's
#: integer grid -- the proved computation runs over the same system the
#: real scientific workload ran over. (The proof covers the KERNEL's
#: computation on this geometry; nothing proves GROMACS's own arithmetic,
#: and no test here claims otherwise.)
ARGON_PAIR = [(1000, 1000, 1000), (1400, 1000, 1000)]


def _spec(positions=None) -> ExecutionSpecification:
    return ExecutionSpecification(
        program=PAIRWISE_ENERGY_DESCRIPTOR,
        configuration=b"",
        input_payload=encode_positions(positions or ARGON_PAIR),
    )


@pytest.fixture(scope="module")
def proved(tmp_path_factory):
    """ONE real proof: native run -> SP1 core proof -> verification, all
    agreeing. Everything downstream interrogates this artifact."""
    proof_dir = tmp_path_factory.mktemp("proofs")
    return prove_and_verify(_spec(), proof_dir / "argon-pair.proof")


def _verify(proof_path, *, program_file=None, input_hex=None, output_hex=None, exit_code=None,
            proved_run=None):
    """Drive `sp1-host verify` with selectively altered expectations."""
    descriptor_file = proof_path.parent / "descriptor.bin"
    descriptor_file.write_bytes(PAIRWISE_ENERGY_DESCRIPTOR)
    native = proved_run.execution
    args = [
        str(HOST), "verify", str(ELF), str(descriptor_file), str(proof_path),
        program_file if program_file is not None else "registered",
        input_hex if input_hex is not None else native.specification.input_payload.hex(),
        output_hex if output_hex is not None else native.output.hex(),
        str(exit_code if exit_code is not None else native.exit_code),
    ]
    proc = subprocess.run(args, capture_output=True, timeout=600)
    assert proc.returncode == 0, proc.stderr.decode()
    fields = {}
    for line in proc.stdout.decode().splitlines()[1:]:
        key, _, value = line.partition(" ")
        fields[key] = value
    return fields


# -- the earned Verified ------------------------------------------------------------------------------


def test_the_full_chain_agrees(proved):
    """specification -> execution -> proof -> independent verification ->
    ProvedRun. Reaching here means: the guest's in-circuit input and
    output commitments equalled this layer's own recomputations, the
    real verifier accepted the proof, and the sealed entry point
    answered `verified` for the exact four-part statement."""
    assert proved.execution.status == "completed"
    assert proved.proof_identity and len(proved.proof_identity) == 64
    assert proved.backend_name == "sp1-cpu"
    assert proved.vkey_hash.startswith("0x")
    assert pathlib.Path(proved.proof_path).stat().st_size > 0


def test_verification_is_reproducible_from_the_artifact(proved):
    """A second, fresh verification of the saved proof -- new process,
    new backend setup -- answers `verified` for the same statement."""
    fields = _verify(pathlib.Path(proved.proof_path), proved_run=proved)
    assert fields["outcome"] == "verified"
    assert fields["coverage"] == "program=true input=true output=true exit_code=true"


# -- the three demanded tamper rejections (plus two) --------------------------------------------------


def test_altered_input_is_rejected(proved):
    tampered = encode_positions([(1001, 1000, 1000), (1400, 1000, 1000)])
    fields = _verify(pathlib.Path(proved.proof_path), input_hex=tampered.hex(), proved_run=proved)
    assert fields["outcome"] == "failed"
    assert "InputMismatch" in fields["failure"]


def test_altered_program_identity_is_rejected(proved, tmp_path):
    other_program = tmp_path / "other-program.bin"
    other_program.write_bytes(b"a different program's canonical bytes")
    fields = _verify(
        pathlib.Path(proved.proof_path), program_file=str(other_program), proved_run=proved
    )
    assert fields["outcome"] == "failed"
    assert "ProgramMismatch" in fields["failure"]


def test_altered_output_commitment_is_rejected(proved):
    tampered_output = bytes(reversed(proved.execution.output)).hex()
    fields = _verify(pathlib.Path(proved.proof_path), output_hex=tampered_output, proved_run=proved)
    assert fields["outcome"] == "failed"
    assert "OutputMismatch" in fields["failure"]


def test_altered_exit_code_is_rejected(proved):
    fields = _verify(pathlib.Path(proved.proof_path), exit_code=3, proved_run=proved)
    assert fields["outcome"] == "failed"
    assert "ExitCodeMismatch" in fields["failure"]


def test_corrupted_proof_bytes_are_rejected(proved, tmp_path):
    corrupted = tmp_path / "corrupted.proof"
    raw = bytearray(pathlib.Path(proved.proof_path).read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    corrupted.write_bytes(bytes(raw))
    fields = _verify(corrupted, proved_run=proved)
    assert fields["outcome"] == "failed"
    assert ("InvalidProof" in fields["failure"]) or ("Malformed" in fields["failure"])


# -- hard failure at the Python layer -----------------------------------------------------------------


def test_a_wrong_program_specification_is_refused_before_proving(tmp_path):
    foreign = ExecutionSpecification(
        program=b"not the registered guest", configuration=b"", input_payload=b""
    )
    with pytest.raises(ProvedRunError, match="no built guest is registered"):
        # The regex was written against a message this refusal no longer
        # carries. Stage 5 replaced "descriptor not registered" with the
        # guest-registry wording, and this assertion was not updated --
        # so it has been red since 3f40d23 while the refusal it tests
        # kept working perfectly. A stale `match=` fails LOUDLY and
        # says nothing true, which is the worst of both: it costs a
        # green suite and buys no coverage.
        prove_and_verify(foreign, tmp_path / "never.proof")


def test_proved_run_has_no_verified_flag(proved):
    """Requirement 8, stated structurally: the object that exists after
    verification has no boolean to consult and therefore none to
    ignore. Failure is an exception; success is existence."""
    assert not hasattr(proved, "verified")
    assert not any("verified" in name for name in vars(proved))


# -- the vertical, gated on proof ---------------------------------------------------------------------


def test_proved_dispatch_through_the_existing_seam(tmp_path):
    """The STE loop with the PROVED runner: the dispatched computation is
    natively executed, proven under SP1, and independently verified
    before its value may proceed to admission -- and the two-ledger
    separation holds exactly as in stage 1. One additional real proof.
    """
    import struct

    from evidence.admission import admit_document, admit_referent
    from evidence.pool import EvidencePool
    from evidence.types import make_document, make_referent, make_source
    from execution.dispatcher import SpecificationDispatcher
    from execution.proving import proved_runner
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
    from operations.trace import SUCCEEDED, OperationTrace
    from retrieval.engine import DeterministicRetrievalEngine

    pool = EvidencePool()
    source = make_source(kind="computational_campaign", name="STE-proved")
    pool.put_source(source)
    doc = make_document(
        source_id=source.id, raw_content="proved execution session",
        retrieval_method="manual_entry", retrieved_at="2026-08-25T00:00:00Z",
    )
    admit_document(pool, doc)
    pool.put_document(doc)
    for key, kind in (("process-lj-cell", "process"), ("formulation-argon-pair", "formulation")):
        referent = make_referent(natural_key=key, kind=kind)
        admit_referent(pool, referent)
        pool.put_referent(referent)
    engine = DeterministicRetrievalEngine()
    query = make_material_program_query(
        ["formulation-argon-pair"], "process-lj-cell", ("interaction_energy",)
    )
    iteration = reevaluate_program(pool, engine, query, (make_criterion("interaction_energy", "<=", 0),))
    session = make_experiment_session(pool, engine, iteration, document_id=doc.id)

    def interpret(candidate, result):
        value = int.from_bytes(result.output, "little", signed=True)
        return {"property": candidate.property, "value": value, "unit": "lj_integer_units"}

    dispatcher = SpecificationDispatcher(
        spec_for=lambda c: _spec(),
        interpret=interpret,
        extracted_at="2026-08-25T00:00:00Z",
        runner=proved_runner(tmp_path),
    )
    candidates = generate_candidates(session.iteration.specification)
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
    trace = OperationTrace()
    step = run_experiment_step(session, candidates, dispatcher, policy, confidence=1.0, trace=trace)

    # Admitted through the unchanged boundary, declared as simulation.
    assert pool.has_observation(step.observation.id)
    assert step.observation.extraction_method == "simulation:deterministic_native_execution"
    # The operation ledger recorded the proved dispatch as one occurrence.
    assert trace.state_of(0) == SUCCEEDED
    # A proof artifact exists on disk for the dispatched computation.
    assert any(p.name.startswith("proof-") for p in tmp_path.iterdir())
    # And the observation's semantic content still carries no execution
    # or proof bookkeeping whatsoever.
    assert "proof" not in step.observation.content
    assert "computation" not in step.observation.content
