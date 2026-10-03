"""Cross-repository qualification of the original 1792 water state in real Godot."""
import argparse
from copy import deepcopy
from pathlib import Path
import json
import shutil
import tempfile
from unittest.mock import patch

from ciw import game_project as p, game_project_workflow as w, game_trace
from ciw.control_contracts import load, save_new
from ciw.operations.runner import seal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--profile-sha256', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    profile = p.read_profile(args.profile, args.profile_sha256)
    binding = p.GodotProjectBinding(args.godot, args.source_root, profile, expected_sha256=p.file_sha(args.godot))
    original = {name:p.file_sha(args.source_root/name) for name in profile['files']}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    checks, reports = [], {}
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    def campaign(name, source, plan, selected=binding, selected_profile=profile):
        root = args.output_dir/name
        reports[name] = w.execute(selected_profile, source, plan, selected, root)
        hashes = {str(f):p.file_sha(f) for f in root.rglob('*.json')}
        with patch('subprocess.Popen', side_effect=AssertionError('inspection started a process')):
            result = w.feedback(root)
        check(name+': no execution during inspection', result['fresh_execution'] is False)
        check(name+': retained bytes unchanged', hashes=={str(f):p.file_sha(f) for f in root.rglob('*.json')})
        save_new(args.output_dir/(name+'-feedback.json'), result)
        workspace = load(root/'session/workspace.json')
        check(name+': native processes', all(e['runtime']['execution_mode']=='native_process' for e in workspace['executions']))
        check(name+': distinct execution occurrences', len({e['execution_id'] for e in workspace['executions']})==len(workspace['executions']))
        check(name+': no formal verification', all(r['verification_id'] is None for r in workspace['results']))
        return result, workspace
    baseline = {'first_deposit_tick':30,'second_deposit_tick':61,'checkpoint_tick':15}
    early = {**baseline,'first_deposit_tick':29}
    source, plan = w.declare(profile, w.grid_orders(profile))
    grid, workspace = campaign('grid', source, plan)
    check('grid: eighteen original game executions', grid['execution_count']==18)
    check('grid: eight accepted and ten rejected schedules', grid['counts']=={'accepted':8,'rejected':10,'held':0,'refused':0,'blocked':0})
    reference = next(r for r in workspace['results'] if r['parameters']['assignment']==baseline)
    for r in workspace['results']:
        native = game_trace.unpack(r['data'])[1]
        check('grid: complete 639-sample capture '+r['result_id'], len(native['samples'])==639 and native['complete'])
    orders = [{'job_id':'candidate','attempts':[early,baseline],'depends_on':[]},
              {'job_id':'regression','attempts':[baseline],'depends_on':['candidate']}]
    source, plan = w.declare(profile, orders)
    repair, workspace = campaign('repair', source, plan)
    check('repair: failed then accepted', [x['status'] for x in repair['jobs']['candidate']['attempts']]==['rejected','accepted'])
    check('repair: downstream unblocked', repair['jobs']['regression']['status']=='accepted')
    selected_id = repair['jobs']['candidate']['attempts'][-1]['candidates'][0]['result_id']
    corrected = next(r for r in workspace['results'] if r['result_id']==selected_id)
    comparison = game_trace.comparison(corrected['data'],reference['data'],corrected['execution_id'],reference['execution_id'],atol=0,rtol=0)
    check('repair: corrected PRIMARY candidate matches baseline', comparison['status']=='PASS')
    save_new(args.output_dir/'corrected-primary-comparison.json', comparison)
    source, plan = w.declare(profile, orders)
    graph = plan['jobs'][0]['attempts'][0]
    graph['nodes'][0]['parameters']['diagnostic_fault']='drop-sample'
    seal(graph);seal(plan)
    missing, _ = campaign('missing', source, plan)
    check('missing: held without repair or downstream execution', missing['counts']['held']==1 and missing['counts']['blocked']==1 and missing['execution_count']==1)
    with tempfile.TemporaryDirectory(prefix='net-explicit-failing-title-fixture-') as directory:
        root = Path(directory)
        for name in profile['files']:
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(args.source_root/name,target)
        (root/profile['entrypoint']).write_text('extends SceneTree\nfunc _initialize():\n\tquit(7)\n',encoding='utf-8')
        broken=deepcopy(profile);broken['files'][broken['entrypoint']]=p.file_sha(root/broken['entrypoint'])
        broken_binding=p.GodotProjectBinding(args.godot,root,broken,expected_sha256=p.file_sha(args.godot))
        source,plan=w.declare(broken,orders)
        refused,_=campaign('refusal',source,plan,broken_binding,broken)
        check('refusal: one actual failed engine process and no result', refused['counts']['refused']==1 and reports['refusal']['execution_count']==1 and reports['refusal']['result_count']==0)
    check('title sources unchanged by all executions', original=={name:p.file_sha(args.source_root/name) for name in profile['files']})
    report={'schema':'ciw.game-project-qualification.v1','profile_sha256':args.profile_sha256,'runtime':binding.runtime_identity(),
        'checks_passed':len(checks),'checks':checks,'campaigns':{name:{k:r[k] for k in ('status','execution_count','result_count','attempt_count')} for name,r in reports.items()},
        'native_process_attempts':sum(r['execution_count'] for r in reports.values()),
        'scope':'original 1792 domain state with explicit initialization/pose fixtures; no rendering, navigation, LLM or autonomous code repair'}
    save_new(args.output_dir/'qualification.json',report)
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
