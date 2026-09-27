"""The installed proof gate cannot pass without its negative statement tests.

These tests validate gate selection and XML accounting, not cryptography.
"""
import ast
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]


def gate_contract():
    # Load only the actual test selection and accounting function. Importing
    # provider provisioning helpers is unnecessary for this unit boundary.
    tree = ast.parse((ROOT / "scripts/check_proved_heat.py").read_text(encoding="utf-8"))
    names = {"TESTS", "REQUIRED_NATIVE_TESTS"}
    nodes = [node for node in tree.body if (
        isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)
    ) or (isinstance(node, ast.FunctionDef) and node.name == "check_tests")]
    namespace = {"ET": ET}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "check_proved_heat.py", "exec"), namespace)
    return namespace


def report(tmp_path, names, tag=None):
    suite = ET.Element("testsuite")
    for name in sorted(names):
        case = ET.SubElement(suite, "testcase", name=name)
        if tag and name == "test_native_proof_rejects_rebound_input":
            ET.SubElement(case, tag)
    path = tmp_path / "tests.xml"
    ET.ElementTree(suite).write(path)
    return path


def test_gate_selects_isolation_suite_and_both_real_statement_challenges():
    gate = gate_contract()
    assert "test_proved_heat_isolation.py" in gate["TESTS"]
    assert {"test_native_proof_rejects_rebound_input", "test_native_proof_rejects_rebound_output"} <= gate["REQUIRED_NATIVE_TESTS"]
    assert len(gate["REQUIRED_NATIVE_TESTS"]) >= 5


@pytest.mark.parametrize("missing", ["test_native_proof_rejects_rebound_input", "test_native_proof_rejects_rebound_output"])
def test_missing_negative_test_does_not_satisfy_gate(tmp_path, missing):
    gate = gate_contract()
    with pytest.raises(AssertionError, match="did not run"):
        gate["check_tests"](report(tmp_path, gate["REQUIRED_NATIVE_TESTS"] - {missing}))


@pytest.mark.parametrize("tag", ["skipped", "failure", "error"])
def test_unperformed_or_failed_negative_test_does_not_satisfy_gate(tmp_path, tag):
    gate = gate_contract()
    with pytest.raises(AssertionError, match="no skips"):
        gate["check_tests"](report(tmp_path, gate["REQUIRED_NATIVE_TESTS"], tag))


def test_empty_report_refuses(tmp_path):
    with pytest.raises(AssertionError):
        gate_contract()["check_tests"](report(tmp_path, set()))


def test_complete_synthetic_accounting_fixture_is_counted(tmp_path):
    gate = gate_contract()
    assert gate["check_tests"](report(tmp_path, gate["REQUIRED_NATIVE_TESTS"])) == len(gate["REQUIRED_NATIVE_TESTS"])
