"""Real-browser interaction checks for the optional v2 covariance information view.

Uses retained report bytes, not a mocked DOM. File navigation and content-loading
are explicitly distinguished; no managed-browser policy is changed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(html: Path, output_dir: Path, executable: str | None = None, mode: str = 'file') -> dict:
    output_dir.mkdir(parents=True,exist_ok=False)
    checks,errors,requests=[],[],[]
    def require(condition,name):
        if not condition:raise AssertionError(name)
        checks.append(name)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
        page=browser.new_page(viewport={'width':1440,'height':1150},device_scale_factor=1)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
        page.on('request',lambda r:requests.append(r.url))
        if mode=='file':page.goto(html.resolve().as_uri())
        else:page.set_content(html.read_text(encoding='utf-8'))
        page.wait_for_selector('body[data-ready=true]')
        require(page.locator('#information-panel').is_visible(),'v2_panel_visible')
        require('Tick 1' in page.locator('#information-context-label').inner_text(),'starts_at_selected_tick')
        require(page.locator('[data-prior-circle]').count()==1,'prior_unit_circle')
        require(page.locator('[data-information-eigenvalue]').count()==2,'both_generalized_directions')
        first=page.locator('#information-ratio').inner_text()
        page.locator('#information-direction').focus();page.keyboard.press('ArrowRight')
        require(page.locator('#information-angle').inner_text()=='5°','keyboard_direction_control')
        require(page.locator('#information-ratio').inner_text()!=first,'direction_updates_variance_ratio')
        require(page.locator('[data-direction-support]').count()==1,'support_point_visible')
        page.locator('#tick').focus();page.keyboard.press('ArrowRight')
        require('Tick 2' in page.locator('#information-context-label').inner_text(),'linked_tick_updates_information')
        before=page.locator('#information-ratio').inner_text()
        page.locator('#stage').select_option('predicted')
        require(page.locator('#information-ratio').inner_text()==before,'state_selector_does_not_redefine_covariance_pair')
        page.locator('#information-context').select_option('forecast')
        require(page.locator('#information-candidates [data-information-mask]').count()==4,'all_four_retained_alternatives')
        page.locator('#information-candidates [data-information-mask="0"]').click()
        require('INFEASIBLE' in page.locator('#information-context-label').inner_text(),'infeasible_no_sensor_alternative_is_labelled')
        require(page.locator('#information-ratio').inner_text()=='1','no_measurement_no_reduction')
        page.locator('#information-candidates [data-information-mask="3"]').click()
        require('INFEASIBLE' in page.locator('#information-context-label').inner_text(),'over_budget_candidate_is_labelled')
        provider=page.locator('#information-provider').inner_text()
        require('Selected: shell' in provider,'original_provider_decision_preserved')
        before=page.locator('[data-information-contour]').get_attribute('points')
        page.locator('#next').click()
        require(page.locator('[data-information-contour]').get_attribute('points')==before,'final_forecast_not_relabelled_as_tick_forecast')
        page.locator('#design-chart [data-candidate="1"]').focus();page.keyboard.press('Enter')
        require(page.locator('body').get_attribute('data-information-mask')=='1','native_score_keyboard_selection_links_geometry')
        require(page.locator('#information-provider').inner_text()==provider,'inspection_does_not_reselect_sensors')
        page.locator('#information-context').select_option('tick')
        require('Tick 3' in page.locator('#information-context-label').inner_text(),'return_to_current_tick')
        page.screenshot(path=str(output_dir/'desktop.png'),full_page=True)
        page.locator('#information-panel').screenshot(path=str(output_dir/'information-panel.png'))
        for width in (700,390):
            page.set_viewport_size({'width':width,'height':844});page.wait_for_timeout(100)
            require(not page.evaluate('document.documentElement.scrollWidth>innerWidth'),f'no_overflow_{width}')
            page.screenshot(path=str(output_dir/f'width-{width}.png'),full_page=True)
        with page.expect_download() as d:page.locator('#download-report').click()
        saved=output_dir/'browser-report-data.json';d.value.save_as(str(saved))
        from ciw.math_inspector import validate_report
        report=json.loads(saved.read_bytes());validate_report(report)
        require(report['schema'].endswith('.v2'),'downloaded_v2_revalidates')
        require(not any(u.startswith(('http:','https:')) for u in requests),'no_network_requests')
        require(not errors,'no_javascript_or_csp_errors')
        version=browser.version;browser.close()
    report={'status':'passed','count':len(checks),'checks':checks,'document_mode':mode,'browser':version,'errors':errors,
        'network_requests':[u for u in requests if u.startswith(('http:','https:'))]}
    (output_dir/'browser-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--html',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--browser-executable');p.add_argument('--document-mode',choices=['file','content'],default='file')
    a=p.parse_args();print(json.dumps(run(a.html,a.output_dir,a.browser_executable,a.document_mode),indent=2))
