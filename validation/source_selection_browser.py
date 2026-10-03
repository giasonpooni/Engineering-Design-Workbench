"""Exercise the actual script-free source inspector in Chromium, with no server."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--browser-executable", type=Path, help="Explicit local browser; CI uses pinned Playwright Chromium")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    checks, errors, requests = [], [], []
    with sync_playwright() as runtime:
        launch = {"headless": True}
        if args.browser_executable:
            launch["executable_path"] = str(args.browser_executable)
        browser = runtime.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.on("request", lambda request: requests.append(request.url) if not request.url.startswith("file:") else None)
        page.goto(args.html.resolve().as_uri(), wait_until="load")
        assert "compute_statistics" in page.locator("#selected-code").inner_text()
        checks.append("actual selected source rendered")
        assert page.locator("script").count() == 0
        checks.append("no script element")
        page.get_by_role("link", name="Mathematics", exact=True).click()
        assert page.url.endswith("#math")
        checks.append("mathematical section navigation")
        page.locator("#math summary").first.click()
        assert page.locator("#math details").first.get_attribute("open") is not None
        checks.append("declaration disclosure opens")
        page.get_by_role("link", name="Evidence", exact=True).click()
        assert page.url.endswith("#evidence")
        checks.append("evidence section navigation")
        for width in (1280, 700, 390):
            page.set_viewport_size({"width": width, "height": 900})
            page.evaluate("window.scrollTo(0,0)")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            page.screenshot(path=str(args.output_dir / f"width-{width}.png"), full_page=True)
            checks.append(f"responsive width {width}")
        assert not errors and not requests, (errors, requests)
        checks.append("no browser errors or non-file requests")
        browser.close()
    report = {"status": "passed", "document_mode": "file", "count": len(checks),
              "checks": checks, "errors": errors, "network_requests": requests}
    (args.output_dir / "browser-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
