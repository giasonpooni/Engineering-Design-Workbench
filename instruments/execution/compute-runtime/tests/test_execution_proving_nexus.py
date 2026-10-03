"""Stage 3 -- Nexus as the second independent implementer, audited live.

Every proof here is a genuine Nexus stwo proof generated on this
machine's CPU. Skips (as an environment gap, never a pass) when the
nexus-host binary or the Nexus guest ELF is not built.

The file asks the same tamper questions the SP1 file asks -- and asserts
the ANSWERS differ where the substrates genuinely differ: SP1's
extract-style verifier names the mismatched dimension (InputMismatch /
OutputMismatch / ExitCodeMismatch); Nexus's confirm-style verifier can
only report that the claimed statement is not the proven one
(StatementMismatch). Recording that asymmetry is part of the audit, not
a defect to hide.

Fork revision under test: nexus-zkvm f2ad126 (workspace 0.3.6),
stwo prover, guest target riscv32im-unknown-none-elf,
toolchain nightly-2025-05-09.
"""

from __future__ import annotations

import pathlib
import subprocess

import pytest

from execution.proving import (
    ProvedRunError,
    default_nexus_guest_elf_path,
    default_nexus_host_path,
    prove_and_verify,
)
from execution.specification import (
    PAIRWISE_ENERGY_DESCRIPTOR,
    ExecutionSpecification,
    encode_positions,
)

HOST = default_nexus_host_path()
ELF = default_nexus_guest_elf_path()

pytestmark = pytest.mark.skipif(
    not (HOST.exists() and ELF.exists()),
    reason="nexus-host or Nexus guest ELF not built (zk/nexus workspace + "
    "nightly-2025-05-09); environment gap, not an architectural pass",
)

#: The identical argon-pair geometry the SP1 proof covers.
ARGON_PAIR = [(1000, 1000, 1000), (1400, 1000, 1000)]


def _spec(positions=None) -> ExecutionSpecification:
    return ExecutionSpecification(
        program=PAIRWISE_ENERGY_DESCRIPTOR,
        configuration=b"",
        input_payload=encode_positions(positions or ARGON_PAIR),
    )


@pytest.fixture(scope="module")
def proved(tmp_path_factory):
    """ONE real Nexus proof, through the identical backend-neutral
    driver the SP1 tests use -- only the two paths differ."""
    proof_dir = tmp_path_factory.mktemp("nexus-proofs")
    return prove_and_verify(
        _spec(), proof_dir / "argon-pair.nexus.proof", host_path=HOST, elf_path=ELF
    )


def _verify(proof_path, *, program_file=None, input_hex=None, output_hex=None, exit_code=None,
            proved_run=None):
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


# -- the contract, implemented a second time ----------------------------------------------------------


def test_the_full_chain_agrees_on_nexus(proved):
    """Native run, Nexus stwo proof, independent verification through
    the SAME sealed entry point and the SAME Python driver -- with the
    guest's in-circuit commitments equal to this layer's recomputations."""
    assert proved.execution.status == "completed"
    assert proved.backend_name == "nexus-stwo"
    assert proved.backend_version == "0.3.6@f2ad126"
    assert len(proved.proof_identity) == 64
    assert pathlib.Path(proved.proof_path).stat().st_size > 0


def test_verification_is_reproducible_from_the_artifact(proved):
    fields = _verify(pathlib.Path(proved.proof_path), proved_run=proved)
    assert fields["outcome"] == "verified"
    assert fields["coverage"] == "program=true input=true output=true exit_code=true"


# -- tampering: same questions, honestly different answers --------------------------------------------


def test_altered_input_is_rejected_as_statement_mismatch(proved):
    tampered = encode_positions([(1001, 1000, 1000), (1400, 1000, 1000)])
    fields = _verify(pathlib.Path(proved.proof_path), input_hex=tampered.hex(), proved_run=proved)
    assert fields["outcome"] == "failed"
    # Confirm-style: the mismatch is real but unattributable to the
    # input dimension specifically. StatementMismatch is the honest
    # answer; an InputMismatch here would be manufactured precision.
    assert "StatementMismatch" in fields["failure"]


def test_altered_program_identity_is_rejected_attributably(proved, tmp_path):
    """Program mismatch IS attributable on Nexus -- the binding check is
    the adapter's own, before the aggregate confirmation."""
    other_program = tmp_path / "other-program.bin"
    other_program.write_bytes(b"a different program's canonical bytes")
    fields = _verify(
        pathlib.Path(proved.proof_path), program_file=str(other_program), proved_run=proved
    )
    assert fields["outcome"] == "failed"
    assert "ProgramMismatch" in fields["failure"]


def test_altered_output_is_rejected_as_statement_mismatch(proved):
    tampered_output = bytes(reversed(proved.execution.output)).hex()
    fields = _verify(pathlib.Path(proved.proof_path), output_hex=tampered_output, proved_run=proved)
    assert fields["outcome"] == "failed"
    assert "StatementMismatch" in fields["failure"]


def test_altered_exit_code_is_rejected_as_statement_mismatch(proved):
    fields = _verify(pathlib.Path(proved.proof_path), exit_code=3, proved_run=proved)
    assert fields["outcome"] == "failed"
    assert "StatementMismatch" in fields["failure"]


def test_corrupted_proof_bytes_are_rejected(proved, tmp_path):
    corrupted = tmp_path / "corrupted.nexus.proof"
    raw = bytearray(pathlib.Path(proved.proof_path).read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    corrupted.write_bytes(bytes(raw))
    fields = _verify(corrupted, proved_run=proved)
    assert fields["outcome"] == "failed"
    assert ("StatementMismatch" in fields["failure"]) or ("Malformed" in fields["failure"])


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
        prove_and_verify(
            foreign, tmp_path / "never.proof", host_path=HOST, elf_path=ELF
        )


# -- the STE boundary under backend swap --------------------------------------------------------------


def test_backend_swap_leaves_the_evidence_ledger_and_trace_invariant(tmp_path):
    """The decisive integration property of this stage, tested inside the
    real STE loop: swapping the proof backend changes the WARRANT (proof
    artifact, verifier identity) and changes NOTHING about the
    specification, the execution result, the admitted evidence identity,
    or the operation-trace semantics.

    Two complete loops over the same specification: one with the plain
    checked engine (no proof), one gated on a real Nexus proof. The
    admitted observation ids are IDENTICAL -- evidence identity is a
    function of scientific content, blind to which (if any) proof system
    warranted the computation -- and both operation traces record one
    SUCCEEDED dispatch whose output_ref is that same observation."""
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

    def _session():
        pool = EvidencePool()
        source = make_source(kind="computational_campaign", name="STE-swap")
        pool.put_source(source)
        doc = make_document(
            source_id=source.id, raw_content="backend swap session",
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
        iteration = reevaluate_program(
            pool, engine, query, (make_criterion("interaction_energy", "<=", 0),)
        )
        return pool, make_experiment_session(pool, engine, iteration, document_id=doc.id)

    def _interpret(candidate, result):
        value = int.from_bytes(result.output, "little", signed=True)
        return {"property": candidate.property, "value": value, "unit": "lj_integer_units"}

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

    steps = {}
    traces = {}
    runners = {
        "unproved": None,
        "nexus": proved_runner(tmp_path, host_path=HOST, elf_path=ELF),
    }
    for label, runner in runners.items():
        pool, session = _session()
        dispatcher = SpecificationDispatcher(
            spec_for=lambda c: _spec(), interpret=_interpret,
            extracted_at="2026-08-25T00:00:00Z", runner=runner,
        )
        trace = OperationTrace()
        candidates = generate_candidates(session.iteration.specification)
        steps[label] = run_experiment_step(
            session, candidates, dispatcher, policy, confidence=1.0, trace=trace
        )
        traces[label] = trace

    # Evidence identity: blind to the warrant, byte-identical.
    assert steps["unproved"].observation.id == steps["nexus"].observation.id
    assert (
        steps["unproved"].observation.extraction_method
        == steps["nexus"].observation.extraction_method
    )
    # ExecutionResult content: identical (same engine, same checks).
    assert steps["unproved"].result.id == steps["nexus"].result.id
    # OperationTrace semantics: identical in both worlds.
    for trace, step in ((traces["unproved"], steps["unproved"]), (traces["nexus"], steps["nexus"])):
        assert trace.state_of(0) == SUCCEEDED
        assert trace.transitions_of(0)[-1].output_ref == step.observation.id
    # And the proof artifact exists only in the proved world.
    assert any(p.name.startswith("proof-") for p in tmp_path.iterdir())
