"""Stage 6 -- RISC Zero as the THIRD independent implementer, audited
live with real receipts.

RISC Zero is an EXTRACT-style verifier like SP1 (the journal carries the
statement; Receipt::verify binds journal + image id), so -- unlike
Nexus's confirm-style StatementMismatch -- tamper rejections here are
attributable per dimension. The tests assert that asymmetry in the
third backend's favour.

Fork revision: risc0-zero 3bbcd44 (risc0-zkvm 5.0.0), guest target
riscv32im-risc0-zkvm-elf, toolchain r0.1.97.0 (linked as `risc0`).
Skips are environment gaps, never passes.
"""

from __future__ import annotations

import pathlib
import subprocess

import pytest

from execution.proving import (
    ProvedRunError,
    default_risc0_heat_guest_elf_path,
    default_risc0_host_path,
    prove_and_verify,
)
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR,
    PAIRWISE_ENERGY_DESCRIPTOR,
    ExecutionSpecification,
    encode_heat_input,
)

HOST = default_risc0_host_path()
ELF = default_risc0_heat_guest_elf_path()

pytestmark = pytest.mark.skipif(
    not (HOST.exists() and ELF.exists()),
    reason="risc0-host or RISC Zero guest artifact not built; environment gap",
)


def _spec():
    return ExecutionSpecification(
        HEAT_DIFFUSION_DESCRIPTOR, b"",
        encode_heat_input(50, [0, 700_000, 1_000_000, 700_000, 0, 0]),
    )


@pytest.fixture(scope="module")
def proved(tmp_path_factory):
    """ONE real RISC Zero receipt, through the identical backend-neutral
    Python driver -- only the two paths differ from SP1/Nexus."""
    return prove_and_verify(
        _spec(), tmp_path_factory.mktemp("r0") / "heat.r0.proof",
        host_path=HOST, elf_path=ELF,
    )


def _verify(proof_path, *, program_file=None, input_hex=None, output_hex=None,
            exit_code=None, proved_run=None):
    descriptor_file = proof_path.parent / "descriptor.bin"
    descriptor_file.write_bytes(HEAT_DIFFUSION_DESCRIPTOR)
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
    return dict(
        line.partition(" ")[::2] for line in proc.stdout.decode().splitlines()[1:]
    )


def test_the_full_chain_agrees_on_risc0(proved):
    assert proved.execution.status == "completed"
    assert proved.backend_name == "risc0-cpu"
    assert len(proved.proof_identity) == 64
    assert pathlib.Path(proved.proof_path).stat().st_size > 0


def test_verification_is_reproducible_from_the_artifact(proved):
    fields = _verify(pathlib.Path(proved.proof_path), proved_run=proved)
    assert fields["outcome"] == "verified"
    assert fields["coverage"] == "program=true input=true output=true exit_code=true"


def test_tampers_are_rejected_attributably(proved, tmp_path):
    """Extract-style: each altered dimension is named, as with SP1."""
    proof = pathlib.Path(proved.proof_path)
    altered_input = encode_heat_input(50, [0, 700_001, 1_000_000, 700_000, 0, 0])
    cases = [
        (dict(input_hex=altered_input.hex()), "InputMismatch"),
        (dict(output_hex=bytes(reversed(proved.execution.output)).hex()), "OutputMismatch"),
        (dict(exit_code=3), "ExitCodeMismatch"),
    ]
    for kwargs, expected in cases:
        fields = _verify(proof, proved_run=proved, **kwargs)
        assert fields["outcome"] == "failed" and expected in fields["failure"], (
            expected, fields)
    other = tmp_path / "other-program.bin"
    other.write_bytes(PAIRWISE_ENERGY_DESCRIPTOR)
    fields = _verify(proof, program_file=str(other), proved_run=proved)
    assert fields["outcome"] == "failed" and "ProgramMismatch" in fields["failure"]
    corrupted = tmp_path / "corrupted.r0.proof"
    raw = bytearray(proof.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    corrupted.write_bytes(bytes(raw))
    fields = _verify(corrupted, proved_run=proved)
    assert fields["outcome"] == "failed"
    assert ("InvalidProof" in fields["failure"]) or ("Malformed" in fields["failure"])


def test_wrong_executable_is_refused_by_artifact_identity(tmp_path):
    """Stage 5's gate covers the third backend automatically: the Nexus
    heat artifact is a real ELF, but not this backend's registered one
    -- refused before anything runs? No: BOTH are registered for this
    program, so identity admits it; what refuses a WRONG-PROGRAM elf is
    the registry. Assert exactly that boundary."""
    from execution.proving import _require_registered_artifact

    spec = _spec()
    _require_registered_artifact(spec, ELF)  # registered: accepted
    with pytest.raises(ProvedRunError):
        _require_registered_artifact(
            spec, pathlib.Path(str(ELF)).parent / "sp1-pairwise.elf"
        )
