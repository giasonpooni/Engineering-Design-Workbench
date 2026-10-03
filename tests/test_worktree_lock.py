"""Managed Git metadata mutations are exclusive across independent processes."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def operators(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import monorepo
    import check_monorepo_inference

    return monorepo, check_monorepo_inference


@pytest.fixture
def repository(tmp_path, operators):
    monorepo, _ = operators
    root = tmp_path / "repository"
    root.mkdir()
    monorepo.git(root, "init", "--quiet")
    monorepo.git(root, "config", "user.name", "Worktree regression")
    monorepo.git(root, "config", "user.email", "worktree-test@example.invalid")
    (root / "source.txt").write_text("unchanged pinned source\n")
    monorepo.git(root, "add", "source.txt")
    monorepo.git(root, "commit", "--quiet", "-m", "Original source pin")
    revision = monorepo.git(root, "rev-parse", "HEAD").decode().strip()
    return root, revision


_WORKER = r'''
from contextlib import contextmanager
import json, os, pathlib, sys, tempfile, time
sys.path.insert(0, sys.argv[1])
import monorepo
import check_monorepo_inference as inference
configuration = json.loads(sys.argv[2])
repository = pathlib.Path(configuration['repository'])
revision = configuration['revision']
common = pathlib.Path(configuration['common'])
worker = pathlib.Path(configuration['worker'])
marker = common / 'mutation-regression-active'
original_git = monorepo.git
original_run = inference._run

@contextmanager
def mutation_observation():
    # This independent marker makes overlap an immediate failure, even when
    # Git's own metadata race does not happen to surface on a fast machine.
    descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        time.sleep(0.03)
        yield
    finally:
        marker.unlink()

def observed_git(root, *arguments):
    if arguments[:2] in {('worktree', 'add'), ('worktree', 'remove')}:
        with mutation_observation():
            return original_git(root, *arguments)
    return original_git(root, *arguments)

def observed_run(arguments, **kwargs):
    if 'worktree' in arguments and arguments[arguments.index('worktree') + 1] in {'add', 'remove'}:
        with mutation_observation():
            return original_run(arguments, **kwargs)
    return original_run(arguments, **kwargs)

monorepo.git = observed_git
inference._run = observed_run
# Exercise the real provider_worktrees lifecycle against one small fixture
# pin rather than requiring the entire industrial manifest in this repository.
monorepo.verify_imports = lambda root: {}
monorepo.load_manifest = lambda root: {'modules': [
    {'role': 'rci', 'runtime_revision': revision, 'import_revision': revision}]}
monorepo._retained = lambda root, pin, module: original_git(root, 'cat-file', '-e', pin + '^{commit}')
(worker / 'ready').write_text('ready')
deadline = time.monotonic() + 30
while not pathlib.Path(configuration['start']).exists():
    if time.monotonic() >= deadline:
        raise RuntimeError('Worker start deadline exceeded')
    time.sleep(0.01)

for iteration in range(4):
    created = []
    try:
        if configuration['lane'] == 'provider':
            context = monorepo.provider_worktrees(repository, roles=['rci'])
        else:
            context = inference._worktree(repository, revision, worker / 'rci', worker, worker / 'commands.log')
        with context as binding:
            path = binding['rci'] if isinstance(binding, dict) else binding
            created.append(path)
            assert original_git(path, 'rev-parse', 'HEAD').decode().strip() == revision
            assert (path / 'source.txt').read_text() == 'unchanged pinned source\n'
            if iteration == 2:
                raise RuntimeError('Expected execution failure')
            time.sleep(0.01)
    except RuntimeError as error:
        if str(error) != 'Expected execution failure':
            raise
    assert created and all(not path.exists() for path in created)
assert (common / 'notations-worktree-mutation.lock').is_file()
print('Completed real add/remove cycles with cleanup after execution failure')
'''


def test_multiprocess_worktree_add_remove_share_common_directory_lock(repository, operators, tmp_path):
    monorepo, _ = operators
    root, revision = repository
    linked = tmp_path / "linked"
    with monorepo.worktree_mutation_lock(root):
        monorepo.git(root, "worktree", "add", "--detach", str(linked), revision)
    processes = []
    start = tmp_path / "start"
    try:
        for index, (lane, source) in enumerate([
            ("provider", root), ("provider", linked),
            ("inference", root), ("inference", linked),
        ]):
            worker = tmp_path / ("worker-" + str(index))
            worker.mkdir()
            configuration = {"repository": str(source), "revision": revision,
                "common": str(root / ".git"), "worker": str(worker),
                "start": str(start), "lane": lane}
            process = subprocess.Popen([sys.executable, "-c", _WORKER, str(ROOT / "scripts"),
                json.dumps(configuration)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            processes.append((process, worker))
        deadline = time.monotonic() + 30
        while not all((worker / "ready").is_file() for _, worker in processes):
            assert all(process.poll() is None for process, _ in processes), "Worker failed before the start barrier"
            assert time.monotonic() < deadline, "Workers did not reach the start barrier"
            time.sleep(0.01)
        start.write_text("start")
        for process, _ in processes:
            stdout, stderr = process.communicate(timeout=60)
            assert process.returncode == 0, stdout + stderr
            assert "Completed real add/remove cycles" in stdout
        records = monorepo.git(root, "worktree", "list", "--porcelain").decode()
        assert records.count("worktree ") == 2
        assert not (root / ".git/mutation-regression-active").exists()
    finally:
        for process, _ in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()
        with monorepo.worktree_mutation_lock(root):
            monorepo.git(root, "worktree", "remove", "--force", str(linked))


def test_inference_worktree_cleanup_and_lock_release_after_validation_failure(repository, operators, tmp_path, monkeypatch):
    monorepo, inference = operators
    root, revision = repository
    path = tmp_path / "failed-provider"

    def reject(*args):
        raise ValueError("Expected source validation failure")

    monkeypatch.setattr(inference, "_validate", reject)
    with pytest.raises(ValueError, match="Expected source validation failure"):
        with inference._worktree(root, revision, path, tmp_path, tmp_path / "commands.log"):
            pytest.fail("An invalid provider must not execute")
    assert not path.exists()
    assert monorepo.git(root, "worktree", "list", "--porcelain").decode().count("worktree ") == 1
    # Acquiring again verifies cleanup did not retain the process lock.
    with monorepo.worktree_mutation_lock(root):
        assert (root / ".git/notations-worktree-mutation.lock").is_file()


def test_worktree_lock_and_git_commands_ignore_inherited_common_directory(repository, operators, tmp_path, monkeypatch):
    monorepo, inference = operators
    root, revision = repository
    monkeypatch.setenv("GIT_COMMON_DIR", str(tmp_path / "wrong-common-directory"))
    path = tmp_path / "provider"
    with inference._worktree(root, revision, path, tmp_path, tmp_path / "commands.log"):
        assert monorepo.git(path, "rev-parse", "HEAD").decode().strip() == revision
    assert not path.exists()
    assert (root / ".git/notations-worktree-mutation.lock").is_file()
    assert not (tmp_path / "wrong-common-directory").exists()
