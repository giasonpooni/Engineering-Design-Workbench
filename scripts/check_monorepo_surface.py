"""Qualify the preserved public Surface package and its original NET binding.

The full unchanged scientific suite imports an independently installed wheel.
Original reports, figures, boundary examples and five determinism cycles are
regenerated outside the repository. The original locked contract lane remains
separate from the NET environment and its historical execution pin.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from email.parser import BytesParser
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
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
    from .check_monorepo import DEPENDENCIES, _copy_source, _environment, _git, _IMPORT_PROBE, _junit, _wheel
    from .monorepo import ROOT, load_manifest, project_version, provider_worktrees, verify_imports
else:
    from check_monorepo import DEPENDENCIES, _copy_source, _environment, _git, _IMPORT_PROBE, _junit, _wheel
    from monorepo import ROOT, load_manifest, project_version, provider_worktrees, verify_imports

SURFACE_REVISION = "1f7bbe380651e8df82db1760d880330aee3dc229"
SURFACE_RUNTIME_REVISION = "bbc535af29c30997e56fd120320c570830676462"
REQUIREMENTS = ["setuptools>=77", "wheel", "hatchling>=1.27",
                "matplotlib>=3.8", "ruff>=0.5", *DEPENDENCIES]
SCOPE = (
    "Public Surface independent-wheel full scientific suite, regenerated numerical reports and "
    "figures, boundary artefact replay, original locked contract checks, and same-machine "
    "determinism; existing exact-pin NET curved-path reference and study replay only. "
    "No private Periodic Space provider, attached browser, physical validation, instrument "
    "calibration, independent verification, state admission, machine or acquisition authority."
)
NET_SELECTION = "not flat-torus-reference and not oblique_lattice"


def _run(arguments, *, cwd: Path, log: Path, bindings=None, timeout=600) -> str:
    environment = _environment()
    for name in list(environment):
        if name.startswith(("CIW_", "GAT_", "SCR_", "UV_")) or name in {
                "RUN_LIVE_TESTS", "NODE_OPTIONS", "NODE_PATH"}:
            environment.pop(name)
    environment.update({"PYTHONDONTWRITEBYTECODE": "1", "MPLBACKEND": "Agg",
                        "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
                        "MKL_NUM_THREADS": "1"})
    environment.update({name: str(value) for name, value in (bindings or {}).items()})
    command = [str(item) for item in arguments]
    display = list(command)
    if "-c" in display:
        index = display.index("-c") + 1
        if "\n" in display[index]:
            display[index] = "<inline-sha256:" + sha256(command[index].encode()).hexdigest() + ">"
    with log.open("ab") as stream:
        stream.write(("\n$ " + " ".join(display) + "\n").encode())
        stream.flush()
        result = subprocess.run(command, cwd=cwd, env=environment, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout, check=False)
        stream.write(result.stdout)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(display[:5])}\n"
                           + result.stdout.decode(errors="replace")[-9000:])
    return result.stdout.decode()


def _python(path: Path, temporary: Path, log: Path) -> Path:
    venv.EnvBuilder(with_pip=True).create(path)
    python = path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    _run([python, "-I", "-m", "pip", "install", *REQUIREMENTS], cwd=temporary, log=log)
    return python


def _surface_wheel(python: Path, source: Path, destination: Path, log: Path) -> dict:
    # The original Hatch package reads its version from contract.py; adding a
    # literal project.version merely to use another gate's helper would change
    # the original package contract.
    project = tomllib.loads((source / "pyproject.toml").read_text())["project"]
    version = project_version(source, project)
    destination.mkdir()
    _run([python, "-I", "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
          source, "--wheel-dir", destination], cwd=source.parent, log=log)
    path, = destination.glob("*.whl")
    with zipfile.ZipFile(path) as archive:
        metadata_path, = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        metadata = BytesParser().parsebytes(archive.read(metadata_path))
        if (metadata["Name"], metadata["Version"]) != (project["name"], version):
            raise AssertionError("Original dynamic Surface wheel identity changed")
        license_path, = [name for name in archive.namelist()
                         if name.endswith(".dist-info/licenses/LICENSE")]
        if archive.read(license_path) != (source / "LICENSE").read_bytes():
            raise AssertionError("Surface wheel must retain its original MPL license bytes")
        if any(name.startswith("instruments/") for name in archive.namelist()):
            raise AssertionError("Independent Surface wheel must not contain monorepo instruments")
    return {"path": str(path), "filename": path.name, "sha256": sha256(path.read_bytes()).hexdigest(),
            "distribution": metadata["Name"], "version": version,
            "license_sha256": sha256((source / "LICENSE").read_bytes()).hexdigest()}


_EXPECTED_SKIPS = r'''
import json, pathlib, runpy, sys
import numpy as np
root = pathlib.Path(sys.argv[1])
module = runpy.run_path(str(root / 'tests/test_documentation_claims.py'))
expected = []
rules = (
 ('test_every_schema_named_in_prose_is_a_schema_a_report_declares', 'names no report schema',
  lambda text: bool(module['SCHEMA_IN_PROSE'].findall(text))),
 ('test_every_check_count_in_prose_is_the_count_in_the_report', 'states no check count',
  lambda text: bool(module['COUNT_IN_PROSE'].findall(text))),
 ('test_a_prose_claim_of_no_failures_is_true', 'claims nothing about failures',
  lambda text: '0 failed' in text),
)
for document in module['_documents']():
    relative = document.relative_to(root).as_posix()
    text = document.read_text()
    for name, reason, applies in rules:
        if not applies(text):
            expected.append({'module':'test_documentation_claims',
                'name':name+'['+relative+']', 'reason':reason, 'qualification':'no_claim_in_document'})
if np.finfo(np.longdouble).tiny >= np.finfo(float).tiny:
    expected.append({'module':'test_covariance_validation',
        'name':'test_extended_precision_variance_cannot_be_erased_by_float64_conversion',
        'reason':'extended precision is unavailable on this platform',
        'qualification':'platform_extended_precision_not_available'})
print(json.dumps(expected,sort_keys=True))
'''


def _surface_junit(path: Path, expected: list[dict]) -> dict:
    tree = ET.parse(path).getroot()
    cases = list(tree.iter("testcase"))
    allowed = {(item["module"], item["name"]): item for item in expected}
    skipped = {}
    if not cases:
        raise AssertionError("The unchanged Surface suite must execute nonempty coverage")
    for case in cases:
        if case.find("failure") is not None or case.find("error") is not None:
            raise AssertionError("Original Surface suite contains a failure or error")
        skip = case.find("skipped")
        if skip is not None:
            key = (case.get("classname", "").rsplit(".", 1)[-1], case.get("name", ""))
            if key not in allowed or key in skipped or skip.get("message") != allowed[key]["reason"]:
                raise AssertionError("Unexpected Surface skip: " + ET.tostring(case, encoding="unicode"))
            skipped[key] = allowed[key]
    if set(skipped) != set(allowed):
        raise AssertionError("The original individually named documentation/platform skips changed")
    if any(int(suite.get(name, "0")) for suite in tree.iter("testsuite") for name in ("errors", "failures")):
        raise AssertionError("Surface collection errors must not be treated as intentional skips")
    return {"tests": len(cases), "passed": len(cases) - len(skipped), "failures": 0,
            "errors": 0, "skipped": len(skipped), "intentional_nonapplicable_checks": list(skipped.values()),
            "junit": str(path), "junit_sha256": sha256(path.read_bytes()).hexdigest()}


_WHEEL_BOUNDARY = r'''
import importlib.metadata, json, pathlib, sys
import geodesic_testbed as g
from geodesic_testbed.boundary import PathGeometryArtefact, TransferRecord
import matplotlib, numpy, pytest
assert g.__version__ == g.RUNTIME_VERSION == importlib.metadata.version('curved-surface-geodesic-sensitivity')
assert pathlib.Path(g.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve())
print(json.dumps({'version':g.__version__, 'package_file':g.__file__, 'numpy':numpy.__version__,
 'matplotlib':matplotlib.__version__, 'pytest':pytest.__version__,
 'boundary_types':[PathGeometryArtefact.__name__,TransferRecord.__name__]},sort_keys=True))
'''


_ARTEFACTS = r'''
from hashlib import sha256
import json, pathlib, sys
import numpy as np
from geodesic_testbed.engine.experiment import content_hash
from geodesic_testbed.boundary import read_artefact, read_record, transfer_record_from_artefact
from PIL import Image
root, committed = map(pathlib.Path, sys.argv[1:3])
reports = {}
for name, count in [('report-v1.json',143),('report-v2-surfaces.json',202)]:
    path = root / name
    value = json.loads(path.read_text())
    old = json.loads((committed / 'validation' / name).read_text())
    checks = {item['id']:item['passed'] for item in value['checks']}
    assert len(checks) == len(value['checks']) == count
    assert checks == {item['id']:item['passed'] for item in old['checks']}
    assert all(checks.values()) and value['summary']['n_failed'] == 0
    assert value['summary']['all_passed'] is True and value['summary']['n_checks'] == count
    core = {key:item for key,item in value.items() if key not in ('environment','summary','content_hash')}
    assert value['content_hash'] == content_hash(core)
    reports[name] = {'schema':value['schema'],'checks':count,'passed':count,'failures':0,
      'content_hash':value['content_hash'],'committed_verdicts_equal':True,
      'cross_machine_byte_identity_claimed':False}
figures = {}
for name in ('jacobi-testbed-v1.png','surfaces-testbed-v1.png'):
    path = root / name
    with Image.open(path) as figure:
        figure.verify()
    with Image.open(path) as figure:
        assert figure.width >= 1000 and figure.height >= 1000
        figures[name] = {'width':figure.width,'height':figure.height,'sha256':sha256(path.read_bytes()).hexdigest()}
reference = json.loads((root / 'reference-report.json').read_text())
assert reference['schema'] == 'geodesic-sensitivity-report-v1'
assert reference['claim_scope'] == 'first-order-computational-analysis'
assert len(reference['numerical_validation']) == 3
assert 'Numerical validation' in (root / 'reference-report.md').read_text()
record = read_record(root / 'boundary/path-sensitivity-record.json')
summary = record.to_dict(include_samples=False)
assert summary['calibration']['bound'] is False
assert summary['resolution']['convergence']['established'] is True
assert summary['covariance']['declared'] is True
artefact = read_artefact(root / 'path-replay/path-geometry-v1.json')
replayed = transfer_record_from_artefact(artefact)
written = read_record(root / 'path-replay/transfer-record-from-artefact.json')
for component in ('a','a_rate','b','b_rate'):
    np.testing.assert_array_equal(getattr(replayed,component),getattr(written,component))
print(json.dumps({'reports':reports,'figures':figures,'reference_report_valid':True,
 'boundary_record_roundtrip_valid':True,'calibration_bound':False,
 'artefact_replay_equal':True,'artefact_samples':int(replayed.arclength.size),
 'files':{path.relative_to(root).as_posix():sha256(path.read_bytes()).hexdigest()
          for path in sorted(root.rglob('*')) if path.is_file()}},sort_keys=True))
'''


_NET_REPLAY = r'''
from hashlib import sha256
import json, pathlib, sys
import numpy as np
from ciw.geodesic_reference import GeodesicReferenceWorkflow
from ciw.telemetry import canonical
configuration = json.loads(pathlib.Path(sys.argv[1]).read_text())
workflow = GeodesicReferenceWorkflow('curved-path-transfer')
repositories = {'csg':pathlib.Path(configuration['provider'])}
source = json.loads(pathlib.Path(configuration['source']).read_bytes())
output = pathlib.Path(configuration['output'])
results = {}
for label,curvature in [('positive',.25),('zero',0.),('negative',-.25)]:
    declaration = source | {'gaussian_curvature':curvature,'experiment_id':source['experiment_id']+':'+label}
    raw = b'\n ' + canonical(declaration) + b'\n'
    original = workflow.create_session(raw,repositories)
    replay = workflow.replay_session(original,repositories)
    fresh = replay['session']
    old,new = original['steps'][0],fresh['steps'][0]
    assert replay['replay_receipt']['numerical_match'] is True
    assert replay['replay_receipt']['admission'] == 'not_performed'
    assert original['verification']['independent'] is fresh['verification']['independent'] is False
    for key in ('execution_id','result_id'):
        assert old[key] != new[key]
    assert old['numerical_result_id'] == new['numerical_result_id']
    assert original['session_id'] != fresh['session_id']
    assert original['verification']['verification_id'] != fresh['verification']['verification_id']
    data = old['result']['data']; record = data['record']; grid = np.array(declaration['arclength'])
    if curvature > 0:
        k = np.sqrt(curvature); a,b = np.cos(k*grid),np.sin(k*grid)/k
    elif curvature < 0:
        k = np.sqrt(-curvature); a,b = np.cosh(k*grid),np.sinh(k*grid)/k
    else:
        a,b = np.ones_like(grid),grid
    phi = np.stack((np.stack((a,b),axis=-1),np.stack((-curvature*b,a),axis=-1)),axis=-2)
    actual = np.stack((np.stack((record['a'],record['b']),axis=-1),
                      np.stack((record['a_rate'],record['b_rate']),axis=-1)),axis=-2)
    np.testing.assert_allclose(actual,phi,rtol=2e-6,atol=2e-7)
    covariance = np.asarray(declaration['starting_covariance']['matrix'])
    np.testing.assert_allclose(data['propagated_covariance'],phi@covariance@phi.transpose(0,2,1),rtol=2e-6,atol=2e-10)
    assert record['calibration']['bound'] is False
    assert record['resolution']['convergence']['established'] is False
    directory = output / label; directory.mkdir(parents=True)
    files = {}
    for name,value in [('source',declaration),('original',original),('replay',fresh),('receipt',replay['replay_receipt'])]:
        path = directory / (name+'.json'); path.write_bytes(canonical(value))
        files[name] = {'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}
    results[label] = {'numerical_replay_equal':True,'fresh_occurrence_identities':True,
                     'analytic_transfer_and_covariance_match':True,'artifacts':files,
                     'runtime':original['runtimes']['csg']}
print(json.dumps({'cases':results,'independent_verification':False,'admission':'not_performed',
 'physical_validation':False,'private_periodic_space_qualified':False},sort_keys=True))
'''


def qualify(args, report: dict, output: Path, log: Path) -> None:
    if sys.version_info < (3, 11):
        raise ValueError("Surface requires Python 3.11 or newer")
    report["imports"] = verify_imports(ROOT)
    module = {item["role"]: item for item in load_manifest(ROOT)["modules"]}["csg"]
    if (module["import_revision"], module["runtime_revision"]) != (SURFACE_REVISION, SURFACE_RUNTIME_REVISION):
        raise ValueError("Surface qualification requires the reviewed green import and unchanged NET runtime pin")
    report["module"] = module
    uv = str(args.uv) if args.uv else shutil.which("uv")
    if uv is None:
        raise RuntimeError("The original locked Surface qualification lane requires uv")
    with tempfile.TemporaryDirectory(prefix="notations-surface-") as directory, ExitStack() as contexts:
        temporary = Path(directory)
        source = contexts.enter_context(provider_worktrees(ROOT, revisions="import", roles=["csg"]))["csg"]
        runtime = contexts.enter_context(provider_worktrees(ROOT, revisions="runtime", roles=["csg"]))["csg"]
        python = _python(temporary / "wheel-environment", temporary, log)
        build = temporary / "surface-build"; _copy_source(source, build)
        surface = _surface_wheel(python, build, temporary / "surface-wheel", log)
        terminal = temporary / "terminal-build"; terminal.mkdir()
        for name in ("pyproject.toml", "README.md", "LICENSE"):
            shutil.copyfile(ROOT / name, terminal / name)
        shutil.copytree(ROOT / "src", terminal / "src")
        ciw = _wheel(python, terminal, temporary / "terminal-wheel", log)
        _run([python,"-I","-m","pip","install","--no-deps",surface["path"],ciw["path"]],cwd=temporary,log=log)
        expected = {"geodesic_testbed":{key:surface[key] for key in ("distribution","version")},
                    "ciw":{key:ciw[key] for key in ("distribution","version")}}
        report["installed_packages"] = json.loads(_run([python,"-I","-c",_IMPORT_PROBE,json.dumps(expected)],cwd=temporary,log=log))
        report["wheel_boundary"] = json.loads(_run([python,"-I","-c",_WHEEL_BOUNDARY],cwd=temporary,log=log))
        report["wheels"] = {name:{key:value for key,value in wheel.items() if key != "path"}
                            for name,wheel in (("surface",surface),("terminal",ciw))}
        suite = temporary / "surface-suite"; _copy_source(source,suite)
        expected_skips = json.loads(_run([python,"-I","-c",_EXPECTED_SKIPS,suite],cwd=temporary,log=log))
        junit = output / "surface-full-tests.xml"
        _run([python,"-I","-m","pytest","-q","-rs","-o","pythonpath=","--import-mode=importlib",
              "--junitxml",junit,"tests"],cwd=suite,log=log,timeout=3600)
        report["full_scientific_suite"] = {**_surface_junit(junit,expected_skips),
            "selection":"all original tests, including numerical markers; imports installed wheel",
            "original_test_hashes":{str(path.relative_to(source)):sha256(path.read_bytes()).hexdigest()
                                    for path in sorted((source / "tests").rglob("*.py"))}}
        _run([python,"-I","-m","ruff","check","."],cwd=suite,log=log)
        report["original_lint_passed"] = True
        # Original run_experiment.py inserts its sibling src directory. Run the
        # unchanged entry points from a fixture copy without that directory, so
        # both it and the unchanged determinism harness import the wheel.
        entrypoints = temporary / "surface-entrypoints"; _copy_source(source,entrypoints)
        shutil.rmtree(entrypoints / "src")
        artifacts = output / "regenerated"; artifacts.mkdir()
        commands = [
            ("run_experiment.py",["--out",artifacts]),
            ("write_reference_report.py",["--out",artifacts]),
            ("emit_boundary_record.py",["--out",artifacts / "boundary"]),
            ("replay_path_artefact.py",["--out",artifacts / "path-replay","--check"]),
        ]
        report["original_entrypoints"] = {}
        for name, options in commands:
            path = entrypoints / "examples" / name
            captured = _run([python,"-I",path,*options],cwd=temporary,log=log,timeout=1800)
            retained = output / (name.removesuffix(".py")+".txt"); retained.write_text(captured)
            report["original_entrypoints"][name] = {"source_sha256":sha256(path.read_bytes()).hexdigest(),
                "output":str(retained),"output_sha256":sha256(retained.read_bytes()).hexdigest()}
        report["regeneration"] = json.loads(_run([python,"-I","-c",_ARTEFACTS,artifacts,source],cwd=temporary,log=log))
        deterministic = output / "surface-determinism.json"
        _run([python,"-I",entrypoints / "tools/e2e.py","--runs","5","--profile","fast",
              "--baseline","self","--report",deterministic],cwd=temporary,log=log,timeout=3600)
        cycles = json.loads(deterministic.read_text())
        if (cycles["runs"],cycles["passed"],cycles["failed"],cycles["profile"],cycles["baseline"]) != (5,5,0,"fast","self"):
            raise AssertionError("Original Surface five-cycle same-machine determinism failed")
        if len(cycles["cycles"]) != 5 or not all(item["passed"] and len(item["steps"]) == 6 for item in cycles["cycles"]):
            raise AssertionError("Determinism must execute each original fast-profile step")
        report["determinism"] = {"report":str(deterministic),"sha256":sha256(deterministic.read_bytes()).hexdigest(),
            "runs":5,"passed":5,"profile":"fast","baseline":"self",
            "hash_seeds":[item["hash_seed"] for item in cycles["cycles"]],
            "thread_counts":[item["threads"] for item in cycles["cycles"]],
            "full_profile_repeated_suite":"not_performed; complete suite and both-stage regeneration executed separately"}
        locked = temporary / "surface-locked"; _copy_source(source,locked)
        lock_bytes = (locked / "uv.lock").read_bytes()
        locked_env = temporary / "locked-environment"
        bindings = {"UV_PROJECT_ENVIRONMENT":locked_env,"UV_PYTHON_DOWNLOADS":"never"}
        report["uv_version"] = _run([uv,"--version"],cwd=temporary,log=log).strip()
        _run([uv,"sync","--locked","--extra","dev","--python",sys.executable],cwd=locked,log=log,bindings=bindings,timeout=900)
        locked_python = locked_env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        _run([locked_python,"-I","-m","ruff","check","."],cwd=locked,log=log)
        junit = output / "surface-locked-contracts.xml"
        _run([locked_python,"-I","-m","pytest","-q","-rs","-m","not numerical","--junitxml",junit],cwd=locked,log=log,timeout=900)
        locked_skips = json.loads(_run([locked_python,"-I","-c",_EXPECTED_SKIPS,locked],cwd=temporary,log=log))
        if (locked / "uv.lock").read_bytes() != lock_bytes:
            raise AssertionError("The original frozen dependency lock changed")
        report["original_locked_lane"] = {**_surface_junit(junit,locked_skips),
            "uv_lock_sha256":sha256(lock_bytes).hexdigest(),"frozen_resolution_reproduced":True,
            "source_editable_contract_suite":True,"original_lint_passed":True}
        integrations = temporary / "terminal-integrations"; (integrations / "tests").mkdir(parents=True)
        names = ("test_geodesic_reference.py","test_curved_path_study.py")
        for name in names:
            shutil.copyfile(ROOT / "tests" / name,integrations / "tests" / name)
        shutil.copytree(ROOT / "examples",integrations / "examples")
        (integrations / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts/check_curved_path_study.py",integrations / "scripts/check_curved_path_study.py")
        junit = output / "terminal-surface-tests.xml"
        native_outputs = output / "native-geodesic-fixtures"
        bindings = {"CIW_CSG_REPO":runtime,"CIW_GEODESIC_FIXTURE_DIR":native_outputs}
        _run([python,"-I","-m","pytest","-q","--import-mode=importlib","-k",NET_SELECTION,
              "--junitxml",junit,"tests"],cwd=integrations,log=log,bindings=bindings,timeout=1200)
        report["terminal_integration_tests"] = {**_junit(junit),"selection":NET_SELECTION,
            "unchanged_test_hashes":{name:sha256((ROOT / "tests" / name).read_bytes()).hexdigest() for name in names},
            "private_periodic_space_provider_qualified":False}
        configuration = temporary / "net-replay.json"
        configuration.write_text(json.dumps({"provider":str(runtime),
            "source":str(integrations / "examples/geodesic-reference/curved-path.json"),
            "output":str(output / "retained-replays")}))
        report["native_replay"] = json.loads(_run([python,"-I","-c",_NET_REPLAY,configuration],cwd=temporary,log=log,timeout=600))
        report["post_execution_imports"] = verify_imports(ROOT)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=ROOT / "results/monorepo-surface")
    parser.add_argument("--uv",type=Path,help="uv executable for the original locked contract lane")
    args = parser.parse_args(argv)
    output = args.output_dir.expanduser().resolve(); output.mkdir(parents=True,exist_ok=True)
    log = output / "commands.log"; log.write_text("")
    report = {"schema":"notations.monorepo-surface-gate.v1","status":"running",
        "verification_id":"verification:"+uuid.uuid4().hex,
        "created_at":datetime.now(timezone.utc).isoformat(),"terminal_revision":_git(ROOT,"rev-parse","HEAD"),
        "python_version":sys.version,"platform":platform.platform(),"minimum_python":"3.11",
        "dependencies":REQUIREMENTS,"claim_scope":SCOPE,"independent_verification":False,
        "admission":"not_performed","log":str(log)}
    try:
        qualify(args,report,output,log)
    except Exception as error:
        report.update(status="failed",error={"type":type(error).__name__,"message":str(error)})
        print("Surface gate failed:",error,file=sys.stderr)
    else:
        report["status"] = "passed"
        print("Surface gate passed: full installed-wheel suite, numerical regeneration, locked contracts and exact NET replay")
    finally:
        (output / "report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
