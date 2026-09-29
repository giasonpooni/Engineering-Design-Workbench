"""Generate the canonical ClockSync portfolio and verification surface.

The scientific computation is delegated to the installed tbrt package. This
script produces representations/evidence; it does not modify clock.py.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import html
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET

from tbrt.cli import example_payload, reconcile_payload

ROOT = Path(__file__).resolve().parents[1]


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def write_json(path: Path, value) -> None:
    path.write_bytes(json_bytes(value))


def manifest() -> dict:
    value = json.loads((ROOT / "instrument.json").read_text(encoding="utf-8"))
    required = {"schema", "identity", "operation", "implementation", "model", "inputs",
                "outputs", "verification", "representations", "limits"}
    if set(value) != required or value["schema"] != "notations.instrument.v1":
        raise ValueError("invalid instrument manifest")
    if value["identity"]["maturity"] not in {"EXPERIMENT", "REFERENCE", "INSTRUMENT", "RELEASE"}:
        raise ValueError("unknown instrument maturity")
    if value["operation"]["id"] != "tbrt.affine-clock-reconcile.v1":
        raise ValueError("manifest numerical operation differs from package contract")
    if value["operation"]["semantic_capability"] != "time.sync.v1":
        raise ValueError("semantic capability identity mismatch")
    if value["implementation"]["network_required"] is not False or value["implementation"]["hardware_required"] is not False:
        raise ValueError("ClockSync standalone profile must remain local/headless")
    return value


def svg(title: str, lines: list[str], *, accent="#1f6feb") -> bytes:
    safe_title = html.escape(title)
    text = []
    y = 86
    for line in lines:
        text.append(f'<text x="48" y="{y}" font-size="20" font-family="ui-monospace, monospace">{html.escape(str(line))}</text>')
        y += 38
    height = max(250, y + 30)
    body = "".join(text)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}">'
        '<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<rect x="0" y="0" width="14" height="{height}" fill="{accent}"/>'
        f'<text x="48" y="44" font-size="28" font-family="system-ui, sans-serif" font-weight="700">{safe_title}</text>'
        f'{body}</svg>\n'
    ).encode()


def build_specimen(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    figures = output / "figures"
    figures.mkdir()

    request = example_payload("offset")
    result = reconcile_payload(request)
    if result["event_time"] != 203.25 or not math.isclose(
            result["variance"], 0.000005, rel_tol=1e-12, abs_tol=1e-15):
        raise AssertionError("canonical ClockSync specimen changed")
    if result["operation_id"] != manifest()["operation"]["id"]:
        raise AssertionError("specimen operation identity differs from manifest")

    refused = deepcopy(request)
    refused["expected_reference"] = {
        "clock_id": "synthetic:wrong-reference",
        "time_scale": "reference-monotonic",
        "unit": "s",
    }
    try:
        reconcile_payload(refused)
    except ValueError as exc:
        failure = {
            "schema": "notations.refusal-example.v1",
            "status": "refused",
            "case": "wrong-reference-frame",
            "reason_type": type(exc).__name__,
            "reason": str(exc),
        }
    else:
        raise AssertionError("deliberate wrong-reference specimen was unexpectedly accepted")

    files = {
        "example_input.json": json_bytes(request),
        "example_output.json": json_bytes(result),
        "failure.json": json_bytes(failure),
        "figures/overview.svg": svg("ClockSync · canonical specimen", [
            f"device timestamp      {request['observation']['device_time']:.6f} s",
            f"reference origin      {request['model']['reference_origin']:.6f} s",
            f"mapped event          {result['event_time']:.6f} s",
            "source observation retained",
        ]),
        "figures/uncertainty.svg": svg("ClockSync · propagated timing uncertainty", [
            f"variance              {result['variance']:.9g} s²",
            f"standard uncertainty  {result['standard_uncertainty']:.9g} s",
            "method                first-order J C Jᵀ",
            "claim                 not a confidence interval",
        ], accent="#8250df"),
        "figures/refusal.svg": svg("ClockSync · refusal specimen", [
            "candidate             wrong reference frame",
            "outcome               REFUSED",
            failure["reason"],
            "no result coordinate emitted",
        ], accent="#cf222e"),
    }
    for name, raw in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return {
        "request": request,
        "result": result,
        "failure": failure,
        "files": {name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in files.items()},
    }


def junit_summary(path: Path | None) -> dict:
    if path is None:
        return {"tests": None, "failures": None, "errors": None, "skipped": None}
    suites = list(ET.parse(path).getroot().iter("testsuite"))
    result = {name: sum(int(s.attrib.get(name, 0)) for s in suites)
              for name in ("tests", "failures", "errors", "skipped")}
    if result["failures"] or result["errors"]:
        raise ValueError("verification JUnit contains failures/errors")
    return result


def source_revision() -> str:
    value = os.environ.get("GITHUB_SHA")
    if value:
        return value
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def build_verification(output: Path, specimen: dict, *, junit: Path | None,
                       release_evidence: Path | None) -> dict:
    release = None
    if release_evidence is not None and release_evidence.is_file():
        release = json.loads(release_evidence.read_text(encoding="utf-8"))
    report = {
        "schema": "notations.verification.v1",
        "instrument": manifest()["identity"],
        "operation_id": manifest()["operation"]["id"],
        "source_revision": source_revision(),
        "platform": platform.platform(),
        "python": sys.version,
        "junit": junit_summary(junit),
        "reference_cases": 1,
        "refusal_cases": 1,
        "canonical_result": {
            "event_time": specimen["result"]["event_time"],
            "variance": specimen["result"]["variance"],
            "standard_uncertainty": specimen["result"]["standard_uncertainty"],
        },
        "specimen_files": specimen["files"],
        "release_evidence": release,
        "claims": [
            "canonical synthetic specimen reproduced",
            "deliberate wrong-reference request refused",
            "manifest and numerical operation identity agree",
        ],
        "not_claimed": [
            "physical synchronization accuracy",
            "metrological traceability",
            "correctness of the caller-supplied clock model",
            "confidence interval or guaranteed error bound",
            "PyPI publication",
        ],
    }
    write_json(output / "verification.json", report)
    card = {
        "schema": "notations.instrument-card.v1",
        "name": "ClockSync",
        "operation": "time.sync.v1",
        "version": manifest()["identity"]["version"],
        "maturity": manifest()["identity"]["maturity"],
        "language": "Python",
        "runtime": "CPython 3.11+",
        "tests": report["junit"]["tests"],
        "examples": 3,
        "input": "timestamp + affine model + joint covariance",
        "output": "reference timestamp + propagated timing uncertainty",
        "deterministic": True,
        "network": False,
        "hardware": False,
        "source_revision": report["source_revision"],
    }
    write_json(output / "instrument-card.json", card)
    (output / "instrument.json").write_bytes((ROOT / "instrument.json").read_bytes())
    return report


def verify_output(output: Path) -> None:
    expected = {"instrument.json", "instrument-card.json", "verification.json",
                "example_input.json", "example_output.json", "failure.json", "figures"}
    if {p.name for p in output.iterdir()} != expected:
        raise ValueError("instrument surface contains missing/unexpected top-level files")
    for name in ("overview.svg", "uncertainty.svg", "refusal.svg"):
        raw = (output / "figures" / name).read_bytes()
        if not raw.startswith(b"<svg ") or len(raw) > 65536:
            raise ValueError("invalid generated SVG")
    report = json.loads((output / "verification.json").read_text(encoding="utf-8"))
    if report["schema"] != "notations.verification.v1":
        raise ValueError("verification schema mismatch")
    if report["canonical_result"]["event_time"] != 203.25:
        raise ValueError("canonical output mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--release-evidence", type=Path)
    args = parser.parse_args()
    manifest()
    specimen = build_specimen(args.output_dir)
    build_verification(args.output_dir, specimen, junit=args.junit,
                       release_evidence=args.release_evidence)
    verify_output(args.output_dir)
    print(json.dumps({"status": "generated", "output_dir": str(args.output_dir),
                      "source_revision": source_revision()}, sort_keys=True))


if __name__ == "__main__":
    main()
