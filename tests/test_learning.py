"""Teaching uses the existing runner; inspection never upgrades a claim."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ciw.cli import main
from ciw.learning import (TOPIC, LEVELS, catalog, lesson, work,
                          inspect_workspace, verify_workspace, replay_workspace)
from ciw.operations.registry import OperationRegistry
from ciw.operations.runner import seal
from ciw.session import Session, read_json, write_json


@pytest.fixture
def retained(tmp_path):
    reply = work(tmp_path / "original")
    assert reply["status"] == "completed"
    return Path(reply["workspace_file"]), reply["result"]


def directory_bytes(directory):
    return {str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def test_curriculum_is_an_outline_and_lessons_are_detached():
    value = catalog()
    assert [book["book"] for book in value["books"]] == ["I", "II", "III", "IV", "V", "VI"]
    assert {book["status"] for book in value["books"]} == {"curriculum_outline"}
    assert value["available_lessons"] == [TOPIC, "oscillator-energy", "oscillator-velocity"]
    content = lesson()
    content["derive"].clear()
    assert len(lesson()["derive"]) == 6
    assert "chronology" in lesson()["history"]["scope"]
