"""The tombstone decision has a deadline, and this is it.

THE DECISION, DEFERRED DELIBERATELY. `evidence_append_only` holds with no
tombstone semantics: payload retirement with retained identity and
provenance edges, and defeasance propagation to downstream canonical
claims, do not exist. So a revocation-compelling source cannot be
honestly onboarded. Taking the bend is a core version increment under
bend_protocol, not a patch.

It is deferred because no such source exists, and building for no
consumer is a proposal wearing measurement's clothes -- the discipline
that stopped the checker optimization at -6%.

WHY IT NEEDS A TRIGGER RATHER THAN A NOTE. The cost is not flat. Today
`EvidencePool` has no persistence layer and legacy records are 0, so the
bend is free: there is nothing stored to migrate and nothing that
predates the semantics. The moment records outlive a process, every
stored record predates them and retrofitting becomes structural.

So the window in which this decision stays cheap closes at a specific,
nameable event -- and a carried-forward note does not close with it. It
survives the event silently, which is exactly how the other items on
that list reached twenty phases. NAME THE EVENT, ASK WHAT GOES RED.

This check is what goes red.
"""

from __future__ import annotations

import pathlib
import re
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

REPO = pathlib.Path(__file__).resolve().parent.parent
POOL = REPO / "evidence" / "pool.py"
REGISTRY = REPO / "architecture" / "invariants.yaml"

#: Names that mean a record can outlive the process that made it. Broad
#: on purpose: a false positive costs one conversation about whether the
#: decision is due, and a false negative costs the window.
PERSISTENCE_MARKERS = (
    r"\bdef\s+(save|load|persist|flush|dump|restore|commit|write_to|read_from)\b",
    r"\bimport\s+(sqlite3|shelve|pickle)\b",
    r"\bfrom\s+(sqlite3|shelve|pickle)\s+import\b",
    r"\bjson\.dump\(", r"\bopen\(", r"\.write_text\(", r"\.write_bytes\(",
)


def _persistence_primitives() -> list[str]:
    source = POOL.read_text()
    return [m.group(0) for pattern in PERSISTENCE_MARKERS
            for m in re.finditer(pattern, source)]


def _tombstone_limitation_still_recorded() -> bool:
    registry = yaml.safe_load(REGISTRY.read_text())
    entry = next(e for e in registry["invariants"] if e["id"] == "evidence_append_only")
    return "TOMBSTONE SEMANTICS ARE ABSENT" in str(entry.get("limitation", ""))


def test_persistence_may_not_land_while_the_tombstone_bend_is_open():
    """THE TRIGGER. Red the moment the window closes.

    Not a check that tombstones exist -- that would be building the thing
    the decision deferred. It checks only that the two facts cannot be
    true at once: records outliving a process, and the semantics for
    retiring one still absent.
    """
    primitives = _persistence_primitives()
    if not primitives:
        return  # the window is open; the deferral holds

    assert not _tombstone_limitation_still_recorded(), (
        "EvidencePool has grown a persistence primitive "
        f"({sorted(set(primitives))}) while evidence_append_only still records "
        "TOMBSTONE SEMANTICS ARE ABSENT.\n\n"
        "The deferral has expired. Until now the bend was free -- nothing "
        "was stored, so nothing predated the semantics. From this commit "
        "every stored record does, and retrofitting is structural.\n\n"
        "This is a DECISION, not a defect, and no measurement resolves it: "
        "take the bend (a core version increment under bend_protocol, "
        "re-running every declared vertical and probe, with an explicit "
        "statement of what is no longer guaranteed), or state why "
        "persistence is admissible without it. Either closes this check. "
        "Deleting it does not."
    )


def test_the_trigger_fires_when_the_event_it_names_occurs(tmp_path, monkeypatch):
    """THE TRIGGER'S OWN REACHABILITY PROOF.

    A check that has never fired is an untested assertion, and this one
    is designed never to fire in the state it ships in -- which is
    exactly the shape that rots unnoticed. So the event is planted and
    the check is required to catch it.
    """
    import tests.test_tombstone_decision_trigger as trigger

    planted = tmp_path / "pool.py"
    planted.write_text("class EvidencePool:\n    def save(self, path):\n        pass\n")
    monkeypatch.setattr(trigger, "POOL", planted)

    assert trigger._persistence_primitives(), "the planted event must be seen"
    assert trigger._tombstone_limitation_still_recorded(), (
        "and the limitation must still be recorded, or the plant proves nothing")

    import pytest as _pytest
    with _pytest.raises(AssertionError, match="deferral has expired"):
        trigger.test_persistence_may_not_land_while_the_tombstone_bend_is_open()


def test_the_deferral_is_recorded_as_a_decision_not_a_note():
    """An item that survives by inertia is indistinguishable from one
    nobody has decided. The registry carries the decision, the trigger
    and the file that enforces it, so the derived register re-emits all
    three on every run."""
    registry = yaml.safe_load(REGISTRY.read_text())
    entry = next(e for e in registry["invariants"] if e["id"] == "evidence_append_only")
    assert entry["awaiting_decision"] is True
    assert "DEFERRED" in entry["decision"]
    assert "EXPIRES" in entry["trigger"]
    assert entry["trigger_enforced_by"] == "tests/test_tombstone_decision_trigger.py"


def test_every_open_decision_states_which_decision_it_is_waiting_on():
    """The property, not the enumeration.

    This assertion first listed the five flagged rows by name. Two were
    then settled and it failed -- correctly, but for the wrong reason:
    it was measuring membership of a set that is supposed to shrink. An
    enumeration is correct exactly until the world changes and then
    fails on the change rather than on a defect.

    What has to hold is the property. A flagged row must say WHICH
    decision it waits on, and a decided row must record the decision and
    stop being flagged. Both directions, so a row cannot be quietly
    unflagged without a resolution, or resolved without unflagging.
    """
    registry = yaml.safe_load(REGISTRY.read_text())
    flagged, decided = [], []
    for entry in registry["invariants"]:
        if entry.get("awaiting_decision"):
            flagged.append(entry)
        if entry.get("decided"):
            decided.append(entry)

    assert flagged, "the mechanism must have subjects or it is untested"
    for entry in flagged:
        assert entry.get("decision"), (
            f"{entry['id']}: flagged as awaiting a decision without stating "
            f"WHICH decision -- that is a note again")
        assert not entry.get("decided"), (
            f"{entry['id']}: both flagged and decided")

    for entry in decided:
        assert not entry.get("awaiting_decision"), (
            f"{entry['id']}: decided and still flagged")
        assert entry["decided"].strip()[:4].isdigit(), (
            f"{entry['id']}: a decision must record WHEN it was taken -- "
            f"undated, it cannot be told from a default nobody chose")


def test_the_tombstone_bend_is_still_among_the_open_ones():
    """The one row this file exists for, asserted by name because it is
    this file's subject rather than a sample of a set."""
    registry = yaml.safe_load(REGISTRY.read_text())
    entry = next(e for e in registry["invariants"] if e["id"] == "evidence_append_only")
    assert entry["awaiting_decision"] is True
    assert entry["deferred_while"], "it is deferred on a condition, not merely open"
