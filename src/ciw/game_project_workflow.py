"""Batch title work orders and agent-readable feedback; no model API or shell grants."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import uuid

from .control_contracts import bytes_ref, detached, keys, load, save_new, text
from .control_plane import experiment
from . import game_project as project
from . import game_trace
from .production import Worker, inspect_production, plan, run_production, validate_plan


def declare(profile: dict, orders: list[dict]) -> tuple[dict, dict]:
    """Compile bounded agent-authored assignments into the ORIGINAL production plan."""
    space = project.validate_profile(profile)
    if type(orders) is not list or not 1 <= len(orders) <= 64:
        raise ValueError('Require 1..64 work orders')
    source = project.make_run(profile)
    jobs = []
    for order in orders:
        keys(order, {'job_id', 'attempts', 'depends_on'})
        text(order['job_id'])
        if type(order['attempts']) is not list or not 1 <= len(order['attempts']) <= 3:
            raise ValueError('Require 1..3 bounded parameter variants')
        graphs = []
        for index, assignment in enumerate(order['attempts']):
            assignment = space.validate(assignment)
            graphs.append(experiment(order['job_id'] + '-' + str(index), model_id=profile['scenario']['model_id'], nodes=[{
                'node_id': 'capture', 'operation_id': project.CAPTURE_OP,
                'parameters': {'assignment': assignment, 'nonce': uuid.uuid4().hex, 'diagnostic_fault': 'none'},
                'inputs': {}, 'depends_on': []}]))
        jobs.append({'job_id': order['job_id'], 'worker_id': 'game-project', 'requires': ['game.project.capture'],
            'attempts': graphs, 'depends_on': deepcopy(order['depends_on']),
            'checks': [{'check_id': 'fixed-game-rules', 'node_id': 'capture', 'gate_id': 'game.project-authored.v1', 'policy': {}}]})
    return source, plan(profile['project_id'] + '-production', project_id=profile['project_id'],
                        source_evidence_id=source['evidence_id'], jobs=jobs)


def grid_orders(profile: dict) -> list[dict]:
    # Existing finite grid generator; no second parameter search or optimizer.
    space = project.validate_profile(profile)
    assignments = space.grid({}, max_cases=64)
    return [{'job_id': 'case-%03d' % i, 'attempts': [row], 'depends_on': []} for i, row in enumerate(assignments)]


def execute(profile: dict, source: dict, specification: dict, binding, output: Path, *, max_operations: int = 128) -> dict:
    project.validate_profile(profile)
    validate_plan(specification)
    if specification['project_id'] != profile['project_id']:
        raise ValueError('Work order project identity differs from the operator profile')
    if source['metadata'].get('game_project') != profile or source['evidence_id'] != project.make_run(profile)['evidence_id']:
        raise ValueError('Declared source differs from the operator-pinned profile')
    # Inspect EVERY candidate before any process or destination creation; the
    # generic controller preflights graph contracts, not domain parameter values.
    for job in specification['jobs']:
        for graph in job['attempts']:
            if graph['model_id'] != profile['scenario']['model_id'] or graph['parameters'] or graph['parent_checkpoint'] is not None:
                raise ValueError('Project work orders cannot change model/global parameters/checkpoint policy')
            for node in graph['nodes']:
                if node['operation_id'] != project.CAPTURE_OP or node['inputs']:
                    raise ValueError('Project work order requires explicitly bound capture operations')
                project.candidate_scenario(profile, node['parameters'])
    return run_production(source, specification, project.registry_for(binding),
        (Worker('game-project', (project.CAPTURE_OP,)),), project.project_gates(), output, max_operations=max_operations)


@contextmanager
def frozen_campaign(root: Path):
    """Freeze bounded exact bytes once so feedback cannot substitute unchecked reads."""
    from .session import loads_json
    root = Path(root)
    if root.is_symlink() or (root / 'session').is_symlink():
        raise ValueError('Campaign directories cannot be symlinks')
    def read(name):
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Require a regular retained campaign file')
        with path.open('rb') as handle:
            raw = handle.read(8 * 1024 * 1024 + 1)
        if not raw or len(raw) > 8 * 1024 * 1024:
            raise ValueError('Retained file exceeds 8 MiB')
        return raw
    raw_report = read('production.json')
    report = loads_json(raw_report.decode('utf-8'))
    count = report.get('attempt_count')
    if type(count) is not int or not 1 <= count <= 192:
        raise ValueError('Invalid bounded attempt count')
    names = ['plan.json', 'bindings.json', 'session/workspace.json']
    for i in range(1, count + 1):
        names += ['attempt-%04d%s.json' % (i, suffix) for suffix in ('', '-graph', '-checks')]
    with tempfile.TemporaryDirectory(prefix='net-project-feedback-') as directory:
        dest = Path(directory)
        (dest / 'production.json').write_bytes(raw_report)
        total = len(raw_report)
        for name in names:
            raw = read(name)
            total += len(raw)
            if total > 64 * 1024 * 1024:
                raise ValueError('Campaign inspection exceeds 64 MiB')
            path = dest / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        yield dest


def feedback(root: Path) -> dict:
    """Validated, machine-readable diagnostics to return to a coding/MCP host."""
    with frozen_campaign(root) as frozen:
        inspected = inspect_production(frozen, project.project_gates())
        report = load(frozen / 'production.json')
        jobs, counts = {}, {s: 0 for s in ('accepted', 'rejected', 'held', 'refused', 'blocked')}
        for name, row in report['jobs'].items():
            counts[row['status']] += 1
            attempts = []
            for ref in row['attempts']:
                receipt = load(frozen / ref['name'])
                graph = load(frozen / receipt['graph']['name'])
                checks = load(frozen / receipt['acceptance']['name'])
                # General graph form is retained, with no assumption about last Session result.
                candidates = []
                for node_id in graph['order']:
                    outcome = graph['nodes'][node_id]
                    result = outcome.get('result')
                    if result is not None:
                        _, captured = game_trace.unpack(result['data'])
                        rejected_actions = [event for event in captured['events'] if event['payload'].get('admitted') is False]
                    else:
                        rejected_actions = []
                    candidates.append({'node_id': node_id, 'status': outcome['status'],
                        'execution_id': outcome.get('execution', {}).get('execution_id'),
                        'result_id': None if result is None else result['result_id'],
                        'assignment': next(n['parameters']['assignment'] for n in graph['experiment']['nodes'] if n['node_id'] == node_id),
                        'rejected_actions': rejected_actions})
                failed = []
                for check in checks['checks']:
                    detail = check['detail']
                    if type(detail) is dict:
                        failed += [{'id': x['id'], 'status': x['status'], 'reason': x['reason']}
                                   for x in detail.get('checks', []) if x['status'] != 'PASS']
                attempts.append({'attempt_index': receipt['attempt_index'], 'status': receipt['status'],
                                 'checks_status': checks['status'], 'failed_rules': failed, 'candidates': candidates})
            jobs[name] = {'status': row['status'], 'blocked_by': row['blocked_by'], 'attempts': attempts}
        return detached({'schema': 'ciw.game-production-feedback.v1', 'fresh_execution': False,
            'campaign_digest': bytes_ref((frozen / 'production.json').read_bytes()), 'status': inspected['status'],
            'counts': counts, 'jobs': jobs, 'execution_count': inspected['execution_count'],
            'scope': 'authored-rule diagnostics; no source rewrite, release approval or historical/visual qualification'})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='net production project', description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('declare', 'grid', 'run'):
        command = commands.add_parser(name)
        command.add_argument('--profile', type=Path, required=True)
        command.add_argument('--profile-sha256', required=True)
        command.add_argument('--output-dir', type=Path, required=True)
        if name == 'declare':
            command.add_argument('--orders', type=Path, required=True)
        if name == 'run':
            command.add_argument('--plan', type=Path, required=True)
            command.add_argument('--source', type=Path, required=True)
            command.add_argument('--source-root', type=Path, required=True)
            command.add_argument('--godot', type=Path, required=True)
            command.add_argument('--godot-sha256', required=True)
            command.add_argument('--max-operations', type=int, default=128)
    read = commands.add_parser('feedback')
    read.add_argument('campaign', type=Path)
    read.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'feedback':
            result = feedback(args.campaign)
            if args.output is not None:
                save_new(args.output, result)
        else:
            profile = project.read_profile(args.profile, args.profile_sha256)
            if args.command in ('declare', 'grid'):
                orders = load(args.orders) if args.command == 'declare' else grid_orders(profile)
                source, specification = declare(profile, orders)
                args.output_dir.mkdir(parents=True, exist_ok=False)
                save_new(args.output_dir / 'source.json', source)
                save_new(args.output_dir / 'plan.json', specification)
                result = {'status': 'declared', 'job_count': len(orders), 'fresh_execution': False}
            else:
                source, specification = load(args.source), load(args.plan)
                binding = project.GodotProjectBinding(args.godot, args.source_root, profile, expected_sha256=args.godot_sha256)
                result = execute(profile, source, specification, binding, args.output_dir, max_operations=args.max_operations)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result['status'] == 'incomplete' else 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        print(json.dumps({'status': 'refused', 'reason': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
