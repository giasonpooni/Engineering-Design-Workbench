"""Exercise actual generated evidence pages. Content-mode is not file navigation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(captures: Path, campaign: Path, output: Path, *, executable: str | None = None, mode: str = "file") -> dict:
    output.mkdir(parents=True, exist_ok=False)
    checks, errors, network = [], [], []
    def check(value, name):
        if not value:
            raise AssertionError(name)
        checks.append(name)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, **({"executable_path": executable} if executable else {}))
        page = browser.new_page(viewport={"width": 1400, "height": 1100}, device_scale_factor=1)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("request", lambda r: network.append(r.url) if not r.url.startswith(("file:", "data:")) else None)
        def load(path):
            if mode == "file": page.goto(path.resolve().as_uri(), wait_until="load")
            else: page.set_content(path.read_text(encoding="utf-8"), wait_until="load")
        def selected(): return json.loads(page.locator("#record-json").text_content())
        load(captures / "index.html")
        t = page.locator("#timeline-data").evaluate("e => JSON.parse(e.textContent).timeline")
        check(page.locator("#executions").inner_text() == "20", "twenty_deduplicated_occurrences")
        check(page.locator("#images").inner_text() == "4" and page.locator("#refusals").inner_text() == "1", "checked_images_and_refusal_counts")
        check("75 shared" in page.locator("#dedup").inner_text(), "shared_source_not_double_counted")
        page.locator("#kind").select_option("capture")
        check(page.locator(".event").count() == 4, "capture_filter")
        delayed = next(e for e in t["entries"] if e["image"] and e["image"]["sample_time_s"] == 0.125)
        page.locator(f'.event[data-execution-id="{delayed["execution_id"]}"]').click()
        check(selected()["image"]["sample_time_s"] == 0.125 and selected()["available_at"]["time_s"] == 0.15625
              and "sample 0.125 s" in page.locator("#image-caption").inner_text()
              and "delivered 0.15625 s" in page.locator("#image-caption").inner_text(), "sample_and_delivery_times_distinct")
        page.wait_for_function("document.getElementById('capture-image').naturalWidth === 1280")
        check(page.locator("#capture-image").evaluate("e=>e.naturalHeight") == 800, "actual_embedded_png_loaded")
        page.locator("#relations button").filter(has_text="Source observation").click()
        check(selected()["execution_id"] == delayed["image"]["source_execution_id"], "capture_to_original_observation_link")
        check(page.locator("#samples tr").count() == len(selected()["samples"]) and len(selected()["samples"]) > 0, "original_exact_samples_visible")
        page.locator("#observer").select_option(delayed["observer"]["observer_id"])
        ids = page.locator(".event").evaluate_all("elements=>elements.map(e=>e.dataset.executionId)")
        check(all(next(e for e in t["entries"] if e["execution_id"] == i)["observer"]["observer_id"] == delayed["observer"]["observer_id"] for i in ids), "observer_filter")
        page.locator("#reset").click(); page.locator("#kind").select_option("capture")
        missing = next(e for e in t["entries"] if e["image"] and e["image"]["sample_time_s"] is None)
        page.locator(f'.event[data-execution-id="{missing["execution_id"]}"]').click()
        check(selected()["image"]["position_xyz_m"] is None and "unavailable" in page.locator("#image-caption").inner_text(), "unavailable_not_filled_from_world_state")
        page.locator("#kind").select_option("refusal")
        check(page.locator(".event").count() == 1 and selected()["result_id"] is None and selected()["world_after"] is None, "refusal_has_no_fabricated_world_result")
        page.locator("#search").fill("no-such-occurrence-000000")
        check(page.locator("#empty").is_visible() and page.locator(".event").count() == 0, "empty_search_state")
        page.locator("#reset").click()
        check(page.locator(".event").count() == 20, "filter_reset")
        current = next(e for e in t["entries"] if e["image"] and e["image"]["sample_time_s"] == 0.15625 and e["image"]["camera"] == "oblique")
        page.locator(f'.event[data-execution-id="{current["execution_id"]}"]').click()
        page.locator("#record-details summary").focus(); page.keyboard.press("Enter")
        check(page.locator("#record-details").get_attribute("open") is not None, "keyboard_record_disclosure")
        page.keyboard.press("Enter")
        page.screenshot(path=str(output / "desktop.png"), full_page=True)
        for width in (700, 390):
            page.set_viewport_size({"width": width, "height": 900})
            check(not page.evaluate("document.documentElement.scrollWidth > innerWidth"), f"no_document_overflow_{width}")
            page.screenshot(path=str(output / f"width-{width}.png"), full_page=True)
        page.set_viewport_size({"width": 1400, "height": 1100})
        load(campaign / "index.html")
        check(page.locator("#executions").inner_text() == "87" and page.locator("#instances").inner_text() == "6", "native_branch_occurrence_counts")
        check(page.locator(".analysis").count() == 2 and "REPLAY · PASS" in page.locator("#analysis-list").inner_text(), "campaign_and_replay_verdicts_bound")
        page.locator(".analysis button").first.click()
        check(selected()["kind"] == "checkpoint", "report_to_checkpoint_navigation")
        page.locator("#relations button").filter(has_text="Restored branch").first.click()
        check(selected()["action"] == "restore", "checkpoint_to_branch_navigation")
        page.screenshot(path=str(output / "campaign.png"), full_page=True)
        check(not network, "no_network_requests")
        check(not errors, "no_script_or_csp_errors")
        version = browser.version
        browser.close()
    result = {"status": "passed", "checks": checks, "count": len(checks), "browser": version,
              "document_mode": mode, "errors": errors, "network_requests": network,
              "scope": "offline view interactions over retained evidence; not a new native simulation"}
    (output / "browser-report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--browser-executable")
    parser.add_argument("--document-mode", choices=["file", "content"], default="file")
    args = parser.parse_args()
    print(json.dumps(run(args.captures, args.campaign, args.output_dir, executable=args.browser_executable, mode=args.document_mode), indent=2))
