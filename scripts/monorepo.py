"""Audit preserved module imports and bind their original standalone Git histories.

This operator helper never changes a runtime pin or loads executable paths from
an investigation. Detached worktrees preserve the existing adapter's strict
repository-root, commit, file-byte and interpreter checks.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from hashlib import sha1
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
_PATHS = {
    "mcur": "instruments/measurement/calibration",
    "tbrt": "instruments/measurement/clocksync",
}
_CACHES = {".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def git(root, *arguments):
    environment = dict(os.environ)
    # Repository selection is explicit; caller environment cannot replace it.
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        environment.pop(name, None)
    return subprocess.run(
        ["git", "--no-replace-objects", "-c", "core.fsmonitor=false", "-c",
         "core.autocrlf=false", "-C", str(root), *arguments],
        env=environment, check=True, capture_output=True, timeout=30,
    ).stdout


def load_manifest(root=ROOT):
    root = Path(root).resolve()
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate manifest key")
            result[key] = value
        return result
    manifest = json.loads((root / "instruments/manifest.json").read_text(), object_pairs_hook=unique)
    if set(manifest) != {"schema", "modules"} or manifest["schema"] != "notations.monorepo-imports.v1":
        raise ValueError("Unsupported import manifest")
    modules = manifest["modules"]
    if not isinstance(modules, list) or len(modules) != len(_PATHS):
        raise ValueError("First-wave manifest must name exactly two modules")
    roles = set()
    pins = json.loads((root / "src/ciw/calibrated-observable-runtimes.json").read_text())
    for module in modules:
        if not isinstance(module, dict):
            raise ValueError("Each module must be an object")
        role = module.get("role")
        if role not in _PATHS or role in roles or module.get("path") != _PATHS[role]:
            raise ValueError("Duplicate or unsupported module role/path")
        roles.add(role)
        if module.get("visibility") != "public" or module.get("license") != "MPL-2.0":
            raise ValueError("First-wave imports require declared public MPL-2.0 source")
        for key in ("import_revision", "import_tree", "runtime_revision"):
            if not isinstance(module.get(key), str) or not re.fullmatch(r"[0-9a-f]{40}", module[key]):
                raise ValueError("Full SHA-1 source identities are required")
        if module["runtime_revision"] != pins[role]["revision"]:
            raise ValueError("Runtime pin differs from the existing NET declaration")
        if module.get("source_root") != "src" or module.get("python_import") != role:
            raise ValueError("Module import contract changed")
        path = (root / module["path"]).resolve()
        if not path.is_relative_to(root) or path != root / module["path"]:
            raise ValueError("Imported module paths must not traverse symlinks")
        project = tomllib.loads((path / "pyproject.toml").read_text())["project"]
        if (project["name"] != module["distribution"] or project["version"] != module["version"]
                or project["license"] != {"text": module["license"]}):
            raise ValueError("Package identity or license differs from the import declaration")
        if module.get("notice") != "NOTICE.md" or not (path / "NOTICE.md").is_file() or not (path / "LICENSE").is_file():
            raise ValueError("Preserved license and notice are required")
    return manifest


def verify_imports(root=ROOT):
    root = Path(root).resolve()
    if Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip()).resolve() != root:
        raise ValueError("Monorepo root must be a Git repository root")
    if git(root, "rev-parse", "--show-object-format").strip() != b"sha1":
        raise ValueError("This import manifest declares SHA-1 source repositories")
    result = {}
    for module in load_manifest(root)["modules"]:
        prefix, revision, tree = module["path"], module["import_revision"], module["import_tree"]
        git(root, "merge-base", "--is-ancestor", revision, "HEAD")
        git(root, "merge-base", "--is-ancestor", module["runtime_revision"], revision)
        if git(root, "rev-parse", revision + "^{tree}").decode().strip() != tree:
            raise ValueError("Original source tree does not match declared import")
        if git(root, "rev-parse", "HEAD:" + prefix).decode().strip() != tree:
            raise ValueError("Imported subtree differs from the original source tree")
        # Hash actual working bytes as well: Git index flags must not hide drift.
        for entry in git(root, "ls-tree", "-r", "-z", revision).split(b"\0"):
            if not entry:
                continue
            metadata, raw_name = entry.split(b"\t", 1)
            mode, kind, expected = metadata.decode("ascii").split()
            path = root / prefix / os.fsdecode(raw_name)
            if kind != "blob" or mode not in {"100644", "100755"} or path.is_symlink() or not path.is_file():
                raise ValueError("Imported files must retain their regular-file types")
            if os.name == "posix" and bool(path.stat().st_mode & 0o111) != (mode == "100755"):
                raise ValueError("Imported executable mode changed")
            data = path.read_bytes()
            if sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest() != expected:
                raise ValueError("Imported working file differs from the preserved source")
        git(root, "diff", "--cached", "--quiet", "--no-ext-diff", "--no-textconv", "HEAD", "--", prefix)
        for raw_name in git(root, "ls-files", "--others", "-z", "--", prefix).split(b"\0"):
            if raw_name and not set(Path(os.fsdecode(raw_name)).relative_to(prefix).parts) & _CACHES:
                raise ValueError("Unexpected untracked file inside an imported module")
        result[module["role"]] = tree
    return result


def verify_terminal_source(root=ROOT):
    """Bind the actual tracked checkout and executable source paths to HEAD.

    This audit reads committed objects, the index and actual file bytes rather
    than trusting Git status, which can hide changes behind index flags. Gate
    output may live outside the executable source directories; generated Python
    caches and package metadata are also permitted within those directories.
    """
    root = Path(root).resolve()
    if Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip()).resolve() != root:
        raise ValueError("Terminal source must be a Git repository root")
    if git(root, "rev-parse", "--show-object-format").strip() != b"sha1":
        raise ValueError("Terminal source qualification requires SHA-1 Git objects")
    revision = git(root, "rev-parse", "HEAD").decode().strip()
    tree = git(root, "rev-parse", revision + "^{tree}").decode().strip()
    entries = []
    for entry in git(root, "ls-tree", "-r", "-z", revision).split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        mode, kind, expected = metadata.decode("ascii").split()
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError("Terminal tracked source must retain regular-file types")
        entries.append((raw_name, mode, expected))
    committed_index = sorted((name, mode, expected, "0") for name, mode, expected in entries)
    observed_index = []
    for entry in git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if entry:
            metadata, raw_name = entry.split(b"\t", 1)
            mode, expected, stage = metadata.decode("ascii").split()
            observed_index.append((raw_name, mode, expected, stage))
    if sorted(observed_index) != committed_index:
        raise ValueError("Terminal index differs from the reported source revision")
    for raw_name, mode, expected in entries:
        path = root / os.fsdecode(raw_name)
        if path.is_symlink() or not path.is_file() or path.resolve() != path:
            raise ValueError("Terminal tracked source changed type or traverses a symlink")
        if os.name == "posix" and bool(path.stat().st_mode & 0o111) != (mode == "100755"):
            raise ValueError("Terminal tracked executable mode differs from its source revision")
        data = path.read_bytes()
        if sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest() != expected:
            raise ValueError("Terminal tracked working bytes differ from the reported source revision")
    # Do not apply exclude-standard: ignored shadow modules are executable too.
    for raw_name in git(root, "ls-files", "--others", "-z", "--", "src", "scripts", "tests").split(b"\0"):
        if not raw_name:
            continue
        parts = Path(os.fsdecode(raw_name)).parts
        if any(part in _CACHES or part.startswith(".venv") or part.endswith(".egg-info")
               for part in parts[1:-1]):
            continue
        raise ValueError("Terminal executable source contains an untracked file: " + os.fsdecode(raw_name))
    if git(root, "rev-parse", "HEAD").decode().strip() != revision:
        raise ValueError("Terminal source revision changed during qualification")
    return {"revision": revision, "source_tree": tree}


@contextmanager
def provider_worktrees(root=ROOT, revisions="runtime"):
    """Yield explicit original-pin bindings, then remove their Git worktrees."""
    if revisions not in {"runtime", "import"}:
        raise ValueError("revisions must be runtime or import")
    root = Path(root).resolve()
    verify_imports(root)
    modules = load_manifest(root)["modules"]
    created = []
    with tempfile.TemporaryDirectory(prefix="notations-providers-") as temporary:
        providers = {}
        try:
            for module in modules:
                path = Path(temporary) / module["role"]
                git(root, "worktree", "add", "--detach", str(path), module[revisions + "_revision"])
                created.append(path)
                providers[module["role"]] = path
            yield providers
        finally:
            for path in reversed(created):
                git(root, "worktree", "remove", "--force", str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps({"schema": "notations.monorepo-audit.v1", "imports": verify_imports(args.root)}, indent=2))


if __name__ == "__main__":
    main()
