"""Small reproducible throughput specimen; no performance threshold is asserted."""
from __future__ import annotations
import argparse
import json
from time import perf_counter

from tbrt.cli import example_payload, reconcile_payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10000)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 1_000_000:
        raise ValueError("iterations must be in 1..1000000")
    request = example_payload("correlated")
    start = perf_counter()
    result = None
    for _ in range(args.iterations):
        result = reconcile_payload(request)
    elapsed = perf_counter() - start
    report = {
        "schema": "notations.benchmark.v1",
        "instrument": "ClockSync",
        "case": "correlated",
        "iterations": args.iterations,
        "elapsed_seconds": elapsed,
        "operations_per_second": args.iterations / elapsed if elapsed else None,
        "event_time": result["event_time"],
        "claim": "observed throughput only; no realtime or cross-platform guarantee"
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
