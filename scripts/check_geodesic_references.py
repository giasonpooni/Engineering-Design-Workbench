"""Exercise installed CIW native references and independent ICRH replay checks."""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

REPOSITORIES = {"ftr": "Flat-Torus-Geodesic-Reference",
                "csg": "Curved-Surface-Geodesic-Sensitivity-Runtime"}
# Exact independent checker validated against the retained native fixture pairs.
ICRH_REVISION = "dc4d826ecd1f28c1d55b724618380ce44e58bedd"
TESTS = ("test_geodesic_reference.py", "test_geodesic_reference_session.py", "test_curved_path_study.py")


# Reuse ICRH's existing numerical profile for every candidate occurrence. This
# does not add a study-policy, physical-validation or ESM-admission profile.
_STUDY_PAIR_CHECK = r"""
import json, sys
from pathlib import Path
from ciw.curved_path_study import load_study
from ciw.session import Session
from ciw.telemetry import canonical
from icrh.geodesic import compare_geodesic_replay
from icrh.geodesic_profiles import profile_spec
root = Path(sys.argv[1])
first = Session.from_workspace(root / 'curved-study/workspace.json')
second = Session.from_workspace(root / 'curved-study-replay/workspace.json')
a = load_study(root / 'curved-study/study.json', first.workbench)
b = load_study(root / 'curved-study-replay/study.json', second.workbench)
if b['replay_of'] != a['study_digest']:
    raise AssertionError('Study parent differs from supplied original')
if {k: v for k, v in a['request'].items() if k != 'baseline_bundle_id'} != {k: v for k, v in b['request'].items() if k != 'baseline_bundle_id'}:
    raise AssertionError('Study request changed across replay')
reports = []
for old, new in zip([a['baseline'], *a['candidates']], [b['baseline'], *b['candidates']]):
    if old['candidate_id'] != new['candidate_id']:
        raise AssertionError('Candidate order changed across replay')
    original = first.workbench.get_bundle(old['references']['bundle_id'])
    replayed = second.workbench.get_bundle(new['references']['bundle_id'])
    report = compare_geodesic_replay(profile_spec('curved-path-transfer'),
        original, canonical(original), replayed, canonical(replayed))
    if report['replay_receipt']['outcome'] != 'REPLAY_PASSED':
        raise AssertionError('Native study occurrence failed independent comparison')
    reports.append({'candidate_id': old['candidate_id'], 'comparison': report})
(root / 'curved-study-icrh.json').write_bytes(canonical({
    'study_digest': a['study_digest'], 'replay_study_digest': b['study_digest'],
    'scope': 'native_constant_curvature_and_covariance_oracles_and_fresh_pair_bindings',
    'study_policy_verification': 'not_performed', 'comparisons': reports}))
print('PASS: independent ICRH checks of', len(reports), 'native study occurrence pairs')
"""


def call(command, **kwargs):
    return subprocess.run(command, check=True, timeout=kwargs.pop("timeout", 300), **kwargs)


def literal(path, name):
    for statement in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in statement.targets):
            return ast.literal_eval(statement.value)
    raise ValueError("Missing literal pin declaration: " + name)


def exact_source(repository, revision):
    from provider_checkouts import validate_checkout
    validate_checkout(repository, revision)
    return call(["git", "--no-replace-objects", "-C", str(repository), "rev-parse", "HEAD^{tree}"],
                capture_output=True, text=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack-root", type=Path, help="Clean exact ftr/csg checkouts; no provider fetch")
    parser.add_argument("--icrh-repo", type=Path, help="Clean exact pinned independent checker; no harness fetch")
    parser.add_argument("--output-dir", type=Path, default=Path("results/geodesic-references"))
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        raise RuntimeError("The native flat-torus reference requires Python 3.12 or newer")
    root = Path(__file__).resolve().parents[1]
    pins = literal(root / "src/ciw/geodesic_reference.py", "PINS")
    revisions = {pin["role"]: pin["revision"] for pin in pins.values()}
    if set(revisions) != set(REPOSITORIES):
        raise ValueError("Require both pinned native reference providers")
    destination = args.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="ciw-ref-") as directory:
        temporary = Path(directory)
        checked = []

        def checkout(role, repository, revision, existing):
            if existing is not None:
                path = existing.resolve(strict=True)
            else:
                path = temporary / role
                call(["git", "clone", "--quiet", "--no-checkout",
                      "https://github.com/atomtrapping/" + repository + ".git", str(path)])
                call(["git", "-C", str(path), "-c", "core.autocrlf=false", "checkout", "--quiet", "--detach", revision])
            checked.append((path, revision, exact_source(path, revision)))
            return path

        repositories = {role: checkout(role, repository, revisions[role],
            args.stack_root / role if args.stack_root else None) for role, repository in REPOSITORIES.items()}
        harness = checkout("icrh", "Instrument-Conformance-and-Replay-Harness", ICRH_REVISION, args.icrh_repo)
        build = temporary / "build"
        shutil.copytree(root / "src", build / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        for name in ("pyproject.toml", "README.md", "LICENSE"):
            if (root / name).is_file():
                shutil.copyfile(root / name, build / name)
        wheels = temporary / "wheels"
        call([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", str(build), "-w", str(wheels)])
        wheel, = wheels.glob("*.whl")
        harness_build = temporary / "harness-build"
        shutil.copytree(harness / "src", harness_build / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        for name in ("pyproject.toml", "README.md", "LICENSE"):
            if (harness / name).is_file():
                shutil.copyfile(harness / name, harness_build / name)
        harness_wheels = temporary / "harness-wheels"
        call([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", str(harness_build), "-w", str(harness_wheels)])
        harness_wheel, = harness_wheels.glob("*.whl")
        environment = temporary / "env"
        call([sys.executable, "-m", "venv", str(environment)])
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        call([str(python), "-m", "pip", "install", str(wheel), str(harness_wheel), "pytest==9.0.2"])
        work = temporary / "check"
        (work / "tests").mkdir(parents=True)
        for name in TESTS:
            shutil.copyfile(root / "tests" / name, work / "tests" / name)
        shutil.copytree(root / "examples/geodesic-reference", work / "examples/geodesic-reference")
        shutil.copytree(root / "examples/curved-path-study", work / "examples/curved-path-study")
        (work / "scripts").mkdir()
        shutil.copyfile(root / "scripts/check_curved_path_study.py", work / "scripts/check_curved_path_study.py")
        env = {**os.environ, "CIW_FTR_REPO": str(repositories["ftr"]), "CIW_CSG_REPO": str(repositories["csg"]),
               "CIW_GEODESIC_FIXTURE_DIR": str(destination)}
        env.pop("PYTHONPATH", None)
        imported = call([str(python), "-I", "-c", "import ciw; print(ciw.__file__)"],
                        cwd=work, env=env, text=True, capture_output=True)
        if not Path(imported.stdout.strip()).resolve().is_relative_to(environment.resolve()):
            raise AssertionError("Gate must execute the installed wheel")
        imported_harness = call([str(python), "-I", "-c", "import icrh; print(icrh.__file__)"],
                                cwd=work, env=env, text=True, capture_output=True)
        if not Path(imported_harness.stdout.strip()).resolve().is_relative_to(environment.resolve()):
            raise AssertionError("Gate must execute the installed independent harness wheel")
        report = destination / "tests.xml"
        call([str(python), "-I", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml", str(report),
              *["tests/" + name for name in TESTS]], cwd=work, env=env, timeout=900)
        if any(int(s.get("skipped", 0)) for s in ET.parse(report).getroot().iter("testsuite")):
            raise AssertionError("Native reference gate cannot pass skipped tests")
        study_root = destination / "curved-study"
        replay_root = destination / "curved-study-replay"
        study_script = work / "scripts/check_curved_path_study.py"
        commands = {
            "run": ["run", "--csg-repo", str(repositories["csg"]),
                    "--source", str(work / "examples/curved-path-study/baseline.json"),
                    "--spec", str(work / "examples/curved-path-study/spec.json"), "--output", str(study_root)],
            "inspect": ["inspect", "--workspace", str(study_root / "workspace.json"),
                        "--study", str(study_root / "study.json")],
            "replay": ["replay", "--csg-repo", str(repositories["csg"]),
                       "--workspace", str(study_root / "workspace.json"),
                       "--study", str(study_root / "study.json"), "--output", str(replay_root)],
        }
        for action, arguments in commands.items():
            result = call([str(python), "-I", str(study_script), *arguments],
                          cwd=work, env=env, capture_output=True)
            (destination / ("curved-study-" + action + ".json")).write_bytes(result.stdout)
        call([str(python), "-I", str(harness / "scripts/check_geodesic_fixtures.py"),
              "--fixtures-dir", str(destination)], cwd=work, env=env)
        call([str(python), "-I", "-c", _STUDY_PAIR_CHECK, str(destination)], cwd=work, env=env)
        for path, revision, tree in checked:
            if exact_source(path, revision) != tree:
                raise AssertionError("Pinned source changed during the gate")
        (destination / "providers.json").write_text(json.dumps({
            "providers": {role: {"revision": revisions[role], "repository": REPOSITORIES[role]} for role in revisions},
            "icrh_revision": ICRH_REVISION, "installed_wheel": wheel.name}, indent=2) + "\n", encoding="utf-8")
    print("PASS: installed native references, shared session, offline restore, fresh replay and independent ICRH checks")


if __name__ == "__main__":
    main()
