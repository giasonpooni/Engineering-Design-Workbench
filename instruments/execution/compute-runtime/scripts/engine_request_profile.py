"""Rust engine per-request component attribution -- by DIFFERENTIAL
measurement, with zero instrumentation and zero implementation change.

The engine is a black box here on purpose: we vary what the request
makes it do and read the cost off the differences. Three points chosen
so input size, output size, and execution work move independently:

    P0  heat steps=0 n=3      input     32 B, output     24 B  -> fixed cost
    P1  attention n=1 d=64    input 49,416 B, output    512 B  -> big IN, small OUT
    P2  heat steps=0 n=4096   input 32,776 B, output 32,768 B  -> big IN, big OUT

heat with steps=0 executes a zero-iteration loop, so P0/P2 carry
essentially no arithmetic: their cost is parse + reconstruct + result
construction + hex + format + write. P1 adds a large input with a small
output (its arithmetic is one token's d*d projections).

    fixed          := P0
    input  per B   := (P1 - P0 - attention_arith) / input_bytes(P1)
    output per B   := (P2 - P0 - input_cost(P2)) / output_bytes(P2)

A fourth point (unrunnable descriptor) isolates spawn + parse + refusal
with no execution and no result body at all.
"""

import pathlib
import struct
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from execution.engine import _encode_request, default_cli_path
from execution.specification import (
    HARDMAX_ATTENTION_DESCRIPTOR,
    HEAT_DIFFUSION_DESCRIPTOR,
    ExecutionSpecification,
    encode_attention_input,
    encode_heat_input,
)

ENGINE = str(default_cli_path())
B = 128
ROUNDS = 5


def heat_spec(nodes: int, steps: int = 0) -> ExecutionSpecification:
    return ExecutionSpecification(
        HEAT_DIFFUSION_DESCRIPTOR, b"", encode_heat_input(steps, [1] * nodes))


def attention_spec(n: int, d: int) -> ExecutionSpecification:
    eye = [[1 if i == j else 0 for j in range(d)] for i in range(d)]
    tokens = [[(i + k) % 7 for k in range(d)] for i in range(n)]
    return ExecutionSpecification(
        HARDMAX_ATTENTION_DESCRIPTOR, b"", encode_attention_input(d, tokens, eye, eye, eye))


def measure(spec: ExecutionSpecification, label: str) -> float:
    """Engine wall time per item at B requests, best of ROUNDS."""
    stream = _encode_request(spec) * B
    best = float("inf")
    for _ in range(ROUNDS):
        t0 = time.monotonic()
        proc = subprocess.run([ENGINE], input=stream, capture_output=True)
        best = min(best, time.monotonic() - t0)
        assert proc.returncode == 0, proc.stderr[:200]
        assert proc.stdout.count(b"ste-execution-result") == B
    per = best / B * 1e6
    out_bytes = len(spec.input_payload)
    print(f"  {label:34} input {out_bytes:6d} B   {per:8.2f} us/item")
    return per


def main():
    print("=== RUST ENGINE PER-REQUEST PROFILE (differential, B=128) ===")

    # spawn + parse + refusal only: no execution, no result body
    unknown = ExecutionSpecification(b"no.such.program.v1", b"", b"")
    stream = _encode_request(unknown) * B
    best = min(
        (lambda t0=time.monotonic(): (subprocess.run([ENGINE], input=stream,
                                                     capture_output=True),
                                      time.monotonic() - t0)[1])()
        for _ in range(ROUNDS))
    refusal = best / B * 1e6
    print(f"  {'unrunnable (parse+refuse, no exec)':34} input      0 B   {refusal:8.2f} us/item")

    p0 = measure(heat_spec(3), "P0 heat steps=0 n=3 (fixed)")
    p1 = measure(attention_spec(1, 64), "P1 attention n=1 d=64 (big IN)")
    p2 = measure(heat_spec(4096), "P2 heat steps=0 n=4096 (IN+OUT)")

    in1, out1 = 49_416, 512
    in2, out2 = 32_776, 32_768

    print()
    print(f"  fixed per-request cost      : {p0:8.2f} us")
    per_in = (p1 - p0) / in1
    print(f"  input-side cost             : {per_in * 1000:8.3f} us/KB  "
          f"(from P1: {p1 - p0:.2f} us over {in1} B, incl. its d*d arithmetic)")
    input_share_p2 = per_in * in2
    per_out = (p2 - p0 - input_share_p2) / out2
    print(f"  output-side cost (hex+fmt)  : {per_out * 1000:8.3f} us/KB  "
          f"(from P2: {p2 - p0 - input_share_p2:.2f} us over {out2} B)")
    print()
    print("  -- attribution for the REAL transformer workload (d=4, n<=5) --")
    real_in, real_out = 8 + 4 * (5 * 4 + 3 * 16), 5 * 4 * 8
    print(f"  typical request: input {real_in} B, output {real_out} B")
    print(f"  fixed          : {p0:8.2f} us  ({100 * p0 / (p0 + per_in * real_in + per_out * real_out):5.1f}%)")
    print(f"  input-scaling  : {per_in * real_in:8.2f} us  "
          f"({100 * per_in * real_in / (p0 + per_in * real_in + per_out * real_out):5.1f}%)")
    print(f"  output-scaling : {per_out * real_out:8.2f} us  "
          f"({100 * per_out * real_out / (p0 + per_in * real_in + per_out * real_out):5.1f}%)")


if __name__ == "__main__":
    main()
