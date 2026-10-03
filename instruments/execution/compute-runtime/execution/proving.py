"""prove_and_verify: the proved path -- `Verified` as an earned property.

The flow, per specification, with every arrow independently checked:

    ExecutionSpecification
        -> native execution        (run_specification: checked engine)
        -> SP1 proof               (sp1-host prove: real CPU proof, no
                                    mock path exists in the adapter)
        -> independent verification(sp1-host verify: the sealed
                                    ProofBackend::verify entry point)
        -> ProvedRun               (exists ONLY if everything agreed)

Stage 3: `prove_and_verify` is BACKEND-NEUTRAL at this layer -- pass the
SP1 host+guest paths (the defaults) or the Nexus ones
(`default_nexus_host_path` / `default_nexus_guest_elf_path`); both hosts
speak the identical `ste-host-result v1` line protocol, and every check
below applies unchanged. The substrate-independence demonstration
extends to this process boundary.

HARD FAILURE, BY CONSTRUCTION (requirement 8): there is no
`verified: bool` anywhere in this module. A mismatch between the guest's
committed input/output commitments and this layer's own recomputation, a
halted guest, a non-`verified` outcome, a missing artifact -- each raises
`ProvedRunError`, and the exception propagates through the dispatch seam
exactly like any dispatch failure: the operation ledger records FAILED
and nothing reaches the evidence path. A `ProvedRun` that exists is one
whose every check passed; a weaker one is unrepresentable.

WHAT A ProvedRun DOES NOT CLAIM: that anything was measured. The proof
establishes that the registered guest program read bytes with THIS input
commitment and produced bytes with THIS output commitment under SP1
semantics. Whether those input bytes describe the world is exactly as
unknowable as it was in Phase 111b.
"""

from __future__ import annotations

import pathlib
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional

from execution.engine import ExecutionResult, run_specification
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR,
    PAIRWISE_ENERGY_DESCRIPTOR,
    ExecutionSpecification,
)

_REPO = pathlib.Path(__file__).resolve().parent.parent


class ProvingUnavailable(RuntimeError):
    """The prover binary or guest ELF is not built in this environment.
    An environment gap -- never reported as a verification outcome."""


class ProvedRunError(RuntimeError):
    """The hard failure. Anything short of full agreement lands here."""


def default_host_path() -> pathlib.Path:
    """Where the zk workspace builds the sp1-host binary."""
    return _REPO / "zk" / "target" / "release" / "sp1-host"


def default_guest_elf_path() -> pathlib.Path:
    """The SP1 pairwise guest -- the reproducible-build artifact."""
    return _REPO / "zk" / "artifacts" / "sp1-pairwise.elf"


def default_nexus_host_path() -> pathlib.Path:
    """Where the nexus workspace builds the nexus-host binary."""
    return _REPO / "zk" / "nexus" / "target" / "release" / "nexus-host"


def default_nexus_guest_elf_path() -> pathlib.Path:
    """Where the pinned nightly builds the Nexus guest ELF."""
    return _REPO / "zk" / "artifacts" / "nexus-pairwise.elf"


def default_heat_guest_elf_path() -> pathlib.Path:
    """The SP1 heat-diffusion guest ELF."""
    return _REPO / "zk" / "artifacts" / "sp1-heat.elf"


def default_nexus_heat_guest_elf_path() -> pathlib.Path:
    """The Nexus heat-diffusion guest ELF."""
    return _REPO / "zk" / "artifacts" / "nexus-heat.elf"


def default_risc0_host_path() -> pathlib.Path:
    """Where the risc0 workspace builds the risc0-host binary."""
    return _REPO / "zk" / "risc0" / "target" / "release" / "risc0-host"


def default_risc0_heat_guest_elf_path() -> pathlib.Path:
    """The RISC Zero heat-diffusion guest ELF."""
    return _REPO / "zk" / "artifacts" / "risc0-heat.elf"


def _registry_entry(spec: ExecutionSpecification):
    """Stage 5: the guest registry is an INDEX from program identity to
    reproducible-build artifacts; the authority is
    `execution.build.verify_build` over the stored recipe. Returns the
    per-backend entries for this specification's program, or None."""
    try:
        from execution.guest_registry import GUESTS
    except ImportError:
        return None
    return GUESTS.get(spec.program_identity())


def _require_registered_artifact(spec: ExecutionSpecification, elf: pathlib.Path) -> None:
    """Refuse to prove or verify against an ELF that is not the
    reproducible artifact registered for this specification's program.
    This replaces stage 4's declared registration as the gate: the
    identity checked here is re-derivable from source by rebuild
    (`verify_build`), so a false registration is CATCHABLE, not merely
    trusted."""
    import hashlib

    entries = _registry_entry(spec)
    if not entries:
        raise ProvedRunError(
            "no built guest is registered for this specification's program descriptor; "
            "refusing to prove a computation outside the capability envelope rather "
            "than pretending -- see execution/guest_registry.py and execution.build"
        )
    actual = hashlib.sha256(elf.read_bytes()).hexdigest()
    expected = {backend: entry["elf_sha256"] for backend, entry in entries.items()}
    if actual not in expected.values():
        raise ProvedRunError(
            f"ELF {elf} (sha256 {actual[:16]}...) is not the reproducible-build artifact "
            f"registered for this program (expected one of {expected}); the registry is an "
            f"index -- rebuild via execution.build to re-derive the authoritative identity"
        )


@dataclass(frozen=True)
class ProvedRun:
    """One execution that was natively run, proven, and independently
    verified -- all in agreement. Every field is data ABOUT the
    verification; none of them is a knob."""

    execution: ExecutionResult
    proof_path: str
    proof_identity: str
    backend_name: str
    backend_version: str
    vkey_hash: str


def _parse(stdout: str) -> dict:
    lines = stdout.splitlines()
    if not lines or lines[0] != "ste-host-result v1":
        raise ProvedRunError(f"unrecognised host output: {lines[:1]!r}")
    fields = {}
    for line in lines[1:]:
        key, _, value = line.partition(" ")
        fields[key] = value
    return fields


def _signal_reason(returncode: int) -> str:
    """What a NEGATIVE return code means, in words.

    `subprocess` reports a signal death as -N. The bare number is the
    least useful thing that could be said about it, and SIGKILL is the
    worst case: the process is destroyed without running a handler, so
    stderr is EMPTY and the message reads `host exited -9:` with nothing
    after the colon. That is indistinguishable, to a reader, from a
    prover that failed silently for a reason in this repository.

    MEASURED, NOT GUESSED. It happened here: nineteen proving tests
    errored with exactly that line while a C++ build ran alongside the
    suite. The prover holds roughly 7 GB and the machine has 15; the
    kernel killed it. The tests pass with the memory free. Two runs of
    the same suite reported eleven and nineteen errors -- the count
    varies with pressure, which is itself the signature.
    """
    import signal as _signal

    if returncode >= 0:
        # Not a signal at all. The caller guards this, but a helper that
        # answers confidently for an input it can be handed is the kind
        # of thing that later gets called from somewhere that does not.
        return f"host exited {returncode}"
    try:
        name = _signal.Signals(-returncode).name
    except (ValueError, TypeError):
        return f"killed by signal {-returncode}"
    if name == "SIGKILL":
        return (
            "killed by SIGKILL (-9). Nothing in this repository sends that: "
            "it is almost always the kernel's out-of-memory killer, and the "
            "prover's peak resident set is several gigabytes. Check free "
            "memory and whether anything else large was running. Note that "
            "stderr is empty above BECAUSE of the signal, not because the "
            "prover said nothing")
    if name == "SIGSEGV":
        return "killed by SIGSEGV (-11) -- a fault inside the prover itself"
    return f"killed by {name} ({returncode})"


def _run_host(host: pathlib.Path, args: list[str], timeout: int) -> dict:
    proc = subprocess.run([str(host), *args], capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace")[-400:]
        detail = (_signal_reason(proc.returncode) if proc.returncode < 0
                  else f"host exited {proc.returncode}")
        raise ProvedRunError(f"{detail}: {stderr}")
    return _parse(proc.stdout.decode())


def prove_and_verify(
    spec: ExecutionSpecification,
    proof_out: pathlib.Path,
    host_path: Optional[pathlib.Path] = None,
    elf_path: Optional[pathlib.Path] = None,
    prove_timeout: int = 3600,
) -> ProvedRun:
    """The whole chain, or an exception. See the module docstring."""
    host = host_path if host_path is not None else default_host_path()
    elf = elf_path if elf_path is not None else default_guest_elf_path()
    if not host.exists() or not elf.exists():
        raise ProvingUnavailable(
            f"sp1-host ({host}) or guest ELF ({elf}) not built; see zk/README notes "
            f"in docs/STE_VERIFICATION_SUBSTRATE.md"
        )
    _require_registered_artifact(spec, elf)

    # 1. The checked native execution.
    native = run_specification(spec)
    return prove_and_verify_result(
        native, spec, proof_out, host, elf, prove_timeout=prove_timeout
    )


def prove_and_verify_result(
    native: ExecutionResult,
    spec: ExecutionSpecification,
    proof_out: pathlib.Path,
    host: pathlib.Path,
    elf: pathlib.Path,
    prove_timeout: int = 3600,
) -> ProvedRun:
    """Stage 7 split: prove and independently verify against an ALREADY
    EXECUTED native result. The scientific computation runs once; how
    many backends warrant it is the verification policy's business, and
    re-running the science per warrant would be both wasteful and a
    category error (the proof's own in-guest execution is part of the
    proof, not a second scientific result)."""
    if not host.exists() or not elf.exists():
        raise ProvingUnavailable(f"host {host} or guest artifact {elf} not built")
    _require_registered_artifact(spec, elf)
    if native.status != "completed":
        raise ProvedRunError(
            f"native execution halted (exit {native.exit_code}); a run with no output "
            f"has nothing to prove in this stage"
        )

    with tempfile.TemporaryDirectory() as tmp:
        descriptor_file = pathlib.Path(tmp) / "descriptor.bin"
        descriptor_file.write_bytes(spec.program)

        # 2. Prove (the host verifies the fresh proof before reporting).
        prove = _run_host(
            host,
            ["prove", str(elf), str(descriptor_file), spec.input_payload.hex(), str(proof_out)],
            timeout=prove_timeout,
        )
        if prove.get("guest_status") != "completed":
            raise ProvedRunError(f"guest halted inside the zkVM: {prove}")

        # 3. Requirement 7 -- the host-side recomputation. The guest's
        # committed commitments must equal OUR canonical commitments over
        # bytes this layer already holds. Any drift between the two
        # implementations of the commitment function, any tampering with
        # the input en route, any disagreement between native and guest
        # kernels -- all land here.
        if prove.get("input_commitment") != native.input_identity:
            raise ProvedRunError(
                f"guest committed input {prove.get('input_commitment')}; "
                f"this layer computed {native.input_identity}"
            )
        if prove.get("output_commitment") != native.output_identity:
            raise ProvedRunError(
                f"guest committed output {prove.get('output_commitment')}; native "
                f"execution of the same kernel produced {native.output_identity}"
            )
        if int(prove.get("exit_code", "-1")) != native.exit_code:
            raise ProvedRunError(
                f"guest exit code {prove.get('exit_code')} != native {native.exit_code}"
            )

        # 4. Independent verification through the sealed entry point.
        verify = _run_host(
            host,
            [
                "verify", str(elf), str(descriptor_file), str(proof_out), "registered",
                spec.input_payload.hex(),
                (native.output or b"").hex(),
                str(native.exit_code),
            ],
            timeout=600,
        )
        if verify.get("outcome") != "verified":
            raise ProvedRunError(
                f"verification did not succeed: outcome={verify.get('outcome')} "
                f"failure={verify.get('failure')}"
            )
        backend_name, _, backend_version = verify.get("backend", " ").partition(" ")

    return ProvedRun(
        execution=native,
        proof_path=str(proof_out),
        proof_identity=verify["proof_identity"],
        backend_name=backend_name,
        backend_version=backend_version,
        vkey_hash=prove.get("vkey_hash", ""),
    )


def proved_runner(
    proof_dir: pathlib.Path,
    host_path: Optional[pathlib.Path] = None,
    elf_path: Optional[pathlib.Path] = None,
) -> Callable[[ExecutionSpecification], ExecutionResult]:
    """A runner for `SpecificationDispatcher` on which every dispatched
    computation must be proven and verified before its result proceeds.

    A verification failure raises out of `dispatch` -- the Phase 125 seam
    records FAILED, nothing is admitted, and there is no flag to check
    and no way to forget to check it (requirement 8)."""

    def run(spec: ExecutionSpecification) -> ExecutionResult:
        # Stage 6 campaign finding: proofs from two backends for one
        # specification collided on one filename. The artifact name now
        # carries the guest ELF stem, which identifies the backend.
        elf_stem = (elf_path if elf_path is not None else default_guest_elf_path()).stem
        proof_out = proof_dir / f"proof-{spec.identity()[:16]}-{elf_stem}.bin"
        proved = prove_and_verify(spec, proof_out, host_path=host_path, elf_path=elf_path)
        return proved.execution

    return run


def verify_existing_proof(
    native: ExecutionResult,
    spec: ExecutionSpecification,
    proof_path: pathlib.Path,
    host: pathlib.Path,
    elf: pathlib.Path,
    verifier_artifact: "pathlib.Path | None" = None,
) -> dict:
    """Stage 8: verify an EXISTING proof artifact against the statement
    of an already-executed native result -- no proving anywhere in this
    path. This is what makes a warrant cache safe: a cache hit is bytes,
    and THIS is the gate those bytes must still pass.

    Stage 10: with `verifier_artifact`, the host reconstructs its
    verifier from the persisted verification artifact (`verify-vk`)
    instead of regenerating the proving key -- the SETUP is reused, the
    verification is exactly as fresh (identical sealed path, identical
    outcome fields). The stage-5 registry gate still runs against `elf`,
    and the artifact's recorded elf_sha256 must MATCH that registered
    artifact -- a verifier artifact for any other build fails closed.
    There is no fallback: a rejected verification artifact is a hard
    error, never a silent detour through the slow path.

    Returns the host's parsed verify fields ({'outcome': 'verified'|
    'failed', 'failure': ..., 'proof_identity': ...}). Raises only for
    protocol/environment problems -- a failed verification is a RESULT
    here (the caller decides refusal/escalation), not an exception,
    because the caller must be able to distinguish 'cache hit but
    warrant invalid' from 'no warrant'."""
    if not host.exists() or not elf.exists():
        raise ProvingUnavailable(f"host {host} or guest artifact {elf} not built")
    _require_registered_artifact(spec, elf)
    if native.status != "completed":
        raise ProvedRunError("nothing to verify: the execution halted")
    with tempfile.TemporaryDirectory() as tmp:
        descriptor_file = pathlib.Path(tmp) / "descriptor.bin"
        descriptor_file.write_bytes(spec.program)
        if verifier_artifact is not None:
            command = [str(host), "verify-vk", str(verifier_artifact)]
        else:
            command = [str(host), "verify", str(elf)]
        proc = subprocess.run(
            command
            + [str(descriptor_file), str(proof_path),
               "registered", spec.input_payload.hex(), (native.output or b"").hex(),
               str(native.exit_code)],
            capture_output=True, timeout=600,
        )
        if proc.returncode != 0:
            raise ProvedRunError(
                f"verifier process failed: {proc.stderr.decode(errors='replace')[-300:]}"
            )
        fields = _parse(proc.stdout.decode())
        if verifier_artifact is not None:
            import hashlib

            recorded = fields.get("artifact_elf_sha256")
            actual = hashlib.sha256(elf.read_bytes()).hexdigest()
            if recorded != actual:
                raise ProvedRunError(
                    f"verification artifact {verifier_artifact} was derived from ELF "
                    f"{recorded}, but the registered artifact is {actual}; refusing"
                )
        return fields


def export_verification_artifact(
    spec: ExecutionSpecification,
    host: pathlib.Path,
    elf: pathlib.Path,
    artifact_out: pathlib.Path,
) -> dict:
    """Stage 10: derive and persist the reusable verification artifact
    for `elf` (the one place the expensive verifier setup runs for a
    guest whose warrants will be re-verified many times). The stage-5
    gate applies: only the REGISTERED reproducible artifact can have a
    verification artifact exported. Returns the host's report fields
    (vkey_hash, elf_sha256, artifact_bytes)."""
    if not host.exists() or not elf.exists():
        raise ProvingUnavailable(f"host {host} or guest artifact {elf} not built")
    _require_registered_artifact(spec, elf)
    with tempfile.TemporaryDirectory() as tmp:
        descriptor_file = pathlib.Path(tmp) / "descriptor.bin"
        descriptor_file.write_bytes(spec.program)
        proc = subprocess.run(
            [str(host), "export-vk", str(elf), str(descriptor_file), str(artifact_out)],
            capture_output=True, timeout=1200,
        )
        if proc.returncode != 0:
            raise ProvedRunError(
                f"export failed: {proc.stderr.decode(errors='replace')[-300:]}"
            )
        return _parse(proc.stdout.decode())
