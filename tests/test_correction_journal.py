"""Dependency reviews change serving projections, never retained science."""

from copy import deepcopy
import json

import pytest

from ciw import correction_journal as journal_module
from ciw.core.identities import content_identity, new_identity
from ciw.correction_journal import CorrectionJournal


OLD_EVIDENCE = "sha256:" + "a" * 64
NEW_EVIDENCE = "sha256:" + "b" * 64


@pytest.fixture
def graph():
    return {
        OLD_EVIDENCE: {"kind": "evidence", "dependencies": []},
        NEW_EVIDENCE: {"kind": "evidence", "dependencies": []},
        "source:old": {"kind": "source", "source_kind": "machine-manifest",
                       "evidence_id": OLD_EVIDENCE, "dependencies": [OLD_EVIDENCE]},
        "source:new": {"kind": "source", "source_kind": "machine-manifest",
                       "evidence_id": NEW_EVIDENCE, "dependencies": [NEW_EVIDENCE]},
        "execution:old": {"kind": "execution", "dependencies": ["source:old"]},
        "result:old": {"kind": "result", "dependencies": ["execution:old"]},
        "view:old": {"kind": "representation", "dependencies": ["result:old"]},
        "execution:new": {"kind": "execution", "dependencies": ["source:new"]},
        "result:new": {"kind": "result", "dependencies": ["execution:new"]},
    }


def propose(journal, graph, **updates):
    return journal.propose({"old_source_id": "source:old", "new_source_id": "source:new",
                            "kind": "calibration_assumptions", "reason": "Revise the declared encoder scale.",
                            **updates}, graph)


def review(journal, graph, correction, decision="accept", **updates):
    return journal.review({"correction_id": correction["correction_id"], "decision": decision,
                           "expected_revision": journal.revision,
                           "reviewer": "Operator declared in this fixture",
                           "reason": "Use the replacement for current computations.", **updates}, graph)


def claim(journal, graph, dependencies=None, **updates):
    return journal.add_claim({"claim_type": "estimated", "predicate": "Encoder travel estimate is 2 m.",
                              "scope": "Retained encoder sample in the declared fixture",
                              "basis": "Arithmetic from the declared calibration scale",
                              "dependencies": dependencies or ["result:old"], **updates}, graph)


def reseal(value):
    value["record_digest"] = content_identity({key: child for key, child in value.items()
                                               if key != "record_digest"})
    return value


def corrupt(value, mutate):
    value = deepcopy(value)
    mutate(value)
    for event in value["events"]:
        reseal(event)
    return reseal(value)


def statuses(journal, graph):
    return {identity: record["status"] for identity, record in journal.status(graph)["artifact_status"].items()}


def test_proposal_is_inert_and_review_is_not_a_verification(graph):
    journal = CorrectionJournal()
    before = deepcopy(graph)
    correction = propose(journal, graph)
    assert journal.revision == 1
    assert set(statuses(journal, graph).values()) == {"current"}
    assert journal.status(graph)["corrections"][0]["status"] == "proposed"
    assert correction["old_evidence_id"] == OLD_EVIDENCE
    assert correction["new_evidence_id"] == NEW_EVIDENCE
    decision = review(journal, graph, correction)
    assert decision["decision_id"].startswith("decision-")
    assert decision["reviewer_identity_basis"] == "caller_declared_not_authenticated"
    for event in journal.serialize()["events"]:
        assert event["verification_status"] == "not_verified" and event["verification_id"] is None
        assert event["state_admission"] == "unadmitted" and event["execution_authorized"] is False
    assert journal.status(graph)["corrections"][0]["status"] == "accepted"
    assert graph == before


def test_acceptance_invalidates_transitive_claims_and_multi_input_descendants(graph):
    journal = CorrectionJournal()
    initial = claim(journal, graph)
    second = claim(journal, graph, [initial["claim_id"], "result:new"], claim_type="predicted")
    correction = propose(journal, graph)
    review(journal, graph, correction)
    current = journal.status(graph)["artifact_status"]
    stale = {"source:old", "execution:old", "result:old", "view:old", initial["claim_id"], second["claim_id"]}
    assert {identity for identity, record in current.items() if record["status"] == "stale"} == stale
    assert all(current[identity]["stale_by"] == [correction["correction_id"]] for identity in stale)
    assert current[OLD_EVIDENCE]["status"] == "current"
    assert current["source:new"]["status"] == current["result:new"]["status"] == "current"
    assert journal.list_claims() == [initial, second]


def test_later_aliases_and_descendants_cannot_bypass_accepted_staleness(graph):
    journal = CorrectionJournal()
    correction = propose(journal, graph)
    review(journal, graph, correction)
    graph["source:later-label"] = {"kind": "source", "source_kind": "machine-manifest",
                                    "evidence_id": OLD_EVIDENCE, "dependencies": [OLD_EVIDENCE]}
    graph["execution:late"] = {"kind": "execution", "dependencies": ["source:later-label"]}
    graph["result:late"] = {"kind": "result", "dependencies": ["execution:late", "result:new"]}
    late_claim = claim(journal, graph, ["result:late"])
    current = statuses(journal, graph)
    assert all(current[identity] == "stale" for identity in
               ("source:later-label", "execution:late", "result:late", late_claim["claim_id"]))
    assert current["result:new"] == current[OLD_EVIDENCE] == "current"
    retained = journal.serialize()
    restored = CorrectionJournal.restore(retained, graph)
    assert restored.serialize() == retained and restored.status(graph) == journal.status(graph)


def test_rejection_is_final_but_does_not_invalidate(graph):
    journal = CorrectionJournal()
    correction = propose(journal, graph)
    decision = review(journal, graph, correction, "reject")
    assert set(statuses(journal, graph).values()) == {"current"}
    assert journal.status(graph)["corrections"][0]["status"] == "rejected"
    before = journal.serialize()
    with pytest.raises(ValueError, match="final decision"):
        review(journal, graph, correction)
    assert journal.serialize() == before
    assert journal.list_reviews() == [decision]


@pytest.mark.parametrize("claim_type", ["verified", "observed", "admitted", [], True])
def test_claim_types_cannot_promote_authority(graph, claim_type):
    journal = CorrectionJournal()
    with pytest.raises(ValueError, match="estimated or predicted"):
        claim(journal, graph, claim_type=claim_type)
    assert journal.revision == 0


@pytest.mark.parametrize("field,value", [("verification_status", "verified"),
                                         ("state_admission", "admitted"),
                                         ("execution_authorized", True),
                                         ("verification_id", "verification-fake")])
def test_unknown_claim_authority_fields_are_refused(graph, field, value):
    journal = CorrectionJournal()
    with pytest.raises(ValueError, match="fields must be exactly"):
        claim(journal, graph, **{field: value})
    assert journal.revision == 0


@pytest.mark.parametrize("dependencies", [["missing"], ["result:old", "result:old"],
                                          [], [True], "result:old"])
def test_claim_requires_known_distinct_dependencies(graph, dependencies):
    journal = CorrectionJournal()
    payload = {"claim_type": "estimated", "predicate": "Estimate", "scope": "Fixture",
               "basis": "Declared parameters", "dependencies": dependencies}
    with pytest.raises(ValueError):
        journal.add_claim(payload, graph)
    assert journal.revision == 0


@pytest.mark.parametrize("change", [
    lambda g: g["result:old"].update(dependencies=["missing"]),
    lambda g: g["source:old"].update(dependencies=["view:old"]),
    lambda g: g["result:new"].update(dependencies=["result:new"]),
    lambda g: g["result:new"].update(dependencies=["source:new", "source:new"]),
])
def test_missing_graph_refs_cycles_and_duplicate_edges_refuse_before_append(graph, change):
    journal = CorrectionJournal()
    change(graph)
    with pytest.raises(ValueError):
        claim(journal, graph)
    assert journal.revision == 0


@pytest.mark.parametrize("changes", [
    {"old_source_id": "result:old"}, {"new_source_id": "missing"},
    {"new_source_id": "source:old"}, {"reason": ""}, {"kind": True},
])
def test_proposal_requires_existing_compatible_source_content(graph, changes):
    journal = CorrectionJournal()
    with pytest.raises(ValueError):
        propose(journal, graph, **changes)
    assert journal.revision == 0


def test_same_evidence_alias_is_not_a_correction_and_kind_must_match(graph):
    journal = CorrectionJournal()
    graph["source:new"]["evidence_id"] = OLD_EVIDENCE
    with pytest.raises(ValueError, match="distinct source and evidence"):
        propose(journal, graph)
    graph["source:new"]["evidence_id"] = NEW_EVIDENCE
    graph["source:new"]["source_kind"] = "different-interpretation"
    with pytest.raises(ValueError, match="same source_kind"):
        propose(journal, graph)
    assert journal.revision == 0


@pytest.mark.parametrize("expected_revision", [0, 2, True, -1])
def test_review_concurrency_revision_is_strict(graph, expected_revision):
    journal = CorrectionJournal()
    correction = propose(journal, graph)
    before = journal.serialize()
    with pytest.raises(ValueError, match="revision conflict"):
        review(journal, graph, correction, expected_revision=expected_revision)
    assert journal.serialize() == before


def test_review_requires_known_proposal_and_exactly_one_final_decision(graph):
    journal = CorrectionJournal()
    with pytest.raises(ValueError, match="missing or future"):
        review(journal, graph, {"correction_id": "correction-" + "a" * 32})
    correction = propose(journal, graph)
    review(journal, graph, correction)
    before = journal.serialize()
    with pytest.raises(ValueError, match="final decision"):
        review(journal, graph, correction, "reject")
    assert journal.serialize() == before


def test_acceptance_cannot_use_an_already_stale_source_or_replacement(graph):
    journal = CorrectionJournal()
    correction = propose(journal, graph)
    duplicate = propose(journal, graph)
    review(journal, graph, correction)
    with pytest.raises(ValueError, match="already-stale"):
        review(journal, graph, duplicate)
    reverse = propose(journal, graph, old_source_id="source:new", new_source_id="source:old")
    with pytest.raises(ValueError, match="already-stale"):
        review(journal, graph, reverse)


def test_replacement_is_not_a_computational_descendant_of_withdrawn_source(graph):
    graph["source:new"]["dependencies"].append("result:old")
    journal = CorrectionJournal()
    correction = propose(journal, graph)
    with pytest.raises(ValueError, match="cannot depend"):
        review(journal, graph, correction)
    assert journal.revision == 1
    assert set(statuses(journal, graph).values()) == {"current"}


def test_sequential_replacement_history_does_not_make_new_source_stale(graph):
    evidence = "sha256:" + "c" * 64
    graph[evidence] = {"kind": "evidence", "dependencies": []}
    graph["source:third"] = {"kind": "source", "source_kind": "machine-manifest",
                             "evidence_id": evidence, "dependencies": [evidence]}
    journal = CorrectionJournal()
    first = propose(journal, graph)
    review(journal, graph, first)
    second = propose(journal, graph, old_source_id="source:new", new_source_id="source:third")
    review(journal, graph, second)
    assert statuses(journal, graph)["source:third"] == "current"
    assert statuses(journal, graph)["source:old"] == statuses(journal, graph)["source:new"] == "stale"
    restored = CorrectionJournal.restore(journal.serialize(), graph)
    assert restored.status(graph) == journal.status(graph)


def test_saved_journal_restores_exactly_without_provider_execution(tmp_path, graph, monkeypatch):
    journal = CorrectionJournal()
    claim(journal, graph)
    correction = propose(journal, graph)
    review(journal, graph, correction)
    path = tmp_path / "journal.json"
    path.write_text(json.dumps(journal.serialize()), encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("Offline restore attempted scientific execution")

    monkeypatch.setattr("ciw.operations.runner.execute", forbidden)
    monkeypatch.setattr("ciw.operations.registry.default_registry", forbidden)
    restored = CorrectionJournal.restore(json.loads(path.read_text(encoding="utf-8")), graph)
    assert restored.serialize() == journal.serialize()
    assert restored.status(graph) == journal.status(graph)


def test_deep_copies_protect_claims_events_and_graph(graph):
    journal = CorrectionJournal()
    before = deepcopy(graph)
    initial = claim(journal, graph)
    correct = deepcopy(initial)
    initial["dependencies"].clear()
    initial["predicate"] = "Caller changed returned value"
    exported = journal.serialize()
    exported["events"].clear()
    projected = journal.status(graph)
    projected["claims"][0]["dependencies"].clear()
    projected["artifact_status"].clear()
    assert journal.list_claims() == [correct] and graph == before


@pytest.mark.parametrize("mutate,match", [
    (lambda v: v["events"][0].update(verification_status="verified"), "cannot confer"),
    (lambda v: v["events"][0].update(execution_authorized=1), "cannot confer"),
    (lambda v: v["events"][0].update(state_admission="admitted"), "cannot confer"),
    (lambda v: v["events"][0].update(revision=True), "revision order"),
    (lambda v: v["events"][0].update(created_at="2026-01-01T00:00:00"), "timezone"),
    (lambda v: v["events"][0].update(dependencies=["missing"]), "missing artifact"),
    (lambda v: v["events"][0].update(extra_permission="operate"), "fields must be exactly"),
    (lambda v: v.update(revision=True), "revision or event count"),
])
def test_resealed_forgeries_cannot_bypass_semantic_checks(graph, mutate, match):
    journal = CorrectionJournal()
    claim(journal, graph)
    with pytest.raises(ValueError, match=match):
        CorrectionJournal.restore(corrupt(journal.serialize(), mutate), graph)


def test_unsealed_tampering_is_refused(graph):
    journal = CorrectionJournal()
    claim(journal, graph)
    value = journal.serialize()
    value["events"][0]["predicate"] = "Changed without seal"
    with pytest.raises(ValueError, match="integrity mismatch"):
        CorrectionJournal.restore(value, graph)


def test_restore_refuses_source_bindings_that_differ_from_proposal(graph):
    journal = CorrectionJournal()
    propose(journal, graph)
    retained = journal.serialize()
    graph["source:new"]["evidence_id"] = "sha256:" + "c" * 64
    with pytest.raises(ValueError, match="source binding mismatch"):
        CorrectionJournal.restore(retained, graph)
    with pytest.raises(ValueError, match="source binding mismatch"):
        journal.status(graph)


def test_restore_refuses_future_claim_links_and_out_of_order_decisions(graph):
    journal = CorrectionJournal()
    first = claim(journal, graph)
    second = claim(journal, graph, [first["claim_id"]])
    forward = corrupt(journal.serialize(), lambda v: v["events"][0].update(dependencies=[second["claim_id"]]))
    with pytest.raises(ValueError, match="future claim"):
        CorrectionJournal.restore(forward, graph)
    journal = CorrectionJournal()
    correction = propose(journal, graph)
    review(journal, graph, correction)
    value = journal.serialize()
    value["events"].reverse()
    for index, event in enumerate(value["events"], 1):
        event["revision"] = index
        event["created_at"] = "2026-10-03T04:00:00+00:00"
        if event["event_type"] == "correction.review":
            event["expected_revision"] = index - 1
        reseal(event)
    with pytest.raises(ValueError, match="missing or future correction"):
        CorrectionJournal.restore(reseal(value), graph)


def test_restore_refuses_duplicate_reviews_even_with_fresh_identity_and_seals(graph):
    journal = CorrectionJournal()
    correction = propose(journal, graph)
    review(journal, graph, correction)
    value = journal.serialize()
    duplicate = deepcopy(value["events"][-1])
    duplicate.update(decision_id=new_identity("decision"), revision=3, expected_revision=2)
    value["events"].append(reseal(duplicate))
    value["revision"] = 3
    with pytest.raises(ValueError, match="final decision"):
        CorrectionJournal.restore(reseal(value), graph)


def test_restore_refuses_duplicate_event_ids_and_reversed_timestamps(graph):
    journal = CorrectionJournal()
    first = claim(journal, graph)
    claim(journal, graph)
    value = corrupt(journal.serialize(), lambda v: v["events"][1].update(claim_id=first["claim_id"]))
    with pytest.raises(ValueError, match="collides|Duplicate"):
        CorrectionJournal.restore(value, graph)
    value = journal.serialize()
    value["events"][0]["created_at"] = "2026-10-03T04:01:00Z"
    value["events"][1]["created_at"] = "2026-10-03T04:00:00Z"
    for event in value["events"]:
        reseal(event)
    with pytest.raises(ValueError, match="timestamps are out of order"):
        CorrectionJournal.restore(reseal(value), graph)


def test_event_and_byte_bounds_do_not_partially_append(graph, monkeypatch):
    monkeypatch.setattr(journal_module, "MAX_EVENTS", 2)
    journal = CorrectionJournal()
    claim(journal, graph)
    claim(journal, graph)
    before = journal.serialize()
    with pytest.raises(ValueError, match="event capacity"):
        claim(journal, graph)
    assert journal.serialize() == before
    journal = CorrectionJournal()
    monkeypatch.setattr(journal_module, "MAX_BYTES", 1)
    before = journal.serialize()
    with pytest.raises(ValueError, match="byte capacity"):
        claim(journal, graph)
    assert journal.serialize() == before


def test_empty_journal_restore_is_a_valid_noop(graph):
    original = CorrectionJournal()
    restored = CorrectionJournal.restore(original.serialize(), graph)
    assert restored.serialize() == original.serialize()
    assert restored.revision == 0 and restored.status(graph)["corrections"] == []
