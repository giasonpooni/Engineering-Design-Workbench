"""Check the actual wheel/sdist and retain build evidence; never publish anything."""
from __future__ import annotations

from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import venv
import zipfile

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def run(args, *, cwd=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True)


def check():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    wheels = list((ROOT / "dist").glob("*.whl"))
    sdists = list((ROOT / "dist").glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1 or len(list((ROOT / "dist").iterdir())) != 2:
        raise RuntimeError("dist must contain exactly one wheel and one sdist")
    wheel, sdist = wheels[0], sdists[0]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_files = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_files) != 1:
            raise RuntimeError("wheel has ambiguous metadata")
        metadata = BytesParser().parsebytes(archive.read(metadata_files[0]))
        if metadata["Name"] != project["name"] or metadata["Version"] != project["version"]:
            raise RuntimeError("distribution identity mismatch")
        if metadata["License-Expression"] != "MPL-2.0":
            raise RuntimeError("license metadata missing")
        for requirement in metadata.get_all("Requires-Dist", []):
            if Requirement(requirement).url:
                raise RuntimeError("PyPI-incompatible direct-URL dependency")
        for suffix in ("/licenses/LICENSE", "/licenses/NOTICE.md", "tbrt/examples.json", "tbrt/__main__.py", "tbrt/clock.py", "tbrt/exchange.py"):
            if not any(name.endswith(suffix) for name in names):
                raise RuntimeError(f"missing wheel member: {suffix}")
        if archive.read("tbrt/clock.py") != (ROOT / "src/tbrt/clock.py").read_bytes():
            raise RuntimeError("wheel numerical core differs from checkout")
    with tarfile.open(sdist, "r:gz") as archive:
        names = archive.getnames()
        for suffix in (
            "/LICENSE", "/NOTICE.md", "/CITATION.cff", "/instrument.json",
            "/requirements-exchange.txt", "/examples/clocksync.json",
            "/tests/test_clock.py", "/tests/test_instrument_surface.py",
            "/src/tbrt/examples.json", "/portfolio/problem.md",
            "/portfolio/model.md", "/portfolio/verification.md",
            "/notebooks/clocksync_demo.ipynb", "/benchmarks/benchmark.py",
            "/scripts/build_instrument_surface.py",
        ):
            if not any(name.endswith(suffix) for name in names):
                raise RuntimeError(f"missing sdist member: {suffix}")
    smoke = '''
import json, math
from importlib.metadata import version
from pathlib import Path
import tbrt
from tbrt.cli import EXAMPLES, example_payload, reconcile_payload
assert version("notations-clocksync") == EXPECTED_VERSION
assert "site-packages" in str(Path(tbrt.__file__))
for name in EXAMPLES:
    result = reconcile_payload(example_payload(name))
    assert math.isfinite(result["event_time"])
assert reconcile_payload(example_payload("offset"))["event_time"] == 203.25
print("installed distribution smoke passed:", tbrt.__file__)
'''.replace("EXPECTED_VERSION", repr(project["version"]))
    with tempfile.TemporaryDirectory(prefix="clocksync-release-") as temporary:
        directory = Path(temporary)
        environment = directory / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        command = scripts / ("clocksync.exe" if os.name == "nt" else "clocksync")
        run([python, "-m", "pip", "install", wheel], cwd=directory)
        for distribution in (wheel, sdist):
            if distribution == sdist:
                run([python, "-m", "pip", "install", "--force-reinstall", "--no-deps", sdist], cwd=directory)
            run([python, "-I", "-c", smoke], cwd=directory)
            run([command, "--version"], cwd=directory)
            request = subprocess.check_output([str(command), "--example", "correlated"], cwd=directory, text=True)
            result = subprocess.run([str(command), "-", "--compact"], cwd=directory, input=request, text=True, capture_output=True, check=True)
            assert json.loads(result.stdout)["operation_id"] == "tbrt.affine-clock-reconcile.v1"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    evidence = {
        "kind": "clocksync.distribution-check.v1", "source_commit": revision,
        "version": project["version"], "python": sys.version,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "claims": ["wheel metadata checked", "license and examples included", "wheel installed outside checkout", "sdist rebuilt and installed outside checkout", "CLI round-trip checked"],
        "not_claimed": ["independent numerical verification", "metrological traceability", "PyPI publication"],
        "artifacts": [{"filename": item.name, "sha256": hashlib.sha256(item.read_bytes()).hexdigest(), "bytes": item.stat().st_size} for item in (wheel, sdist)],
    }
    (ROOT / "release-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    check()
