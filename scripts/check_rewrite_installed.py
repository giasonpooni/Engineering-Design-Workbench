"""Run selected rewrite tests against a wheel, with no checkout import fallback."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import site
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


_ISOLATED_TESTS = r"""
from importlib.machinery import PathFinder
import json
from pathlib import Path
import sys

target, tests, report, dependency_paths, names = json.loads(sys.argv[1])
target = Path(target).resolve(strict=True)
sys.path.insert(0, str(target))
# Isolated mode deliberately omits user-site dependencies. Add only the explicit
# dependency directories supplied by the parent; the wheel stays first.
for directory in dependency_paths:
    if directory not in sys.path:
        sys.path.append(directory)

class InstalledCiwOnly:
    def find_spec(self, fullname, path=None, target_module=None):
        if fullname != 'ciw' and not fullname.startswith('ciw.'):
            return None
        spec = PathFinder.find_spec(fullname, [str(target)] if fullname == 'ciw' else path)
        if spec is None or spec.origin is None or not Path(spec.origin).resolve().is_relative_to(target):
            raise ModuleNotFoundError(f"CIW module absent from installed wheel: {fullname}")
        return spec

# Fail before execution if a missing wheel module would fall back to an
# editable-install finder or any other external CIW package.
sys.meta_path.insert(0, InstalledCiwOnly())
import ciw.hypergraph_rewrite as rewrite
origin = Path(rewrite.__file__).resolve(strict=True)
assert origin.is_relative_to(target), f"rewrite imported outside installed wheel: {origin}"

import pytest
status = pytest.main([
    '-q', '-c', str(Path(tests) / 'pytest.ini'), '--override-ini=pythonpath=',
    '--confcutdir=' + tests, '--junitxml=' + report, *names,
])
for name, module in tuple(sys.modules.items()):
    if name == 'ciw' or name.startswith('ciw.'):
        path = getattr(module, '__file__', None)
        assert path is not None and Path(path).resolve().is_relative_to(target), (
            f"checkout or external CIW import: {name}: {path}")
print(json.dumps({'installed_module': str(origin), 'pytest_exit_code': status}))
raise SystemExit(status)
"""


def _junit_counts(path: Path) -> dict:
    suites = list(ET.parse(path).getroot().iter("testsuite"))
    counts = {key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    if not counts["tests"] or any(counts[key] for key in ("failures", "errors", "skipped")):
        raise RuntimeError(f"Installed qualification requires passing tests without skips: {counts}")
    return counts


def qualify(wheel: Path, tests_root: Path, test_files: list[str],
            junitxml: Path | None = None) -> dict:
    wheel = wheel.resolve(strict=True)
    tests_root = tests_root.resolve(strict=True)
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError("--wheel must identify a built wheel")
    if not test_files or len(set(test_files)) != len(test_files):
        raise ValueError("Select at least one distinct test file")
    for name in test_files:
        if Path(name).name != name or not name.startswith("test_") or not name.endswith(".py"):
            raise ValueError("Test selections must be test_*.py basenames")
        if not (tests_root / name).is_file():
            raise ValueError(f"Missing test file: {name}")

    dependency_paths = site.getsitepackages()
    user_site = site.getusersitepackages()
    dependency_paths.extend([user_site] if isinstance(user_site, str) else user_site)
    dependency_paths = [str(Path(path).resolve()) for path in dependency_paths if Path(path).is_dir()]
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"}}
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    with tempfile.TemporaryDirectory(prefix="net-rewrite-installed-") as directory:
        root = Path(directory).resolve()
        target, tests = root / "installed", root / "tests"
        tests.mkdir()
        report = root / "installed.xml"
        for name in test_files:
            shutil.copy2(tests_root / name, tests / name)
        (tests / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        installed = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-deps", "--no-compile",
             "--target", str(target), str(wheel)],
            cwd=root, env=env, capture_output=True, text=True, timeout=180)
        if installed.returncode:
            raise RuntimeError(f"Wheel installation failed:\n{installed.stdout}\n{installed.stderr}")
        arguments = [str(target), str(tests), str(report), dependency_paths, test_files]
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _ISOLATED_TESTS, json.dumps(arguments)],
            cwd=tests, env=env, capture_output=True, text=True, timeout=300)
        if completed.returncode:
            raise RuntimeError(f"Isolated installed tests failed:\n{completed.stdout}\n{completed.stderr}")
        counts = _junit_counts(report)
        origin = json.loads(completed.stdout.strip().splitlines()[-1])["installed_module"]
        if junitxml is not None:
            junitxml = junitxml.resolve()
            junitxml.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(report, junitxml)
        return {"status": "PASS", "wheel": wheel.name,
                "wheel_sha256": sha256(wheel.read_bytes()).hexdigest(),
                "python": sys.version.split()[0], "test_files": test_files,
                **counts, "isolated_python": True, "checkout_imports": "absent",
                "installed_module": origin}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--tests-root", type=Path, required=True)
    parser.add_argument("--tests", nargs="+", default=["test_hypergraph_rewrite.py"])
    parser.add_argument("--junitxml", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(qualify(arguments.wheel, arguments.tests_root, arguments.tests,
                             arguments.junitxml), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
