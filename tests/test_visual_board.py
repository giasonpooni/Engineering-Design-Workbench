from copy import deepcopy
from http.client import HTTPConnection
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from ciw.control_plane import builtin_registry
from ciw.core.identities import content_identity
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.semantic_capabilities import builtin_semantic_registry
from ciw.system_board import board_from_spec, compile_board
from ciw.visual_board import (apply_parameter_edit, default_view, demo_board, project_scene,
                              render_html, validate_edit, validate_view, view_from_spec, write_html)
from ciw.visual_board_server import BoardWorkbench, make_server


@pytest.fixture
def board():
    return demo_board()


def request_for(board, replacement='v'):
    return {'schema': 'ciw.board-parameter-edit.v1', 'base_board_ref': board['record_digest'],
            'node_id': 'statistics', 'parameter': 'channel', 'replacement': replacement}


def semantic():
    return builtin_semantic_registry(builtin_registry(bind=True))


def scene(board, **changes):
    return project_scene(board, view_from_spec(board, {**default_view(board), **changes}))


def test_collapse_is_a_partition_of_existing_node_identities(board):
    before = deepcopy(board)
    collapsed = scene(board, collapsed_groups=['analysis'])
    members = [nid for item in collapsed['items'] for nid in item['node_ids']]
    assert sorted(members) == sorted(n['node_id'] for n in board['nodes'])
    assert len(members) == len(set(members))
    assert collapsed['node_to_visual']['statistics'] == 'group:analysis'
    assert collapsed['hidden_internal_edge_ids'] == ['signal-dependency']
    assert board == before


def test_outermost_collapse_wins_and_selection_is_retained(board):
    v = view_from_spec(board, {**default_view(board), 'collapsed_groups': ['instrument', 'analysis'],
                              'selected_node_id': 'statistics'})
    s = project_scene(board, v)
    assert len(s['items']) == 1
    assert s['items'][0]['visual_id'] == 'group:instrument'
    assert len(s['items'][0]['node_ids']) == 6
    assert v['specification']['selected_node_id'] == 'statistics'
    assert len(s['hidden_internal_edge_ids']) == len(board['edges'])


def test_view_mode_is_filter_not_new_graph(board):
    all_scene = scene(board)
    dependency = scene(board, mode='DEPENDENCY')
    assert len(dependency['edges']) == 1
    assert dependency['edges'][0]['kind'] == 'DEPENDENCY'
    assert len(dependency['filtered_edge_ids']) == 3
    assert len(scene(board, mode='AUTHORITY')['edges']) == 0
    assert all_scene['board_ref'] == dependency['board_ref'] == board['record_digest']


def test_all_edges_are_retained_or_hidden_or_filtered(board):
    s = scene(board, mode='DEPENDENCY', collapsed_groups=['analysis'])
    ids = [e['edge_id'] for e in s['edges']] + s['hidden_internal_edge_ids'] + s['filtered_edge_ids']
    assert sorted(ids) == sorted(e['edge_id'] for e in board['edges'])


@pytest.mark.parametrize('changes', [
    {'board_ref': 'sha256:'+'0'*64}, {'mode': 'CAUSAL'}, {'mode': []},
    {'collapsed_groups': ['absent']}, {'collapsed_groups': ['analysis','analysis']},
    {'collapsed_groups': [{}]}, {'selected_node_id': 'absent'},
    {'selected_node_id': []}, {'positions': {'absent': {'x':0,'y':0}}},
    {'positions': {'node:statistics': {'x': True, 'y':0}}},
    {'viewport': {'x':0,'y':0,'zoom':0}}, {'viewport': {'x':0,'y':0,'zoom':float('nan')}},
])
def test_view_contract_refuses_ambiguous_or_invalid_identity_and_geometry(board, changes):
    with pytest.raises(ValueError):
        view_from_spec(board, {**default_view(board), **changes})


def test_resealed_view_claim_cannot_invent_authority(board):
    v = view_from_spec(board, default_view(board))
    v['claims']['execution_authority'] = True
    with pytest.raises(ValueError):
        validate_view(seal(v), board)


def test_candidate_compiles_through_unchanged_existing_path(board):
    sem = semantic()
    before = deepcopy(board)
    edit = apply_parameter_edit(board, request_for(board), sem)
    assert edit['compilation'] == compile_board(edit['candidate_board'], sem)
    assert edit['dependency_closure'] == ['statistics','spectrum']
    assert edit['unaffected_operation_ids'] == ['energy_statistics']
    assert board == before
    assert edit['candidate_board']['record_digest'] != board['record_digest']
    assert edit['candidate_board']['edges'] == board['edges']
    assert edit['candidate_board']['groups'] == board['groups']
    assert not edit['claims']['provider_execution']
    assert validate_edit(edit, board, sem) == edit


@pytest.mark.parametrize('replacement', ['pressure', True, {}, float('nan'), 'q'])
def test_edit_refuses_out_of_domain_malformed_and_noop(board, replacement):
    with pytest.raises(ValueError):
        apply_parameter_edit(board, request_for(board, replacement), semantic())


def test_stale_ref_unknown_coordinate_nonoperation_refuse(board):
    for changes in ({'base_board_ref':'sha256:'+'f'*64}, {'node_id':'missing'},
                    {'parameter':'missing'}, {'node_id':'model'}, {'schema':'other'}):
        with pytest.raises(ValueError):
            apply_parameter_edit(board, {**request_for(board), **changes}, semantic())


def test_nonexposed_and_fixed_are_enforced_by_parameter_program(board):
    board['nodes'][3]['parameters']['channel']['exposed'] = False
    with pytest.raises(ValueError, match='exposed'):
        apply_parameter_edit(seal(board), request_for(seal(board)), semantic())
    board['nodes'][3]['parameters']['channel']['exposed'] = True
    board['nodes'][3]['parameters']['channel']['domain'] = {
        'kind':'FIXED','minimum':None,'maximum':None,'values':None,'log_base':None}
    with pytest.raises(ValueError, match='FIXED'):
        apply_parameter_edit(seal(board), request_for(seal(board)), semantic())


def test_resealed_fake_candidate_and_closure_are_recomputed(board):
    sem = semantic()
    e = apply_parameter_edit(board, request_for(board), sem)
    e['dependency_closure'].append('energy_statistics')
    with pytest.raises(ValueError):
        validate_edit(seal(e), board, sem)


def test_offline_html_uses_inert_data_no_remote_assets_and_no_overwrite(board, tmp_path):
    board['title'] = '</script><script>window.PWNED=true</script>'
    board = seal(board)
    html = render_html(board).decode()
    assert board['title'] not in html
    assert "connect-src 'none'" in html
    assert 'script-src \'sha256-' in html
    assert 'innerHTML' not in html
    out = tmp_path/'board.html'
    write_html(out, board)
    with pytest.raises(FileExistsError):
        write_html(out, board)
    assert out.read_text() == html


def test_live_shell_does_not_leak_board_or_token_before_authentication(board):
    raw = render_html(None, live=True)
    assert board['record_digest'].encode() not in raw
    assert b"connect-src 'self'" in raw
    with pytest.raises(ValueError):
        render_html(board, live=True)


def test_cli_same_request_same_candidate_identity(board, tmp_path):
    b, r, out = tmp_path/'board.json', tmp_path/'request.json', tmp_path/'preview.json'
    b.write_text(json.dumps(board)); r.write_text(json.dumps(request_for(board)))
    args = [sys.executable, '-m', 'ciw.net', 'board', 'edit', str(b), str(r), '--output', str(out)]
    done = subprocess.run(args, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert json.loads(out.read_text()) == apply_parameter_edit(board, request_for(board), semantic())
    assert subprocess.run(args, capture_output=True).returncode == 1


def test_real_baseline_needle_delta_reuses_existing_source_and_instruments(board, tmp_path):
    source = make_demo_run()
    before = deepcopy((board,source))
    w = BoardWorkbench(board,tmp_path/'work',source=source,allow_run=True)
    base = w.run_baseline()
    original = deepcopy(w.baseline)
    out = w.run_candidate(request_for(board), base['baseline_ref'])
    assert out['run']['rerun_nodes'] == ['statistics','spectrum']
    assert out['run']['reused_nodes'] == ['energy_statistics']
    rows={r['node_id']:r for r in out['delta']['nodes']}
    assert rows['statistics']['data_changed'] is True
    assert rows['spectrum']['data_changed'] is False
    assert rows['energy_statistics']['recomputation'] == 'REUSED'
    assert out['receipt']['source_evidence_id'] == source['evidence_id']
    assert out['receipt']['candidate_board_ref'] != board['record_digest']
    assert w.baseline == original
    assert (board,source) == before
    assert len(w.session.executions) == 5
    retained = tmp_path/'work'/out['retained_directory']
    assert all((retained/f).is_file() for f in ('request.json','preview.json','plan.json','run.json','delta.json','receipt.json'))


def test_execution_opt_in_source_and_baseline_boundaries(board, tmp_path):
    w=BoardWorkbench(board,tmp_path/'offline')
    with pytest.raises(ValueError,match='disabled'):
        w.run_baseline()
    w=BoardWorkbench(board,tmp_path/'work',source=make_demo_run(),allow_run=True)
    with pytest.raises(ValueError,match='baseline'):
        w.run_candidate(request_for(board),'sha256:'+'0'*64)
    w.run_baseline()
    with pytest.raises(ValueError,match='baseline'):
        w.run_candidate(request_for(board),'sha256:'+'0'*64)
    with pytest.raises(ValueError,match='source'):
        BoardWorkbench(board,tmp_path/'no-source',allow_run=True)
    assert not (tmp_path/'no-source').exists()


def test_serving_arbitrary_executable_workloads_is_not_enabled(board, tmp_path):
    board['model_id']='factory-model'
    with pytest.raises(ValueError,match='only'):
        BoardWorkbench(seal(board),tmp_path/'work',source=make_demo_run(),allow_run=True)
    assert not (tmp_path/'work').exists()


@pytest.fixture
def server(board,tmp_path):
    work=BoardWorkbench(board,tmp_path/'server')
    server=make_server(work)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    yield server,work
    server.shutdown();thread.join();server.server_close()


def http(server, path, *, value=None, token=True, headers=None, raw=None):
    h={}
    if token: h['X-NET-Board-Token']=server.board_token
    if value is not None: raw=json.dumps(value);h['Content-Type']='application/json'
    h.update(headers or {})
    conn=HTTPConnection('127.0.0.1',server.server_port,timeout=3)
    conn.request('POST' if raw is not None else 'GET',path,body=raw,headers=h)
    response=conn.getresponse(); data=response.read(); code=response.status;conn.close()
    return code,data


def test_api_requires_capability_but_serves_only_inert_shell_without_one(server):
    s,w=server
    code,raw=http(s,'/',token=False)
    assert code==200 and w.board['record_digest'].encode() not in raw
    assert http(s,'/api/state',token=False)[0]==403
    assert http(s,'/api/state',headers={'X-NET-Board-Token':'wrong'})[0]==403
    assert http(s,'/api/state')[0]==200


@pytest.mark.parametrize('headers', [
    {'Host':'attacker.invalid'}, {'Origin':'https://attacker.invalid'},
    {'Origin':'null'}, {'Host':'localhost'},
])
def test_cross_origin_and_dns_rebinding_host_refusal(server, headers):
    s,_=server
    assert http(s,'/api/state',headers=headers)[0]==403


def test_api_and_cli_use_same_candidate_validator(server):
    s,w=server
    req=request_for(w.board)
    code,raw=http(s,'/api/edit',value=req)
    assert code==200
    result=json.loads(raw)['preview']
    assert result==apply_parameter_edit(w.board,req,w.semantic)
    assert w.session is None


def test_fixed_endpoints_and_malformed_json_fail_closed(server):
    s,w=server
    assert http(s,'/../../etc/passwd')[0]==404
    assert http(s,'/api/shell',raw='{}')[0]==404
    assert http(s,'/api/edit',raw='{',headers={'Content-Type':'application/json'})[0]==400
    assert http(s,'/api/edit',raw='{"x":1,"x":2}',headers={'Content-Type':'application/json'})[0]==400
    assert http(s,'/api/edit',raw='{}',headers={'Content-Type':'text/plain'})[0]==400
    assert http(s,'/api/edit',raw='{}',headers={'Content-Type':'application/json','Content-Length':'9999999'})[0]==400
    assert http(s,'/api/baseline',value={'board_ref':w.board['record_digest']})[0]==400
    assert w.session is None


def test_api_validation_before_any_candidate_retention(server):
    s,w=server
    before=list(w.output_dir.iterdir())
    code,_=http(s,'/api/edit',value=request_for(w.board,'invalid'))
    assert code==400
    assert list(w.output_dir.iterdir())==before
