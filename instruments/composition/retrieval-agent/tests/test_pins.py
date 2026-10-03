"""The install contract and the identity written to receipts must agree."""
import tomllib
from pathlib import Path

import pytest

from schematics.pins import JSPT, PLSR, RCI


@pytest.mark.parametrize("extra,pin", [("jspt", JSPT), ("plsr", PLSR), ("rci", RCI)])
def test_install_extras_match_receipt_pins(extra, pin):
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]
    expected = f"git+https://github.com/{pin['repo']}.git@{pin['sha']}"
    assert len(extras[extra]) == 1
    requirement = extras[extra][0]
    assert requirement.split(" @ ", 1)[1] == expected
    assert requirement in extras["kernels"]
