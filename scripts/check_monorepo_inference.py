"""Qualify public inference imports through unchanged suites and exact replay.

Current independent wheels, historical exchange dependencies, and the original
eight-provider execution pins are separate identities. Public FlowState remains
an external provider. Two original CBSR checks against an unprovisioned GTE are
retained as explicitly unqualified skips; every other test must execute.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
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

if __package__:
    from .check_monorepo import DEPENDENCIES, _copy_source, _environment, _git, _IMPORT_PROBE, _junit, _run, _wheel
    from .monorepo import ROOT, load_manifest, provider_worktrees, verify_imports
else:
    from check_monorepo import DEPENDENCIES, _copy_source, _environment, _git, _IMPORT_PROBE, _junit, _run, _wheel
    from monorepo import ROOT, load_manifest, provider_worktrees, verify_imports

ROLES = frozenset({"mcur", "tbrt", "oit", "gsie", "cbsr", "fdir", "set"})
FLOWSTATE_REPOSITORY = "https://github.com/giasonpooni/Notations-FlowState.git"
FLOWSTATE_REPOSITORY_ID = 1366033244
FLOWSTATE_REVISION = "d7c181fb9967883e085b3728d38096f59e54efbd"
CBSR_FLOWSTATE_REVISION = "56a2bea58ad2657e5aacf0181fe2d0b982b09f3b"
LEGACY_SET_REVISION = "bd261a765281a95312f7c91a3857233476294c5b"
GSIE_SET_REVISION = "542e672be512bf43b61253f2b2a43cd967cb3062"
GSIE_TERMINAL_REVISION = "1ec11eb46bcf19ec57b40603dcd5921d284307ff"
SCOPE = (
    "Synthetic public eight-provider computational interoperability and exact "
    "recomputation only. No physical validation, independent verification, "
    "canonical state admission, full FlowState-suite qualification, or GTE "
    "integration qualification."
)
GTE_SKIPS = frozenset({
    "test_gte_pinned_fixture_tangent_at_basepoint_has_same_covariance_projection",
    "test_affine_tangent_is_not_silently_promoted_to_global_circle_projection",
})
GTE_SKIP_REASON = "set CBSR_GTE_REPO to run pinned cross-instrument checks"
_PROVIDER_ENVIRONMENT = ("GSIE_SET_REPO", "GSIE_CIW_REPO", "SET_CIW_REPO",
                         "CBSR_FSRT_REPO", "CBSR_GTE_REPO", "CIW_CALIBRATED_STACK_ROOT")


def _run_bound(arguments, *, cwd: Path, log: Path, bindings=None, stdin: bytes | None = None,
               timeout: int = 300) -> str:
    """Run original tests with only the explicitly provisioned provider paths."""
    environment = _environment()
    for key in _PROVIDER_ENVIRONMENT:
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
        result = subprocess.run(command, cwd=cwd, env=environment, input=stdin,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
        stream.write(result.stdout)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(display[:4])}\n"
                           + result.stdout.decode(errors="replace")[-8000:])
    return result.stdout.decode()


def _validate(path: Path, revision: str, temporary: Path, log: Path) -> None:
    code = """
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location('inference_checkout_validator', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.validate_checkout(pathlib.Path(sys.argv[2]), sys.argv[3])
print('Exact checkout bytes, index and source identity verified')
"""
    _run_bound([sys.executable, "-I", "-c", code, ROOT / "src/ciw/provider_checkouts.py", path, revision],
               cwd=temporary, log=log)


@contextmanager
def _worktree(repository: Path, revision: str, path: Path, temporary: Path, log: Path):
    _run(["git", "-c", "core.autocrlf=false", "-C", repository,
          "worktree", "add", "--detach", path, revision],
         cwd=temporary, log=log)
    try:
        _validate(path, revision, temporary, log)
        yield path
    finally:
        _run(["git", "-C", repository, "worktree", "remove", "--force", path],
             cwd=temporary, log=log)


def _flowstate(supplied: Path | None, temporary: Path, log: Path) -> Path:
    repository = supplied.expanduser().resolve() if supplied else temporary / "flowstate-source"
    if supplied is None:
        _run(["git", "-c", "core.autocrlf=false", "clone", "--no-checkout",
              FLOWSTATE_REPOSITORY, repository], cwd=temporary, log=log, timeout=180)
    if Path(_git(repository, "rev-parse", "--show-toplevel")).resolve() != repository:
        raise ValueError("--flowstate-root must be a standalone Git repository root")
    for revision in (FLOWSTATE_REVISION, CBSR_FLOWSTATE_REVISION):
        _git(repository, "cat-file", "-e", revision + "^{commit}")
    return repository


def _environment_python(path: Path, temporary: Path, log: Path, *, build=False) -> Path:
    venv.EnvBuilder(with_pip=True).create(path)
    python = path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    dependencies = (["setuptools>=77", "wheel"] if build else []) + DEPENDENCIES
    _run([python, "-I", "-m", "pip", "install", *dependencies], cwd=temporary, log=log)
    return python


def _probe(python: Path, wheels: dict, temporary: Path, log: Path) -> dict:
    expected = {module: {key: wheel[key] for key in ("distribution", "version")}
                for module, wheel in wheels.items()}
    return json.loads(_run_bound([python, "-I", "-c", _IMPORT_PROBE, json.dumps(expected)],
                                cwd=temporary, log=log))


def _cbsr_junit(path: Path) -> dict:
    cases = list(ET.parse(path).getroot().iter("testcase"))
    observed = {}
    for case in cases:
        if case.find("failure") is not None or case.find("error") is not None:
            raise AssertionError("CBSR original suite contains a failure or error")
        skip = case.find("skipped")
        if skip is not None:
            name = case.get("name")
            if (name not in GTE_SKIPS or name in observed
                    or not case.get("classname", "").endswith("test_cross_instrument")
                    or skip.get("message") != GTE_SKIP_REASON):
                raise AssertionError("Unexpected original-suite skip: " + ET.tostring(case, encoding="unicode"))
            observed[name] = GTE_SKIP_REASON
    if set(observed) != GTE_SKIPS or len(cases) <= len(observed):
        raise AssertionError("Only the two original unprovisioned GTE checks may be skipped")
    for suite in ET.parse(path).getroot().iter("testsuite"):
        if int(suite.get("errors", "0")) or int(suite.get("failures", "0")):
            raise AssertionError("CBSR collection errors are not qualified skips")
    return {"tests": len(cases), "passed": len(cases) - len(observed), "failures": 0,
            "errors": 0, "skipped": len(observed), "unqualified_checks": observed,
            "junit": str(path), "junit_sha256": sha256(path.read_bytes()).hexdigest()}


_SNAPSHOT = r'''
from copy import deepcopy
from hashlib import sha256
import json, math, pathlib, sys
import numpy as np
from ciw.adapters.protocol import AdapterRefusal
from ciw.calibrated_observable import (OPERATIONS, create_session, replay_session,
    save_session, inspect_session, canonical)

configuration = json.loads(pathlib.Path(sys.argv[1]).read_text())
repositories = {role: pathlib.Path(path) for role, path in configuration['providers'].items()}
raw = pathlib.Path(configuration['source']).read_bytes()
original = create_session(raw, repositories)
replay = replay_session(original, repositories)
fresh = replay['session']
assert original['verification']['outcome'] == fresh['verification']['outcome'] == 'passed'
assert original['verification']['independent'] is False
assert fresh['verification']['independent'] is False
assert replay['replay_receipt']['verification']['independent'] is False
assert replay['replay_receipt']['numerical_match'] is True
assert replay['replay_receipt']['admission'] == 'not_performed'
assert original['session_id'] != fresh['session_id']
assert original['verification']['verification_id'] != fresh['verification']['verification_id']
assert [s['numerical_result_id'] for s in original['steps']] == [s['numerical_result_id'] for s in fresh['steps']]
assert [(s['runtime_ref'], s['operation_id']) for s in original['steps']] == list(OPERATIONS)
evidence_ids = {record['artifact_ref'] for record in original['source']['evidence']}
operation_ids = {step['operation_id'] for step in original['steps']}
execution_ids = {step['execution_id'] for session in (original, fresh) for step in session['steps']}
result_ids = {step['result_id'] for session in (original, fresh) for step in session['steps']}
verification_ids = {session['verification']['verification_id'] for session in (original, fresh)}
groups = [evidence_ids, operation_ids, execution_ids, result_ids, verification_ids]
assert len(execution_ids) == len(result_ids) == 2 * len(OPERATIONS)
assert all(not first.intersection(second) for i, first in enumerate(groups) for second in groups[i + 1:])
data = {s['runtime_ref']: s['result'].get('data', s['result']) for s in original['steps']}
np.testing.assert_array_equal([c['event_time'] for c in data['tbrt']['channels']], [5., 5.])
np.testing.assert_array_equal(data['mcur']['values'], [52., 46.])
np.testing.assert_array_equal(data['mcur']['covariance']['matrix'], [[1., .25], [.25, 1.]])
assert data['oit']['rank'] == 2 and data['oit']['status'] == 'observable'
assert math.isclose(data['oit']['condition_number'], 1., rel_tol=1e-13)
np.testing.assert_allclose(data['gsie']['mean'], [607/12, 589/12], rtol=1e-13, atol=0)
np.testing.assert_allclose(data['gsie']['covariance'], [[19/96, 1/96], [1/96, 19/96]], rtol=1e-13, atol=0)
np.testing.assert_array_equal(data['gsie']['innovation'], [2., -4.])
np.testing.assert_array_equal(data['gsie']['innovation_covariance'], [[1.25, .25], [.25, 1.25]])
assert data['cbsr']['status'] == 'accepted'
np.testing.assert_allclose(data['cbsr']['reconciled']['estimate'], [50.75, 49.25], rtol=1e-13, atol=0)
np.testing.assert_allclose(data['cbsr']['reconciled']['covariance'], [[3/32, -3/32], [-3/32, 3/32]], rtol=1e-13, atol=0)
assert math.isclose(data['cbsr']['normalized_residual'], 4/15, rel_tol=1e-13)
assert math.isclose(data['fdir']['detection']['nis'], 58/3, rel_tol=1e-13)
assert data['fdir']['isolability']['isolated_fault'] == 'sensor:tank-2:bias'
source = json.loads(raw)
for declared, clock, calibration in zip(source['channels'], data['tbrt']['channels'], data['mcur']['channels']):
    assert declared['observation']['device_time'] == clock['reconciliation']['observation']['device_time']
    assert declared['observation']['raw_value'] == calibration['calibration']['raw_value']
    assert declared['clock_joint_covariance'] == clock['reconciliation']['joint_covariance']
assert source['calibrated_covariance'] == data['mcur']['covariance']
assert raw == pathlib.Path(configuration['source']).read_bytes()

root = pathlib.Path(configuration['sessions'])
original_path = save_session(original, root / 'original')
replay_path = save_session(fresh, root / 'replay')
receipt_path = root / 'replay-receipt.json'
receipt_path.write_text(json.dumps(replay['replay_receipt'], sort_keys=True, indent=2) + '\n')
refusals = {}
for label, mutate, expected in (
    ('unknown_calibrated_covariance', lambda s: s['calibrated_covariance'].update(cross_covariance_policy='unknown'), 'CALIBRATED_MCUR_REFUSED'),
    ('expired_calibration', lambda s: s['channels'][0]['calibration_profile'].update(valid_until='2025-12-31T00:00:00Z'), 'CALIBRATED_MCUR_REFUSED'),
    ('missing_synchronization_evidence', lambda s: s['channels'][0]['clock_model'].update(synchronization_evidence_ids=[]), 'CALIBRATED_FSRT_REFUSED'),
):
    altered = deepcopy(source)
    mutate(altered)
    try:
        create_session(canonical(altered), repositories)
    except AdapterRefusal as error:
        assert error.code == expected
        refusals[label] = {'expected': expected, 'actual': error.code}
    else:
        raise AssertionError('Invalid source accepted: ' + label)

report = {'schema': 'notations.monorepo-inference-composition.v1',
    'claim_scope': configuration['claim_scope'], 'independent_verification': False,
    'canonicalAdmission': False, 'admission': 'not_performed',
    'source_sha256': sha256(raw).hexdigest(), 'numerical_replay_equal': True,
    'original_session_id': original['session_id'], 'replayed_session_id': fresh['session_id'],
    'original_verification_id': original['verification']['verification_id'],
    'replayed_verification_id': fresh['verification']['verification_id'],
    'runtimes': original['runtimes'], 'inspection': inspect_session(original), 'refusals': refusals,
    'identity_separation': True, 'analytic_fixture_checks': {
        'aligned_times': [5., 5.], 'calibrated_values': [52., 46.],
        'observability_rank': 2, 'estimate': [607/12, 589/12],
        'reconciled_estimate': [50.75, 49.25], 'fault_nis': 58/3,
        'estimator_covariance_checked': True, 'reconciliation_covariance_checked': True,
        'raw_device_times_and_declared_uncertainty_retained': True},
    'artifacts': {label: {'path': str(path), 'sha256': sha256(path.read_bytes()).hexdigest()}
        for label, path in (('original', original_path), ('replay', replay_path), ('receipt', receipt_path))}}
pathlib.Path(configuration['report']).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps({'snapshot': 'passed', 'numerical_replay': True, 'independent': False, 'admission': 'not_performed'}))
'''


def _qualify(args, report: dict, output: Path, log: Path) -> None:
    if sys.version_info < (3, 12):
        raise ValueError("Full inference composition requires Python >=3.12, as declared by pinned public FlowState")
    manifest = load_manifest(root=ROOT)
    modules = {module["role"]: module for module in manifest["modules"]}
    if set(modules) != ROLES:
        raise ValueError("Inference gate requires the seven declared public module imports")
    report["imports"] = verify_imports(root=ROOT)
    report["modules"] = manifest["modules"]
    with tempfile.TemporaryDirectory(prefix="notations-inference-gate-") as directory, ExitStack() as contexts:
        temporary = Path(directory)
        python = _environment_python(temporary / "current-venv", temporary, log, build=True)
        legacy_python = _environment_python(temporary / "legacy-exchange-venv", temporary, log)
        flowstate = _flowstate(args.flowstate_root, temporary, log)
        flowstate_project = tomllib.loads(_git(flowstate, "show", FLOWSTATE_REVISION + ":pyproject.toml"))["project"]
        legacy_set = contexts.enter_context(provider_worktrees(root=ROOT, roles=["set"],
            overrides={"set": LEGACY_SET_REVISION}))["set"]
        checker_set = contexts.enter_context(provider_worktrees(root=ROOT, roles=["set"],
            overrides={"set": GSIE_SET_REVISION}))["set"]
        _run(["git", "-C", ROOT, "merge-base", "--is-ancestor", GSIE_TERMINAL_REVISION, "HEAD"],
             cwd=temporary, log=log)
        historical_terminal = contexts.enter_context(_worktree(ROOT, GSIE_TERMINAL_REVISION,
            temporary / "gsie-historical-terminal", temporary, log))
        cross_flowstate = contexts.enter_context(_worktree(flowstate, CBSR_FLOWSTATE_REVISION,
            temporary / "cbsr-public-flowstate", temporary, log))
        report["external_dependencies"] = {
            "flowstate": {"repository": FLOWSTATE_REPOSITORY, "repository_id": FLOWSTATE_REPOSITORY_ID,
                "visibility": "public", "migrated": False, "runtime_revision": FLOWSTATE_REVISION,
                "runtime_tree": _git(flowstate, "rev-parse", FLOWSTATE_REVISION + "^{tree}"),
                "distribution": flowstate_project["name"], "version": flowstate_project["version"],
                "requires_python": flowstate_project["requires-python"], "license": flowstate_project["license"],
                "cross_instrument_revision": CBSR_FLOWSTATE_REVISION,
                "cross_instrument_tree": _git(cross_flowstate, "rev-parse", "HEAD^{tree}"),
                "full_provider_suite_qualified": False},
            "legacy_exchange_set": {"revision": LEGACY_SET_REVISION,
                "source_tree": _git(legacy_set, "rev-parse", "HEAD^{tree}")},
            "gsie_checker_set": {"revision": GSIE_SET_REVISION,
                "source_tree": _git(checker_set, "rev-parse", "HEAD^{tree}")},
            "gsie_cli_terminal": {"revision": GSIE_TERMINAL_REVISION,
                "source_tree": _git(historical_terminal, "rev-parse", "HEAD^{tree}")}}
        build = temporary / "build-sources"
        build.mkdir()
        terminal = build / "terminal"
        terminal.mkdir()
        shutil.copytree(ROOT / "src", terminal / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        for name in ("pyproject.toml", "LICENSE"):
            shutil.copyfile(ROOT / name, terminal / name)
        wheels = {"ciw": _wheel(python, terminal, temporary / "wheel-ciw", log)}
        suites = {}
        with provider_worktrees(root=ROOT, revisions="import", roles=sorted(ROLES)) as imported:
            for role, module in sorted(modules.items()):
                _copy_source(imported[role], build / role)
                wheel = _wheel(python, build / role, temporary / ("wheel-" + role), log)
                if (wheel["distribution"], wheel["version"]) != (module["distribution"], module["version"]):
                    raise AssertionError("Imported distribution identity changed")
                wheels[module["python_import"]] = wheel
                suite = temporary / ("provider-suite-" + role)
                _copy_source(imported[role], suite)
                suites[role] = suite
        _copy_source(legacy_set, build / "legacy-set")
        legacy_wheel = _wheel(python, build / "legacy-set", temporary / "wheel-legacy-set", log)
        _run([python, "-I", "-m", "pip", "install", "--no-deps",
              *[wheel["path"] for wheel in wheels.values()]], cwd=temporary, log=log)
        legacy_wheels = dict(wheels)
        legacy_wheels[modules["set"]["python_import"]] = legacy_wheel
        _run([legacy_python, "-I", "-m", "pip", "install", "--no-deps",
              *[wheel["path"] for wheel in legacy_wheels.values()]], cwd=temporary, log=log)
        report["installed_packages"] = {"current": _probe(python, wheels, temporary, log),
            "legacy_exchange": _probe(legacy_python, legacy_wheels, temporary, log)}
        report["wheels"] = {name: {key: value for key, value in wheel.items() if key != "path"}
                            for name, wheel in wheels.items()}
        report["legacy_exchange_wheel"] = {key: value for key, value in legacy_wheel.items() if key != "path"}
        report["provider_tests"] = {}
        report["provider_examples"] = {}
        configuration = temporary / "pytest.ini"
        configuration.write_text("[pytest]\n")
        for role, module in sorted(modules.items()):
            suite = suites[role]
            selected_python = legacy_python if role in {"mcur", "tbrt", "oit", "fdir"} else python
            bindings = {"GSIE_SET_REPO": checker_set, "GSIE_CIW_REPO": historical_terminal,
                        "SET_CIW_REPO": ROOT, "CBSR_FSRT_REPO": cross_flowstate}
            junit = output / (role + "-tests.xml")
            # SET's unchanged tests import sibling test_contracts; preserve their
            # original prepend mode in this separate installed-wheel process.
            import_mode = [] if role == "set" else ["--import-mode=importlib"]
            _run_bound([selected_python, "-I", "-m", "pytest", "-q", "-c", configuration,
                        *import_mode, "--junitxml", junit, suite / "tests"],
                       cwd=suite, log=log, bindings=bindings, timeout=600)
            tests = _cbsr_junit(junit) if role == "cbsr" else _junit(junit)
            tests.setdefault("passed", tests["tests"])
            report["provider_tests"][role] = {**tests, "revision": module["import_revision"],
                "source_tree": module["import_tree"],
                "environment": "legacy_exchange" if selected_python == legacy_python else "current"}
            examples = {}
            names = (("replay.py", "exchange_roundtrip.py") if role == "gsie"
                     else (() if role in {"set", "cbsr"} else ("replay.py", "exchange.py")))
            for name in names:
                source = suite / "examples" / name
                arguments = [selected_python, "-I", source]
                if role == "gsie" and name == "exchange_roundtrip.py":
                    arguments += ["--validator-repo", checker_set]
                raw = _run_bound(arguments, cwd=suite, log=log, bindings=bindings)
                json.loads(raw)
                path = output / (role + "-" + name.removesuffix(".py") + ".json")
                path.write_text(raw)
                examples[name] = {"source_sha256": sha256(source.read_bytes()).hexdigest(),
                    "output": str(path), "output_sha256": sha256(path.read_bytes()).hexdigest()}
            if role == "cbsr":
                source = suite / "examples/affine_exact.json"
                raw = _run_bound([python, "-I", "-m", "cbsr"], cwd=suite, log=log,
                                 stdin=source.read_bytes(), bindings=bindings)
                if json.loads(raw)["status"] != "accepted":
                    raise AssertionError("CBSR original affine example did not accept its fixture")
                path = output / "cbsr-affine-exact.json"
                path.write_text(raw)
                examples["affine_exact.json"] = {"source_sha256": sha256(source.read_bytes()).hexdigest(),
                    "output": str(path), "output_sha256": sha256(path.read_bytes()).hexdigest()}
            report["provider_examples"][role] = examples
        with provider_worktrees(root=ROOT, revisions="runtime", roles=sorted(ROLES)) as providers:
            parents = {path.parent for path in providers.values()}
            if len(parents) != 1:
                raise ValueError("Original calibrated suite requires sibling role worktrees")
            provider_root, = parents
            with _worktree(flowstate, FLOWSTATE_REVISION, provider_root / "fsrt", temporary, log) as fsrt:
                providers = {**providers, "fsrt": fsrt}
                process_suite = temporary / "calibrated-observable-suite"
                (process_suite / "tests").mkdir(parents=True)
                shutil.copyfile(ROOT / "tests/test_calibrated_observable.py",
                                process_suite / "tests/test_calibrated_observable.py")
                shutil.copytree(ROOT / "examples/calibrated-observable",
                                process_suite / "examples/calibrated-observable")
                junit = output / "calibrated-observable-tests.xml"
                _run_bound([python, "-I", "-m", "pytest", "-q", "-c", configuration,
                            "--import-mode=importlib", "--junitxml", junit, process_suite / "tests"],
                           cwd=process_suite, log=log, bindings={"CIW_CALIBRATED_STACK_ROOT": provider_root},
                           timeout=1800)
                report["calibrated_observable_tests"] = {**_junit(junit),
                    "source_test_sha256": sha256((ROOT / "tests/test_calibrated_observable.py").read_bytes()).hexdigest()}
                snapshots = output / ("sessions-" + report["verification_id"].split(":", 1)[1])
                snapshot_configuration = temporary / "snapshot.json"
                composition_path = output / "composition.json"
                snapshot_configuration.write_text(json.dumps({
                    "providers": {role: str(path) for role, path in providers.items()},
                    "source": str(process_suite / "examples/calibrated-observable/source.json"),
                    "sessions": str(snapshots), "report": str(composition_path), "claim_scope": SCOPE}))
                _run_bound([python, "-I", "-c", _SNAPSHOT, snapshot_configuration],
                           cwd=temporary, log=log, timeout=600)
                report["composition"] = json.loads(composition_path.read_text())
        report["post_execution_imports"] = verify_imports(root=ROOT)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flowstate-root", type=Path,
                        help="Existing public FlowState repository containing both declared historical commits")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/monorepo-inference")
    args = parser.parse_args(argv)
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    log = output / "commands.log"
    log.write_text("")
    report = {"schema": "notations.monorepo-inference-gate.v1", "status": "running",
        "verification_id": "verification:" + uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(), "terminal_revision": _git(ROOT, "rev-parse", "HEAD"),
        "python_version": sys.version, "minimum_python": "3.12",
        "claim_scope": SCOPE, "independent_verification": False, "canonicalAdmission": False,
        "admission": "not_performed", "gte_integration_qualified": False,
        "dependencies": DEPENDENCIES, "log": str(log)}
    try:
        _qualify(args, report, output, log)
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        print(f"Public inference gate failed: {error}", file=sys.stderr)
    else:
        report["status"] = "passed"
        total = sum(check["passed"] for check in report["provider_tests"].values())
        print(f"Public inference gate passed: {total} provider tests; two GTE checks unqualified; "
              f"{report['calibrated_observable_tests']['tests']} original process tests; retained exact replay.")
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
