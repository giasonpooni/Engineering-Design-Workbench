"""Stage 3's critical architectural test, executed with real proofs:

    SP1 proof ------+
                    +---> the same computational statement
    Nexus proof ----+

`VerifiedExecution` claims to represent a verified computational fact,
not an SP1 fact. This file tests that proposition with one specification
proven under BOTH substrates.

Skips unless BOTH backends' artifacts are built.
"""

from __future__ import annotations

import pytest

from execution.proving import (
    default_guest_elf_path,
    default_host_path,
    default_nexus_guest_elf_path,
    default_nexus_host_path,
    prove_and_verify,
)
from execution.specification import (
    PAIRWISE_ENERGY_DESCRIPTOR,
    ExecutionSpecification,
    encode_positions,
)

SP1 = (default_host_path(), default_guest_elf_path())
NEXUS = (default_nexus_host_path(), default_nexus_guest_elf_path())

pytestmark = pytest.mark.skipif(
    not all(p.exists() for pair in (SP1, NEXUS) for p in pair),
    reason="both backends' hosts and guest ELFs are required; environment gap, "
    "not an architectural pass",
)

ARGON_PAIR = [(1000, 1000, 1000), (1400, 1000, 1000)]


@pytest.fixture(scope="module")
def both(tmp_path_factory):
    """ONE specification, TWO real proofs -- one per substrate, through
    the identical Python driver."""
    spec = ExecutionSpecification(
        program=PAIRWISE_ENERGY_DESCRIPTOR,
        configuration=b"",
        input_payload=encode_positions(ARGON_PAIR),
    )
    proofs = tmp_path_factory.mktemp("two-backends")
    sp1 = prove_and_verify(spec, proofs / "argon.sp1.proof",
                           host_path=SP1[0], elf_path=SP1[1])
    nexus = prove_and_verify(spec, proofs / "argon.nexus.proof",
                             host_path=NEXUS[0], elf_path=NEXUS[1])
    return spec, sp1, nexus


def test_one_specification_one_computation_two_proofs(both):
    """The statement is substrate-independent; only the warrants differ.

    Same ExecutionSpecification identity, same program identity (the
    DESCRIPTOR-level identity -- the Phase 126 decision that a backend's
    native commitment is never the canonical identity is what makes this
    equality possible at all), same input identity, same output bytes,
    same output identity, same computation identity. Different proof
    systems, different proof artifacts, different proof identities,
    different backends."""
    spec, sp1, nexus = both

    # The statement: identical across substrates.
    assert sp1.execution.specification_identity == nexus.execution.specification_identity
    assert sp1.execution.program_identity == nexus.execution.program_identity
    assert sp1.execution.input_identity == nexus.execution.input_identity
    assert sp1.execution.output == nexus.execution.output
    assert sp1.execution.output_identity == nexus.execution.output_identity
    assert sp1.execution.computation_identity == nexus.execution.computation_identity
    assert sp1.execution.exit_code == nexus.execution.exit_code == 0

    # The warrants: genuinely distinct.
    assert sp1.backend_name == "sp1-cpu"
    assert nexus.backend_name == "nexus-stwo"
    assert sp1.proof_identity != nexus.proof_identity
    assert sp1.proof_path != nexus.proof_path


def test_the_kernel_is_the_same_code_not_two_agreeing_codes(both):
    """The output bytes agree because native, SP1 guest and Nexus guest
    all compile the ONE execution-kernel crate -- asserted here against
    the native run both proved runs were checked against."""
    spec, sp1, nexus = both
    from execution.engine import run_specification

    native = run_specification(spec)
    assert native.output == sp1.execution.output == nexus.execution.output
    assert (
        native.computation_identity
        == sp1.execution.computation_identity
        == nexus.execution.computation_identity
    )


def test_cross_backend_verification_is_refused_not_confused(both):
    """A Nexus proof handed to the SP1 verifier (and vice versa) must
    fail loudly -- artifacts are backend-bound even though statements
    are not. Exercised at the CLI layer with mismatched proof files."""
    import subprocess

    spec, sp1, nexus = both
    descriptor = None
    for run, (host, elf) in ((nexus, SP1), (sp1, NEXUS)):
        import pathlib
        proof_path = pathlib.Path(run.proof_path)
        descriptor = proof_path.parent / "descriptor.bin"
        descriptor.write_bytes(PAIRWISE_ENERGY_DESCRIPTOR)
        proc = subprocess.run(
            [
                str(host), "verify", str(elf), str(descriptor), str(proof_path),
                "registered",
                spec.input_payload.hex(),
                run.execution.output.hex(),
                "0",
            ],
            capture_output=True, timeout=600,
        )
        assert proc.returncode == 0, proc.stderr.decode()
        text = proc.stdout.decode()
        assert "outcome failed" in text, f"foreign proof was not refused: {text}"
