"""run_specification: one subprocess per execution, checked not trusted.

The Rust engine (`crates/execution-cli`) is invoked with the request on
stdin and answers on stdout. This module then RECOMPUTES, from bytes
Python already holds, every identity the engine echoed -- specification,
program, input, and (for completions) output and computation -- and
raises `EngineIdentityMismatch` on any disagreement. Every execution
therefore doubles as a cross-language identity-agreement check and a
tamper check on the channel: a lying or corrupted engine binary cannot
hand this layer a wrong identity without being caught, because this
layer never accepts an identity it did not derive itself. (What CANNOT
be caught this way: an engine that runs a different computation and
honestly reports that computation's real output. That is the
bytes-vs-behavior gap, it is declared, and it is what a zkVM backend
would close.)

Statuses map onto the operation vocabulary of Phase 124:

    completed / halted  -- the program RAN (an engine-side occurrence
                           was minted and resolved; halted = no output,
                           and absence of output stays absent: no
                           OutputIdentity, no ComputationIdentity)
    unrunnable          -- the engine REFUSED to start (unknown program,
                           unsupported configuration): NEVER_STARTED at
                           this seam, surfaced as `ExecutionRefused`

The engine-side occurrence number is per-process (a fresh trace per
invocation -- always 0) and is recorded as exactly that; the durable
operation record for a dispatch lives in the Python `OperationTrace` at
the Phase 125 seam. Cross-process occurrence identity remains unsolved
and is not quietly solved here.
"""

from __future__ import annotations

import pathlib
import struct
import subprocess
from dataclasses import dataclass
from typing import Optional

from execution.commitments import (
    COMPUTATION_TAG,
    INPUT_TAG,
    OUTPUT_TAG,
    canonical_u32,
    commit_hex,
)
from execution.specification import ExecutionSpecification

_REPO = pathlib.Path(__file__).resolve().parent.parent


class EngineProtocolError(RuntimeError):
    """The engine's answer did not parse, or the process misbehaved."""


class EngineIdentityMismatch(RuntimeError):
    """The engine echoed an identity this layer's own recomputation
    contradicts. Never downgraded to a warning: a channel that can
    corrupt one identity can corrupt any of them."""


class ExecutionRefused(RuntimeError):
    """The engine refused to start the program (status `unrunnable`).
    Nothing ran; no occurrence was resolved; there is no result."""


@dataclass(frozen=True)
class ExecutionResult:
    """One checked execution as seen from Python.

    `output` is None exactly when the run halted without committing
    output -- and then `output_identity` and `computation_identity` are
    None too. An absent output is never represented as b"" (which is a
    real, committable output) or as any placeholder."""

    specification: ExecutionSpecification
    specification_identity: str
    program_identity: str
    input_identity: str
    engine_occurrence: int
    status: str  # "completed" | "halted"
    exit_code: int
    output: Optional[bytes]
    output_identity: Optional[str]
    computation_identity: Optional[str]
    detail: Optional[str]


def default_cli_path() -> pathlib.Path:
    """Where the workspace builds the engine binary."""
    return _REPO / "crates" / "target" / "release" / "execution-cli"


def _encode_request(spec: ExecutionSpecification) -> bytes:
    out = b""
    for field in (spec.program, spec.configuration, spec.input_payload):
        out += struct.pack("<Q", len(field)) + field
    return out


def _parse_lines(text: str) -> dict:
    lines = text.splitlines()
    if not lines or lines[0] != "ste-execution-result v1":
        raise EngineProtocolError(f"unrecognised result header: {lines[:1]!r}")
    fields = {}
    for line in lines[1:]:
        key, _, value = line.partition(" ")
        fields[key] = value
    return fields


def run_specification(
    spec: ExecutionSpecification, cli_path: Optional[pathlib.Path] = None
) -> ExecutionResult:
    """Execute `spec` in a fresh engine process and check everything it
    says. A batch of one: the wire format and semantics are byte-for-byte
    the original single-request contract."""
    return run_specifications([spec], cli_path=cli_path)[0]


def run_specifications(
    specs: "list[ExecutionSpecification]",
    cli_path: Optional[pathlib.Path] = None,
) -> "list[ExecutionResult]":
    """The batched forward of the SAME contract: B independent requests,
    one engine process, B result blocks in request order, each checked
    exactly as a single run is checked. The batch amortizes process
    startup; it changes no computation: every constituent keeps its own
    specification, program, input, output and computation identity, and
    the engine's occurrence numbers record execution order within the
    process. An unrunnable item raises `ExecutionRefused` naming its
    index -- refusal semantics are per-item and deterministic; a HALTED
    item is an ordinary per-item result, exactly as in a single run."""
    if not specs:
        raise ValueError("an empty batch is refused; there is nothing to execute")
    path = cli_path if cli_path is not None else default_cli_path()
    if not path.exists():
        raise EngineProtocolError(
            f"execution engine binary not found at {path}; build it with "
            f"`cargo build --release -p execution-cli` in crates/"
        )
    request = b"".join(_encode_request(spec) for spec in specs)
    proc = subprocess.run(
        [str(path)], input=request, capture_output=True,
        timeout=60 + 5 * len(specs),
    )
    if proc.returncode != 0:
        raise EngineProtocolError(
            f"engine exited {proc.returncode}: {proc.stderr.decode(errors='replace')!r}"
        )
    blocks = _split_blocks(proc.stdout.decode())
    if len(blocks) != len(specs):
        raise EngineProtocolError(
            f"engine answered {len(blocks)} result blocks for {len(specs)} requests"
        )
    # Per-batch digest reuse (checker-cost phase): identical BYTES have
    # identical digests, so a digest computed once per distinct byte
    # string may be shared across batch members -- dict key equality IS
    # the byte-for-byte identity proof, and the digests are produced by
    # the very same identity functions. This reuses COMPUTATION of an
    # identity, never an identity across different bytes, and it changes
    # no acceptance decision: `_check_result` with no precomputed
    # identities remains the semantic reference, and the two are locked
    # to agree (tests/test_execution_batch.py).
    program_digests: dict = {}
    input_digests: dict = {}
    spec_digests: dict = {}
    results = []
    for at, (spec, block) in enumerate(zip(specs, blocks)):
        program_key = spec.program
        program_identity = program_digests.get(program_key)
        if program_identity is None:
            program_identity = program_digests[program_key] = spec.program_identity()
        input_key = spec.input_payload
        input_identity = input_digests.get(input_key)
        if input_identity is None:
            input_identity = input_digests[input_key] = spec.input_identity()
        spec_key = (spec.program, spec.configuration, spec.input_payload)
        spec_identity = spec_digests.get(spec_key)
        if spec_identity is None:
            spec_identity = spec_digests[spec_key] = spec.identity()
        try:
            results.append(_check_result(
                spec, _parse_lines(block),
                precomputed=(spec_identity, program_identity, input_identity)))
        except ExecutionRefused as refusal:
            raise ExecutionRefused(f"batch item {at}: {refusal}") from refusal
    return results


def _split_blocks(text: str) -> "list[str]":
    header = "ste-execution-result v1"
    blocks: "list[list[str]]" = []
    for line in text.splitlines():
        if line == header:
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
        elif line:
            raise EngineProtocolError(f"output before the first result header: {line!r}")
    return ["\n".join(block) for block in blocks]


def _check_result(
    spec: ExecutionSpecification,
    fields: dict,
    precomputed: "Optional[tuple]" = None,
) -> ExecutionResult:
    """Check ONE result block against OUR recomputation -- the original
    single-run logic, verbatim in behavior, shared by both paths.

    `precomputed`, when given, carries (spec_identity, program_identity,
    input_identity) digests ALREADY produced by the same identity
    functions over byte-identical inputs (the batch path's per-batch
    reuse). With `precomputed=None` this function computes everything
    itself and is the semantic REFERENCE the optimized path is locked
    against. Either way: recompute-and-compare, never trust."""
    # The result must name the request it answers (Phase 128 probe 1, at
    # the process seam) -- and the name must be OUR recomputation.
    expected_spec = spec.identity() if precomputed is None else precomputed[0]
    if fields.get("spec") != expected_spec:
        raise EngineIdentityMismatch(
            f"engine answered spec {fields.get('spec')!r}; this request is {expected_spec}"
        )

    status = fields.get("status")
    if status == "unrunnable":
        raise ExecutionRefused(fields.get("detail", "engine refused the specification"))
    if status not in ("completed", "halted"):
        raise EngineProtocolError(f"unknown status {status!r}")

    if precomputed is None:
        program_identity = spec.program_identity()
        input_identity = spec.input_identity()
    else:
        _, program_identity, input_identity = precomputed
    for key, expected in (("program", program_identity), ("input", input_identity)):
        if fields.get(key) != expected:
            raise EngineIdentityMismatch(
                f"engine echoed {key} {fields.get(key)!r}; recomputed {expected}"
            )

    exit_code = int(fields["exit_code"])
    occurrence = int(fields["occurrence"])

    if status == "halted":
        return ExecutionResult(
            specification=spec, specification_identity=expected_spec,
            program_identity=program_identity, input_identity=input_identity,
            engine_occurrence=occurrence, status="halted", exit_code=exit_code,
            output=None, output_identity=None, computation_identity=None,
            detail=fields.get("detail"),
        )

    output = bytes.fromhex(fields.get("output", ""))
    output_identity = commit_hex(OUTPUT_TAG, [output])
    if fields.get("output_id") != output_identity:
        raise EngineIdentityMismatch(
            f"engine echoed output_id {fields.get('output_id')!r}; "
            f"recomputed {output_identity} from the returned bytes"
        )
    computation_identity = commit_hex(
        COMPUTATION_TAG,
        [
            bytes.fromhex(program_identity),
            bytes.fromhex(input_identity),
            bytes.fromhex(output_identity),
            canonical_u32(exit_code),
        ],
    )
    if fields.get("computation") != computation_identity:
        raise EngineIdentityMismatch(
            f"engine echoed computation {fields.get('computation')!r}; "
            f"recomputed {computation_identity}"
        )
    return ExecutionResult(
        specification=spec, specification_identity=expected_spec,
        program_identity=program_identity, input_identity=input_identity,
        engine_occurrence=occurrence, status="completed", exit_code=exit_code,
        output=output, output_identity=output_identity,
        computation_identity=computation_identity, detail=None,
    )
