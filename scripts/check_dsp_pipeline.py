"""Qualify the DSP CLI using independently installed wheels outside the checkout."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def _snapshot(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*") if path.is_file()
    }


def _final_json(stdout: str) -> dict:
    """Read the final JSON object, allowing preceding informational output."""
    decoder = json.JSONDecoder()
    for index, character in enumerate(stdout):
        if character != "{":
            continue
        try:
            value, end = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and not stdout[index + end:].strip():
            return value
    raise AssertionError("CLI did not emit a final JSON object")


def _wheel(directory: Path, prefix: str) -> Path:
    matches = sorted(directory.glob(prefix + "-*.whl"))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {prefix} wheel in {directory}; found {len(matches)}")
    return matches[0].resolve(strict=True)


def qualify(wheel_dir: Path, destination: Path) -> dict:
    """Install three wheels in a fresh venv and retain an actual CLI journey."""
    wheel_dir = wheel_dir.resolve(strict=True)
    wheels = [
        _wheel(wheel_dir, "computational_instrumentation_workbench"),
        _wheel(wheel_dir, "streaming_telemetry_feature_extraction"),
        _wheel(wheel_dir, "streaming_telemetry_dsp_extension"),
    ]
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME"}}
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUTF8"] = "1"

    def run_logged(name: str, arguments: list[str], cwd: Path, *, timeout: int = 180) -> str:
        result = subprocess.run(arguments, cwd=cwd, env=env, capture_output=True,
                                text=True, timeout=timeout)
        (destination / (name + ".stdout.log")).write_text(result.stdout, encoding="utf-8")
        (destination / (name + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
        if result.returncode:
            raise AssertionError(f"{name} exited {result.returncode}: "
                                 f"{result.stderr or result.stdout}")
        return result.stdout

    try:
        with tempfile.TemporaryDirectory(prefix="net-dsp-wheel-qualification-") as temporary:
            outside = Path(temporary)
            environment = outside / "environment"
            working = outside / "working"
            working.mkdir()
            venv.EnvBuilder(with_pip=True).create(environment)
            executable_dir = environment / ("Scripts" if os.name == "nt" else "bin")
            python = executable_dir / ("python.exe" if os.name == "nt" else "python")
            net = executable_dir / ("net.exe" if os.name == "nt" else "net")
            run_logged("installation", [str(python), "-m", "pip", "install",
                       *map(str, wheels), "scipy==1.17.0", "pytest==9.0.2"],
                       working, timeout=300)
            probe = """
import importlib, json, pathlib, sys
prefix = pathlib.Path(sys.prefix).resolve()
paths = {}
for name in ('ciw.net', 'ciw.dsp_pipeline', 'stfe.window', 'stfe_dsp.dsp', 'stfe_dsp.pipeline', 'stfe_dsp.pump'):
    location = pathlib.Path(importlib.import_module(name).__file__).resolve()
    assert location.is_relative_to(prefix), (name, str(location), str(prefix))
    paths[name] = str(location)
print(json.dumps({'isolated_environment': str(prefix), 'module_paths': paths}))
"""
            imports = _final_json(run_logged("installed-imports", [str(python), "-I", "-c", probe], working))
            run_logged("installed-packages", [str(python), "-m", "pip", "freeze"], working)

            def command(name: str, *arguments: str) -> dict:
                return _final_json(run_logged(name, [str(net), "dsp", "pipeline", *arguments], working))

            original = destination / "pump"
            demo = command("demo", "demo", "--seed", "7", "--output-dir", str(original))
            assert demo["schema"] == "ciw.dsp-pipeline-inspection.v1", demo
            assert demo["status"] == "completed" and demo["stage_count"] > 0, demo
            assert demo["state_admission"] == "not_performed", demo
            for key in ("evidence_id", "operation_id", "execution_id", "result_id"):
                assert isinstance(demo[key], str) and demo[key], (key, demo)
            assert (original / "request.json").is_file()
            assert (original / "workspace.json").is_file()
            before = _snapshot(original)

            inspected = command("inspect", "inspect", str(original))
            assert inspected["status"] == "completed", inspected
            assert inspected["fresh_execution"] is False, inspected
            assert inspected["numerical_verification"] == "not_performed", inspected
            for key in ("evidence_id", "operation_id", "execution_id", "result_id"):
                assert inspected[key] == demo[key], (key, inspected, demo)
            assert _snapshot(original) == before, "Inspection modified retained evidence"

            rerun = command("run", "run", "--request", str(original / "request.json"),
                            "--output-dir", str(destination / "rerun"))
            assert rerun["status"] == "completed", rerun
            assert rerun["evidence_id"] == demo["evidence_id"], rerun
            assert rerun["operation_id"] == demo["operation_id"], rerun
            assert rerun["execution_id"] != demo["execution_id"], rerun
            assert rerun["result_id"] != demo["result_id"], rerun

            replay = command("replay", "replay", str(original), "--output-dir",
                             str(destination / "replay"), "--atol", "1e-10", "--rtol", "1e-9")
            assert replay["schema"] == "ciw.dsp-pipeline-replay.v1", replay
            assert replay["status"] == replay["comparison"]["status"] == "PASS", replay
            assert replay["runtime_match"] is True, replay
            assert replay["source_evidence_id"] == demo["evidence_id"], replay
            assert replay["original_execution_id"] == demo["execution_id"], replay
            assert replay["original_result_id"] == demo["result_id"], replay
            assert replay["replay_execution_id"] != replay["original_execution_id"], replay
            assert replay["replay_result_id"] != replay["original_result_id"], replay
            assert isinstance(replay["verification_id"], str) and replay["verification_id"], replay
            assert replay["state_admission"] == replay["physical_validation"] == "not_performed", replay
            assert (destination / "replay" / "replay-verification.json").is_file()
            assert _snapshot(original) == before, "Replay modified the original evidence"

        report = {
            "schema": "ciw.dsp-pipeline-installed-qualification.v1",
            "status": "PASS",
            "wheels": {wheel.name: hashlib.sha256(wheel.read_bytes()).hexdigest() for wheel in wheels},
            "imports": imports,
            "commands": ["demo", "inspect", "run", "replay"],
            "stage_count": demo["stage_count"],
            "original_retained_files": len(before),
            "original_unchanged": True,
            "replay_verification_id": replay["verification_id"],
            "physical_validation": "not_performed",
            "state_admission": "not_performed",
        }
    except Exception as error:
        report = {"schema": "ciw.dsp-pipeline-installed-qualification.v1",
                  "status": "FAIL", "error": str(error)}
        (destination / "qualification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        raise
    (destination / "qualification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(qualify(arguments.wheel_dir, arguments.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
