"""One acceptance run through existing operations, learning checks and optional USD.

This is orchestration over Session, not a new workflow engine. The changed input
is the selected time window of a fixed synthetic oscillator, not a new solver or
an optimized physical design. Failure never produces a passed pilot report.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import json
import platform
from uuid import uuid4

from .instruments import make_demo_run
from .session import Session
from .learning import verify_workspace, inspect_workspace, replay_workspace
from .telemetry import canonical, digest


def _call(session, operation, parameters):
    reply = session.handle({"protocol_version": 1, "request_id": uuid4().hex,
        "type": "operation.execute", "payload": {"operation_id": operation, "parameters": parameters}})
    if reply["type"] != "response" or reply["payload"].get("status") != "completed":
        raise ValueError("Pilot calculation was not completed: " + str(reply.get("payload")))
    return reply["payload"]["result"]


def run(output_dir: Path, *, with_usd=False) -> dict:
    if type(with_usd) is not bool:
        raise ValueError("with_usd must be a Boolean")
    if with_usd:
        from .usd_export import _sdk
        _sdk()  # Refuse the explicitly requested path before starting any work.
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=False)
    try:
        session = Session(make_demo_run(), root / "records")
        early = _call(session, "statistics.v1", {"channel": "q", "interval_s": [0., 6.]})
        late = _call(session, "statistics.v1", {"channel": "q", "interval_s": [6., 12.]})
        spectrum = _call(session, "spectrum.periodogram.v1", {"channel": "q", "interval_s": [0., 12.]})
        workspace = session.save_workspace(root / "workspace.json")
        original_bytes = workspace.read_bytes()
        checks = {name: verify_workspace(workspace, result["result_id"])
                  for name, result in (("early", early), ("late", late))}
        if any(check["status"] != "matched" for check in checks.values()):
            raise ValueError("Independent RMS reference comparison failed")
        views = {name: inspect_workspace(workspace, result["result_id"])
                 for name, result in (("early", early), ("late", late))}
        if views["early"]["result"] != early or views["late"]["result"] != late:
            raise ValueError("Provider-free inspection changed a retained result")
        replay = replay_workspace(workspace, early["result_id"], root / "replay")
        if (replay["status"] != "matched" or replay["result"]["execution_id"] == early["execution_id"]
                or replay["result"]["result_id"] == early["result_id"]):
            raise ValueError("Fresh replay did not preserve distinct occurrences and numerical agreement")
        if workspace.read_bytes() != original_bytes:
            raise ValueError("Original workspace changed during inspection or replay")
        scene = {"status": "not_requested"}
        if with_usd:
            from .usd_export import export_workspace, verify_export
            export_workspace(workspace, early["result_id"], root / "scene")
            scene = {"status": "passed", **verify_export(root / "scene")}
        report = {
            "schema": "ciw.oscillator-pilot.v1", "status": "passed",
            "scope": "synthetic_recording_analysis_learning_replay_and_optional_scene",
            "question": "Compare displacement amplitude in [0,6) and [6,12) seconds of the fixed synthetic oscillator",
            "workspace_file": "workspace.json", "workspace_sha256": digest(json.loads(original_bytes)),
            "results": {name: {k: result[k] for k in ("result_id", "execution_id", "operation_id", "interval_s")}
                        for name, result in (("early", early), ("late", late), ("spectrum", spectrum))},
            "rms_checks": checks,
            "window_comparison": {"early_rms_m": early["data"]["rms"], "late_rms_m": late["data"]["rms"],
                                  "late_minus_early_m": late["data"]["rms"] - early["data"]["rms"],
                                  "scope": "change_of_analysis_window_not_model_optimization"},
            "replay": {"workspace_file": "replay/workspace.json", "result_id": replay["result"]["result_id"],
                       "execution_id": replay["result"]["execution_id"], "comparison": deepcopy(replay["comparison"])},
            "scene": scene, "python_version": platform.python_version(),
            "authority": {"physical_validation": "not_performed", "cryptographic_verification": "not_performed",
                          "equipment_control": "not_performed", "state_admission": "not_performed"},
        }
        report["report_id"] = digest(report)
        with (root / "pilot.json").open("xb") as stream:
            stream.write(canonical(report))
        return report
    except Exception as exc:
        failure = {"schema": "ciw.oscillator-pilot-failure.v1", "status": "failed",
                   "error_type": type(exc).__name__, "success_report": "not_published"}
        with (root / "failure.json").open("xb") as stream:
            stream.write(canonical(failure))
        raise


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--with-usd", action="store_true", help="Require real OpenUSD export/reload; never silently skip")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args.output_dir, with_usd=args.with_usd), indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        import sys
        print("ciw pilot: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
