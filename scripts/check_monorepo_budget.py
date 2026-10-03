"""Qualify YWIR as an independent wheel and one pinned advisory provider.

The caller owns the isolated environment and exact source worktrees. This
component exercises the unchanged provider suite and examples, then checks the
existing fixed NET dispatch for one YWIR adapter. It does not qualify the
eleven-provider identified-design workflow or authorize external work.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import tomllib
import zipfile

if __package__:
    from .check_monorepo import _copy_source, _git, _IMPORT_PROBE, _junit, _run, _wheel
else:
    from check_monorepo import _copy_source, _git, _IMPORT_PROBE, _junit, _run, _wheel


SCOPE = (
    "Synthetic YWIR token-budget qualification, installed original provider "
    "tests/examples and exact-pin advisory replay only. No EDSPT selection "
    "recomputation, full eleven-provider workflow, durable or distributed "
    "budget recovery, provider billing, machine authority, independent "
    "verification, physical validation or canonical state admission."
)


_REPLAY = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from ywir import YwirRefuse, replay_token_admission
payload = json.loads(sys.stdin.buffer.read())
try:
    result = replay_token_admission(payload['request'], payload['retained'])
except YwirRefuse as error:
    output = {'status': 'refused', 'code': error.code}
else:
    output = {'status': 'ok', 'data': result}
print(json.dumps(output, allow_nan=False, sort_keys=True))
'''


_SMOKE = "REPLAY_CODE = " + repr(_REPLAY) + "\n" + r'''
from copy import deepcopy
from hashlib import sha256
from importlib import resources
import json, pathlib, sys, uuid
import ciw
from ciw.adapters.protocol import AdapterRefusal
from ciw.adapters.subprocess import PinnedSubprocessAdapter, _json
from ciw.identified_design import _invoke
from ciw.identified_semantics import _ywir
from ciw.telemetry import canonical, digest
from ywir import Proposal, Settlement, YwirRefuse, open_host, settle, snapshot

configuration = json.loads(pathlib.Path(sys.argv[1]).read_text())
if not pathlib.Path(ciw.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):
    raise AssertionError('NET smoke must use its installed isolated wheel')
pin = json.loads(resources.files('ciw').joinpath('identified-design-runtimes.json').read_text())['ywir']
adapter = PinnedSubprocessAdapter(configuration['runtime_source'], pin['revision'],
    pin['module'], source_root=pin['source_root'])
runtime = adapter.runtime_identity()
payload = {
    'schema': 'ywir.observation-design-token-request.v1',
    'selection_content_id': 'fixture:selection:' + 'a' * 64,
    'selected_candidate_id': 'synthetic:pressure',
    'budget_unit': 'inference_token', 'department': 'exploration',
    'token_budget': 100, 'requested_tokens': 16,
    'yield_claim': {'expected_rank_delta': 0, 'expected_new_morphism': False},
    'eta_hat': 0.0, 'similarity_to_store': 0.0,
}
before = deepcopy(payload)
evidence_id = 'evidence:sha256:' + sha256(canonical(payload)).hexdigest()
operation_id = 'ywir.observation-design-token-admission.v1'
pathlib.Path(configuration['request']).write_bytes(canonical(payload))

def evaluate(request):
    envelope = {'schema': 'ciw.adapter-request.v1', 'operation_id': operation_id,
                'inputs': request}
    result = _invoke('ywir', {'ywir': adapter}, envelope)
    _ywir(result, request, request['selected_candidate_id'], request['selection_content_id'])
    assert result['authority_scope'] == 'advisory_only'
    assert not {'host_id', 'decision_id', 'reservation_id', 'settlement_id',
                'execution_id', 'verification_id'} & result.keys()
    return result

def replay(request, retained):
    adapter.runtime_identity()
    code, output = adapter._run(REPLAY_CODE, [str(adapter.source_root)],
                               canonical({'request': request, 'retained': retained}))
    assert code == 0, 'Fixed pinned advisory replay did not complete'
    adapter.runtime_identity()
    response = _json(output)
    assert type(response) is dict
    if response.get('status') == 'ok':
        assert set(response) == {'status', 'data'}
    else:
        assert set(response) == {'status', 'code'} and response['status'] == 'refused'
    return response

runs = []
for mode in ('evaluate', 'replay'):
    execution_id = 'execution:' + uuid.uuid4().hex
    if mode == 'evaluate':
        result = evaluate(payload)
    else:
        response = replay(payload, runs[0]['data'])
        assert response['status'] == 'ok'
        result = response['data']
        _ywir(result, payload, payload['selected_candidate_id'], payload['selection_content_id'])
    assert result['admitted'] is True and result['advisory_token_cap'] == 16
    artifact = {'schema': 'notations.monorepo-budget-smoke-result.v1',
        'operation_id': operation_id, 'execution_ref': execution_id,
        'input_refs': [evidence_id], 'data': result}
    runs.append({'mode': mode, 'execution_id': execution_id,
        'verification_id': 'verification:' + uuid.uuid4().hex,
        'result_id': 'result:' + digest(artifact), 'data': result})
assert payload == before
assert runs[0]['data'] == runs[1]['data']
occurrences = [run[key] for run in runs for key in ('execution_id', 'verification_id', 'result_id')]
content_ids = [runs[0]['data'][key] for key in
               ('request_content_id', 'proposal_content_id', 'result_content_id')]
identities = [evidence_id, operation_id, *occurrences, *content_ids]
assert len(identities) == len(set(identities))

refusals = {}
for name, changes, support in (
    ('closed_budget', {'token_budget': 0}, 'BUDGET_CLOSED'),
    ('insufficient_budget', {'token_budget': 15}, 'DEPARTMENT_STARVED'),
    ('gauge_spend', {'department': 'gauge'}, 'GAUGE_SPILL'),
):
    request = deepcopy(payload)
    request.update(changes)
    result = evaluate(request)
    assert result['admitted'] is False and result['advisory_token_cap'] == 0
    assert result['support_code'] == support
    assert replay(request, result) == {'status': 'ok', 'data': result}
    refusals[name] = {'expected': support, 'actual': result['support_code']}

for name, mutate in (
    ('measurement_cost_as_token_budget', lambda request: request.update(budget_unit='USD')),
    ('missing_selection', lambda request: request.pop('selection_content_id')),
):
    request = deepcopy(payload)
    mutate(request)
    try:
        evaluate(request)
    except AdapterRefusal as error:
        assert error.code == 'DESIGN_YWIR_REFUSED'
        refusals[name] = {'expected': error.code, 'actual': error.code}
    else:
        raise AssertionError('Invalid advisory input accepted: ' + name)

forged = deepcopy(runs[0]['data'])
forged['advisory_token_cap'] = 17
forged.pop('result_content_id')
forged['result_content_id'] = 'ywir:token-admission:' + sha256(
    b'ywir:token-admission\0' + canonical(forged)).hexdigest()
assert replay(payload, forged) == {'status': 'refused', 'code': 'replay_mismatch'}
refusals['rehashed_advisory_tamper'] = {'expected': 'replay_mismatch', 'actual': 'replay_mismatch'}

host = open_host('isolated-monorepo-budget-check', {'exploration': 100})
unchanged = snapshot(host)
try:
    settle(host, Proposal(host.loop, 'exploration', 16), Settlement(16, 0, True),
           reservation=runs[0]['data'])
except YwirRefuse as error:
    assert error.code == 'reservation_required'
    assert snapshot(host) == unchanged
    refusals['advice_is_not_spend_authority'] = {'expected': error.code, 'actual': error.code}
else:
    raise AssertionError('Advisory result incorrectly conferred spending authority')

try:
    PinnedSubprocessAdapter(configuration['dirty_source'], pin['revision'],
        pin['module'], source_root=pin['source_root'])
except AdapterRefusal as error:
    assert error.code == 'SOURCE_PIN_MISMATCH'
    refusals['dirty_pinned_source'] = {'expected': error.code, 'actual': error.code}
else:
    raise AssertionError('Changed temporary YWIR source was accepted')

assert runtime == adapter.runtime_identity()
assert pathlib.Path(configuration['request']).read_bytes() == canonical(payload)
report = {'schema': 'notations.monorepo-budget-adapter-check.v1',
    'claim_scope': configuration['claim_scope'], 'runtime': runtime,
    'evidence_id': evidence_id, 'request_sha256': sha256(canonical(payload)).hexdigest(),
    'selection_fixture_not_recomputed': True, 'independent_verification': False,
    'canonicalAdmission': False, 'admission': 'not_performed',
    'full_eleven_provider_workflow_qualified': False, 'external_provider_work_executed': False,
    'machine_authority': False, 'runs': runs, 'advisory_replay_equal': True,
    'fresh_execution_and_verification_ids': True, 'identity_separation': True,
    'refusals': refusals}
pathlib.Path(configuration['report']).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps({'budget_adapter': 'passed', 'runs': len(runs), 'refusals': sorted(refusals)}))
'''


def qualify_budget(python, source, runtime_source, work, output, log) -> dict:
    """Return retained qualification records for operator-supplied YWIR sources.

    ``python`` must be an isolated environment with CIW, pytest and hatchling
    installed. ``source`` is the preserved import checkout, ``runtime_source``
    is its original NET-pinned checkout, and ``work`` is outside both sources.
    The caller remains responsible for its complete import-manifest audit.
    """
    python = Path(python).expanduser().absolute()
    source, runtime_source = (Path(path).expanduser().resolve()
                              for path in (source, runtime_source))
    work, output, log = (Path(path).expanduser().resolve() for path in (work, output, log))
    for destination in (work, output, log):
        if any(destination.is_relative_to(root) for root in (source, runtime_source)):
            raise ValueError("Budget gate outputs and work must remain outside original provider sources")
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    build = work / "ywir-build-source"
    _copy_source(source, build)
    project = tomllib.loads((build / "pyproject.toml").read_text())["project"]
    if (project["name"], project["version"], project.get("license")) != (
            "yield-weighted-inference-runtime", "0.2.0", "MIT"):
        raise ValueError("Budget module must preserve its original package version and MIT license")
    wheel = _wheel(python, build, work / "wheel-ywir", log)
    license_bytes = (source / "LICENSE").read_bytes()
    with zipfile.ZipFile(wheel["path"]) as archive:
        license_path, = [name for name in archive.namelist()
                         if name.endswith(".dist-info/licenses/LICENSE")]
        if archive.read(license_path) != license_bytes:
            raise AssertionError("Independent YWIR wheel did not preserve its original license")
    wheel["license_sha256"] = sha256(license_bytes).hexdigest()
    _run([python, "-I", "-m", "pip", "install", "--force-reinstall", "--no-deps", wheel["path"]],
         cwd=work, log=log)
    installed = json.loads(_run([python, "-I", "-c", _IMPORT_PROBE,
        json.dumps({"ywir": {key: wheel[key] for key in ("distribution", "version")}})],
        cwd=work, log=log))

    suite = work / "ywir-provider-suite"
    suite.mkdir()
    for directory in ("tests", "examples", "validation"):
        shutil.copytree(source / directory, suite / directory)
    configuration = work / "ywir-pytest.ini"
    configuration.write_text("[pytest]\n")
    junit = output / "ywir-tests.xml"
    _run([python, "-I", "-m", "pytest", "-q", "-c", configuration,
          "--import-mode=importlib", "--junitxml", junit, suite / "tests"],
         cwd=suite, log=log)
    tests = {**_junit(junit), "revision": _git(source, "rev-parse", "HEAD"),
             "source_tree": _git(source, "rev-parse", "HEAD^{tree}")}
    examples = {}
    for name in ("quickstart", "mill_token_gate"):
        example = suite / "examples" / (name + ".py")
        stdout = _run([python, "-I", example], cwd=suite, log=log)
        result = suite / "results" / (name + ".md")
        if result.read_text() != stdout.replace("\r\n", "\n"):
            raise AssertionError("Original YWIR example output differs from its written report")
        retained = output / ("ywir-" + name + ".md")
        shutil.copyfile(result, retained)
        examples[name + ".py"] = {"source_sha256": sha256(example.read_bytes()).hexdigest(),
            "output_sha256": sha256(retained.read_bytes()).hexdigest(), "output": str(retained)}

    pin = json.loads((Path(__file__).resolve().parents[1] /
                      "src/ciw/identified-design-runtimes.json").read_text())["ywir"]
    if _git(runtime_source, "rev-parse", "HEAD") != pin["revision"]:
        raise ValueError("Budget smoke requires the unchanged existing NET YWIR runtime pin")
    dirty = work / "dirty-ywir"
    _run(["git", "-c", "core.autocrlf=false", "clone", "--shared", "--no-checkout",
          runtime_source, dirty], cwd=work, log=log)
    _run(["git", "-C", dirty, "-c", "core.autocrlf=false", "checkout", "--detach", pin["revision"]],
         cwd=work, log=log)
    with (dirty / "src/ywir/__init__.py").open("a") as stream:
        stream.write("\n# Deliberate gate mutation of an isolated source copy.\n")
    smoke_path = output / "ywir-adapter-smoke.json"
    smoke_configuration = work / "ywir-smoke-configuration.json"
    smoke_configuration.write_text(json.dumps({"runtime_source": str(runtime_source),
        "dirty_source": str(dirty), "claim_scope": SCOPE,
        "request": str(output / "ywir-advisory-request.json"), "report": str(smoke_path)}))
    _run([python, "-I", "-c", _SMOKE, smoke_configuration], cwd=work, log=log)
    return {"claim_scope": SCOPE,
        "wheel": {key: value for key, value in wheel.items() if key != "path"},
        "installed_package": installed, "provider_tests": tests,
        "provider_examples": examples, "adapter_smoke": json.loads(smoke_path.read_text())}
