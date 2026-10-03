"""Stage 10 locks -- the verification artifact reuses SETUP, never a verdict.

The artifact is 398 bytes of verifier machinery (the SP1 verifying key
with a self-identifying, fail-closed header). Every test here drives a
REAL SP1 proof through it in a separate host process; nothing in these
tests -- or in the artifact -- can hold "verified=true".

Proof budget: one SP1 core proof of water's pairwise statement (~4 min,
the module fixture) plus one cheap Nexus proof for the cross-backend
refusal; the battery itself is ~0.7 s per verification.
"""

from __future__ import annotations

import pathlib
import subprocess

import pytest

from campaign.policy import VerificationLane, VerificationPolicy, WarrantRecord, policy_runner
from campaign.warrant_cache import WarrantCache, statement_key
from execution.engine import default_cli_path, run_specification
from execution.proving import (
    ProvedRunError,
    default_host_path,
    default_nexus_host_path,
    export_verification_artifact,
    prove_and_verify_result,
    verify_existing_proof,
)
from structures.library import WATER
from structures.lowering import molecule_to_pairwise_spec

REPO = pathlib.Path(__file__).resolve().parent.parent
SP1_ELF = REPO / "zk" / "artifacts" / "sp1-pairwise.elf"
SP1_VKART = REPO / "zk" / "artifacts" / "sp1-pairwise.elf.vkart"
HEAT_VKART = REPO / "zk" / "artifacts" / "sp1-heat.elf.vkart"
NEXUS_ELF = REPO / "zk" / "artifacts" / "nexus-pairwise.elf"

pytestmark = pytest.mark.skipif(
    not (default_cli_path().exists() and default_host_path().exists()
         and SP1_ELF.exists() and SP1_VKART.exists()),
    reason="sp1 host / registered guest / exported artifact not built; environment gap",
)

SPEC = molecule_to_pairwise_spec(WATER)


@pytest.fixture(scope="module")
def proved(tmp_path_factory):
    """One real SP1 proof of water's pairwise statement, shared by the
    whole battery."""
    out = tmp_path_factory.mktemp("stage10") / "water-sp1.bin"
    native = run_specification(SPEC)
    run = prove_and_verify_result(native, SPEC, out, default_host_path(), SP1_ELF)
    return native, pathlib.Path(run.proof_path), run.proof_identity


def _host_verify_vk(artifact, proof, input_hex, output_hex, exit_code):
    """Drive verify-vk directly (its own process, like every host call)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        descriptor = pathlib.Path(tmp) / "d.bin"
        descriptor.write_bytes(SPEC.program)
        return subprocess.run(
            [str(default_host_path()), "verify-vk", str(artifact), str(descriptor),
             str(proof), "registered", input_hex, output_hex, str(exit_code)],
            capture_output=True, timeout=600,
        )


def test_export_refuses_an_unregistered_elf(tmp_path):
    """The stage-5 gate applies at EXPORT: only an artifact registered
    for THIS program can have verification machinery derived from it
    (the risc0 heat guest is registered -- for the heat program, not
    this one). Refused before any setup runs -- this test is instant."""
    other = REPO / "zk" / "artifacts" / "risc0-heat.elf"
    if not other.exists():
        pytest.skip("risc0 heat guest not built; environment gap")
    with pytest.raises(ProvedRunError, match="not the reproducible-build artifact"):
        export_verification_artifact(SPEC, default_host_path(), other,
                                     tmp_path / "never.vkart")


def test_artifact_verification_is_fresh_equal_and_cross_process(proved):
    """The persisted artifact, loaded by a brand-new process, verifies
    the same proof to the same proof identity as the setup-per-hit path
    -- two DISTINCT verification operations of one statement, neither
    consulting any stored verdict (there is nowhere one could live: the
    artifact is 398 bytes of key material with a validated header)."""
    native, proof, _ = proved
    slow = verify_existing_proof(native, SPEC, proof, default_host_path(), SP1_ELF)
    fast = verify_existing_proof(native, SPEC, proof, default_host_path(), SP1_ELF,
                                 verifier_artifact=SP1_VKART)
    assert slow["outcome"] == fast["outcome"] == "verified"
    assert slow["proof_identity"] == fast["proof_identity"]
    assert SP1_VKART.stat().st_size < 1024, "the artifact is key material, tiny"


def test_corrupted_proof_still_fails_through_the_artifact(proved, tmp_path):
    """Reused setup does not soften verification: one flipped byte in
    the PROOF fails exactly as before."""
    native, proof, _ = proved
    raw = bytearray(proof.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    corrupted = tmp_path / "corrupted.bin"
    corrupted.write_bytes(bytes(raw))
    fields = verify_existing_proof(native, SPEC, corrupted, default_host_path(),
                                   SP1_ELF, verifier_artifact=SP1_VKART)
    assert fields["outcome"] == "failed"


def test_corrupted_or_tampered_artifact_fails_closed(proved, tmp_path):
    """A flipped byte in the artifact PAYLOAD, or a tampered header
    hash, is a hard refusal ('no answer exists') -- never a fallback,
    never an outcome."""
    native, proof, _ = proved
    raw = bytearray(SP1_VKART.read_bytes())
    raw[-10] ^= 0xFF  # payload corruption
    bad = tmp_path / "bad.vkart"
    bad.write_bytes(bytes(raw))
    with pytest.raises(ProvedRunError, match="verifier process failed"):
        verify_existing_proof(native, SPEC, proof, default_host_path(), SP1_ELF,
                              verifier_artifact=bad)

    text = SP1_VKART.read_bytes()
    swapped = text.replace(b"vkey_hash 0x", b"vkey_hash 0y", 1)
    tampered = tmp_path / "tampered.vkart"
    tampered.write_bytes(swapped)
    proc = _host_verify_vk(tampered, proof, SPEC.input_payload.hex(),
                           (native.output or b"").hex(), native.exit_code)
    assert proc.returncode != 0
    assert b"vkey_hash does not re-derive" in proc.stderr


def test_wrong_guest_artifact_is_refused_by_binding(proved):
    """The heat guest's artifact presented for a pairwise statement is
    refused at LOAD (program binding disagreement) -- before any
    cryptography could be asked the wrong question."""
    if not HEAT_VKART.exists():
        pytest.skip("sp1-heat artifact not exported; environment gap")
    native, proof, _ = proved
    proc = _host_verify_vk(HEAT_VKART, proof, SPEC.input_payload.hex(),
                           (native.output or b"").hex(), native.exit_code)
    assert proc.returncode != 0
    assert b"program binding disagrees" in proc.stderr


def test_forged_elf_provenance_is_caught_by_the_python_gate(proved, tmp_path):
    """An artifact whose header claims a DIFFERENT source ELF (payload
    untouched, so the Rust load succeeds) is refused by the Python
    layer's registry cross-check -- provenance is validated end to end,
    not just internal consistency."""
    native, proof, _ = proved
    raw = SP1_VKART.read_bytes()
    import re

    forged = re.sub(rb"elf_sha256 [0-9a-f]{64}", b"elf_sha256 " + b"ab" * 32, raw, count=1)
    fake = tmp_path / "forged.vkart"
    fake.write_bytes(forged)
    with pytest.raises(ProvedRunError, match="was derived from ELF"):
        verify_existing_proof(native, SPEC, proof, default_host_path(), SP1_ELF,
                              verifier_artifact=fake)


def test_cross_backend_proofs_are_refused(proved, tmp_path):
    """A REAL Nexus proof of the same statement fails through the SP1
    artifact (Malformed -- the bytes are not an SP1 proof), preserving
    one computation -> multiple warrants -> backend-specific machinery."""
    nexus_host = default_nexus_host_path()
    if not (nexus_host.exists() and NEXUS_ELF.exists()):
        pytest.skip("nexus pairwise guest not built; environment gap")
    native, _, _ = proved
    nexus_run = prove_and_verify_result(
        native, SPEC, tmp_path / "water-nexus.bin", nexus_host, NEXUS_ELF)
    fields = verify_existing_proof(native, SPEC, pathlib.Path(nexus_run.proof_path),
                                   default_host_path(), SP1_ELF,
                                   verifier_artifact=SP1_VKART)
    assert fields["outcome"] == "failed"
    assert "Malformed" in fields.get("failure", "")


def test_statement_tampering_still_fails_through_the_artifact(proved):
    """Wrong input, wrong output, wrong exit code -- each fails with the
    attributable mismatch, exactly as on the setup-per-hit path."""
    native, proof, _ = proved
    good_in = SPEC.input_payload.hex()
    good_out = (native.output or b"").hex()
    for input_hex, output_hex, exit_code, expected in (
        ("00" * 24, good_out, 0, b"InputMismatch"),
        (good_in, "00" * 16, 0, b"OutputMismatch"),
        (good_in, good_out, 7, b"ExitCodeMismatch"),
    ):
        proc = _host_verify_vk(SP1_VKART, proof, input_hex, output_hex, exit_code)
        assert proc.returncode == 0
        assert b"outcome failed" in proc.stdout and expected in proc.stdout


def test_two_hit_verifications_are_two_operations_one_evidence(proved, tmp_path):
    """Through the policy + cache + artifact: verifying one cached
    warrant twice is TWO warrant records and one unchanged proof /
    computation / statement identity. Operations never collapse;
    content always does."""
    native, proof, proof_identity = proved
    cache = WarrantCache(tmp_path / "cache")
    key = statement_key("sp1", SP1_ELF, SPEC)
    cache.store(key, proof.read_bytes(), "sp1", SPEC.identity())

    warrants: list[WarrantRecord] = []
    policy = VerificationPolicy(routine="sp1", independent=None, heavyweight=None)
    lanes = {"sp1": VerificationLane("sp1", default_host_path())}
    runner = policy_runner(policy, tmp_path, warrants, lanes=lanes, cache=cache)
    first = runner(SPEC)
    second = runner(SPEC)
    assert first.output == second.output
    assert [w.cache for w in warrants] == ["hit", "hit"]
    assert all(w.outcome == "verified" for w in warrants)
    assert len(warrants) == 2, "two verification operations, on the record"
    assert len({w.proof_identity for w in warrants}) == 1 == len({w.spec_identity for w in warrants})
    assert warrants[0].seconds < 10, "the hit went through the artifact, not setup"
