"""Exercise every installed weather profile outside the source checkout."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess


def snapshot(directory: Path) -> dict:
    return {str(path.relative_to(directory)): sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*") if path.is_file()}


def qualify(executable: Path, destination: Path) -> dict:
    executable = executable.resolve(strict=True)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    count = 0

    def command(*args, expected=0):
        nonlocal count
        response = subprocess.run([str(executable), "weather", *args], cwd=destination,
                                  env=environment, text=True, capture_output=True, check=False)
        count += 1
        assert response.returncode == expected, response.stderr or response.stdout
        return json.loads(response.stderr if expected == 1 else response.stdout)

    catalog = command("catalog")
    results = {}
    for name in catalog["profiles"]:
        request, directory = name + ".json", name + "-run"
        command("example", name, "--output", request)
        original = command("run", request, "--output-dir", directory)
        assert original["status"] == "LOCAL" and all(original["checks"].values())
        before = snapshot(destination / directory)
        assert command("inspect", directory) == original
        checked = command("verify", directory)
        assert checked["fresh_numerical_verification"] is True
        replay = command("replay", directory, "--output-dir", name + "-replay")
        assert replay["status"] == "PASS" and replay["result_digest_matches"]
        assert replay["source_execution_id"] != replay["replay_execution_id"]
        command("export", directory, "--output", name + "-result.json")
        assert before == snapshot(destination / directory)
        results[name] = {"status": "PASS", "evidence_id": original["evidence_id"],
                         "result_digest": original["result_digest"], "checks": len(original["checks"])}
    (destination / "invalid.json").write_text('{"schema":1,"schema":2}', encoding="utf-8")
    command("run", "invalid.json", "--output-dir", "invalid-run", expected=1)
    assert not (destination / "invalid-run").exists()
    report = {"status": "PASS", "profiles": results, "cli_calls": count,
              "claim": "installed_numerical_lifecycle_only", "physical_validation": "not_established"}
    (destination / "qualification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--net", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.net, args.output_dir), indent=2))
