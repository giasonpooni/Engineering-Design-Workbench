"""Measure external single-agent revisions without replacing workcell authority.

Agent identity/observed inputs are declarations, not provider attestations. This
module neither calls a model nor infers token costs, active human time or artistic
quality from technical PASS. Native execution remains in the original workcell.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import tempfile

from .agent_api import identifier
from .control_contracts import bytes_ref, content_ref, keys, load, number
from .core.identities import content_identity
from .foundry_packets import read_file, relative, root_dir
from .session import loads_json


def read_revision(path: Path, expected_sha256: str, *, agent_id: str, writable: tuple[str, ...]) -> tuple[dict, dict[str, str]]:
    """Freeze a declared external model response; never import or execute its text."""
    path = Path(path).absolute()
    root = root_dir(path.parent)
    raw = read_file(root, path.name)
    content_ref(expected_sha256)
    if len(raw) > 65536 or bytes_ref(raw) != expected_sha256:
        raise ValueError('Agent response differs from its explicit digest/budget')
    doc = loads_json(raw.decode('utf-8'))
    keys(doc, {'schema', 'revision_id', 'agent_id', 'mode', 'author_attestation',
               'decision_summary', 'observed_evidence', 'replacements', 'provider_usage',
               'human_active_seconds', 'external_review'})
    if doc['schema'] != 'ciw.agent-revision.v1' or doc['mode'] != 'interactive_llm_session':
        raise ValueError('Unsupported explicit agent mode')
    identifier(doc['revision_id']); identifier(doc['agent_id'])
    if doc['agent_id'] != agent_id or doc['author_attestation'] != 'current_assistant_session_self_reported_not_provider_signed':
        raise ValueError('Agent identity or attestation scope mismatch')
    # These fields are unknown for this session relay; do not let an agent invent bills/time.
    if any(doc[k] is not None for k in ('provider_usage', 'human_active_seconds')) or doc['external_review'] != 'not_performed':
        raise ValueError('Interactive relay cannot assert provider billing, human time or independent review')
    if type(doc['decision_summary']) is not str or not 1 <= len(doc['decision_summary']) <= 4096:
        raise ValueError('Require a bounded decision summary, not hidden reasoning or executable instructions')
    observations = doc['observed_evidence']
    if type(observations) is not list or not 1 <= len(observations) <= 8:
        raise ValueError('Require bounded prior-evidence references')
    for item in observations:
        keys(item, {'kind', 'label', 'sha256'})
        if item['kind'] not in {'native_preview', 'workcell_feedback'}:
            raise ValueError('Unsupported observed evidence kind')
        relative(item['label']); content_ref(item['sha256'])
    refs = doc['replacements']
    if type(refs) is not dict or not 1 <= len(refs) <= 2 or set(refs) - set(writable):
        raise ValueError('Candidate must name only operator-granted source paths')
    changes = {}
    for target, spec in refs.items():
        relative(target); keys(spec, {'file', 'sha256'}); content_ref(spec['sha256'])
        data = read_file(root, spec['file'])
        if len(data) > 65536 or bytes_ref(data) != spec['sha256']:
            raise ValueError('Candidate source differs from its frozen response')
        changes[target] = data.decode('utf-8')
    if sum(len(s.encode()) for s in changes.values()) > 131072:
        raise ValueError('Candidate exceeds total source budget')
    return doc, changes


def audit_attempt(path: Path) -> dict:
    """Recompute original gates from a private frozen snapshot, then extract metrics.

    The source workspace is never read again after validation. Timings are the
    original container-stage wall observations, not CPU/GPU time or model latency.
    """
    from .workcell import inspect_attempt
    source = root_dir(path)
    names = ['plan.json', 'bindings.json', 'production.json', 'session/workspace.json']
    for i in range(1, 4):
        for suffix in ('.json', '-graph.json', '-checks.json'):
            name = f'attempt-{i:04d}{suffix}'
            if (source/name).exists() or (source/name).is_symlink(): names.append(name)
    for name in ('smith.pck', 'daylight.png', 'evening.png'):
        if (source/name).exists() or (source/name).is_symlink(): names.append(name)
    total = 0
    with tempfile.TemporaryDirectory(prefix='net-agent-metrics-') as directory:
        frozen = Path(directory)
        for name in names:
            raw = read_file(source, name)
            total += len(raw)
            if total > 32*1024*1024: raise ValueError('Experiment input exceeds byte budget')
            target = frozen/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
        feedback = inspect_attempt(frozen)
        workspace = load(frozen/'session/workspace.json')
        results = workspace['results']; executions = workspace['executions']
        if len(results) != feedback['result_count'] or len(executions) != feedback['execution_count']:
            raise ValueError('Original workcell counts disagree')
        source_declaration = workspace['run']['metadata']['workcell']
        cid = source_declaration['candidate_id']
        stages = []
        for result in results:
            value = result['data']; observations = value['process']['observations']
            elapsed = number(value['elapsed_wall_s'])
            if elapsed < 0: raise ValueError('Negative measured duration')
            stages.append({'stage': value['stage'], 'execution_id': result['execution_id'],
                'result_id': result['result_id'], 'container_id': value['isolation']['container_id'],
                'image_id': value['isolation']['image_id'], 'wall_s': elapsed,
                'process_outcome': value['process']['outcome'],
                'inventory': None if observations is None else observations.get('inventory'),
                'captures': None if observations is None else observations.get('captures')})
        package_accepted = feedback['jobs'].get('package', {}).get('status') == 'accepted'
        return {'schema': 'ciw.agent-attempt-measurement.v1', 'candidate_id': cid,
            'production_id': feedback['production_id'], 'technical_status': feedback['status'],
            'package_accepted': package_accepted,
            'package_sha256': bytes_ref((frozen/'smith.pck').read_bytes()) if (frozen/'smith.pck').exists() else None,
            'execution_count': len(executions), 'capture_count': len(results),
            'captured_stage_wall_s': sum(s['wall_s'] for s in stages),
            'duration_coverage': 'complete' if len(results) == len(executions) else 'partial_refused_execution',
            'stages': stages, 'feedback': feedback,
            'validation': 'original_workcell_gates_recomputed_no_provider_execution',
            'artistic_acceptance': 'unreviewed', 'release_authorized': False}


def summarize(baseline: dict, revisions: list[dict]) -> dict:
    """Count unique changed candidates; repeated transport/builds cannot inflate yield."""
    unique = {}; ids = set(); container_ids = set(); timing = 0.0
    for row in [baseline, *revisions]:
        for stage in row['stages']:
            if stage['execution_id'] in ids or stage['container_id'] in container_ids:
                raise ValueError('An occurrence is duplicated across measurements')
            ids.add(stage['execution_id']); container_ids.add(stage['container_id'])
        timing += row['captured_stage_wall_s']
    for row in revisions:
        if row['candidate_id'] == baseline['candidate_id']: continue
        if row['candidate_id'] not in unique:
            unique[row['candidate_id']] = row
        elif row['package_accepted']:
            unique[row['candidate_id']] = row
    accepted = sum(r['package_accepted'] for r in unique.values())
    attempted = len(unique)
    return {'schema': 'ciw.single-agent-yield.v1', 'declared_agents': 1,
        'decision_mode': 'interactive_LLM_session_with_deterministic_MCP_relay',
        'baseline_technically_accepted': baseline['package_accepted'],
        'revision_execution_attempts': len(revisions), 'unique_changed_candidates': attempted,
        'unique_technically_accepted_revisions': accepted,
        'technical_acceptance_fraction': accepted/attempted if attempted else None,
        'workcell_execution_attempts': sum(r['execution_count'] for r in [baseline, *revisions]),
        'observed_native_containers': len(container_ids),
        'total_retained_stage_wall_s': timing,
        'duration_coverage': 'complete' if all(r['duration_coverage']=='complete' for r in [baseline,*revisions]) else 'partial',
        'model_tokens': None, 'model_cost_usd': None, 'model_generation_wall_s': None,
        'human_active_seconds': None, 'accepted_revisions_per_human_hour': None,
        'independently_art_accepted_revisions': None, 'merged_revisions': 0,
        'limitations': 'n=1 task; session author also designs relay; not a blinded independent-agent study, autonomous hosted model run or exponential-throughput estimate',
        'release_authorized': False}
