"""Qualify the unchanged public FlowState import as a package and source suite.

Wheel execution and repository-relative source tests are separate identities.
The original default suite includes extended tests and excludes slow tests;
--full-reproduction additionally executes its public slow reproduction lane.
Only the exact original private DAF checks may remain unqualified skips.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import tomllib
import uuid
import venv
import xml.etree.ElementTree as ET

if __package__:
    from .check_monorepo import DEPENDENCIES, _copy_source, _environment, _git, _IMPORT_PROBE, _wheel
    from .check_monorepo_inference import _validate, _worktree
    from .monorepo import ROOT, load_manifest, provider_worktrees, verify_imports, verify_terminal_source
else:
    from check_monorepo import DEPENDENCIES, _copy_source, _environment, _git, _IMPORT_PROBE, _wheel
    from check_monorepo_inference import _validate, _worktree
    from monorepo import ROOT, load_manifest, provider_worktrees, verify_imports, verify_terminal_source

SENSITIVITY_REPOSITORY = "https://github.com/giasonpooni/Notations-Sensitivity-Testbed.git"
SENSITIVITY_REPOSITORY_ID = 1372780016
SENSITIVITY_REVISION = "c0a01c1a27f10b099ac200c7e83b0f03187ee4d2"
DAF_SKIP_REASON = "set DAF_ROOT to a DAF checkout"
DEFAULT_DAF_SKIPS = {
    ("test_bridge_daf", "test_daf_recomputes_every_committed_id"),
    ("test_bridge_daf", "test_export_tool_reproduces_the_committed_fixture_files"),
    ("test_real_diagnosis", "test_exporting_one_session_leaves_every_other_manifest_entry_byte_identical"),
}
SLOW_DAF_SKIPS = {
    ("test_bridge_daf", "test_export_tool_reproduces_every_committed_file"),
}
PUBLIC_SLOW_TESTS = (
    "tests/test_calibration_sweep.py::test_full_calibration_and_sweep_reproduce_the_committed_files",
    "tests/test_results_reproduce.py::test_phase1_results_reproduce",
)
SCOPE = (
    "Public FlowState independent-wheel numerical execution and unchanged source-suite checks only. "
    "No private acquisition replay qualification, physical validation, authenticated source evidence, "
    "independent verification, canonical state admission, or device execution authority."
)


def _run(arguments, *, cwd: Path, log: Path, stdin: bytes | None = None, timeout: int = 300) -> str:
    environment = _environment()
    environment.pop("DAF_ROOT", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["OPENBLAS_NUM_THREADS"] = "1"
    environment["OMP_NUM_THREADS"] = "1"
    command = [str(item) for item in arguments]
    display = list(command)
    if "-c" in display:
        index = display.index("-c") + 1
        if "\n" in display[index]:
            display[index] = "<inline-sha256:" + sha256(command[index].encode()).hexdigest() + ">"
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


def _python(path: Path, temporary: Path, log: Path) -> Path:
    venv.EnvBuilder(with_pip=True).create(path)
    executable = path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    _run([executable, "-I", "-m", "pip", "install", "setuptools>=77", "wheel",
          "hatchling>=1.27", *DEPENDENCIES], cwd=temporary, log=log)
    return executable


def _sensitivity(supplied: Path) -> Path:
    repository = supplied.expanduser().resolve()
    if Path(_git(repository, "rev-parse", "--show-toplevel")).resolve() != repository:
        raise ValueError("--sensitivity-root must be a standalone Git repository root")
    _git(repository, "cat-file", "-e", SENSITIVITY_REVISION + "^{commit}")
    return repository


def _junit(path: Path, expected_skips: set[tuple[str, str]]) -> dict:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if not cases:
        raise AssertionError("Source suite must execute nonempty test coverage")
    skipped = {}
    for case in cases:
        if case.find("failure") is not None or case.find("error") is not None:
            raise AssertionError("Original FlowState suite contains a failure or error")
        skip = case.find("skipped")
        if skip is not None:
            module = case.get("classname", "").rsplit(".", 1)[-1]
            key = (module, case.get("name", ""))
            if (key not in expected_skips or key in skipped
                    or skip.get("message") != DAF_SKIP_REASON):
                raise AssertionError("Unexpected original-suite skip: " + ET.tostring(case, encoding="unicode"))
            skipped[key] = {"module": module, "test": key[1], "reason": DAF_SKIP_REASON,
                            "qualification": "not_performed_private_acquisition_dependency"}
    if set(skipped) != expected_skips:
        raise AssertionError("Private acquisition exclusions must remain individually visible")
    for suite in root.iter("testsuite"):
        if int(suite.get("failures", "0")) or int(suite.get("errors", "0")):
            raise AssertionError("Collection errors cannot be treated as unqualified skips")
    return {"tests": len(cases), "passed": len(cases) - len(skipped), "failures": 0,
            "errors": 0, "skipped": len(skipped), "unqualified_checks": list(skipped.values()),
            "junit": str(path), "junit_sha256": sha256(path.read_bytes()).hexdigest()}


_SOURCE_PROBE = r'''
import importlib.metadata, json, pathlib, sys
import numpy, pytest, set_lcm, sensitivity
expected = json.loads(sys.argv[1])
location = pathlib.Path(set_lcm.__file__).resolve()
root = pathlib.Path(expected['source']).resolve()
if not location.is_relative_to(root / 'src'):
    raise AssertionError('Original source suite must import its exact standalone worktree')
distribution = importlib.metadata.distribution(expected['distribution'])
if distribution.version != expected['version']:
    raise AssertionError('Editable source distribution changed identity')
if not pathlib.Path(sensitivity.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):
    raise AssertionError('Public optional dependency must come from its isolated installed wheel')
print(json.dumps({'python': sys.version, 'numpy': numpy.__version__, 'pytest': pytest.__version__,
    'prefix': sys.prefix, 'module_file': str(location), 'editable_source_root': str(root),
    'distribution': distribution.metadata['Name'], 'version': distribution.version,
    'sensitivity_file': sensitivity.__file__,
    'editable_build_dependency': {'editables': importlib.metadata.version('editables')}}, sort_keys=True))
'''


_WHEEL_NUMERICS = r'''
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json, pathlib, sys
import numpy as np
from set_lcm.bridge.ciw import evaluate
from set_lcm.bridge.jspt import map_covariance

raw = pathlib.Path(sys.argv[1]).read_bytes()
request = json.loads(raw)
untouched = deepcopy(request)
result = evaluate(request)
assert result['status'] == 'ok', result
assert request == untouched
assert result == evaluate(request)
data = result['data']
assert data['diagnostics']['physical_truth_verified'] is False
assert data['calibrated_observation']['covariance'] == [[1., .25], [.25, 1.]]
artifacts = data['covariance_artifacts']
np.testing.assert_array_equal(artifacts['innovation']['matrix'], [[26., .25], [.25, 26.]])
expected_covariance = np.array([[Fraction(2075, 2163), Fraction(500, 2163)],
                              [Fraction(500, 2163), Fraction(2075, 2163)]], dtype=float)
expected_mean = np.array([Fraction(112390, 2163), Fraction(99790, 2163)], dtype=float)
np.testing.assert_allclose(artifacts['posterior']['matrix'], expected_covariance, rtol=1e-14, atol=1e-14)
np.testing.assert_allclose(data['unprojected_estimate']['values'], expected_mean, rtol=1e-14, atol=1e-14)
held = deepcopy(request)
held['inputs']['observations'][0]['values'] = [60., 50.]
held_artifact = held['inputs']['observation_covariance']
held_artifact['reference_values'] = [60., 50.]
held_body = {key: value for key, value in held_artifact.items() if key != 'covariance_id'}
held_artifact['covariance_id'] = 'sha256:' + sha256(json.dumps(held_body, sort_keys=True,
    separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
held_result = evaluate(held)
assert held_result['status'] == 'ok', held_result
held_data = held_result['data']
assert held_data['diagnostics']['reconciliation_status'] == 'model_inconsistent'
assert held_data['estimate']['values'] == held_data['unprojected_estimate']['values']
assert held_data['residuals']['correction'] is None
invalid = deepcopy(request)
invalid['inputs']['observations'][0]['unit'] = 'm'
refused = evaluate(invalid)
assert refused['status'] == 'refused'
transport = map_covariance([[1000., 0.], [0., 1000.]], [[1., .2], [.2, 1.5]])
np.testing.assert_allclose(transport, [[1e6, 2e5], [2e5, 1.5e6]], rtol=1e-12)
print(json.dumps({'schema': 'notations.flowstate-wheel-numerics.v1',
    'request_sha256': sha256(raw).hexdigest(), 'successful_result': result,
    'held_result': held_result, 'refused_result': refused,
    'pinned_sensitivity_covariance': transport.tolist(),
    'checks': {'analytic_posterior': True, 'joint_covariance_retained': True,
        'raw_request_preserved': True, 'deterministic_repeat': True,
        'held_correction_retained': True, 'unsupported_units_refused': True,
        'public_pinned_covariance_transport': True}}, sort_keys=True))
'''


def _qualify(args, report: dict, output: Path, log: Path) -> None:
    if sys.version_info < (3, 12):
        raise ValueError("FlowState qualification requires Python >=3.12")
    manifest = load_manifest(root=ROOT)
    modules = {item["role"]: item for item in manifest["modules"]}
    if "fsrt" not in modules:
        raise ValueError("The public FlowState source must be imported and registered before qualification")
    module = modules["fsrt"]
    if (module["distribution"], module["python_import"], module["source_root"], module["license"]) != (
            "fluid-state-reconstruction-testbed", "set_lcm", "src", "MIT"):
        raise ValueError("FlowState package, import, source layout or licence identity changed")
    report["imports"] = verify_imports(root=ROOT)
    report["module"] = module
    pins = json.loads((ROOT / "src/ciw/calibrated-observable-runtimes.json").read_text())
    if module["runtime_revision"] != pins["fsrt"]["revision"]:
        raise ValueError("Import must retain the existing calibrated-observable execution pin")
    report["existing_execution_binding"] = pins["fsrt"]
    with tempfile.TemporaryDirectory(prefix="notations-flowstate-gate-") as directory:
        temporary = Path(directory)
        wheel_python = _python(temporary / "wheel-venv", temporary, log)
        source_python = _python(temporary / "source-venv", temporary, log)
        with provider_worktrees(root=ROOT, revisions="import", roles=["fsrt"]) as imported, ExitStack() as contexts:
            if args.sensitivity_root is None:
                if "jspt" not in modules:
                    raise ValueError("The public optional dependency requires retained Sensitivity history or --sensitivity-root")
                sensitivity = contexts.enter_context(provider_worktrees(
                    root=ROOT, roles=["jspt"], overrides={"jspt": SENSITIVITY_REVISION}))["jspt"]
                sensitivity_route = "retained_monorepo_history"
            else:
                sensitivity_repository = _sensitivity(args.sensitivity_root)
                sensitivity = contexts.enter_context(_worktree(sensitivity_repository, SENSITIVITY_REVISION,
                    temporary / "sensitivity-pinned", temporary, log))
                sensitivity_route = "explicit_external_repository"
            source = imported["fsrt"]
            _validate(source, module["import_revision"], temporary, log)
            project = tomllib.loads((source / "pyproject.toml").read_text())["project"]
            if SENSITIVITY_REVISION not in project["optional-dependencies"]["jspt"][0]:
                raise ValueError("Public optional dependency pin differs from the original package extra")
            report["external_dependency"] = {"repository": SENSITIVITY_REPOSITORY,
                "repository_id": SENSITIVITY_REPOSITORY_ID, "visibility": "public", "migrated": "jspt" in modules,
                "binding_route": sensitivity_route, "revision": SENSITIVITY_REVISION,
                "source_tree": _git(sensitivity, "rev-parse", "HEAD^{tree}")}
            lock = source / "uv.lock"
            locked = tomllib.loads(lock.read_text())
            report["original_lock"] = {"sha256": sha256(lock.read_bytes()).hexdigest(),
                "registry_versions": {item["name"]: item["version"] for item in locked["package"]
                    if "registry" in item.get("source", {})}, "frozen_uv_environment_reproduced": False,
                "test_environment": "separately provisioned explicit NET dependency versions"}
            build = temporary / "build"
            build.mkdir()
            _copy_source(source, build / "flowstate")
            _copy_source(sensitivity, build / "sensitivity")
            wheels = {"set_lcm": _wheel(wheel_python, build / "flowstate", temporary / "wheel-flowstate", log),
                      "sensitivity": _wheel(wheel_python, build / "sensitivity", temporary / "wheel-sensitivity", log)}
            if (wheels["set_lcm"]["distribution"], wheels["set_lcm"]["version"]) != (
                    module["distribution"], module["version"]):
                raise AssertionError("Independent wheel package identity differs from its imported source")
            _run([wheel_python, "-I", "-m", "pip", "install", "--no-deps",
                  *[item["path"] for item in wheels.values()]], cwd=temporary, log=log)
            expected = {name: {key: item[key] for key in ("distribution", "version")}
                        for name, item in wheels.items()}
            report["wheel_installation"] = json.loads(_run(
                [wheel_python, "-I", "-c", _IMPORT_PROBE, json.dumps(expected)], cwd=temporary, log=log))
            report["wheels"] = {name: {key: value for key, value in item.items() if key != "path"}
                                for name, item in wheels.items()}
            raw = _run([wheel_python, "-I", "-c", _WHEEL_NUMERICS,
                        source / "examples/ciw_tank_request_v2.json"], cwd=temporary, log=log)
            numerical = output / "wheel-numerics.json"
            numerical.write_text(raw)
            report["wheel_numerics"] = {"output": str(numerical),
                "sha256": sha256(numerical.read_bytes()).hexdigest(), "checks": json.loads(raw)["checks"]}
            report["wheel_examples"] = {}
            for name in ("quickstart.py", "fluid_baseline.py", "invariant_fluid.py", "camera_baseline.py"):
                example = source / "examples" / name
                arguments = [wheel_python, "-I", example]
                if name == "camera_baseline.py":
                    arguments += ["--out-dir", output / "synthetic-camera-example"]
                captured = _run(arguments, cwd=temporary, log=log)
                result = output / ("wheel-" + name.removesuffix(".py") + ".txt")
                result.write_text(captured)
                report["wheel_examples"][name] = {"source_sha256": sha256(example.read_bytes()).hexdigest(),
                    "output": str(result), "output_sha256": sha256(result.read_bytes()).hexdigest()}
            captured = _run([wheel_python, "-I", "-m", "set_lcm.recording", "init",
                             output / "recording-kit"], cwd=temporary, log=log)
            (output / "wheel-recording-kit.txt").write_text(captured)
            report["recording_kit"] = {"path": str(output / "recording-kit"),
                "status": "blank_kit_created_no_physical_recording_performed"}
            _run([source_python, "-I", "-m", "pip", "install", "--no-deps", wheels["sensitivity"]["path"]],
                 cwd=temporary, log=log)
            _run([source_python, "-I", "-m", "pip", "install", "editables>=0.3"],
                 cwd=temporary, log=log)
            _run([source_python, "-I", "-m", "pip", "install", "--no-deps", "--no-build-isolation",
                  "--editable", source], cwd=temporary, log=log)
            expected_source = {"source": str(source), "distribution": module["distribution"], "version": module["version"]}
            report["source_installation"] = json.loads(_run(
                [source_python, "-I", "-c", _SOURCE_PROBE, json.dumps(expected_source)], cwd=temporary, log=log))
            junit = output / "flowstate-default-tests.xml"
            _run([source_python, "-I", "-m", "pytest", "-q", "-rs", "--junitxml", junit],
                 cwd=source, log=log, timeout=2700)
            report["source_tests"] = {**_junit(junit, DEFAULT_DAF_SKIPS),
                "selection": "original default addopts: not slow; extended tests included",
                "source_revision": module["import_revision"], "source_tree": module["import_tree"]}
            if args.full_reproduction:
                junit = output / "flowstate-slow-tests.xml"
                _run([source_python, "-I", "-m", "pytest", "-q", "-rs", "-o", "addopts=", "-m", "slow",
                      "--junitxml", junit], cwd=source, log=log, timeout=3600)
                report["slow_reproduction"] = {"status": "passed", **_junit(junit, SLOW_DAF_SKIPS)}
            else:
                report["slow_reproduction"] = {"status": "not_performed",
                    "public_tests_not_executed": PUBLIC_SLOW_TESTS,
                    "private_test_not_executed": next(iter(SLOW_DAF_SKIPS))[1],
                    "command_option": "--full-reproduction"}
            _validate(source, module["import_revision"], temporary, log)
            _validate(sensitivity, SENSITIVITY_REVISION, temporary, log)
        report["post_execution_imports"] = verify_imports(root=ROOT)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sensitivity-root", type=Path,
                        help="Explicit external Sensitivity repository; otherwise materialize its optional-extra pin from retained history")
    parser.add_argument("--full-reproduction", action="store_true",
                        help="Additionally run original public slow report reproductions; private DAF export stays unqualified")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/monorepo-flowstate")
    args = parser.parse_args(argv)
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    log = output / "commands.log"
    log.write_text("")
    report = {"schema": "notations.monorepo-flowstate-gate.v1", "status": "running",
        "verification_id": "verification:" + uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(), "terminal_revision": _git(ROOT, "rev-parse", "HEAD"),
        "python_version": sys.version, "platform": platform.platform(), "minimum_python": "3.12",
        "dependencies": DEPENDENCIES, "claim_scope": SCOPE, "independent_verification": False,
        "canonicalAdmission": False, "admission": "not_performed", "private_daf_qualified": False,
        "log": str(log)}
    try:
        report["terminal_source"] = verify_terminal_source(root=ROOT)
        if report["terminal_source"]["revision"] != report["terminal_revision"]:
            raise ValueError("Terminal revision changed before qualification")
        _qualify(args, report, output, log)
        if verify_terminal_source(root=ROOT) != report["terminal_source"]:
            raise ValueError("Terminal source identity changed during qualification")
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        print(f"FlowState gate failed: {error}", file=sys.stderr)
    else:
        report["status"] = "passed"
        source = report["source_tests"]
        print(f"FlowState gate passed: {source['passed']} original default-source tests, "
              f"{source['skipped']} exact unqualified acquisition checks, isolated wheel operations and examples.")
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
