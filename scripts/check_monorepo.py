"""Qualify the public measurement imports as independent wheels and providers.

This gate exercises unchanged provider suites and the existing Terminal adapter
at its historical runtime pins. It does not qualify the full eight-provider
workflow, admit scientific state, or claim physical calibration or validation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.parser import BytesParser
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import uuid
import venv
import xml.etree.ElementTree as ET
import zipfile

if __package__:
    from .monorepo import ROOT, load_manifest, provider_worktrees, verify_imports, verify_terminal_source
else:
    from monorepo import ROOT, load_manifest, provider_worktrees, verify_imports, verify_terminal_source

SET_REVISION = "bd261a765281a95312f7c91a3857233476294c5b"
SET_REPOSITORY = "https://github.com/giasonpooni/Notations-Estimator-Bench.git"
DEPENDENCIES = ["numpy==2.4.3", "pytest==9.0.2", "websockets==16.0"]
SCOPE = (
    "Synthetic computational interoperability of public calibration and clock "
    "providers only; no physical calibration, validation, state admission, "
    "causal fault claim, or full eight-provider workflow qualification."
)


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTEST_ADDOPTS", "PYTEST_PLUGINS",
                "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        environment.pop(key, None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    environment["PIP_NO_INPUT"] = "1"
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return environment


def _run(arguments, *, cwd: Path, log: Path, timeout: int = 300) -> str:
    command = [str(argument) for argument in arguments]
    display = list(command)
    if "-c" in display and display[display.index("-c") + 1].count("\n"):
        code_index = display.index("-c") + 1
        display[code_index] = "<inline-sha256:" + sha256(command[code_index].encode()).hexdigest() + ">"
    with log.open("ab") as stream:
        stream.write(("\n$ " + " ".join(display) + "\n").encode())
        result = subprocess.run(command, cwd=cwd, env=_environment(),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
        stream.write(result.stdout)
    if result.returncode:
        tail = result.stdout.decode(errors="replace")[-6000:]
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(display[:4])}\n{tail}")
    return result.stdout.decode(errors="strict")


def _git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(root),
         "-c", "core.fsmonitor=false", *arguments],
        env=_environment(), timeout=30, text=True).strip()


def _copy_source(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "*.pyc", "*.egg-info", "build", "dist",
        ".pytest_cache", ".venv", ".venv*"))


def _set_checkout(supplied: Path | None, temporary: Path, log: Path) -> Path:
    checkout = supplied.expanduser().resolve() if supplied else temporary / "set-checkout"
    if supplied is None:
        _run(["git", "-c", "core.autocrlf=false", "clone", "--no-checkout",
              SET_REPOSITORY, checkout], cwd=temporary, log=log, timeout=180)
        _run(["git", "-C", checkout, "-c", "core.autocrlf=false", "checkout",
              "--detach", SET_REVISION], cwd=temporary, log=log)
    if Path(_git(checkout, "rev-parse", "--show-toplevel")).resolve() != checkout:
        raise ValueError("--set-root must be the standalone dependency repository root")
    if _git(checkout, "rev-parse", "HEAD") != SET_REVISION:
        raise ValueError(f"Standalone SET must be at exact revision {SET_REVISION}")
    # Use the existing byte/index validator in a fresh process with sanitized Git
    # environment. Git status alone can hide ignored or assume-unchanged source.
    validation = """
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location('monorepo_checkout_validator', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.validate_checkout(pathlib.Path(sys.argv[2]), sys.argv[3])
print('Standalone SET exact source bytes and index verified')
"""
    _run([sys.executable, "-I", "-c", validation, ROOT / "src/ciw/provider_checkouts.py",
          checkout, SET_REVISION], cwd=temporary, log=log)
    return checkout


def _wheel(python: Path, source: Path, wheel_dir: Path, log: Path) -> dict:
    wheel_dir.mkdir()
    project = tomllib.loads((source / "pyproject.toml").read_text())["project"]
    _run([python, "-I", "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
          source, "--wheel-dir", wheel_dir], cwd=source.parent, log=log)
    wheel, = wheel_dir.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        metadata_file, = [name for name in archive.namelist()
                          if name.endswith(".dist-info/METADATA")]
        metadata = BytesParser().parsebytes(archive.read(metadata_file))
        if metadata["Name"] != project["name"] or metadata["Version"] != project["version"]:
            raise AssertionError("Wheel distribution name/version changed during build")
        if any(name.startswith("instruments/") for name in archive.namelist()):
            raise AssertionError("Independent wheels must not contain the monorepo instruments tree")
    return {"path": str(wheel), "filename": wheel.name,
            "sha256": sha256(wheel.read_bytes()).hexdigest(),
            "distribution": metadata["Name"], "version": metadata["Version"]}


def _junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    counts = {name: sum(1 for case in cases if case.find(name) is not None)
              for name in ("failure", "error", "skipped")}
    suites = list(root.iter("testsuite"))
    if not cases or any(counts.values()) or any(
        int(suite.get(name, "0")) for suite in suites
        for name in ("failures", "errors", "skipped")
    ):
        raise AssertionError(f"Provider tests require nonempty success with zero skips: {counts}")
    return {"tests": len(cases), "failures": 0, "errors": 0, "skipped": 0,
            "junit": str(path), "junit_sha256": sha256(path.read_bytes()).hexdigest()}


_IMPORT_PROBE = r'''
import importlib, importlib.metadata, json, pathlib, sys
expected = json.loads(sys.argv[1])
prefix = pathlib.Path(sys.prefix).resolve()
records = {}
for module_name, specification in expected.items():
    module = importlib.import_module(module_name)
    location = pathlib.Path(module.__file__).resolve()
    distribution = importlib.metadata.distribution(specification['distribution'])
    if not location.is_relative_to(prefix):
        raise AssertionError('Package imported outside isolated venv: ' + str(location))
    if distribution.version != specification['version']:
        raise AssertionError('Independent distribution version changed')
    if not pathlib.Path(distribution.locate_file('')).resolve().is_relative_to(prefix):
        raise AssertionError('Distribution installed outside isolated venv')
    records[module_name] = {'module_file': str(location),
        'distribution': distribution.metadata['Name'], 'version': distribution.version}
print(json.dumps({'python': sys.version, 'prefix': str(prefix), 'imports': records}, sort_keys=True))
'''


_COMPOSITION = r'''
from copy import deepcopy
from hashlib import sha256
from importlib import resources
import json, math, pathlib, sys, uuid
from ciw.adapters.protocol import AdapterRefusal
from ciw.adapters.subprocess import PinnedSubprocessAdapter
from ciw.calibrated_observable import RESULT_SCHEMA, _invoke, _source
from ciw.telemetry import digest

configuration = json.loads(pathlib.Path(sys.argv[1]).read_text())
raw = pathlib.Path(configuration['source']).read_bytes()
experiment = _source(raw)
original = deepcopy(experiment)
pins = json.loads(resources.files('ciw').joinpath('calibrated-observable-runtimes.json').read_text())
adapters = {}
for role in ('tbrt', 'mcur'):
    pin = pins[role]
    declared = configuration['modules'][role]
    assert pin['revision'] == declared['runtime_revision']
    assert pin['source_root'] == declared['source_root']
    adapters[role] = PinnedSubprocessAdapter(configuration['providers'][role],
        pin['revision'], pin['module'], source_root=pin['source_root'])

evidence_id = 'evidence:sha256:' + sha256(raw).hexdigest()
operations = {'tbrt': 'ciw.tbrt-two-channel.v1', 'mcur': 'ciw.mcur-two-channel.v1'}
def request(role, source, aligned=None):
    if role == 'tbrt':
        inputs = {'channels': source['channels'], 'alignment': source['configuration']['alignment']}
    else:
        inputs = {'channels': source['channels'], 'epoch_utc': source['epoch_utc'],
            'alignment': aligned, 'calibrated_covariance': source['calibrated_covariance']}
    return {'schema': 'ciw.adapter-request.v1', 'operation_id': operations[role], 'inputs': inputs}

def execute():
    steps = []
    aligned = None
    for role in ('tbrt', 'mcur'):
        execution_id = 'execution:' + uuid.uuid4().hex
        supplied = request(role, experiment, aligned)
        output = _invoke(role, adapters, supplied)
        refs = [evidence_id] if role == 'tbrt' else [evidence_id, steps[0]['result_id']]
        result = {'schema': RESULT_SCHEMA, 'operation_id': operations[role],
            'execution_ref': execution_id, 'input_refs': refs, 'data': output}
        result_id = 'result:' + digest(result)
        assert result_id.startswith('result:sha256:')
        assert len(result_id.removeprefix('result:sha256:')) == 64
        steps.append({'operation_id': operations[role], 'execution_id': execution_id,
            'input_refs': refs, 'request_sha256': digest(supplied),
            'result_id': result_id, 'data': output})
        if role == 'tbrt':
            aligned = output
    clock, calibration = (step['data'] for step in steps)
    assert [row['event_time'] for row in clock['channels']] == [5.0, 5.0]
    assert calibration['values'] == [52.0, 46.0]
    assert calibration['covariance']['matrix'] == [[1.0, .25], [.25, 1.0]]
    assert calibration['covariance'] == experiment['calibrated_covariance']
    assert clock['time_uncertainty_policy'] == experiment['configuration']['alignment']['measurement_time_policy']
    for source, reconciled, calibrated in zip(experiment['channels'], clock['channels'], calibration['channels']):
        time = reconciled['reconciliation']
        assert time['observation']['device_time'] == source['observation']['device_time']
        assert time['observation']['evidence_id'] == source['observation']['artifact_id']
        assert time['model']['synchronization_evidence_ids'] == source['clock_model']['synchronization_evidence_ids']
        assert time['joint_covariance'] == source['clock_joint_covariance']
        # The second channel multiplies binary64 6.4e-5 by 1.25 squared;
        # compare its analytic 1e-4 result within final-rounding tolerance.
        assert math.isclose(time['variance'], .0001, rel_tol=1e-14, abs_tol=0)
        value = calibrated['calibration']
        assert value['raw_value'] == source['observation']['raw_value']
        assert value['indicated_value'] == source['observation']['indicated_value']
        assert value['observation_id'] == source['observation']['observation_id']
        assert value['profile_id'] == source['calibration_profile']['profile_id']
        assert value['variance'] == 1.0
    assert experiment == original, 'Original evidence must remain unchanged'
    report_id = 'verification:' + uuid.uuid4().hex
    ids = [evidence_id, report_id] + [step[key] for step in steps for key in ('operation_id', 'execution_id', 'result_id')]
    assert len(set(ids)) == len(ids), 'Evidence, operation, execution, result and verification identities must be distinct'
    return {'report_id': report_id, 'evidence_id': evidence_id, 'steps': steps,
        'checks': {'expected_times': True, 'expected_values': True, 'covariance_retained': True,
            'raw_evidence_and_device_times_retained': True, 'declared_time_uncertainty_retained': True,
            'identity_separation': True}}

runs = [execute(), execute()]
assert [step['data'] for step in runs[0]['steps']] == [step['data'] for step in runs[1]['steps']]
assert runs[0]['report_id'] != runs[1]['report_id']
for first, second in zip(runs[0]['steps'], runs[1]['steps']):
    assert first['execution_id'] != second['execution_id']
    assert first['result_id'] != second['result_id']

def refused(role, changed, expected_code, aligned=None):
    try:
        _invoke(role, adapters, request(role, changed, aligned))
    except AdapterRefusal as error:
        assert error.code == expected_code, (error.code, expected_code)
        return {'role': role, 'expected_code': expected_code, 'actual_code': error.code}
    raise AssertionError('Invalid declared inputs were accepted')

refusals = {}
changed = deepcopy(experiment)
changed['channels'][0]['clock_model']['synchronization_evidence_ids'] = []
refusals['missing_synchronization_evidence'] = refused('tbrt', changed, 'CALIBRATED_TBRT_REFUSED')
aligned = runs[0]['steps'][0]['data']
changed = deepcopy(experiment)
changed['channels'][0]['calibration_profile']['valid_until'] = '2025-12-31T23:59:59Z'
refusals['expired_calibration'] = refused('mcur', changed, 'CALIBRATED_MCUR_REFUSED', aligned)
changed = deepcopy(experiment)
changed['calibrated_covariance']['cross_covariance_policy'] = 'unknown'
refusals['unknown_calibrated_covariance'] = refused('mcur', changed, 'CALIBRATED_MCUR_REFUSED', aligned)

dirty = pathlib.Path(configuration['dirty_provider'])
target = dirty / pins['tbrt']['source_root'] / 'tbrt' / '__init__.py'
with target.open('a') as stream:
    stream.write('\n# Deliberate temporary gate mutation.\n')
try:
    PinnedSubprocessAdapter(dirty, pins['tbrt']['revision'], pins['tbrt']['module'],
        source_root=pins['tbrt']['source_root'])
except AdapterRefusal as error:
    assert error.code == 'SOURCE_PIN_MISMATCH'
    refusals['dirty_source'] = {'role': 'tbrt', 'expected_code': 'SOURCE_PIN_MISMATCH', 'actual_code': error.code}
else:
    raise AssertionError('Dirty temporary source was accepted')

report = {'schema': 'notations.monorepo-composition-check.v1',
    'claim_scope': configuration['claim_scope'],
    'private_eight_provider_workflow_qualified': False,
    'source_sha256': sha256(raw).hexdigest(), 'experiment_id': experiment['experiment_id'],
    'runs': runs, 'numerical_replay_equal': True, 'fresh_execution_and_verification_ids': True,
    'refusals': refusals, 'runtimes': {role: adapter.runtime_identity() for role, adapter in adapters.items()}}
pathlib.Path(configuration['report']).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps({'composition': 'passed', 'refusals': sorted(refusals), 'runs': len(runs)}))
'''


def _qualify(args, report: dict, output: Path, log: Path) -> None:
    report["terminal_source"] = verify_terminal_source(root=ROOT)
    if report["terminal_source"]["revision"] != report["terminal_revision"]:
        raise ValueError("Terminal revision changed before qualification")
    manifest = load_manifest(root=ROOT)
    modules = {module["role"]: module for module in manifest["modules"] if module["role"] in {"mcur", "tbrt"}}
    if set(modules) != {"tbrt", "mcur"}:
        raise ValueError("Initial measurement gate binds exactly calibration and clock providers")
    report["imports"] = verify_imports(root=ROOT)
    report["modules"] = manifest["modules"]
    with tempfile.TemporaryDirectory(prefix="notations-monorepo-gate-") as directory:
        temporary = Path(directory)
        environment = temporary / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        _run([python, "-I", "-m", "pip", "install", "setuptools>=77", "wheel", *DEPENDENCIES],
             cwd=temporary, log=log)
        set_checkout = _set_checkout(args.set_root, temporary, log)
        report["external_dependency"] = {"repository": SET_REPOSITORY,
            "revision": SET_REVISION, "source_tree": _git(set_checkout, "rev-parse", "HEAD^{tree}"),
            "migrated": False}
        build = temporary / "build-sources"
        build.mkdir()
        terminal = build / "terminal"
        terminal.mkdir()
        shutil.copytree(ROOT / "src", terminal / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        for name in ("pyproject.toml", "LICENSE"):
            shutil.copyfile(ROOT / name, terminal / name)
        _copy_source(set_checkout, build / "set")
        wheels = {"ciw": _wheel(python, terminal, temporary / "wheel-ciw", log),
                  "state_estimation_testbed": _wheel(python, build / "set", temporary / "wheel-set", log)}
        provider_checks = {}
        with provider_worktrees(root=ROOT, revisions="import", roles=modules) as imported:
            for role, module in sorted(modules.items()):
                _copy_source(imported[role], build / role)
                wheels[module["python_import"]] = _wheel(python, build / role, temporary / ("wheel-" + role), log)
                wheel = wheels[module["python_import"]]
                if (wheel["distribution"], wheel["version"]) != (module["distribution"], module["version"]):
                    raise AssertionError("Imported distribution identity differs from the manifest")
                suite = temporary / ("provider-suite-" + role)
                suite.mkdir()
                shutil.copytree(imported[role] / "tests", suite / "tests")
                shutil.copytree(imported[role] / "examples", suite / "examples")
                provider_checks[role] = {"suite_path": str(suite), "revision": module["import_revision"],
                    "source_tree": _git(imported[role], "rev-parse", "HEAD^{tree}")}
        _run([python, "-I", "-m", "pip", "install", "--no-deps",
              *[wheel["path"] for wheel in wheels.values()]], cwd=temporary, log=log)
        expected = {name: {key: wheel[key] for key in ("distribution", "version")}
                    for name, wheel in wheels.items()}
        report["installed_packages"] = json.loads(_run(
            [python, "-I", "-c", _IMPORT_PROBE, json.dumps(expected)], cwd=temporary, log=log))
        report["wheels"] = {name: {key: value for key, value in wheel.items() if key != "path"}
                            for name, wheel in wheels.items()}
        pytest_config = temporary / "pytest.ini"
        pytest_config.write_text("[pytest]\n")
        report["provider_tests"] = {}
        report["provider_examples"] = {}
        for role, check in sorted(provider_checks.items()):
            suite = Path(check.pop("suite_path"))
            junit = output / (role + "-tests.xml")
            _run([python, "-I", "-m", "pytest", "-q", "-c", pytest_config,
                  "--import-mode=importlib", "--junitxml", junit, suite / "tests"],
                 cwd=suite, log=log)
            report["provider_tests"][role] = {**check, **_junit(junit)}
            examples = {}
            for name in ("replay.py", "exchange.py"):
                example = suite / "examples" / name
                result = _run([python, "-I", example], cwd=suite, log=log)
                retained = output / (role + "-" + name.removesuffix(".py") + ".json")
                retained.write_text(result)
                json.loads(result)
                examples[name] = {"source_sha256": sha256(example.read_bytes()).hexdigest(),
                    "output_sha256": sha256(result.encode()).hexdigest(), "output": str(retained)}
            report["provider_examples"][role] = examples
        with provider_worktrees(root=ROOT, revisions="runtime", roles=modules) as providers:
            dirty = temporary / "dirty-tbrt"
            _run(["git", "init", dirty], cwd=temporary, log=log)
            _run(["git", "-C", dirty, "fetch", "--depth=1", providers["tbrt"],
                  modules["tbrt"]["runtime_revision"]], cwd=temporary, log=log)
            _run(["git", "-C", dirty, "checkout", "--detach", "FETCH_HEAD"], cwd=temporary, log=log)
            source = temporary / "calibrated-observable-source.json"
            shutil.copyfile(ROOT / "examples/calibrated-observable/source.json", source)
            composition_path = output / "composition.json"
            configuration = temporary / "composition-configuration.json"
            configuration.write_text(json.dumps({"providers": {role: str(path) for role, path in providers.items()},
                "modules": modules, "source": str(source), "dirty_provider": str(dirty),
                "report": str(composition_path), "claim_scope": SCOPE}))
            _run([python, "-I", "-c", _COMPOSITION, configuration], cwd=temporary, log=log)
            report["composition"] = json.loads(composition_path.read_text())
        report["post_execution_imports"] = verify_imports(root=ROOT)
        if verify_terminal_source(root=ROOT) != report["terminal_source"]:
            raise ValueError("Terminal source identity changed during qualification")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set-root", type=Path,
                        help=f"Standalone SET dependency checkout at exact revision {SET_REVISION}")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/monorepo",
                        help="Retained gate report, JUnit, example outputs and command log")
    args = parser.parse_args(argv)
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    log = output / "commands.log"
    log.write_text("")
    report = {"schema": "notations.monorepo-gate-report.v1", "status": "running",
        "verification_id": "verification:" + uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "claim_scope": SCOPE, "private_eight_provider_workflow_qualified": False,
        "terminal_revision": _git(ROOT, "rev-parse", "HEAD"),
        "dependencies": DEPENDENCIES, "log": str(log)}
    try:
        _qualify(args, report, output, log)
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        print(f"Monorepo gate failed: {error}", file=sys.stderr)
    else:
        report["status"] = "passed"
        total = sum(check["tests"] for check in report["provider_tests"].values())
        print(f"Monorepo gate passed: {total} provider tests, four unchanged examples, two-provider replay and refusals.")
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
