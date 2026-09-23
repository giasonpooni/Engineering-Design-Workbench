"""Build in a temporary copy; test the installed wheel with no source fallback."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv


ROOT = Path(__file__).resolve().parents[1]


def execute(arguments, cwd, environment):
    subprocess.run(arguments, cwd=cwd, env=environment, check=True, timeout=180)


def main():
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(key, None)
    environment["TSDE_INSTALLED_TEST"] = "1"
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    with tempfile.TemporaryDirectory(prefix="tsde-wheel-") as temporary:
        scratch = Path(temporary).resolve()
        build = scratch / "build"
        build.mkdir()
        for filename in ("pyproject.toml", "README.md", "LICENSE"):
            shutil.copy2(ROOT / filename, build / filename)
        shutil.copytree(ROOT / "src", build / "src",
                        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        wheels = scratch / "wheels"
        execute([sys.executable, "-m", "pip", "wheel", "--no-index", "--no-deps",
                 "--no-build-isolation", ".", "--wheel-dir", str(wheels)], build, environment)
        artifacts = list(wheels.glob("translation_surface_dynamics-*.whl"))
        if len(artifacts) != 1:
            raise RuntimeError("Expected exactly one provider wheel")
        virtual = scratch / "venv"
        venv.EnvBuilder(with_pip=True).create(virtual)
        python = virtual / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        case = scratch / "installed-case"
        case.mkdir()
        for folder in ("tests", "examples"):
            shutil.copytree(ROOT / folder, case / folder,
                            ignore=shutil.ignore_patterns("__pycache__"))
        for filename in ("README.md", "portfolio-project.json"):
            shutil.copy2(ROOT / filename, case / filename)
        execute([str(python), "-m", "pip", "install", "--no-index", "--no-deps",
                 str(artifacts[0])], case, environment)
        provenance = (
            "from pathlib import Path; import sys, translation_surface_dynamics as p; "
            "assert Path(p.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), p.__file__; "
            "assert p.__version__ == '0.1.0'; print('Installed provider:', p.__file__)"
        )
        execute([str(python), "-I", "-c", provenance], case, environment)
        execute([str(python), "-I", "-m", "unittest", "discover", "-s", "tests", "-v"],
                case, environment)
        completed = subprocess.run([str(python), "-I", "-m", "translation_surface_dynamics"],
                                   input=(case / "examples/request.json").read_bytes(),
                                   cwd=case, env=environment, capture_output=True, check=True, timeout=30)
        result = json.loads(completed.stdout)
        assert result["status"] == "completed"
        assert result["gluing_validation"]["genus"] == 2
        assert result["final_state"]["tile"] == 1
        assert result["final_state"]["position"] == ["1/4", "5/6"]
        print("Installed genus-two CLI artifact:", result["artifact_digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
