"""Actual generated-file Chromium inspection; not an engine or GPU benchmark."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(html: Path, output: Path, executable: str | None = None, mode: str = "file") -> dict:
    output.mkdir(parents=True, exist_ok=False)
    checks, errors, requests = [], [], []
    def require(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, **({"executable_path": executable} if executable else {}))
        page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("request", lambda r: requests.append(r.url))
        if mode == "file":
            page.goto(html.resolve().as_uri())
        else:
            page.set_content(html.read_text(encoding="utf-8"))
        require(page.locator("section.card").count() == 4, "four_actual_variants")
        require(page.locator("svg circle").count() == 28, "28_retained_scalar_samples")
        require(page.locator(".summary tbody tr").count() == 4, "all_comparisons_listed")
        require(page.locator("script, iframe, img").count() == 0, "no_executable_or_remote_elements")
        page.screenshot(path=str(output / "desktop.png"), full_page=True)
        page.locator('a[href="#variant-3"]').click()
        require(page.url.endswith("#variant-3"), "variant_navigation")
        summary = page.locator("#variant-3 summary")
        summary.focus()
        page.keyboard.press("Enter")
        require(page.locator("#variant-3 details").get_attribute("open") is not None, "keyboard_disclosure")
        require(page.locator("#variant-3 tbody tr").count() == 7, "exact_values_accessible")
        for width in (700, 390):
            page.set_viewport_size({"width": width, "height": 844})
            require(not page.evaluate("document.documentElement.scrollWidth > innerWidth"), f"no_page_overflow_{width}")
            page.screenshot(path=str(output / f"width-{width}.png"), full_page=True)
        require(all(url.startswith("file:") for url in requests), "no_network_requests")
        require(not errors, "no_browser_errors")
        version = browser.version
        browser.close()
    report = {"status": "passed", "browser": version, "document_mode": mode, "checks": checks,
              "count": len(checks), "errors": errors, "requests": requests}
    (output / "browser-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--browser-executable")
    parser.add_argument("--document-mode", choices=["file", "content"], default="file")
    args = parser.parse_args()
    print(json.dumps(run(args.html, args.output_dir, args.browser_executable, args.document_mode), indent=2))
