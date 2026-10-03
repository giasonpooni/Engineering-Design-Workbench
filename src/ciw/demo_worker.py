"""Trusted, isolated worker for the synthetic browser demo.

This is resource containment for fixed, trusted scientific code, not a sandbox
for executing visitor programs. All descendants remain in the process group
created by the server so its deadline and cancellation also stop providers.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


def install_limits(cpu_seconds: int, memory_mib: int, output_bytes: int) -> None:
    if sys.platform.startswith("linux"):
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        memory = memory_mib * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_FSIZE, (output_bytes, output_bytes))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # Existing provider adapters ordinarily create their own process groups.
    # In this worker they inherit the outer group, including their descendants.
    original = subprocess.Popen

    class ContainedProcess(original):
        def __init__(self, *args, **kwargs):
            kwargs["start_new_session"] = False
            super().__init__(*args, **kwargs)

    subprocess.Popen = ContainedProcess
    from .adapters import subprocess as adapter
    adapter._stop = lambda process: _kill_child(process)


def _kill_child(process) -> None:
    try:
        process.kill()
    except ProcessLookupError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gsie-repo", required=True)
    parser.add_argument("--jspt-repo", required=True)
    parser.add_argument("--cpu-seconds", type=int, default=30)
    parser.add_argument("--memory-mib", type=int, default=2048)
    parser.add_argument("--output-bytes", type=int, default=8 * 1024 * 1024)
    args = parser.parse_args(argv)
    if args.cpu_seconds < 1 or args.memory_mib < 256 or args.output_bytes < 1024:
        parser.error("Worker limits must be positive and sufficient for trusted providers")
    install_limits(args.cpu_seconds, args.memory_mib, args.output_bytes)
    from .adapters.protocol import AdapterRefusal
    from .adapters.subprocess import _json
    from .sensor_fusion_ekf_workflow import SensorFusionEKFWorkflow
    from .telemetry import canonical
    try:
        raw = sys.stdin.buffer.read(args.output_bytes + 1)
        if len(raw) > args.output_bytes:
            raise ValueError("Worker input exceeds its retained evidence budget")
        request = _json(raw)
        repositories = {"gsie": args.gsie_repo, "jspt": args.jspt_repo}
        workflow = SensorFusionEKFWorkflow()
        if isinstance(request, dict) and set(request) == {"mode", "source"} and request["mode"] == "execute":
            payload = {"bundle": workflow.create_session(canonical(request["source"]), repositories),
                       "replay_receipt": None}
        elif isinstance(request, dict) and set(request) == {"mode", "bundle"} and request["mode"] == "replay":
            replay = workflow.replay_session(request["bundle"], repositories)
            payload = {"bundle": replay["session"], "replay_receipt": replay["replay_receipt"]}
        else:
            raise ValueError("Require one fixed execute or retained replay request")
        response = {"ok": True, **payload}
        encoded = canonical(response)
        if len(encoded) > args.output_bytes:
            raise ValueError("Worker result exceeds its output budget")
        sys.stdout.buffer.write(encoded)
        return 0
    except (AdapterRefusal, ValueError, OSError, MemoryError) as exc:
        code = getattr(exc, "code", "WORKER_REFUSED")
        # Provider paths and runtime stderr remain private to the operator.
        response = {"ok": False, "error": {"code": code,
                    "message": "The pinned scientific worker refused this execution. Reset the example or contact the operator."}}
        sys.stdout.write(json.dumps(response, allow_nan=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
