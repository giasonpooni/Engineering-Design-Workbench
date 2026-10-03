"""Source/packaging and scoped-credential regressions; no provider qualification."""
from __future__ import annotations

import ast
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ci_provider_access', ROOT / 'scripts/ci_provider_access.py')
access = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(access)


def test_workbench_is_normal_python_without_runtime_source_expansion():
    from ciw import workbench
    source = Path(workbench.__file__).read_text(encoding='utf-8')
    tree = ast.parse(source)
    assert any(isinstance(node, ast.ClassDef) and node.name == 'Workbench' for node in tree.body)
    assert '_wb_pack_' not in source
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id in {'exec', 'eval'} for node in ast.walk(tree))
    assert workbench._workflow('project-graph').operation == 'ciw.project-graph.v1'
    assert 'project' in workbench.INSTRUMENT_ROLES
    assert 'project-graph' in workbench.REPRODUCED_KINDS


@pytest.mark.parametrize('path', [
    'atomtrapping/Scientific-Computation-Runtime.git',
    'atomtrapping/scientific-computation-runtime',
    'atomtrapping/Parameterized-Lyapunov-Stability-Runtime.git',
    'atomtrapping/Notations-Compute-Runtime.git',
    'atomtrapping/notations-data-intake',
])
def test_helper_answers_only_an_allowlisted_repo(path):
    request = 'protocol=https\nhost=github.com\npath=' + path + '\n\n'
    assert access.credential(request, 'test-secret') == 'username=x-access-token\npassword=test-secret\n\n'


@pytest.mark.parametrize('wire_request', [
    'protocol=http\nhost=github.com\npath=atomtrapping/Scientific-Computation-Runtime.git\n',
    'protocol=https\nhost=github.com.attacker.test\npath=atomtrapping/Scientific-Computation-Runtime.git\n',
    'protocol=https\nhost=github.com:443\npath=atomtrapping/Scientific-Computation-Runtime.git\n',
    'protocol=https\nhost=github.com\npath=other/Scientific-Computation-Runtime.git\n',
    'protocol=https\nhost=github.com\npath=giasonpooni/Scientific-Computation-Runtime.git\n',
    'protocol=https\nhost=github.com\npath=atomtrapping/Unregistered-Repository.git\n',
    'protocol=https\nhost=github.com\npath=atomtrapping/../Scientific-Computation-Runtime.git\n',
    'protocol=https\nhost=github.com\npath=atomtrapping/Scientific-Computation-Runtime.git/info/refs\n',
    'protocol=https\nhost=github.com\nhost=github.com\npath=atomtrapping/Scientific-Computation-Runtime.git\n',
    'protocol=https\nhost=github.com\n', 'x' * 8193,
])
def test_helper_refuses_unbound_or_ambiguous_destinations(wire_request):
    assert access.credential(wire_request, 'test-secret') == ''


def test_configuration_contains_no_token_and_quotes_paths(tmp_path, monkeypatch):
    helper = tmp_path / "directory with spaces" / "helper's file.py"
    monkeypatch.setenv('CIW_PROVIDER_READ_TOKEN', 'test-secret')
    config = access.configuration(helper)
    assert 'test-secret' not in str(config)
    assert config['GIT_CONFIG_COUNT'] == '3'
    assert config['GIT_CONFIG_VALUE_0'] == ''
    assert config['GIT_CONFIG_VALUE_2'] == 'true'
    assert config['GIT_TERMINAL_PROMPT'] == '0'


def test_missing_secret_refuses_without_writing_environment(tmp_path, monkeypatch):
    destination = tmp_path / 'env'
    monkeypatch.delenv('CIW_PROVIDER_READ_TOKEN', raising=False)
    monkeypatch.setenv('GITHUB_ENV', str(destination))
    assert access.main(['configure']) == 2
    assert not destination.exists()


@pytest.mark.parametrize('event,ref', [('pull_request','refs/pull/1/merge'), ('push','refs/heads/unreviewed')])
def test_unreviewed_events_never_configure_credentials(tmp_path, monkeypatch, event, ref):
    destination = tmp_path / 'env'
    monkeypatch.setenv('CIW_PROVIDER_READ_TOKEN', 'test-secret')
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('GITHUB_EVENT_NAME', event)
    monkeypatch.setenv('GITHUB_REF', ref)
    monkeypatch.setenv('GITHUB_ENV', str(destination))
    assert access.main(['configure']) == 2
    assert not destination.exists()


def test_main_configuration_writes_no_secret(tmp_path, monkeypatch, capsys):
    destination = tmp_path / 'env'
    for key, value in {'CIW_PROVIDER_READ_TOKEN':'test-secret', 'GITHUB_ACTIONS':'true',
                       'GITHUB_EVENT_NAME':'push', 'GITHUB_REF':'refs/heads/main',
                       'GITHUB_ENV':str(destination)}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('GIT_CONFIG_COUNT', raising=False)
    assert access.main(['configure']) == 0
    assert 'test-secret' not in destination.read_text()
    output = capsys.readouterr()
    assert 'test-secret' not in output.out + output.err


def test_store_and_erase_do_not_persist_credentials(monkeypatch, capsys):
    monkeypatch.setenv('CIW_PROVIDER_READ_TOKEN', 'test-secret')
    for operation in ('store', 'erase'):
        assert access.main(['credential', operation]) == 0
    assert capsys.readouterr().out == ''


def test_real_git_credential_protocol_obeys_repository_allowlist(tmp_path):
    env = dict(os.environ, **access.configuration(Path(access.__file__)),
               CIW_PROVIDER_READ_TOKEN='test-secret', GIT_CONFIG_NOSYSTEM='1',
               GIT_CONFIG_GLOBAL=os.devnull)
    allowed = subprocess.run(['git','credential','fill'], input='protocol=https\nhost=github.com\npath=atomtrapping/Scientific-Computation-Runtime.git\n\n',
                             env=env, cwd=tmp_path, text=True, capture_output=True, timeout=10)
    assert allowed.returncode == 0
    assert 'password=test-secret' in allowed.stdout
    denied = subprocess.run(['git','credential','fill'], input='protocol=https\nhost=github.com\npath=attacker/other.git\n\n',
                            env=env, cwd=tmp_path, text=True, capture_output=True, timeout=10)
    assert denied.returncode != 0
    assert 'test-secret' not in denied.stdout + denied.stderr


def test_ci_concurrency_and_provider_wiring():
    spec = importlib.util.spec_from_file_location('ci_policy', ROOT / 'scripts/check_ci_policy.py')
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    assert policy.main(ROOT) == 0
    assert "github.event_name == 'push' && github.ref" in policy.GROUP
    assert 'github.event.pull_request.number' in policy.GROUP
    for path in (ROOT / '.github/workflows').glob('*.yml'):
        workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        for job in workflow.get('jobs', {}).values():
            if 'matrix' in job.get('strategy', {}):
                assert job['strategy']['fail-fast'] == 'false', path.name
            if 'CIW_PROVIDER_READ_TOKEN' not in job.get('env', {}):
                continue
            assert 'secrets.CIW_PROVIDER_READ_TOKEN' in job['env']['CIW_PROVIDER_READ_TOKEN']
            steps = job['steps']
            assert any(step.get('run') == 'python scripts/ci_provider_access.py configure' for step in steps)
            for step in steps:
                if step.get('with', {}).get('repository', '').startswith('atomtrapping/'):
                    assert step['with']['token'] == '${{ env.CIW_PROVIDER_READ_TOKEN }}'
                    assert step['with']['persist-credentials'] == 'false'
