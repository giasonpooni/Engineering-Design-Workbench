"""One-time source repair on the exact reviewed baseline; not runtime code.

Unpack the verified historical source, restore the missing project registration,
and materialize ordinary readable Python. Refuse unknown source rather than
reconstructing or overwriting concurrent edits. This script is removed from the
published repair commit.
"""
from pathlib import Path
import ast
import base64
import hashlib
import re
import zlib

ROOT = Path(__file__).resolve().parents[1]
OLD_GROUP = "${{ github.workflow }}-${{ github.event_name }}-${{ github.event.pull_request.number || github.run_id }}"
NEW_GROUP = "${{ github.workflow }}-${{ github.event_name }}-${{ github.event.pull_request.number || (github.event_name == 'push' && github.ref) || github.run_id }}"
SECRET = "${{ ((github.event_name == 'push' && (github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/'))) || github.event_name == 'workflow_dispatch') && secrets.CIW_PROVIDER_READ_TOKEN || '' }}"
PRIVATE = {
    "acquired-stream.yml", "calibrated-observable.yml", "calibrated-window.yml",
    "ci.yml", "declared-workloads.yml", "exchange.yml", "free-energy.yml",
    "geodesic-references.yml", "geometry-research.yml", "identified-design.yml",
    "integrated-modules.yml", "proved-heat.yml", "remaining-modules.yml",
    "telemetry.yml", "workbench-candidates.yml",
}


def replace_once(text, old, new):
    assert text.count(old) == 1, ("Ambiguous repair anchor", old)
    return text.replace(old, new, 1)


def repair_workbench():
    package = ROOT / "src/ciw"
    packed = "".join((package / f"_wb_pack_{i}.txt").read_text(encoding="utf-8") for i in range(4))
    tree = ast.parse(packed)
    literals = [ast.literal_eval(node.args[0]) for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "b64decode"]
    assert len(literals) == 1
    raw = zlib.decompress(base64.b64decode(literals[0], validate=True))
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    assert blob == "d136f0a31be80a324db16ea591cfc3562f12f61d", "Unexpected decoded source; reconcile first"
    text = raw.decode("utf-8")
    changes = (
        ('"native-interop"})', '"native-interop", "project-graph"})'),
        ('"machine", "julia"})', '"machine", "julia", "project"})'),
        ('    "native-interop": "ciw.native-interop.v1",', '    "native-interop": "ciw.native-interop.v1",\n    "project-graph": "ciw.project-graph.v1",'),
        ('def _workflow(kind):', 'def _workflow(kind):\n    if kind == "project-graph":\n        from .project_workflow import ProjectGraphWorkflow\n        return ProjectGraphWorkflow()'),
        ('"machine-manifest": {}}', '"machine-manifest": {}, "project-graph": {}}'),
        ('"native-interop": "native_computation"}.get', '"native-interop": "native_computation", "project-graph": "project_graph_inspection"}.get'),
    )
    for old, new in changes:
        text = replace_once(text, old, new)
    ast.parse(text)
    (package / "workbench.py").write_text(text, encoding="utf-8", newline="\n")
    for i in range(4):
        (package / f"_wb_pack_{i}.txt").unlink()
    path = ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(', "_wb_pack_*.txt"', '').replace('"_wb_pack_*.txt", ', '')
    for i in range(4):
        text = text.replace(', "_wb_pack_' + str(i) + '.txt"', '')
    assert "_wb_pack" not in text
    path.write_text(text, encoding="utf-8", newline="\n")


def wire_job(job):
    lines = job.splitlines(True)
    env = next((i for i, line in enumerate(lines) if line == '    env:\n'), None)
    if env is None:
        lines[1:1] = ['    env:\n', '      CIW_PROVIDER_READ_TOKEN: ' + SECRET + '\n']
    else:
        lines.insert(env + 1, '      CIW_PROVIDER_READ_TOKEN: ' + SECRET + '\n')
    job = ''.join(lines)
    # Do not leave the primary repository token in local Git config.
    job = re.sub(r'(      - uses: actions/checkout@[^\n]+\n)(?=      -)', r'\1        with:\n          persist-credentials: false\n', job, count=1)
    match = re.search(r'      - uses: actions/setup-python@[^\n]+\n', job)
    assert match, "Private provider job has no Python setup"
    next_step = job.find('      - ', match.end())
    assert next_step != -1
    configure = ('      - name: Configure read-only private-provider access\n'
                 '        run: python scripts/ci_provider_access.py configure\n')
    job = job[:next_step] + configure + job[next_step:]
    # Explicit secondary checkouts must not use the single-repository default.
    job = re.sub(r'(          repository: giasonpooni/[^\n]+\n)',
                 r'\1          token: ${{ env.CIW_PROVIDER_READ_TOKEN }}\n', job)
    return job


def repair_workflows():
    for path in sorted((ROOT / '.github/workflows').glob('*.yml')):
        if path.name == 'ci-repair-build.yml':
            continue
        text = path.read_text(encoding='utf-8').replace(OLD_GROUP, NEW_GROUP)
        text = text.replace('    strategy:\n      matrix:', '    strategy:\n      fail-fast: false\n      matrix:')
        if path.name in PRIVATE or path.name == 'test.yml':
            sections = re.split(r'(?=^  [A-Za-z0-9_-]+:\s*$)', text, flags=re.MULTILINE)
            for i, section in enumerate(sections):
                name = section.split(':', 1)[0].strip()
                if '    steps:\n' in section and (path.name in PRIVATE or name == 'plsr-terminal'):
                    sections[i] = wire_job(section)
            text = ''.join(sections)
        path.write_text(text, encoding='utf-8', newline='\n')
    path = ROOT / 'scripts/check_ci_policy.py'
    text = path.read_text(encoding='utf-8').replace(OLD_GROUP, NEW_GROUP)
    text = text.replace('cancel only superseded PR runs', 'cancel superseded branch/PR runs while isolating manual dispatches')
    path.write_text(text, encoding='utf-8', newline='\n')


if __name__ == '__main__':
    repair_workbench()
    repair_workflows()
