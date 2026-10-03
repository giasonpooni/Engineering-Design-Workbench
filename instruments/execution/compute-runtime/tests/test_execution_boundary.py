"""STE execution vertical -- the cross-process boundary, audited in place.

Every test here exercises the REAL engine binary (a fresh Rust process
per execution) or the real commitment functions. Audit dimensions from
the STE directive covered in this file: identity, determinism, repeat
execution, failure, retry, configuration change, input change, output
change, cross-process behavior, serialization, tampering, boundary
violations, unrepresentable states.
"""

from __future__ import annotations

import ast
import pathlib
import stat
import subprocess

import pytest

from execution.commitments import (
    COMPUTATION_TAG,
    INPUT_TAG,
    PROGRAM_TAG,
    SPECIFICATION_TAG,
    canonical,
    commit_hex,
)
from execution.engine import (
    EngineIdentityMismatch,
    ExecutionRefused,
    default_cli_path,
    run_specification,
)
from execution.specification import (
    PAIRWISE_ENERGY_DESCRIPTOR,
    ExecutionSpecification,
    encode_positions,
)

REPO = pathlib.Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    not default_cli_path().exists(),
    reason="execution engine binary not built (cargo build --release -p execution-cli); "
    "this is an environment gap, not an architectural pass",
)


def _spec(positions=((0, 0, 0), (5, 0, 0), (0, 5, 0))) -> ExecutionSpecification:
    return ExecutionSpecification(
        program=PAIRWISE_ENERGY_DESCRIPTOR,
        configuration=b"",
        input_payload=encode_positions(list(positions)),
    )


# -- cross-language identity agreement ---------------------------------------------------------------


def test_commitments_match_the_rust_vectors():
    """The exact vectors `crates/execution-core/tests/semantics.rs` pins
    from the Rust side, pinned here from the Python side. One function,
    two languages, zero drift."""
    assert commit_hex(PROGRAM_TAG, [b"hello"]) == (
        "9ebc0016a12b82a8588c1e021d46b5cf3f43f330ebc71ead63a6e36fab8f4535")
    assert commit_hex(INPUT_TAG, [b"hello"]) == (
        "df8dafd17d787e3f0ae9b123547bc46e2188c6259fabcf0b0f3c5ac9c24dc4a7")
    assert commit_hex("scout.execution.output.v1", [b""]) == (
        "86a35cb4e4a48a18646c34a9986f3fcf85eb3bbaa3089809904844c12d38cff1")


def test_canonical_encoding_is_injective_at_the_seams():
    assert canonical("t", [b"ab", b""]) != canonical("t", [b"a", b"b"])
    assert canonical("t", []) != canonical("t", [b""])
    assert commit_hex(PROGRAM_TAG, [b"x"]) != commit_hex(INPUT_TAG, [b"x"])


def test_specification_identity_separates_every_dimension():
    base = _spec()
    other_input = ExecutionSpecification(base.program, b"", encode_positions([(0, 0, 0), (6, 0, 0)]))
    other_config = ExecutionSpecification(base.program, b"cutoff=12", base.input_payload)
    other_program = ExecutionSpecification(b"some other program", b"", base.input_payload)
    identities = {base.identity(), other_input.identity(), other_config.identity(), other_program.identity()}
    assert len(identities) == 4, "program, configuration and input each separate the request"
    assert base.identity() == _spec().identity(), "and identical requests are one request"


# -- the live engine: determinism, cross-process behavior --------------------------------------------


def test_execution_completes_and_every_identity_is_recomputed_and_agrees():
    result = run_specification(_spec())
    assert result.status == "completed"
    assert result.exit_code == 0
    assert result.output is not None and len(result.output) == 16
    # run_specification already compared every engine echo against its
    # own recomputation -- reaching here IS the agreement. Re-assert the
    # computation identity explicitly for the reader:
    assert result.computation_identity == commit_hex(
        COMPUTATION_TAG,
        [
            bytes.fromhex(result.program_identity),
            bytes.fromhex(result.input_identity),
            bytes.fromhex(result.output_identity),
            (0).to_bytes(4, "little"),
        ],
    )


def test_cross_process_determinism_two_processes_one_computation():
    """Two SEPARATE engine processes, same request: identical output
    bytes, identical computation identity. Cross-process OCCURRENCE
    identity stays unsolved -- each process's trace starts at 0, and the
    number is recorded as per-process, not global."""
    first = run_specification(_spec())
    second = run_specification(_spec())
    assert first.output == second.output
    assert first.computation_identity == second.computation_identity
    assert first.engine_occurrence == 0 and second.engine_occurrence == 0


def test_different_input_different_computation():
    near = run_specification(_spec(((0, 0, 0), (2, 0, 0))))
    far = run_specification(_spec(((0, 0, 0), (200, 0, 0))))
    assert near.output != far.output
    assert near.computation_identity != far.computation_identity
    assert near.program_identity == far.program_identity


# -- failure, retry, refusal -------------------------------------------------------------------------


def test_fault_yields_no_output_and_nothing_fabricated():
    bad = ExecutionSpecification(PAIRWISE_ENERGY_DESCRIPTOR, b"", b"not-twelve")
    result = run_specification(bad)
    assert result.status == "halted"
    assert result.exit_code == 2
    assert result.output is None
    assert result.output_identity is None
    assert result.computation_identity is None, "unknown output stays unknown"


def test_coincident_particles_fault_rather_than_zero():
    result = run_specification(_spec(((7, 7, 7), (7, 7, 7))))
    assert result.status == "halted" and result.exit_code == 3


def test_retry_after_failure_succeeds_independently():
    failed = run_specification(ExecutionSpecification(PAIRWISE_ENERGY_DESCRIPTOR, b"", b"xyz"))
    assert failed.status == "halted"
    retried = run_specification(_spec())
    assert retried.status == "completed"


def test_unknown_program_is_refused_not_run():
    with pytest.raises(ExecutionRefused):
        run_specification(ExecutionSpecification(b"no such program", b"", b""))


def test_configuration_is_refused_not_silently_ignored():
    """The silent-drop hazard: if the engine ignored configuration bytes,
    two DIFFERENT requests would yield 'the same' computation. It
    refuses instead."""
    configured = ExecutionSpecification(
        PAIRWISE_ENERGY_DESCRIPTOR, b"cutoff=12", encode_positions([(0, 0, 0), (5, 0, 0)])
    )
    with pytest.raises(ExecutionRefused):
        run_specification(configured)


# -- tampering ---------------------------------------------------------------------------------------


def test_a_lying_engine_is_caught(tmp_path):
    """A fake engine that answers with a perfect-looking result whose
    computation identity is wrong by one nibble. The channel is checked,
    not trusted: run_specification recomputes and refuses."""
    honest = run_specification(_spec())
    lied = honest.computation_identity[:-1] + ("0" if honest.computation_identity[-1] != "0" else "1")
    fake = tmp_path / "lying-engine"
    fake.write_text(
        "#!/bin/sh\n"
        "cat > /dev/null\n"
        "printf 'ste-execution-result v1\\n'\n"
        f"printf 'spec {honest.specification_identity}\\n'\n"
        f"printf 'program {honest.program_identity}\\n'\n"
        f"printf 'input {honest.input_identity}\\n'\n"
        "printf 'occurrence 0\\n'\n"
        "printf 'status completed\\n'\n"
        "printf 'exit_code 0\\n'\n"
        f"printf 'output {honest.output.hex()}\\n'\n"
        f"printf 'output_id {honest.output_identity}\\n'\n"
        f"printf 'computation {lied}\\n'\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    with pytest.raises(EngineIdentityMismatch):
        run_specification(_spec(), cli_path=fake)


def test_an_engine_answering_for_a_different_request_is_caught(tmp_path):
    """The detachable-warrant hazard at the process seam: a result that
    names a DIFFERENT specification is refused outright, before any
    other field is looked at."""
    other = run_specification(_spec(((0, 0, 0), (9, 9, 9))))
    fake = tmp_path / "misdirected-engine"
    fake.write_text(
        "#!/bin/sh\ncat > /dev/null\n"
        "printf 'ste-execution-result v1\\n'\n"
        f"printf 'spec {other.specification_identity}\\n'\n"
        "printf 'status completed\\n'\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    with pytest.raises(EngineIdentityMismatch):
        run_specification(_spec(), cli_path=fake)


def test_tampered_input_bytes_change_every_downstream_identity():
    spec = _spec()
    tampered = ExecutionSpecification(
        spec.program, spec.configuration, spec.input_payload[:-1] + b"\x01"
    )
    assert spec.identity() != tampered.identity()
    assert spec.input_identity() != tampered.input_identity()


# -- boundary violations -----------------------------------------------------------------------------


def test_execution_package_touches_no_evidence_machinery():
    """The execution layer must not write into EvidencePool -- enforced
    structurally: no module under execution/ imports from evidence/ (or
    scout/, materials/, retrieval/) at all, and none names an admission
    call. Its only production imports besides the stdlib are the two
    seam types it returns into (experiment.interface) and the candidate
    type it reads (materials.candidates -- via the dispatcher module's
    type annotation only)."""
    allowed_local = {"execution", "experiment", "materials", "operations"}
    forbidden_calls = {
        "admit_observation", "admit_claimed_relationship", "put_observation",
        "put_claimed_relationship", "put_record", "put_document", "put_source",
        "admit_record", "admit_document", "admit_experimental_result",
    }
    for module in sorted((REPO / "execution").glob("*.py")):
        tree = ast.parse(module.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert root not in {"evidence", "scout", "retrieval", "workbench"}, (
                    f"{module.name} imports {node.module}")
                if root not in allowed_local:
                    continue
            if isinstance(node, ast.Attribute) and node.attr in forbidden_calls:
                raise AssertionError(f"{module.name} calls {node.attr}")
            if isinstance(node, ast.Name) and node.id in forbidden_calls:
                raise AssertionError(f"{module.name} references {node.id}")


def test_specification_identity_excludes_occurrence_and_time():
    """Unrepresentable by construction: the specification has exactly
    three fields, so no occurrence number, timestamp, hostname or engine
    version CAN enter its identity."""
    import dataclasses

    fields = [f.name for f in dataclasses.fields(ExecutionSpecification)]
    assert fields == ["program", "configuration", "input_payload"]


def test_protocol_error_is_not_a_result(tmp_path):
    """A malformed request produces process exit 2 and NO result lines --
    a protocol failure is unrepresentable as an execution outcome."""
    proc = subprocess.run([str(default_cli_path())], input=b"\x03", capture_output=True)
    assert proc.returncode == 2
    assert b"ste-execution-result" not in proc.stdout


def test_specification_tag_is_domain_separated_from_all_others():
    payload = [b"a", b"b", b"c"]
    assert commit_hex(SPECIFICATION_TAG, payload) not in {
        commit_hex(PROGRAM_TAG, payload),
        commit_hex(INPUT_TAG, payload),
        commit_hex(COMPUTATION_TAG, payload),
    }
