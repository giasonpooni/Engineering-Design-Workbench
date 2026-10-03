"""Actual Chromium interaction qualification of the installed mathematical viewer.

No screenshot mock or DOM fixture. Defaults to opening the generated local HTML.
--document-mode content supports environments that administratively block file://;
that mode tests identical document bytes but is reported separately.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def run(html: Path, output_dir: Path, executable: str | None, mode: str) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
    document = html.read_text(encoding='utf-8')
    errors, requests, completed = [], [], []
    def require(value, name):
        if not value: raise AssertionError(name)
        completed.append(name)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, **({'executable_path': executable} if executable else {}))
        page = browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: errors.append(m.text) if m.type=='error' else None)
        page.on('request', lambda r: requests.append(r.url))
        if mode=='file': page.goto(html.resolve().as_uri())
        else: page.set_content(document)
        page.wait_for_selector('body[data-ready="true"]')
        require(page.locator('#time-chart circle.point').count()==6,'six_native_temperature_samples')
        require(page.locator('#time-chart [data-measurement]').count()==5,'missing_measurement_not_drawn_as_zero')
        require(page.locator('#time-chart [data-missing]').count()==1,'explicit_missing_measurement_label')
        require(page.locator('#design-chart [data-candidate]').count()==4,'all_native_sensor_candidates_retained')
        require(page.locator('#prev').is_disabled(),'first_tick_boundary')
        require('1 / 3' in page.locator('#tick-label').inner_text(),'initial_cursor')
        original_mean = page.locator('#metric-mean').inner_text()
        path_2 = page.locator('[data-contour]').get_attribute('points')
        page.locator('#radius').select_option('1')
        require(page.locator('[data-contour]').get_attribute('points')!=path_2,'contour_radius_changes_display')
        page.locator('#radius').select_option('2')
        require(page.locator('#metric-mean').inner_text()==original_mean,'radius_does_not_change_retained_mean')
        page.screenshot(path=str(output_dir/'desktop.png'),full_page=True)
        page.locator('#tick').focus();page.keyboard.press('ArrowRight')
        page.wait_for_selector('body[data-tick="1"]')
        require(page.locator('#availability').inner_text()=='CORE','cursor_updates_missing_sensor_context')
        require('1 active measurement' in page.locator('#metric-dimension').inner_text(),'cursor_updates_innovation_dimension')
        after_cursor = page.locator('#metric-mean').inner_text()
        page.locator('#stage').select_option('predicted')
        require(page.locator('#metric-mean').inner_text()!=after_cursor,'stage_switch_uses_native_prediction')
        cross_cov = page.locator('[data-cell="0-1"]').inner_text()
        page.locator('#matrix-mode').select_option('correlation')
        require(page.locator('[data-cell="0-1"]').inner_text()!=cross_cov,'correlation_toggle')
        require(page.locator('[data-cell="0-0"]').inner_text()=='1','correlation_diagonal')
        page.locator('#next').click()
        require(page.locator('#next').is_disabled(),'last_tick_boundary')
        page.locator('#nis-chart [data-nis-tick="0"]').click()
        require(page.locator('body').get_attribute('data-tick')=='0','nis_selection_links_all_panels')
        for width in (700,390):
            page.set_viewport_size({'width':width,'height':844});page.wait_for_timeout(100)
            require(not page.evaluate('document.documentElement.scrollWidth > innerWidth'),f'no_horizontal_overflow_{width}')
            page.screenshot(path=str(output_dir/f'width-{width}.png'),full_page=True)
        page.locator('.provenance summary').click()
        require(page.locator('#raw-tick').is_visible(),'raw_numerical_context_accessible')
        require('posterior_covariance' in page.locator('#raw-tick').inner_text(),'original_covariance_inspectable')
        with page.expect_download() as info:page.locator('#download-report').click()
        saved=output_dir/'browser-retained-report.json';info.value.save_as(str(saved))
        from ciw.math_inspector import validate_report
        validate_report(json.loads(saved.read_bytes()))
        require(True,'downloaded_report_validates_offline')
        require(not requests or all(url.startswith(('file:', 'blob:')) for url in requests),'no_network_requests')
        require(not errors,'no_javascript_or_csp_errors')
        version=browser.version
        browser.close()
    result={'status':'passed','browser':version,'document_mode':mode,
            'checks':completed,'count':len(completed),'network_requests':[u for u in requests if u.startswith(('http:','https:'))],
            'errors':errors}
    (output_dir/'browser-report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--html',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--browser-executable')
    p.add_argument('--document-mode',choices=['file','content'],default='file')
    a=p.parse_args()
    print(json.dumps(run(a.html,a.output_dir,a.browser_executable,a.document_mode),indent=2))
