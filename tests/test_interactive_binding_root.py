"""Operator-bound adapter sources, not native execution qualification."""
import copy
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import pytest
from ciw import interactive_simulation as flow


@pytest.fixture
def sources(tmp_path):
    root = tmp_path / 'adapter source'
    for folder, name in [('godot', 'projectile.gd'), ('blender', 'author.py'), ('bevy/src', 'main.rs')]:
        path = root / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'TEST SOURCE ONLY; NOT NATIVE QUALIFICATION\n')
    (root / 'bevy/Cargo.toml').write_text('test-only manifest')
    (root / 'bevy/Cargo.lock').write_text('test-only lock')
    return root


@pytest.mark.parametrize('engine', ['godot', 'bevy', 'blender'])
def test_explicit_root_works_without_source_tree(engine, sources, tmp_path):
    with patch.object(flow, 'ROOT', tmp_path / 'absent'), patch.object(flow, 'run_process', side_effect=AssertionError('binding must not execute')):
        binding = flow.Binding(engine, sys.executable, adapter_root=sources)
        assert binding.runtime_identity()['provider'] == 'ciw.interactive.' + engine


@pytest.mark.parametrize('engine', ['godot', 'bevy', 'blender'])
def test_relocated_identical_sources_preserve_reproduction_identity(engine, sources, tmp_path):
    binding = flow.Binding(engine, sys.executable, adapter_root=sources)
    relocated = tmp_path / 'relocated'
    shutil.copytree(sources, relocated)
    assert flow.Binding(engine, sys.executable, expected=binding.runtime_identity(), adapter_root=relocated).runtime_identity() == binding.runtime_identity()


@pytest.mark.parametrize('file', ['godot/projectile.gd', 'bevy/Cargo.lock'])
def test_reproduction_rejects_changed_sources_or_dependency_lock(file, sources):
    engine = 'godot' if file.startswith('godot') else 'bevy'
    binding = flow.Binding(engine, sys.executable, adapter_root=sources)
    (sources / file).write_text('changed bytes')
    with pytest.raises(ValueError, match='runtime identity differs'):
        flow.Binding(engine, sys.executable, expected=binding.runtime_identity(), adapter_root=sources)


def test_oversize_adapter_refused(sources):
    (sources/'godot/projectile.gd').write_bytes(b'x'*(2*1024*1024+1))
    with pytest.raises(ValueError, match='source exceeds'):
        flow.Binding('godot', sys.executable, adapter_root=sources)


def test_inspect_cli_has_no_adapter_or_executable_argument():
    with pytest.raises(SystemExit):
        flow.main(['inspect', 'never-read.json', '--adapter-root', '/untrusted'])
