"""Acceptance checks for a built and installed distribution, outside the source tree."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


def call(*args: str, cwd: Path) -> dict:
    completed = subprocess.run([sys.executable, "-m", "ciw", *args], cwd=cwd,
                               check=True, capture_output=True, text=True, timeout=30)
    return json.loads(completed.stdout)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ciw-installed-") as directory:
        root = Path(directory)
        demo = call("demo", "--output", str(root / "recording.json"), cwd=root)
        assert demo["sample_count"] == 768
        result = call("analyze", "spectrum", "--recording", str(root / "recording.json"),
                      "--start", "0", "--end", "12", "--output-dir", str(root / "results"), cwd=root)
        assert result["type"] == "response"
        result = result["payload"]
        assert result["operation_id"] == "spectrum.periodogram.v1"
        workspace = call("inspect", str(root / "results" / "workspace.json"), cwd=root)
        assert workspace["results"][0] == result
        assert workspace["run"]["evidence_id"] == demo["evidence_id"]
        lesson = call("math", "work", "oscillator-rms", "--output-dir", str(root / "lesson"), cwd=root)
        assert lesson["status"] == "completed"
        lesson_path = lesson["workspace_file"]
        lesson_result = lesson["result"]
        arguments = (lesson_path, "--result-id", lesson_result["result_id"])
        before = Path(lesson_path).read_bytes()
        inspected = call("math", "inspect", *arguments, cwd=root)
        assert inspected["result"] == lesson_result
        checked = call("math", "verify", *arguments, cwd=root)
        assert checked["status"] == "matched" and checked["verification_status"] == "not_verified"
        replay = call("math", "replay", *arguments, "--output-dir", str(root / "lesson-replay"), cwd=root)
        assert replay["status"] == "matched"
        assert replay["result"]["execution_id"] != lesson_result["execution_id"]
        assert replay["result"]["result_id"] != lesson_result["result_id"]
        assert replay["result"]["evidence_id"] == lesson_result["evidence_id"]
        assert Path(lesson_path).read_bytes() == before
    print("PASS: installed distribution generates, analyzes, teaches and replays retained evidence")


if __name__ == "__main__":
    main()
