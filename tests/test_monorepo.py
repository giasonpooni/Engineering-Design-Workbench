"""Migration must retain real source histories and the existing verifier gates."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from ciw.adapters.protocol import AdapterRefusal
from ciw.adapters.subprocess import PinnedSubprocessAdapter

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("monorepo_operator", ROOT / "scripts/monorepo.py")
monorepo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monorepo)


@pytest.fixture
def checkout(tmp_path):
    path = tmp_path / "monorepo"
    subprocess.run(["git", "clone", "--quiet", "--local", "--no-hardlinks", str(ROOT), str(path)], check=True)
    # Gate sources may still be staged during development; copy just helper metadata.
    (path / "instruments/manifest.json").write_bytes((ROOT / "instruments/manifest.json").read_bytes())
    return path


def test_both_imports_and_original_runtime_commits_remain_verifiable():
    assert set(monorepo.verify_imports()) == {"mcur", "tbrt", "oit", "gsie", "cbsr", "fdir", "set"}
    with monorepo.provider_worktrees(roles=["mcur", "tbrt"]) as providers:
        bindings = []
        for role, path in providers.items():
            pin = next(m for m in monorepo.load_manifest()["modules"] if m["role"] == role)
            adapter = PinnedSubprocessAdapter(path, pin["runtime_revision"], role + (".core" if role == "mcur" else ".clock"))
            assert adapter.runtime_identity()["revision"] == pin["runtime_revision"]
            bindings.append(path)
    assert all(not path.exists() for path in bindings)


def test_subtree_directory_does_not_bypass_standalone_repository_check():
    module = monorepo.load_manifest()["modules"][0]
    with pytest.raises(AdapterRefusal, match="not a repository root"):
        PinnedSubprocessAdapter(ROOT / module["path"], module["runtime_revision"], "mcur.core")


def test_working_byte_changes_cannot_hide_behind_git_index_flags(checkout):
    relative = "instruments/measurement/calibration/src/mcur/core.py"
    monorepo.git(checkout, "update-index", "--assume-unchanged", relative)
    path = checkout / relative
    path.write_bytes(path.read_bytes() + b"\n# modified\n")
    with pytest.raises(ValueError, match="working file differs"):
        monorepo.verify_imports(checkout)


def test_staged_source_change_is_rejected_even_when_working_bytes_are_restored(checkout):
    relative = "instruments/measurement/calibration/src/mcur/core.py"
    path = checkout / relative
    original = path.read_bytes()
    path.write_bytes(original + b"\n# staged modification\n")
    monorepo.git(checkout, "add", relative)
    path.write_bytes(original)
    with pytest.raises(subprocess.CalledProcessError):
        monorepo.verify_imports(checkout)


def test_ignored_shadow_module_is_rejected(checkout):
    exclude = checkout / ".git/info/exclude"
    exclude.write_text(exclude.read_text() + "\ninstruments/measurement/clocksync/src/tbrt/shadow.py\n")
    path = checkout / "instruments/measurement/clocksync/src/tbrt/shadow.py"
    path.write_text("print('untracked shadow')\n")
    with pytest.raises(ValueError, match="untracked"):
        monorepo.verify_imports(checkout)


def test_import_snapshot_without_original_commit_ancestry_is_rejected(checkout):
    # Recommit the same tree without parents. File copies are insufficient.
    tree = monorepo.git(checkout, "rev-parse", "HEAD^{tree}").decode().strip()
    monorepo.git(checkout, "config", "user.name", "Migration test")
    monorepo.git(checkout, "config", "user.email", "migration-test@example.invalid")
    commit = monorepo.git(checkout, "commit-tree", tree, "-m", "snapshot without source ancestry").decode().strip()
    monorepo.git(checkout, "checkout", "--detach", commit)
    with pytest.raises(subprocess.CalledProcessError):
        monorepo.verify_imports(checkout)


def test_manifest_cannot_silently_change_existing_runtime_pin(checkout):
    path = checkout / "instruments/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["modules"][0]["runtime_revision"] = manifest["modules"][0]["import_revision"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Runtime pin differs"):
        monorepo.load_manifest(checkout)


def test_worktrees_are_removed_when_execution_fails():
    paths = []
    with pytest.raises(RuntimeError, match="fixture failure"):
        with monorepo.provider_worktrees(revisions="import") as providers:
            paths.extend(providers.values())
            raise RuntimeError("fixture failure")
    assert all(not path.exists() for path in paths)


def test_all_registered_runtime_bindings_use_unchanged_NET_pins():
    pins = json.loads((ROOT / "src/ciw/calibrated-observable-runtimes.json").read_text())
    with monorepo.provider_worktrees() as providers:
        assert len(providers) == 7
        for role, path in providers.items():
            pin = pins[role]
            adapter = PinnedSubprocessAdapter(path, pin["revision"], pin["module"], source_root=pin["source_root"])
            assert adapter.runtime_identity()["revision"] == pin["revision"]


def test_legacy_exchange_binding_keeps_distinct_SET_runtime_identity():
    modules = {m["role"]: m for m in monorepo.load_manifest()["modules"]}
    revision = "bd261a765281a95312f7c91a3857233476294c5b"
    with monorepo.provider_worktrees(roles=["set"], overrides={"set": revision}) as providers:
        assert set(providers) == {"set"}
        assert monorepo.git(providers["set"], "rev-parse", "HEAD").decode().strip() == revision
        adapter = PinnedSubprocessAdapter(providers["set"], revision, "state_estimation_testbed.contracts", source_root=".")
        assert adapter.runtime_identity()["revision"] == revision
    assert modules["set"]["runtime_revision"] == "5e7bda36f521a5c1b0082b512f35e29803bffafc"
    assert {m["role"]: m for m in monorepo.load_manifest()["modules"]} == modules


def test_source_override_cannot_bind_an_unrelated_terminal_commit():
    with pytest.raises(subprocess.CalledProcessError):
        with monorepo.provider_worktrees(roles=["set"], overrides={"set": "55d67d42beea95d7ce98af935b48bd84df5e9b4b"}):
            pytest.fail("Unrelated source override must not yield a provider binding")


def test_first_wave_history_remains_an_ancestor():
    monorepo.git(ROOT, "merge-base", "--is-ancestor", "4b9fd7a13e58122644d91467ba1639a5745a087e", "HEAD")


def test_manifest_cannot_relabel_an_imported_license(checkout):
    path = checkout / "instruments/manifest.json"
    manifest = json.loads(path.read_text())
    module = next(module for module in manifest["modules"] if module["role"] == "cbsr")
    module["license"] = "MPL-2.0"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="original per-module license"):
        monorepo.load_manifest(checkout)
