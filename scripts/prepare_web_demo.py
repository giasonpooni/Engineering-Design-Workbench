#!/usr/bin/env python3
"""Install the synthetic browser demo and export its pinned local providers.

Provider preparation uses only the native Git objects retained in this checkout.
Package installation may use PyPI, or an explicitly supplied offline wheelhouse.
No existing scientific provider pin, imported subtree or Git branch is changed.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PYTHON_VERSION = "3.12.14"
BUILD_TOOLS = ("pip==25.0.1", "setuptools==84.0.0", "wheel==0.48.0", "packaging==26.3")
DEPENDENCIES = ("numpy==2.4.3", "websockets==16.0")
PROVIDERS = {
    "gsie": ("5241eee6dab434533bdf0cf0e824bc43b4a79831", "375c031c07592d5bcb1d224780f18ceb886df4a1"),
    "jspt": ("d910f5a1d7f6dd5f2dd87dfca66990f714f97b18", "5643cc8204b7aa6cbb73df6bf8984abdcec47d3b"),
}
ROOT = Path(__file__).resolve().parents[1]


def run(arguments, *, cwd=None, capture=False):
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        environment.pop(key, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return subprocess.run([str(value) for value in arguments], cwd=cwd, env=environment,
                          check=True, capture_output=capture, text=capture).stdout


def git(root, *arguments):
    return run(["git", "--no-replace-objects", "-c", "core.fsmonitor=false", "-c", "core.autocrlf=false", "-C", root, *arguments], capture=True).strip()


def verify_provider(directory, revision, tree):
    if Path(git(directory, "rev-parse", "--show-toplevel")).resolve() != directory:
        raise ValueError(f"{directory} must be an independent provider repository root")
    if git(directory, "rev-parse", "HEAD") != revision or git(directory, "rev-parse", "HEAD^{tree}") != tree:
        raise ValueError(f"{directory} differs from its declared provider pin; keep it unchanged and choose a fresh --providers directory")
    if git(directory, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError(f"{directory} contains changed or untracked files; choose a fresh --providers directory")
    # Compare actual bytes as well: skip-worktree/assume-unchanged cannot hide drift.
    for line in git(directory, "ls-tree", "-r", "HEAD").splitlines():
        metadata, name = line.split("\t", 1)
        mode, kind, object_id = metadata.split()
        path = directory / name
        if kind != "blob" or mode not in {"100644", "100755"} or not path.is_file() or path.is_symlink():
            raise ValueError(f"Unsupported provider source entry: {path}")
        if git(directory, "hash-object", "--no-filters", path) != object_id:
            raise ValueError(f"Pinned provider bytes changed: {path}")


def prepare_providers(destination):
    destination.mkdir(parents=True, exist_ok=True)
    result = {}
    for role, (revision, tree) in PROVIDERS.items():
        if git(ROOT, "rev-parse", revision + "^{tree}") != tree:
            raise ValueError(f"The checkout lacks the retained {role} source tree {tree}; obtain a native Git clone with the imported histories")
        # A runtime checkout contains the exact original commit and its source tree.
        # The full inherited history remains in the monorepo, not the image.
        directory = (destination / role).resolve()
        if not directory.exists():
            with tempfile.TemporaryDirectory(prefix=role + "-", dir=destination) as staging:
                staged = Path(staging) / "provider"
                run(["git", "init", "--quiet", staged])
                git(staged, "fetch", "--quiet", "--no-tags", "--depth=1", ROOT, revision)
                git(staged, "checkout", "--quiet", "--detach", "FETCH_HEAD")
                verify_provider(staged.resolve(), revision, tree)
                staged.rename(directory)
        verify_provider(directory, revision, tree)
        result[role] = {"repository_root": str(directory), "revision": revision, "source_tree": tree}
    return result


def install(environment, interpreter, wheelhouse):
    version = run([interpreter, "-I", "-c", "import platform; print(platform.python_version())"], capture=True).strip()
    if version != PYTHON_VERSION:
        raise ValueError(f"Demo qualification pins Python {PYTHON_VERSION}; selected interpreter reports {version}. Select it with --python /path/to/python3.12")
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if environment.exists() and not (environment / "pyvenv.cfg").is_file():
        raise ValueError(f"Refusing to reuse a non-virtual-environment directory: {environment}")
    if not environment.exists():
        run([interpreter, "-I", "-m", "venv", environment])
    actual = run([python, "-I", "-c", "import platform; print(platform.python_version())"], capture=True).strip()
    if actual != PYTHON_VERSION:
        raise ValueError(f"Existing environment reports Python {actual}; choose a fresh --environment directory")
    package_source = ["--no-index", "--find-links", wheelhouse] if wheelhouse else []
    run([python, "-I", "-m", "pip", "install", *package_source, *BUILD_TOOLS, *DEPENDENCIES])
    with tempfile.TemporaryDirectory(prefix="net-demo-wheel-") as temporary:
        stage = Path(temporary) / "source"
        stage.mkdir()
        for filename in ("pyproject.toml", "README.md", "LICENSE"):
            shutil.copy2(ROOT / filename, stage / filename)
        shutil.copytree(ROOT / "src", stage / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
        wheels = Path(temporary) / "wheels"
        run([python, "-I", "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--wheel-dir", wheels, stage])
        candidates = list(wheels.glob("computational_instrumentation_workbench-*.whl"))
        if len(candidates) != 1:
            raise ValueError("Expected exactly one freshly built workbench wheel")
        wheel = candidates[0]
        wheel_digest = sha256(wheel.read_bytes()).hexdigest()
        run([python, "-I", "-m", "pip", "install", "--no-deps", "--force-reinstall", wheel])
    run([python, "-I", "-m", "pip", "check"])
    check = run([python, "-I", "-c", "import ciw, importlib.metadata as m, json; print(json.dumps({'ciw':ciw.__file__, 'packages':{k:m.version(k) for k in ['pip','setuptools','wheel','packaging','numpy','websockets']}}))"], capture=True)
    details = json.loads(check)
    if not Path(details["ciw"]).resolve().is_relative_to(environment):
        raise ValueError("The demo must import its installed wheel from the virtual environment")
    return {"python": str(python), "python_version": actual, "wheel_sha256": wheel_digest, **details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", type=Path, default=ROOT / ".venv-demo", help="Fresh isolated virtual environment")
    parser.add_argument("--providers", type=Path, default=ROOT / ".demo-providers", help="Persistent local provider checkout directory")
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help=f"Python {PYTHON_VERSION} interpreter")
    parser.add_argument("--wheelhouse", type=Path, help="Offline wheels for the exact pinned build/runtime packages")
    parser.add_argument("--providers-only", action="store_true", help="Export native provider Git snapshots without installing Python packages")
    args = parser.parse_args()
    environment, providers = args.environment.resolve(), args.providers.resolve()
    if environment == providers or environment.is_relative_to(providers) or providers.is_relative_to(environment):
        parser.error("Environment and provider directories must be separate")
    try:
        report = {"schema": "ciw.web-demo-setup.v1", "git_revision": git(ROOT, "rev-parse", "HEAD"),
                  "build_tools": list(BUILD_TOOLS), "dependencies": list(DEPENDENCIES),
                  "providers": prepare_providers(providers)}
        if not args.providers_only:
            report["installation"] = install(environment, args.python.resolve(), args.wheelhouse.resolve() if args.wheelhouse else None)
        (providers / "setup.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        if not args.providers_only:
            print("Start: " + str(environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")) +
                  " -I -m ciw.demo_server --gsie-repo " + str(providers / "gsie") +
                  " --jspt-repo " + str(providers / "jspt") + " --host 127.0.0.1 --port 4173")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Demo preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
