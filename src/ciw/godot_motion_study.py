"""Native Godot workload over existing Session/lifecycle/checkpoint/replay tools."""
from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys
import tempfile

from .control_checks import compare
from .control_contracts import bytes_ref, load, save_new, keys, MAX_BYTES
from .operations.runner import seal, check_seal
from .simulation_control import SimulationControl, completed, open_workspace
from .simulation_records import observer, projected_samples, require
from .simulation_replay import replay, validate_replay
from .telemetry import canonical

SCHEMA = "ciw.godot-motion-study.v1"


def _derived(session, ids, replay_report):
    require(type(ids) is dict and set(ids) == {"checkpoint", "player", "debugger", "narrator", "alternative"},
            "Study must bind its exact retained results")
    records = {k: session.results[v] for k, v in ids.items()}
    parent = records['debugger']['data']['after']
    candidate = records['alternative']['data']['after']
    comparison = compare(projected_samples(records['alternative'], quantity='position'),
                         projected_samples(records['debugger'], quantity='position'), atol=0.0, rtol=0.0)
    def latest(name):
        samples = records[name]['data']['observations']['samples']
        return max(o['clock']['time_s'] for o in samples) if samples else None
    validate_replay(replay_report)
    require(replay_report['checkpoint'] == records['checkpoint'], 'Replay checkpoint/source differs')
    # Every embedded occurrence must also exist in the actual Session ledger.
    for record in [replay_report['checkpoint'], replay_report['restored'], *replay_report['source'], *replay_report['replayed']]:
        require(session.results.get(record['result_id']) == record, 'Replay references another investigation')
    baseline = records['checkpoint']['data']['after']
    require(parent['instance_id'] == baseline['instance_id'] and candidate['instance_id'] != baseline['instance_id'],
            'Counterfactual instance binding differs')
    require(candidate['parent'] == {'instance_id': baseline['instance_id'],
            'checkpoint_ref': records['checkpoint']['data']['checkpoint']['record_digest']}, 'Counterfactual parent differs')
    return {'world_time_s': parent['provider']['clock']['time_s'], 'player_latest_sample_s': latest('player'),
            'narrator_latest_sample_s': latest('narrator'), 'debugger_latest_sample_s': latest('debugger'),
            'replay': replay_report['outcome'], 'branch_comparison': comparison['outcome']}, comparison


def demo(executable: Path, expected_sha256: str, output_dir: Path):
    from .godot_motion import GodotMotion, PROVIDER_ID
    from .instruments import make_demo_run
    from .session import Session
    require(not Path(output_dir).exists(), 'Choose a new study directory')
    # Establish the trusted executable before creating the requested output.
    parent = GodotMotion(executable, expected_sha256)
    providers = [parent]
    try:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=False)
        session = Session(make_demo_run(), output_dir)
        control = SimulationControl(session)
        original = control.attach(parent, provider_id=PROVIDER_ID, experiment_id='godot-motion-baseline')
        call = lambda action, **args: completed(original.command(action, **args))
        replay_report = None
        try:
            call('start')
            call('step', dt=1);call('step', dt=1)
            call('intervene', actor_id='operator', operation='motion.queue-impulse.v1', target='body-1',
                 parameters={'at_tick': 4, 'delta_v': 3})
            call('pause');checkpoint = call('checkpoint')
            suffix = [call('resume')]
            suffix += [call('step', dt=1) for _ in range(4)]
            observed = {}
            for kind, name, channels in [('embodied_agent','player',['position']),
                ('debugger','debugger',['position','velocity']), ('retrospective_narrator','narrator',['position'])]:
                result = call('observe', observer=observer(name, kind=kind, channels=channels))
                observed[name] = result
                suffix.append(result)
            suffix.append(call('pause'))
            before = original.inspect()
            before_snapshot = parent.snapshot()
            alternative_provider = GodotMotion(executable, expected_sha256)
            providers.append(alternative_provider)
            alternative, restored = control.branch(checkpoint, alternative_provider, experiment_id='godot-motion-alternate')
            completed(restored)
            completed(alternative.command('intervene', actor_id='operator', operation='motion.queue-impulse.v1',
                target='body-1', parameters={'at_tick': 3, 'delta_v': 2}))
            completed(alternative.command('resume'))
            for _ in range(4):completed(alternative.command('step', dt=1))
            alternative_result = completed(alternative.command('observe',
                observer=observer('debugger', kind='debugger', channels=['position','velocity'])))
            completed(alternative.command('pause'))
            reproduced_provider = GodotMotion(executable, expected_sha256)
            providers.append(reproduced_provider)
            reproduction, replay_report = replay(control, checkpoint, suffix, reproduced_provider,
                experiment_id='godot-motion-reproduction')
            require(original.inspect() == before and parent.snapshot() == before_snapshot, 'Branch mutated parent')
            ids = {**{key: value['result_id'] for key,value in observed.items()},
                   'checkpoint': checkpoint['result_id'], 'alternative': alternative_result['result_id']}
            derived, comparison = _derived(session, ids, replay_report)
            require(derived['replay']['status'] == 'PASS', 'Native replay diverged; retained data is required')
            require(derived['branch_comparison']['status'] == 'FAIL', 'Counterfactual unexpectedly matched')
            save_new(output_dir/'replay.json', replay_report)
            save_new(output_dir/'branch-comparison.json', comparison)
            for instance in [original, alternative, reproduction]:
                completed(instance.command('stop'))
        finally:
            session.save_workspace(output_dir/'workspace.json')
            for provider in reversed(providers):provider.close()
            save_new(output_dir/'engine-processes.json', {'processes': [p.diagnostics() for p in providers],
                'scope': 'process diagnostics, not scientific evidence or complete system attestation'})
        raw = (output_dir/'workspace.json').read_bytes()
        report = seal({'schema': SCHEMA, 'workspace_sha256': bytes_ref(raw), 'result_ids': ids,
            'derived': derived, 'native_engine': True, 'model_semantics': 'synthetic',
            'verification_status': 'not_verified', 'state_admission': 'not_performed'})
        # Read back through the original reader before publishing completion.
        _inspect(output_dir, report)
        save_new(output_dir/'study.json', report)
        return report
    finally:
        for provider in reversed(providers):provider.close()


def _inspect(directory, report):
    keys(report, {'schema','workspace_sha256','result_ids','derived','native_engine','model_semantics',
                  'verification_status','state_admission','record_digest'})
    check_seal(report)
    require(report['schema'] == SCHEMA and report['native_engine'] is True and report['model_semantics']=='synthetic'
        and report['verification_status']=='not_verified' and report['state_admission']=='not_performed', 'Study authority differs')
    directory = Path(directory)
    # Freeze exact bytes once, then hash and reopen that same snapshot in scratch.
    path = directory/'workspace.json'
    require(path.is_file() and not path.is_symlink(), 'Select a regular workspace file')
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES+1)
    require(len(raw)<=MAX_BYTES, 'Workspace exceeds byte budget')
    require(bytes_ref(raw)==report['workspace_sha256'], 'Workspace bytes differ')
    with tempfile.TemporaryDirectory(prefix='net-godot-study-inspect-') as temp:
        snapshot = Path(temp)/'workspace.json'
        snapshot.write_bytes(raw)
        session = open_workspace(snapshot, output_dir=Path(temp)/'reader')
        replay_report = load(directory/'replay.json')
        derived, comparison = _derived(session, report['result_ids'], replay_report)
        require(canonical(derived) == canonical(report['derived']), 'Summary contradicts retained records')
        require(canonical(load(directory/'branch-comparison.json')) == canonical(comparison), 'Comparison differs')
        return {'status': 'retained_godot_study_checked', 'derived': derived,
                'execution_count': len(session.executions), 'result_count': len(session.results),
                'provider_execution': 'not_performed', 'verification_status': 'not_verified'}


def inspect(directory):
    return _inspect(directory, load(Path(directory)/'study.json'))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_subparsers(dest='action',required=True)
    command=actions.add_parser('demo')
    command.add_argument('--godot',type=Path,required=True)
    command.add_argument('--godot-sha256',required=True)
    command.add_argument('--output-dir',type=Path,required=True)
    command=actions.add_parser('inspect');command.add_argument('directory',type=Path)
    args=parser.parse_args(argv)
    try:
        result=inspect(args.directory) if args.action=='inspect' else demo(args.godot,args.godot_sha256,args.output_dir)
        print(canonical(result).decode())
        return 0
    except (OSError,ValueError,RuntimeError,TypeError,KeyError) as exc:
        print(canonical({'status':'refused','message':str(exc)}).decode(),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
