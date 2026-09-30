"""Actual Chromium qualification of view identity, exports and Session/Needle UI.

The embedded-only option is a limited local DOM test for environments whose
managed browser refuses file and loopback navigation. It never claims live UI
or file-navigation qualification. Hosted CI uses the full default mode.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import re
from pathlib import Path
import threading

from playwright.sync_api import expect, sync_playwright

from ciw.core.identities import content_identity
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.visual_board import demo_board, project_scene, render_html, view_from_spec
from ciw.visual_board_server import BoardWorkbench, make_server


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--chromium')
    parser.add_argument('--embedded-only',action='store_true')
    args=parser.parse_args()
    root=args.output_dir.resolve();root.mkdir(parents=True,exist_ok=False)
    board=demo_board(); original=deepcopy(board)
    html=root/'board.html';html.write_bytes(render_html(board))
    checks=[];errors=[];external=[]
    def check(name,condition):
        if not condition: raise AssertionError(name)
        checks.append(name)
    def parity(page):
        snapshot=page.evaluate('window.netBoardViewSnapshot()')
        expected=project_scene(board,view_from_spec(board,snapshot['view']))
        actual=snapshot['scene']
        for field in ('items','node_to_visual','edges','hidden_internal_edge_ids','filtered_edge_ids'):
            check('Python / browser scene parity: '+field,actual[field]==expected[field])
        check('Board digest preserved',snapshot['board_ref']==board['record_digest'])
    def observe(page):
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
        page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http://','https://'))
                and not r.url.startswith('http://127.0.0.1:') else None)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,**({'executable_path':args.chromium} if args.chromium else {}))
        page=browser.new_page(viewport={'width':1600,'height':1100})
        observe(page)
        if args.embedded_only: page.set_content(html.read_text(encoding='utf-8'))
        else: page.goto(html.as_uri())
        expect(page.locator('#status')).to_have_text(re.compile(r'^Ready\.'))
        check('Six original graph objects visible',page.locator('.graph-node').count()==6)
        check('Offline execution disabled',page.locator('#run-baseline').is_disabled())
        page.screenshot(path=str(root/'board-initial.png'),full_page=True)
        page.get_by_role('button',name='Collapse Signal analysis',exact=True).click()
        check('Collapsed group replaces two nodes by one view',page.locator('.graph-node').count()==5)
        parity(page)
        page.locator('[data-visual-id="group:analysis"]').dblclick()
        check('Expanded identities restored',page.locator('.graph-node').count()==6)
        for mode in ('DEPENDENCY','SCIENTIFIC','AUTHORITY','ALL'):
            page.locator('[data-mode="'+mode+'"]').click();parity(page)
        page.get_by_role('button',name='Collapse Oscillator instrument',exact=True).click()
        check('Root collapse exposes one group',page.locator('.graph-node').count()==1)
        parity(page)
        page.get_by_role('button',name='Expand Oscillator instrument',exact=True).click()
        target=page.locator('[data-visual-id="node:statistics"]')
        target.click()
        check('Exact node selected',page.locator('#node-title').inner_text()=='Signal statistics')
        bounds=target.bounding_box();x=bounds['x']+30;y=bounds['y']+30
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x-40,y+35,steps=4);page.mouse.up()
        page.wait_for_timeout(100)
        snap=page.evaluate('window.netBoardViewSnapshot()')
        check('Node drag is inspectable layout data','node:statistics' in snap['view']['positions'])
        parity(page)
        page.get_by_role('button',name='Zoom in',exact=True).click()
        check('Zoom is inspectable view state',page.evaluate('window.netBoardViewSnapshot().view.viewport.zoom')>1)
        page.locator('#fit-view').click()
        if not args.embedded_only:
            page.locator('#parameter-channel').select_option(label='v')
            with page.expect_download() as info:
                page.locator('#parameter-editor .edit-button').click()
            edit_path=root/'browser-edit.json';info.value.save_as(edit_path)
            req=json.loads(edit_path.read_text())
            check('Browser exports exact Board parameter request',req=={
                'schema':'ciw.board-parameter-edit.v1','base_board_ref':board['record_digest'],
                'node_id':'statistics','parameter':'channel','replacement':'v'})
            with page.expect_download() as info:page.locator('#download-view').click()
            info.value.save_as(root/'browser-view-spec.json')
            view_from_spec(board,json.loads((root/'browser-view-spec.json').read_text()))
            check('Exported view accepted by core validator',True)
        hostile=deepcopy(board);hostile['title']='</script><script>window.PWNED=true</script>'
        other=browser.new_page();observe(other)
        other.set_content(render_html(seal(hostile)).decode())
        expect(other.locator('#status')).to_have_text(re.compile(r'^Ready\.'))
        check('Hostile label remains inert text',other.evaluate('window.PWNED===undefined'))
        other.close()
        page.set_viewport_size({'width':600,'height':850})
        page.screenshot(path=str(root/'board-narrow.png'),full_page=True)
        check('Narrow layout has no document horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))
        page.close()
        if not args.embedded_only:
            work=BoardWorkbench(board,root/'live-evidence',source=make_demo_run(),allow_run=True)
            server=make_server(work);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                page=browser.new_page(viewport={'width':1600,'height':1100});observe(page)
                page.goto(server.board_url)
                expect(page.locator('#status')).to_have_text(re.compile(r'^Ready\.'))
                check('Explicitly opted-in live baseline enabled',page.locator('#run-baseline').is_enabled())
                check('No execution before Run click',work.session is None)
                page.locator('#run-baseline').click()
                expect(page.locator('#run-summary')).to_contain_text('Baseline completed')
                check('Three baseline execution occurrences',len(work.session.executions)==3)
                prior=deepcopy(work.baseline)
                page.locator('#parameter-channel').select_option(label='v')
                page.get_by_role('button',name='Compile candidate',exact=True).click()
                expect(page.locator('#run-candidate')).to_be_enabled()
                check('Compiling preview did not execute provider',len(work.session.executions)==3)
                page.locator('#run-candidate').click()
                expect(page.locator('#run-summary')).to_contain_text('2 rerun')
                check('Only two new execution occurrences',len(work.session.executions)==5)
                check('Unchanged baseline content',work.baseline==prior)
                text=page.locator('#delta-list').inner_text()
                check('Changed statistics shown','statistics: RERUN · changed' in text)
                check('Unchanged rerun shown','spectrum: RERUN · unchanged' in text)
                check('Reused independent branch shown','energy_statistics: REUSED' in text)
                check('Actual retained numerical result inspectable','m/s' in page.locator('#node-observations').inner_text())
                page.screenshot(path=str(root/'board-executed.png'),full_page=True)
                with page.expect_download() as info:page.locator('#download-view').click()
                info.value.save_as(root/'validated-browser-view.json')
                check('Validated view exported',json.loads((root/'validated-browser-view.json').read_text())['schema']=='ciw.board-view.v1')
                page.close()
            finally:
                server.shutdown();thread.join();server.server_close()
        browser_version=browser.version
        browser.close()
    check('Caller Board unmodified',board==original)
    check('No external network requests',external==[])
    check('No browser errors',errors==[])
    report={'status':'passed','count':len(checks),'checks':checks,'errors':errors,'external_requests':external,
            'browser_version':browser_version,'offline_document_mode':'embedded' if args.embedded_only else 'file',
            'live_browser_execution':'not_performed' if args.embedded_only else 'performed',
            'board_ref':board['record_digest'],'board_content_identity':content_identity(board)}
    (root/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
