from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module():
    path = ROOT / "scripts" / "build_instrument_surface.py"
    spec = importlib.util.spec_from_file_location("instrument_surface", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_manifest_contract_is_bounded_and_versioned():
    value = module().manifest()
    assert value["schema"] == "notations.instrument.v1"
    assert value["identity"]["maturity"] == "INSTRUMENT"
    assert value["operation"]["semantic_capability"] == "time.sync.v1"
    assert value["implementation"]["network_required"] is False
    assert value["implementation"]["hardware_required"] is False


def test_specimen_and_failure_are_generated_from_real_package(tmp_path):
    tool = module()
    specimen = tool.build_specimen(tmp_path / "surface")
    result = specimen["result"]
    assert result["event_time"] == 203.25
    assert result["variance"] == pytest.approx(0.000005, rel=1e-12, abs=1e-15)
    assert result["operation_id"] == "tbrt.affine-clock-reconcile.v1"
    assert specimen["failure"]["status"] == "refused"
    assert "expected reference" in specimen["failure"]["reason"].lower()


def test_specimen_is_byte_reproducible(tmp_path):
    tool = module()
    left = tmp_path / "left"
    right = tmp_path / "right"
    tool.build_specimen(left)
    tool.build_specimen(right)
    files = ["example_input.json", "example_output.json", "failure.json",
             "figures/overview.svg", "figures/uncertainty.svg", "figures/refusal.svg"]
    assert all((left / name).read_bytes() == (right / name).read_bytes() for name in files)


def test_verification_uses_junit_without_claiming_physical_validation(tmp_path):
    tool = module()
    surface = tmp_path / "surface"
    specimen = tool.build_specimen(surface)
    junit = tmp_path / "tests.xml"
    root = ET.Element("testsuites")
    ET.SubElement(root, "testsuite", tests="7", failures="0", errors="0", skipped="0")
    ET.ElementTree(root).write(junit)
    report = tool.build_verification(surface, specimen, junit=junit, release_evidence=None)
    assert report["junit"]["tests"] == 7
    assert "physical synchronization accuracy" in report["not_claimed"]
    tool.verify_output(surface)


def test_failed_junit_cannot_generate_successful_verification(tmp_path):
    tool = module()
    surface = tmp_path / "surface"
    specimen = tool.build_specimen(surface)
    junit = tmp_path / "tests.xml"
    root = ET.Element("testsuites")
    ET.SubElement(root, "testsuite", tests="1", failures="1", errors="0", skipped="0")
    ET.ElementTree(root).write(junit)
    with pytest.raises(ValueError, match="failures"):
        tool.build_verification(surface, specimen, junit=junit, release_evidence=None)


def test_notebook_is_a_single_viewing_surface_not_an_implementation():
    value = json.loads((ROOT / "notebooks" / "clocksync_demo.ipynb").read_text())
    assert value["nbformat"] == 4
    code = "\n".join("".join(cell.get("source", [])) for cell in value["cells"] if cell["cell_type"] == "code")
    assert "reconcile_payload" in code
    assert "def reconcile" not in code


def test_citation_and_portfolio_documents_exist():
    assert "MPL-2.0" in (ROOT / "CITATION.cff").read_text()
    for name in ("problem.md", "model.md", "verification.md"):
        assert (ROOT / "portfolio" / name).is_file()
