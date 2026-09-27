"""Shim: apply --attempt-execute layer overlay onto coverage report after build.

Used when build_coverage_report.py on a lean tip lacks --attempt-execute.
run_executable_coverage.py prefers native --attempt-execute; falls back here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WORKFLOWS = Path(__file__).resolve().parent
REPORT_JSON = WORKFLOWS / "coverage_report.json"
REPORT_MD = WORKFLOWS / "coverage_report.md"
ATTEMPTS = WORKFLOWS / "executable_evidence" / "attempts.json"


def overlay_attempts(report: dict[str, Any], attempts_doc: dict[str, Any]) -> dict[str, Any]:
    attempts = attempts_doc.get("attempts") or {}
    report["attempt_execute"] = True
    report["executable_inventory"] = attempts_doc.get("inventory")
    statement = report.get("statement") or ""
    if "--attempt-execute" not in statement:
        report["statement"] = (
            statement.rstrip(".")
            + ". Export/teaching emit plus --attempt-execute strongest honest local "
            "paths were exercised; HOST synthetic numerics are distinguished from "
            "native provider sessions; FSRT stays blocked (no fluid-volume.v1); "
            "PROVED_HEAT stays unavailable without SP1 binaries; ESM remains cite_only."
        )
    for run in report.get("representative_runs") or []:
        if run.get("representative_kind") != "unique_computational_config":
            # Still overlay boundary layers from attempts when present
            family = run.get("family")
            attempt = attempts.get(family) or {}
            alayers = attempt.get("layers") or {}
            if alayers and run.get("layers"):
                for key in ("executable", "numerical", "replay"):
                    if key in alayers:
                        run["layers"][key] = alayers[key]
                if alayers.get("checking") == "fail":
                    run["layers"]["checking"] = "fail"
            continue
        family = run.get("family")
        attempt = attempts.get(family) or {}
        alayers = attempt.get("layers") or {}
        if not alayers:
            continue
        layers = dict(run.get("layers") or {})
        layers["executable"] = alayers.get("executable", layers.get("executable"))
        layers["numerical"] = alayers.get("numerical", layers.get("numerical"))
        if alayers.get("checking") == "fail":
            layers["checking"] = "fail"
        layers["replay"] = alayers.get("replay", layers.get("replay"))
        run["layers"] = layers
        for cmd in attempt.get("commands") or []:
            run.setdefault("commands", []).append(cmd)
        run["attempt_path_class"] = attempt.get("path_class")
        run["attempt_note"] = attempt.get("note")
        run["attempt_evidence"] = attempt.get("evidence")
    # Recompute unique-profile layer histogram
    from collections import Counter, defaultdict

    profile_layer_summary: dict[str, Counter] = defaultdict(Counter)
    for run in report.get("representative_runs") or []:
        if run.get("representative_kind") != "unique_computational_config":
            continue
        for layer, st in (run.get("layers") or {}).items():
            profile_layer_summary[layer][st] += 1
    report["layer_counts_representatives"] = {
        k: dict(v) for k, v in profile_layer_summary.items()
    }
    return report


def rewrite_md_histogram(md: str, report: dict[str, Any]) -> str:
    hist = report.get("layer_counts_representatives") or {}
    lines = md.splitlines()
    out: list[str] = []
    in_table = False
    for line in lines:
        if line.startswith("## Layer counts"):
            in_table = True
            out.append(line)
            continue
        if in_table and line.startswith("## "):
            in_table = False
        if in_table and line.startswith("| `") and "|" in line[3:]:
            # | `layer` | hist |
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                layer = parts[0].strip("`")
                cell_map = hist.get(layer) or {}
                cell = ", ".join(f"{st}={n}" for st, n in sorted(cell_map.items())) or "(none)"
                out.append(f"| `{layer}` | {cell} |")
                continue
        out.append(line)
    # Ensure attempt_execute note near Generated line
    text = "\n".join(out)
    if "attempt_execute" not in text:
        text = text.replace(
            "## Catalog exhausted",
            "Attempt-execute overlay applied (strongest honest local paths).\n\n## Catalog exhausted",
            1,
        )
    return text if text.endswith("\n") else text + "\n"


def apply(report_json: Path = REPORT_JSON, report_md: Path = REPORT_MD, attempts_path: Path = ATTEMPTS) -> dict[str, Any]:
    attempts_doc = json.loads(attempts_path.read_text(encoding="utf-8"))
    report = json.loads(report_json.read_text(encoding="utf-8"))
    report = overlay_attempts(report, attempts_doc)
    report_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if report_md.is_file():
        report_md.write_text(
            rewrite_md_histogram(report_md.read_text(encoding="utf-8"), report),
            encoding="utf-8",
        )
    return {
        "report_json": str(report_json),
        "attempt_execute": True,
        "families": sorted((attempts_doc.get("attempts") or {}).keys()),
    }


if __name__ == "__main__":
    print(json.dumps(apply(), indent=2))
