"""Qualify six public mathematical instruments without replacing runtime pins.

Each current package is checked as its own installed wheel. Metrology's current
0.2.0 release and its retained 0.1.0 adapter are separate qualifications. The
unchanged Terminal measurement chain uses exact historical public source roots;
its replay is computational reproduction, with no state admission or independent
scientific verification. Surface and the full identified-design stack are outside
this gate.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import uuid
import venv

if __package__:
    from .check_monorepo import _copy_source, _environment, _git, _IMPORT_PROBE, _junit, _run, _wheel
    from .check_monorepo_inference import _validate, _worktree
    from .monorepo import ROOT, _retained, load_manifest, provider_worktrees, verify_imports
else:
    from check_monorepo import _copy_source, _environment, _git, _IMPORT_PROBE, _junit, _run, _wheel
    from check_monorepo_inference import _validate, _worktree
    from monorepo import ROOT, _retained, load_manifest, provider_worktrees, verify_imports

ROLES = frozenset({"edspt", "sidt", "jspt", "rci", "stfe", "tsde"})
DEPENDENCIES = ["numpy==2.4.3", "pytest==8.4.2", "websockets==16.0"]
LEGACY_SET_REVISION = "bd261a765281a95312f7c91a3857233476294c5b"
STFE_SET_REVISION = "c4d39c755187796ce2c72552a90454871c516c8f"
STFE_TERMINAL_REVISION = "4ac382b4f3bab490de30347af58c7cfdffa9547e"
RCI_REVISION = "f863bdd69d49224e0cdc871943bbb052e5b0a975"
RCI_LEGACY_REVISION = "97fcc01a45985defd6a76532b1fefe90d66dd159"
JSPT_REVISION = "d910f5a1d7f6dd5f2dd87dfca66990f714f97b18"
FLOWSTATE_REPOSITORY = "https://github.com/giasonpooni/Notations-FlowState.git"
FLOWSTATE_REPOSITORY_ID = 1366033244
FLOWSTATE_REVISION = "09a756dd9cdd3a9bb6cb14b5cd498f6259937ac2"
FLOWSTATE_LEGACY_REVISION = "d34588819f657b6639c8e9a19450215844610007"
PROCESS_TESTS = (
    "test_measurement_chain.py", "test_covariance_integration.py",
    "test_covariance_artifacts.py", "test_covariance_records.py",
    "test_covariance_replay_refusal.py", "test_rci_records.py",
    "test_investigation.py", "test_adapter_cli.py",
)
SCOPE = (
    "Independent public package wheels, unchanged original suites and examples, "
    "and exact historical public RCI/FSRT/JSPT measurement-chain reproduction. "
    "No physical validation, independent scientific verification, state admission, "
    "full FlowState-suite qualification, Surface qualification, or full "
    "identified-design-stack qualification."
)
_BINDING_KEYS = (
    "STFE_SET_REPO", "STFE_CIW_REPO", "CIW_RCI_REPO", "CIW_FSRT_REPO",
    "CIW_JSPT_REPO", "CIW_RCI_LEGACY_REPO", "CIW_FSRT_LEGACY_REPO",
    "CIW_MEASUREMENT_CHAIN_STACK_ROOT", "CIW_CALIBRATED_STACK_ROOT",
    "CIW_IDENTIFIED_DESIGN_STACK_ROOT", "TSDE_INSTALLED_TEST",
    "GSIE_SET_REPO", "GSIE_CIW_REPO", "SET_CIW_REPO", "CBSR_FSRT_REPO", "CBSR_GTE_REPO",
)


def _run_bound(arguments, *, cwd: Path, log: Path, bindings=None,
               stdin: bytes | None = None, timeout: int = 300) -> str:
    environment = _environment()
    for key in _BINDING_KEYS:
        environment.pop(key, None)
    environment.update({key: str(value) for key, value in (bindings or {}).items()})
    command = [str(argument) for argument in arguments]
    display = list(command)
    if "-c" in display:
        position = display.index("-c") + 1
        if "\n" in display[position]:
            display[position] = "<inline-sha256:" + sha256(command[position].encode()).hexdigest() + ">"
    with log.open("ab") as stream:
        stream.write(("\n$ " + " ".join(display) + "\n").encode())
        completed = subprocess.run(command, cwd=cwd, env=environment, input=stdin,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   timeout=timeout, check=False)
        stream.write(completed.stdout)
    if completed.returncode:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(display[:4])}\n"
                           + completed.stdout.decode(errors="replace")[-8000:])
    return completed.stdout.decode()


def _python(path: Path, temporary: Path, log: Path, *, build=False, jax=False) -> Path:
    venv.EnvBuilder(with_pip=True).create(path)
    python = path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    dependencies = list(DEPENDENCIES)
    if build:
        dependencies += ["setuptools>=77", "wheel", "hatchling>=1.27"]
    if jax:
        dependencies += ["jax[cpu]>=0.4"]
    _run_bound([python, "-I", "-m", "pip", "install", *dependencies],
               cwd=temporary, log=log, timeout=600)
    return python


def _probe(python: Path, wheels: dict, temporary: Path, log: Path) -> dict:
    expected = {name: {key: wheel[key] for key in ("distribution", "version")}
                for name, wheel in wheels.items()}
    return json.loads(_run_bound([python, "-I", "-c", _IMPORT_PROBE, json.dumps(expected)],
                                cwd=temporary, log=log))


def _test_hashes(source: Path) -> dict[str, str]:
    return {str(path.relative_to(source)): sha256(path.read_bytes()).hexdigest()
            for path in sorted((source / "tests").rglob("*.py"))}


def _suite(source: Path, target: Path, *, source_root="src", package_path=None) -> tuple[Path, dict]:
    expected = _test_hashes(source)
    _copy_source(source, target)
    # Keep fixtures, declarations, docs and examples at their original paths,
    # but physically remove importable provider source from wheel-test copies.
    package = target / (package_path if source_root == "." else source_root)
    if package.exists():
        shutil.rmtree(package)
    if _test_hashes(target) != expected:
        raise AssertionError("An original provider test changed while preparing its suite")
    return target, expected


_PYTEST = r'''
import importlib, pathlib, sys
suite, module_name = sys.argv[1:3]
module = importlib.import_module(module_name)
prefix = pathlib.Path(sys.prefix).resolve()
if not pathlib.Path(module.__file__).resolve().is_relative_to(prefix):
    raise AssertionError('Tests must import the installed provider wheel')
# SIDT's original tests import its examples namespace. The copied root has no
# provider package or src tree; adding it cannot supply provider implementation.
sys.path.insert(0, suite)
import pytest
raise SystemExit(pytest.main(sys.argv[3:]))
'''

_ORIGINAL_SCRIPT = r'''
import importlib, pathlib, runpy, sys
script, module_name = sys.argv[1:3]
path = pathlib.Path(script).resolve()
module = importlib.import_module(module_name)
if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):
    raise AssertionError('Example must use the installed provider wheel')
# Preserve original sibling-example imports without restoring provider source.
sys.path.insert(0, str(path.parent))
sys.path.insert(1, str(path.parent.parent))
sys.argv = [script]
runpy.run_path(script, run_name='__main__')
if not pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):
    raise AssertionError('Example replaced the installed provider')
'''


def _pytest(python: Path, suite: Path, module_name: str, configuration: Path,
            junit: Path, log: Path, *, bindings=None, timeout=900) -> dict:
    _run_bound([python, "-I", "-c", _PYTEST, suite, module_name,
                "-q", "-c", configuration, "--import-mode=importlib",
                "--junitxml", junit, suite / "tests"],
               cwd=suite, log=log, bindings=bindings, timeout=timeout)
    return _junit(junit)


def _example(python: Path, suite: Path, module_name: str, name: str,
             label: str, output: Path, log: Path, *, bindings=None) -> dict:
    script = suite / "examples" / name
    raw = _run_bound([python, "-I", "-c", _ORIGINAL_SCRIPT, script, module_name],
                     cwd=suite, log=log, bindings=bindings)
    path = output / (label + "-" + name.removesuffix(".py") + ".txt")
    path.write_text(raw)
    artifacts = {}
    for artifact in sorted((suite / "results").rglob("*")) if (suite / "results").exists() else ():
        if artifact.is_file():
            target = output / "example-artifacts" / label / artifact.relative_to(suite / "results")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(artifact, target)
            artifacts[str(artifact.relative_to(suite / "results"))] = {
                "path": str(target), "sha256": sha256(target.read_bytes()).hexdigest()}
    return {"source_sha256": sha256(script.read_bytes()).hexdigest(),
            "output": str(path), "output_sha256": sha256(path.read_bytes()).hexdigest(),
            "artifacts": artifacts}


def _flowstate(supplied: Path | None, temporary: Path, log: Path) -> Path:
    repository = supplied.expanduser().resolve() if supplied else ROOT
    if Path(_git(repository, "rev-parse", "--show-toplevel")).resolve() != repository:
        raise ValueError("FlowState source binding must name its Git repository root")
    retained_module = None
    if supplied is None:
        retained_module = next((module for module in load_manifest(root=ROOT)["modules"]
                                if module["role"] == "fsrt"), None)
        if retained_module is None:
            raise ValueError("Default FlowState binding requires its declared retained public history")
    for revision in (FLOWSTATE_REVISION, FLOWSTATE_LEGACY_REVISION):
        _git(repository, "cat-file", "-e", revision + "^{commit}")
        if retained_module is not None:
            _retained(ROOT, revision, retained_module)
    return repository


def _unittest_result(raw: str, path: Path, *, expected=19) -> dict:
    counts = re.findall(r"\bRan (\d+) tests? in ", raw)
    if counts != [str(expected)] or re.search(r"\b(skipped|FAILED|ERROR)\b", raw):
        raise AssertionError("Original Polygon unittest suite must execute all 19 tests without skips")
    path.write_text(raw)
    return {"tests": expected, "failures": 0, "errors": 0, "skipped": 0,
            "output": str(path), "output_sha256": sha256(path.read_bytes()).hexdigest()}


_SNAPSHOT = r'''
from copy import deepcopy
from hashlib import sha256
import json, pathlib, sys
import numpy as np
from ciw import measurement_chain as chain
from ciw.session import write_json
from ciw.telemetry import canonical

configuration = json.loads(pathlib.Path(sys.argv[1]).read_text())
source_path = pathlib.Path(configuration['source'])
raw = source_path.read_bytes()
source = chain._source(raw)
providers = {role: pathlib.Path(path) for role, path in configuration['providers'].items()}
assert set(providers) == chain.ROLES
original = chain.create_session(raw, providers)
before = deepcopy(original)
replayed = chain.replay_session(original, providers)
fresh, receipt = replayed['session'], replayed['replay_receipt']
assert original == before and source_path.read_bytes() == raw
assert chain._validate(original) == raw and chain._validate(fresh) == raw
assert canonical(original['steps'][0]['numerical_result']) == canonical(fresh['steps'][0]['numerical_result'])
assert original['steps'][0]['numerical_result_id'] == fresh['steps'][0]['numerical_result_id']
assert original['source'] == fresh['source']
assert receipt['numerical_match'] is True and receipt['admission'] == 'not_performed'
assert original['session_id'] != fresh['session_id']
assert original['bundle_digest'] != fresh['bundle_digest']
assert not chain.native_occurrences(original) & chain.native_occurrences(fresh)
for bundle in (original, fresh):
    verification = bundle['verification']
    assert verification['outcome'] == 'passed' and verification['independent'] is False
    assert verification['authority']['state_admission'] == 'not_performed'
    step = bundle['steps'][0]
    assert step['result']['authority']['state_admission'] == 'not_performed'
    assert bundle['configuration'] == source['configuration'] == chain.POLICY
    assert step['execution_id'] != verification['reproduction']['execution_id']
    assert step['result_id'] != verification['reproduction']['result_id']
    assert not chain.native_ids(step) & chain.native_ids(verification['reproduction'])
    chain.identity_claims(bundle)
    native = step['result']['data']['native_workspace']
    fsrt, jspt = native['results']
    assert [fsrt['operation_id'], jspt['operation_id']] == [chain.FSRT_OPERATION, chain.JSPT_OPERATION]
    assert fsrt['verification_status'] == jspt['verification_status'] == 'not_verified'
    selected = fsrt['data']['covariance_artifacts'][source['covariance_map']['source_artifact']]
    assert selected == jspt['data']['input_covariance']
    covariance = np.asarray(selected['matrix'])
    jacobian = np.asarray(source['covariance_map']['jacobian'])
    np.testing.assert_allclose(jspt['data']['output_covariance']['matrix'], jacobian @ covariance @ jacobian.T,
                               rtol=1e-12, atol=1e-15)
    assert covariance[0,1] != 0
    assert not np.allclose(jacobian @ covariance @ jacobian.T,
                          jacobian @ np.diag(np.diag(covariance)) @ jacobian.T, rtol=1e-12, atol=1e-15)
    assert jspt['parameters']['source_result_id'] == fsrt['result_id']
    for supplied, sensor in zip(source['investigation']['sensors'], native['run']['metadata']['rci_source']['sensors']):
        assert sensor['request'] == supplied['request']
        assert sensor['measurement']['records'][0]['raw_record_b64'] == supplied['request']['inputs']['records'][0]['raw_record_b64']
        assert sensor['measurement']['uncertainty']['covariance_basis'] == supplied['request']['inputs']['calibration']['covariance_basis']
    runtimes = chain._runtime_records(native)
    for role, runtime in runtimes.items():
        assert runtime['revision'] == chain.PINS[role]['revision']
        assert runtime['source_tree'] == chain.PINS[role]['source_tree']
for field in ('execution_id', 'result_id'):
    assert original['steps'][0][field] != fresh['steps'][0][field]
assert original['verification']['verification_id'] != fresh['verification']['verification_id']
directory = pathlib.Path(configuration['sessions'])
directory.mkdir(parents=True)
artifacts = {}
for label, value in (('original', original), ('replay', fresh), ('receipt', receipt)):
    path = write_json(directory / (label + '.json'), value)
    artifacts[label] = {'path': str(path), 'sha256': sha256(path.read_bytes()).hexdigest()}
report = {'schema': 'notations.monorepo-measurement-chain-check.v1', 'status': 'passed',
    'claim_scope': configuration['claim_scope'], 'independent_verification': False,
    'canonicalAdmission': False, 'admission': 'not_performed',
    'numerical_replay_equal': True, 'fresh_native_occurrences': True,
    'full_covariance_retained': True, 'original_raw_bytes_retained': True,
    'original_source_sha256': sha256(raw).hexdigest(),
    'numerical_result_id': original['steps'][0]['numerical_result_id'],
    'original_session_id': original['session_id'], 'replayed_session_id': fresh['session_id'],
    'runtimes': chain._runtime_records(original['steps'][0]['result']['data']['native_workspace']),
    'artifacts': artifacts}
pathlib.Path(configuration['report']).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps({'measurement_chain': 'passed', 'exact_replay': True, 'admission': 'not_performed'}))
'''


def _qualify(args, report: dict, output: Path, log: Path) -> None:
    if sys.version_info < (3, 12):
        raise ValueError("Mathematical instrument qualification requires Python >=3.12")
    manifest = load_manifest(root=ROOT)
    all_modules = {module["role"]: module for module in manifest["modules"]}
    if not ROLES <= set(all_modules) or "set" not in all_modules:
        raise ValueError("Math gate requires all six declared public modules and retained SET history")
    modules = {role: all_modules[role] for role in sorted(ROLES)}
    if modules["rci"]["version"] != "0.2.0":
        raise ValueError("Current Metrology qualification must remain distinct from historical 0.1.0")
    if modules["rci"]["runtime_revision"] != RCI_REVISION or modules["jspt"]["runtime_revision"] != JSPT_REVISION:
        raise ValueError("Measurement-chain original runtime pins changed")
    report["imports"] = verify_imports(root=ROOT)
    report["modules"] = list(modules.values())
    with tempfile.TemporaryDirectory(prefix="notations-math-gate-") as directory, ExitStack() as contexts:
        temporary = Path(directory)
        build_python = _python(temporary / "build-venv", temporary, log, build=True)
        build = temporary / "build-sources"
        build.mkdir()
        terminal = build / "terminal"
        terminal.mkdir()
        shutil.copytree(ROOT / "src", terminal / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        for filename in ("pyproject.toml", "LICENSE"):
            shutil.copyfile(ROOT / filename, terminal / filename)
        ciw_wheel = _wheel(build_python, terminal, temporary / "wheel-ciw", log)
        wheels, suites, test_hashes = {}, {}, {}
        with provider_worktrees(root=ROOT, revisions="import", roles=sorted(ROLES)) as imported:
            for role, module in modules.items():
                _copy_source(imported[role], build / role)
                wheel = _wheel(build_python, build / role, temporary / ("wheel-" + role), log)
                if (wheel["distribution"], wheel["version"]) != (module["distribution"], module["version"]):
                    raise AssertionError("Independent distribution identity changed")
                wheels[role] = wheel
                suites[role], test_hashes[role] = _suite(imported[role], temporary / ("suite-" + role),
                    source_root=module["source_root"], package_path=module["python_import"].replace(".", "/"))
                if role == "tsde":
                    _copy_source(imported[role], temporary / "polygon-source-suite")
        legacy_set = contexts.enter_context(provider_worktrees(root=ROOT, roles=["set"],
            overrides={"set": LEGACY_SET_REVISION}))["set"]
        stfe_set = contexts.enter_context(provider_worktrees(root=ROOT, roles=["set"],
            overrides={"set": STFE_SET_REVISION}))["set"]
        _run(["git", "-C", ROOT, "merge-base", "--is-ancestor", STFE_TERMINAL_REVISION, "HEAD"],
             cwd=temporary, log=log)
        stfe_terminal = contexts.enter_context(_worktree(ROOT, STFE_TERMINAL_REVISION,
            temporary / "stfe-historical-terminal", temporary, log))
        _copy_source(legacy_set, build / "legacy-set")
        legacy_set_wheel = _wheel(build_python, build / "legacy-set", temporary / "wheel-legacy-set", log)
        report["historical_dependencies"] = {
            "legacy_exchange_set": {"revision": LEGACY_SET_REVISION, "source_tree": _git(legacy_set, "rev-parse", "HEAD^{tree}")},
            "stfe_set": {"revision": STFE_SET_REVISION, "source_tree": _git(stfe_set, "rev-parse", "HEAD^{tree}")},
            "stfe_terminal": {"revision": STFE_TERMINAL_REVISION, "source_tree": _git(stfe_terminal, "rev-parse", "HEAD^{tree}"),
                "qualification": "explicit original integration companion source, not current CIW wheel"},
        }
        report["wheels"] = {role: {key: value for key, value in wheel.items() if key != "path"}
                            for role, wheel in {**wheels, "ciw": ciw_wheel, "legacy_set": legacy_set_wheel}.items()}
        report["installed_packages"], report["provider_tests"], report["provider_examples"] = {}, {}, {}
        configuration = temporary / "pytest.ini"
        configuration.write_text("[pytest]\nmarkers =\n    slow: original provider numerical checks\n")
        for role, module in modules.items():
            python = _python(temporary / (role + "-venv"), temporary, log,
                             build=role == "tsde", jax=role == "jspt")
            installed = {module["python_import"]: wheels[role], "ciw": ciw_wheel}
            if role in {"edspt", "sidt"}:
                installed["state_estimation_testbed"] = legacy_set_wheel
            _run_bound([python, "-I", "-m", "pip", "install", "--no-deps",
                        *[wheel["path"] for wheel in installed.values()]], cwd=temporary, log=log)
            report["installed_packages"][role] = _probe(python, installed, temporary, log)
            suite = suites[role]
            bindings = {"STFE_SET_REPO": stfe_set, "STFE_CIW_REPO": stfe_terminal} if role == "stfe" else {}
            if role == "jspt":
                bindings["JAX_PLATFORMS"] = "cpu"
                jax_probe = "import jax, json; assert jax.default_backend() == 'cpu'; print(json.dumps({'version':jax.__version__, 'backend':jax.default_backend()}))"
                report["installed_packages"][role]["jax"] = json.loads(_run_bound(
                    [python, "-I", "-c", jax_probe], cwd=temporary, log=log, bindings=bindings))
            if role == "tsde":
                source_suite = temporary / "polygon-source-suite"
                raw = _run_bound([python, "-I", "-m", "unittest", "discover", "-s", "tests", "-v"],
                                 cwd=source_suite, log=log)
                source_result = _unittest_result(raw, output / "tsde-source-unittest.txt")
                raw = _run_bound([python, "-I", "-m", "unittest", "discover", "-s", "tests", "-v"],
                                 cwd=suite, log=log, bindings={"TSDE_INSTALLED_TEST": "1"})
                tests = _unittest_result(raw, output / "tsde-installed-unittest.txt")
                # Run the exact upstream gate separately. It creates/probes its
                # own wheel venv and has its own original source-fallback guard.
                script = source_suite / "scripts/check_installed.py"
                raw = _run_bound([python, "-I", script], cwd=source_suite, log=log, timeout=900)
                original_gate = _unittest_result(raw, output / "tsde-original-installed-gate.txt")
                if "Installed provider:" not in raw or "Installed genus-two CLI artifact:" not in raw:
                    raise AssertionError("Original Polygon installed-wheel gate did not complete")
                tests.update(source_suite=source_result, original_installed_gate=original_gate,
                             original_installed_gate_sha256=sha256(script.read_bytes()).hexdigest())
            else:
                tests = _pytest(python, suite, module["python_import"], configuration,
                                output / (role + "-tests.xml"), log, bindings=bindings)
            if _test_hashes(suite) != test_hashes[role]:
                raise AssertionError("Execution modified an original provider test")
            report["provider_tests"][role] = {**tests, "revision": module["import_revision"],
                "source_tree": module["import_tree"], "qualification": "current independent installed wheel",
                "original_test_sha256": test_hashes[role]}
            examples = {}
            names = {"edspt": ("replay.py", "exchange.py"),
                "sidt": ("replay.py", "exchange.py", "declared.py"),
                "jspt": ("quickstart.py", "fluid_composition.py", "construction_composition.py"),
                "rci": ("displacement_bench.py", "displacement_budget.py")}.get(role, ())
            # JSPT commits example reports. Remove only these temporary copied
            # outputs so retained example artifacts must be produced in this run.
            if names and (suite / "results").exists():
                shutil.rmtree(suite / "results")
            for name in names:
                examples[name] = _example(python, suite, module["python_import"], name, role, output, log, bindings=bindings)
            if role in {"jspt", "stfe"}:
                name, endpoint = (("covariance_request.json", "sensitivity.ciw_adapter") if role == "jspt"
                                  else ("window_mean.json", "stfe"))
                source = suite / "examples" / name
                raw = _run_bound([python, "-I", "-m", endpoint], cwd=suite, log=log,
                                 stdin=source.read_bytes(), bindings=bindings)
                result = json.loads(raw)
                if role == "jspt" and result["status"] != "ok":
                    raise AssertionError("Original JSPT adapter fixture refused")
                if role == "stfe" and result["result_artifact"]["covariance"]["matrix"] != [[3.0]]:
                    raise AssertionError("Original STFE example lost cross-covariance")
                path = output / (role + "-endpoint.json")
                path.write_text(raw)
                examples[name] = {"source_sha256": sha256(source.read_bytes()).hexdigest(),
                    "output": str(path), "output_sha256": sha256(path.read_bytes()).hexdigest()}
            report["provider_examples"][role] = examples

        with provider_worktrees(root=ROOT, revisions="runtime", roles=["rci", "jspt"]) as providers:
            parents = {path.parent for path in providers.values()}
            if len(parents) != 1:
                raise ValueError("Measurement-chain tests require sibling role worktrees")
            provider_root, = parents
            flowstate = _flowstate(args.flowstate_root, temporary, log)
            with _worktree(flowstate, FLOWSTATE_REVISION, provider_root / "fsrt", temporary, log) as fsrt:
                providers = {**providers, "fsrt": fsrt}
                legacy_rci = contexts.enter_context(provider_worktrees(root=ROOT, roles=["rci"],
                    overrides={"rci": RCI_LEGACY_REVISION}))["rci"]
                legacy_fsrt = contexts.enter_context(_worktree(flowstate, FLOWSTATE_LEGACY_REVISION,
                    temporary / "legacy-public-flowstate", temporary, log))
                project = tomllib.loads((providers["rci"] / "pyproject.toml").read_text())["project"]
                if project["version"] != "0.1.0":
                    raise AssertionError("Historical Metrology adapter wheel must remain version0.1.0")
                _copy_source(providers["rci"], build / "historical-rci")
                historical_wheel = _wheel(build_python, build / "historical-rci", temporary / "wheel-historical-rci", log)
                historical_python = _python(temporary / "historical-rci-venv", temporary, log)
                _run_bound([historical_python, "-I", "-m", "pip", "install", "--no-deps", historical_wheel["path"]],
                           cwd=temporary, log=log)
                report["installed_packages"]["historical_rci"] = _probe(historical_python,
                    {"instrument_chain": historical_wheel}, temporary, log)
                old_suite, old_tests = _suite(providers["rci"], temporary / "historical-rci-suite")
                tests = _pytest(historical_python, old_suite, "instrument_chain", configuration,
                                output / "historical-rci-tests.xml", log)
                if _test_hashes(old_suite) != old_tests:
                    raise AssertionError("Historical original Metrology tests changed")
                report["historical_rci_tests"] = {**tests, "revision": RCI_REVISION,
                    "source_tree": _git(providers["rci"], "rev-parse", "HEAD^{tree}"),
                    "qualification": "separate exact historical0.1.0 installed wheel",
                    "original_test_sha256": old_tests,
                    "wheel": {key: value for key, value in historical_wheel.items() if key != "path"}}
                report["historical_rci_examples"] = {name: _example(historical_python, old_suite,
                    "instrument_chain", name, "historical-rci", output, log)
                    for name in ("displacement_bench.py", "displacement_budget.py", "ciw_calibration.py", "ciw_calibration_v2.py")}

                ciw_python = _python(temporary / "measurement-chain-venv", temporary, log)
                _run_bound([ciw_python, "-I", "-m", "pip", "install", "--no-deps", ciw_wheel["path"]],
                           cwd=temporary, log=log)
                report["installed_packages"]["measurement_chain"] = _probe(ciw_python,
                    {"ciw": ciw_wheel}, temporary, log)
                process_suite = temporary / "measurement-chain-suite"
                (process_suite / "tests").mkdir(parents=True)
                process_hashes = {}
                for name in PROCESS_TESTS:
                    source = ROOT / "tests" / name
                    shutil.copyfile(source, process_suite / "tests" / name)
                    process_hashes["tests/" + name] = sha256(source.read_bytes()).hexdigest()
                for folder in ("adapters", "measurement-chain"):
                    shutil.copytree(ROOT / "examples" / folder, process_suite / "examples" / folder)
                # One unchanged historical replay test reads this original data
                # file relative to ROOT; no CIW Python implementation is copied.
                manifest_folder = process_suite / "src/ciw"
                manifest_folder.mkdir(parents=True)
                shutil.copyfile(ROOT / "src/ciw/adapter-runtimes.json", manifest_folder / "adapter-runtimes.json")
                bindings = {"CIW_RCI_REPO": providers["rci"], "CIW_FSRT_REPO": fsrt,
                    "CIW_JSPT_REPO": providers["jspt"], "CIW_RCI_LEGACY_REPO": legacy_rci,
                    "CIW_FSRT_LEGACY_REPO": legacy_fsrt, "CIW_MEASUREMENT_CHAIN_STACK_ROOT": provider_root}
                tests = _pytest(ciw_python, process_suite, "ciw", configuration,
                                output / "measurement-chain-tests.xml", log, bindings=bindings, timeout=1800)
                if _test_hashes(process_suite) != process_hashes:
                    raise AssertionError("An original Terminal process test changed")
                report["measurement_chain_tests"] = {**tests, "original_test_sha256": process_hashes,
                    "qualification": "current CIW installed wheel and exact historical provider source worktrees"}
                report["external_flowstate"] = {"repository": FLOWSTATE_REPOSITORY,
                    "repository_id": FLOWSTATE_REPOSITORY_ID, "visibility": "public", "migrated": "fsrt" in all_modules,
                    "binding_route": "external_public_repository" if args.flowstate_root else "retained_monorepo_history",
                    "revision": FLOWSTATE_REVISION, "source_tree": _git(fsrt, "rev-parse", "HEAD^{tree}"),
                    "legacy_revision": FLOWSTATE_LEGACY_REVISION,
                    "legacy_source_tree": _git(legacy_fsrt, "rev-parse", "HEAD^{tree}"),
                    "full_provider_suite_qualified": False}
                report["historical_dependencies"]["legacy_rci_replay"] = {"revision": RCI_LEGACY_REVISION,
                    "source_tree": _git(legacy_rci, "rev-parse", "HEAD^{tree}")}
                composition = output / "composition.json"
                snapshot_configuration = temporary / "measurement-chain-snapshot.json"
                snapshot_configuration.write_text(json.dumps({
                    "providers": {role: str(path) for role, path in providers.items()},
                    "source": str(process_suite / "examples/measurement-chain/source.json"),
                    "sessions": str(output / ("sessions-" + report["verification_id"].split(":", 1)[1])),
                    "report": str(composition), "claim_scope": SCOPE}))
                _run_bound([ciw_python, "-I", "-c", _SNAPSHOT, snapshot_configuration],
                           cwd=temporary, log=log, timeout=900)
                report["composition"] = json.loads(composition.read_text())
                for role, path in providers.items():
                    _validate(path, {"rci": RCI_REVISION, "jspt": JSPT_REVISION, "fsrt": FLOWSTATE_REVISION}[role], temporary, log)
        report["post_execution_imports"] = verify_imports(root=ROOT)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flowstate-root", type=Path,
                        help="Existing public FlowState Git repository containing both exact historical adapter pins")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/monorepo-math")
    args = parser.parse_args(argv)
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    log = output / "commands.log"
    log.write_text("")
    report = {"schema": "notations.monorepo-math-gate.v1", "status": "running",
        "verification_id": "verification:" + uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "terminal_revision": _git(ROOT, "rev-parse", "HEAD"), "python_version": sys.version,
        "minimum_python": "3.12", "dependencies": DEPENDENCIES,
        "claim_scope": SCOPE, "independent_verification": False, "canonicalAdmission": False,
        "admission": "not_performed", "surface_qualified": False,
        "identified_design_stack_qualified": False, "log": str(log)}
    try:
        _qualify(args, report, output, log)
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        print(f"Public mathematical instrument gate failed: {error}", file=sys.stderr)
    else:
        report["status"] = "passed"
        total = sum(check["tests"] for check in report["provider_tests"].values())
        print(f"Public mathematical instrument gate passed: {total} current provider tests; "
              f"{report['historical_rci_tests']['tests']} historical Metrology tests; "
              f"{report['measurement_chain_tests']['tests']} original Terminal process tests; "
              "retained exact measurement-chain replay; zero skips.")
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
