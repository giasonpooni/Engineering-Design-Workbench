"""Append-only dependency reviews and bounded, unverified scientific claims.

The journal never modifies source, execution, result, or verification records.
An accepted review withdraws a source from *current dependency use*; the source
bytes and their historical applicability remain evidence. Reviewer names are
caller declarations, not authenticated principals. Seals establish content
integrity, not physical validity, state admission, or execution authority.
"""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
import threading
import uuid

from .core.identities import content_identity, new_identity, validate_identity
from .core.records import finite_tree


SCHEMA = "ciw.correction-journal.v1"
EVENT_SCHEMA = "ciw.correction-event.v1"
MAX_EVENTS = 1024
MAX_BYTES = 2 * 1024 * 1024
MAX_DEPENDENCIES = 64
MAX_GRAPH_NODES = 32768
MAX_GRAPH_EDGES = 262144
_BASE = {"schema", "event_type", "revision", "created_at", "record_digest"}
_LIMITS = {
    "verification_status": "not_verified", "verification_id": None,
    "state_admission": "unadmitted", "execution_authorized": False,
}
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _fields(value, expected, name):
    _require(isinstance(value, dict) and set(value) == expected,
             f"{name} fields must be exactly: " + ", ".join(sorted(expected)))


def _text(value, name, maximum=4096):
    _require(isinstance(value, str) and bool(value.strip()) and len(value) <= maximum,
             f"{name} must be a nonempty string of at most {maximum} characters")
    return value


def _timestamp(value):
    _require(isinstance(value, str) and _TIMESTAMP.fullmatch(value) is not None,
             "Journal created_at must be an ISO timestamp with seconds and timezone")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Journal created_at must be a valid timezone-aware timestamp") from exc
    _require(instant.utcoffset() is not None, "Journal created_at must include a timezone")
    return instant


def _event_identity(value, prefix):
    if prefix == "decision":
        return validate_identity(value, prefix)
    _require(isinstance(value, str) and re.fullmatch(prefix + r"-[0-9a-f]{32}", value) is not None,
             f"Invalid {prefix} identity")
    return value


def _sealed(record):
    result = deepcopy(record)
    result["record_digest"] = content_identity({key: value for key, value in result.items()
                                                 if key != "record_digest"})
    return result


def _check_seal(record):
    _require(isinstance(record, dict) and record.get("record_digest") ==
             content_identity({key: value for key, value in record.items() if key != "record_digest"}),
             "Correction journal content integrity mismatch")


def _dependencies(value, name):
    _require(isinstance(value, list) and 0 < len(value) <= MAX_DEPENDENCIES,
             f"{name} must contain 1 to {MAX_DEPENDENCIES} dependencies")
    for identity in value:
        _text(identity, "Dependency identity", 512)
    _require(len(value) == len(set(value)), "Dependencies must not contain duplicate identities")
    return value


def _graph(value):
    """Validate a trusted, explicit computational DAG without importing code."""
    _require(isinstance(value, dict) and len(value) <= MAX_GRAPH_NODES,
             "Artifact graph is malformed or exceeds the node bound")
    result = deepcopy(value)
    edge_count = 0
    for identity, node in result.items():
        _text(identity, "Artifact identity", 512)
        _require(isinstance(node, dict), "Artifact graph nodes must be objects")
        finite_tree(node, "artifact graph node")
        _text(node.get("kind"), "Artifact kind", 128)
        dependencies = node.get("dependencies")
        _require(isinstance(dependencies, list), "Artifact graph dependencies must be a list")
        for dependency in dependencies:
            _text(dependency, "Artifact dependency", 512)
            _require(dependency in result, "Artifact graph contains a missing dependency")
        _require(len(dependencies) == len(set(dependencies)), "Artifact graph contains duplicate dependencies")
        edge_count += len(dependencies)
        _require(edge_count <= MAX_GRAPH_EDGES, "Artifact graph exceeds the dependency bound")
        if node["kind"] == "source":
            _text(node.get("source_kind"), "Source kind", 128)
            _text(node.get("evidence_id"), "Source evidence identity", 512)
    _acyclic(result)
    return result


def _acyclic(graph):
    """Use iterative topological traversal rather than unbounded recursion."""
    parents = {identity: len(node["dependencies"]) for identity, node in graph.items()}
    children = {identity: [] for identity in graph}
    for identity, node in graph.items():
        for dependency in node["dependencies"]:
            _require(dependency in graph, "Artifact graph contains a missing dependency")
            children[dependency].append(identity)
    pending = deque(identity for identity, count in parents.items() if count == 0)
    visited = 0
    while pending:
        current = pending.popleft()
        visited += 1
        for child in children[current]:
            parents[child] -= 1
            if parents[child] == 0:
                pending.append(child)
    _require(visited == len(graph), "Artifact dependencies contain a cycle")


class CorrectionJournal:
    """Append claims, proposed source corrections, and one final review each.

    ``graph`` is a current retained-artifact identity map supplied by the session.
    Staleness is recomputed on each read, including newly added source aliases or
    downstream artifacts. Proposals and rejections have no invalidation effect.
    Historical comparison and replacement links are not computational edges.
    """

    def __init__(self):
        self._events = []
        self._lock = threading.RLock()

    @property
    def revision(self):
        with self._lock:
            return len(self._events)

    def _combined_graph(self, graph, events=None):
        result = _graph(graph)
        for record in self._events if events is None else events:
            kind = record["event_type"]
            if kind == "correction.propose":
                _require(record["correction_id"] not in result,
                         "Correction identity collides with a retained artifact")
                old, new = self._source_pair(record["old_source_id"], record["new_source_id"], result)
                _require((old["source_kind"], old["evidence_id"], new["evidence_id"]) ==
                         (record["source_kind"], record["old_evidence_id"], record["new_evidence_id"]),
                         "Correction proposal source binding mismatch")
                continue
            if kind == "correction.review":
                _require(record["decision_id"] not in result,
                         "Decision identity collides with a retained artifact")
                continue
            if kind != "claim.add":
                continue
            identity = record["claim_id"]
            _require(identity not in result, "Claim identity collides with a retained artifact")
            _require(all(dependency in result for dependency in record["dependencies"]),
                     "Claim refers to a missing artifact or a future claim")
            result[identity] = {"kind": "claim", "dependencies": list(record["dependencies"])}
        _acyclic(result)
        return result

    def _new_event(self, event_type):
        created_at = datetime.now(timezone.utc).isoformat()
        # Wall-clock rollback must not invent reversed journal chronology.
        if self._events and _timestamp(created_at) < _timestamp(self._events[-1]["created_at"]):
            created_at = self._events[-1]["created_at"]
        return {"schema": EVENT_SCHEMA, "event_type": event_type,
                "revision": len(self._events) + 1, "created_at": created_at}

    def _append(self, record):
        _require(len(self._events) < MAX_EVENTS, "Correction journal event capacity exceeded")
        record = _sealed(record)
        prospective = _sealed({"schema": SCHEMA, "revision": len(self._events) + 1,
                               "events": self._events + [record]})
        _require(len(json.dumps(prospective, allow_nan=False).encode("utf-8")) <= MAX_BYTES,
                 "Correction journal byte capacity exceeded")
        self._events.append(record)
        return deepcopy(record)

    def add_claim(self, payload, graph):
        """Retain an estimated/predicted declaration without verifying it."""
        payload = deepcopy(payload)
        _fields(payload, {"claim_type", "predicate", "scope", "basis", "dependencies"}, "Claim payload")
        _require(isinstance(payload["claim_type"], str) and payload["claim_type"] in {"estimated", "predicted"},
                 "Claims must be estimated or predicted")
        for field in ("predicate", "scope", "basis"):
            _text(payload[field], "Claim " + field)
        _dependencies(payload["dependencies"], "Claim dependencies")
        with self._lock:
            combined = self._combined_graph(graph)
            _require(all(dependency in combined for dependency in payload["dependencies"]),
                     "Claim refers to a missing retained artifact")
            record = self._new_event("claim.add")
            record.update(claim_id="claim-" + uuid.uuid4().hex, **payload, **_LIMITS)
            return self._append(record)

    def _source_pair(self, old_id, new_id, graph):
        for identity in (old_id, new_id):
            _text(identity, "Correction source identity", 512)
            _require(identity in graph and graph[identity]["kind"] == "source",
                     "Correction requires two existing retained sources")
        old, new = graph[old_id], graph[new_id]
        _require(old_id != new_id and old["evidence_id"] != new["evidence_id"],
                 "Correction needs distinct source and evidence identities")
        _require(old["source_kind"] == new["source_kind"],
                 "Correction sources must have the same source_kind")
        return old, new

    def propose(self, payload, graph):
        """Record a candidate replacement; do not invalidate anything yet."""
        payload = deepcopy(payload)
        _fields(payload, {"old_source_id", "new_source_id", "kind", "reason"}, "Correction payload")
        _text(payload["kind"], "Correction kind", 128)
        _text(payload["reason"], "Correction reason")
        with self._lock:
            combined = self._combined_graph(graph)
            old, new = self._source_pair(payload["old_source_id"], payload["new_source_id"], combined)
            record = self._new_event("correction.propose")
            record.update(correction_id="correction-" + uuid.uuid4().hex, **payload,
                          source_kind=old["source_kind"], old_evidence_id=old["evidence_id"],
                          new_evidence_id=new["evidence_id"], status="proposed", **_LIMITS)
            return self._append(record)

    def review(self, payload, graph):
        """Accept/reject dependency use only; reviewer identity is declared."""
        payload = deepcopy(payload)
        _fields(payload, {"correction_id", "decision", "expected_revision", "reviewer", "reason"}, "Review payload")
        _event_identity(payload["correction_id"], "correction")
        _require(isinstance(payload["decision"], str) and payload["decision"] in {"accept", "reject"},
                 "Review decision must be accept or reject")
        _text(payload["reviewer"], "Declared reviewer", 512)
        _text(payload["reason"], "Review reason")
        with self._lock:
            _require(type(payload["expected_revision"]) is int and
                     payload["expected_revision"] == len(self._events), "Correction journal revision conflict")
            combined = self._combined_graph(graph)
            self._validate_review_target(payload, combined, self._events)
            record = self._new_event("correction.review")
            record.update(decision_id=new_identity("decision"), **payload,
                          reviewer_identity_basis="caller_declared_not_authenticated", **_LIMITS)
            return self._append(record)

    def _validate_review_target(self, payload, graph, preceding):
        proposals = {event["correction_id"]: event for event in preceding
                     if event["event_type"] == "correction.propose"}
        proposal = proposals.get(payload["correction_id"])
        _require(proposal is not None, "Review refers to a missing or future correction proposal")
        _require(not any(event["event_type"] == "correction.review" and
                         event["correction_id"] == payload["correction_id"] for event in preceding),
                 "Correction proposal already has a final decision")
        old, new = self._source_pair(proposal["old_source_id"], proposal["new_source_id"], graph)
        _require((old["source_kind"], old["evidence_id"], new["evidence_id"]) ==
                 (proposal["source_kind"], proposal["old_evidence_id"], proposal["new_evidence_id"]),
                 "Correction source content differs from its retained proposal")
        if payload["decision"] == "accept":
            projection = self._projection(graph, preceding)
            _require(projection[proposal["old_source_id"]]["status"] == "current" and
                     projection[proposal["new_source_id"]]["status"] == "current",
                     "Cannot accept an already-stale source or replacement")
            # The replacement may be linked in history but must not depend
            # computationally on the source being withdrawn.
            hypothetical = preceding + [{"event_type": "correction.review",
                                           "correction_id": payload["correction_id"], "decision": "accept"}]
            _require(self._projection(graph, hypothetical)[proposal["new_source_id"]]["status"] == "current",
                     "Replacement source cannot depend on the source being corrected")

    @staticmethod
    def _projection(graph, events):
        proposals = {event["correction_id"]: event for event in events
                     if event["event_type"] == "correction.propose"}
        accepted = [proposals[event["correction_id"]] for event in events
                    if event["event_type"] == "correction.review" and event["decision"] == "accept"]
        children = {identity: [] for identity in graph}
        for identity, node in graph.items():
            for dependency in node["dependencies"]:
                children[dependency].append(identity)
        stale = {identity: [] for identity in graph}
        for proposal in accepted:
            # Labels do not create independent evidence. Include aliases added
            # after acceptance while leaving the immutable evidence node alone.
            roots = [identity for identity, node in graph.items()
                     if node["kind"] == "source" and node.get("source_kind") == proposal["source_kind"]
                     and node.get("evidence_id") == proposal["old_evidence_id"]]
            pending, visited = deque(roots), set()
            while pending:
                identity = pending.popleft()
                if identity in visited:
                    continue
                visited.add(identity)
                stale[identity].append(proposal["correction_id"])
                pending.extend(children[identity])
        return {identity: {"artifact_id": identity, "kind": graph[identity]["kind"],
                           "status": "stale" if causes else "current", "stale_by": causes}
                for identity, causes in stale.items()}

    def status(self, graph):
        """Return current-use projections separately from exact retained events."""
        with self._lock:
            combined = self._combined_graph(graph)
            reviews = {event["correction_id"]: event for event in self._events
                       if event["event_type"] == "correction.review"}
            corrections = [{"proposal": deepcopy(event), "review": deepcopy(reviews.get(event["correction_id"])),
                            "status": ("accepted" if reviews[event["correction_id"]]["decision"] == "accept"
                                       else "rejected") if event["correction_id"] in reviews else "proposed"}
                           for event in self._events if event["event_type"] == "correction.propose"]
            return {"revision": len(self._events), "artifact_status": self._projection(combined, self._events),
                    "claims": self.list_claims(), "corrections": corrections}

    snapshot = status

    def list_claims(self):
        with self._lock:
            return deepcopy([event for event in self._events if event["event_type"] == "claim.add"])

    def list_proposals(self):
        with self._lock:
            return deepcopy([event for event in self._events if event["event_type"] == "correction.propose"])

    def list_reviews(self):
        with self._lock:
            return deepcopy([event for event in self._events if event["event_type"] == "correction.review"])

    def serialize(self):
        with self._lock:
            return _sealed({"schema": SCHEMA, "revision": len(self._events), "events": self._events})

    @classmethod
    def restore(cls, value, graph):
        """Validate a full retained journal without computation or code loading."""
        value = deepcopy(value)
        _fields(value, {"schema", "revision", "events", "record_digest"}, "Retained journal")
        _check_seal(value)
        _require(value["schema"] == SCHEMA, "Unsupported correction journal schema")
        _require(isinstance(value["events"], list) and len(value["events"]) <= MAX_EVENTS and
                 type(value["revision"]) is int and value["revision"] == len(value["events"]),
                 "Malformed correction journal revision or event count")
        finite_tree(value, "correction journal")
        _require(len(json.dumps(value, allow_nan=False).encode("utf-8")) <= MAX_BYTES,
                 "Correction journal byte capacity exceeded")
        restored = cls()
        combined = _graph(graph)
        identities = set(combined)
        last_time = None
        for index, event in enumerate(value["events"], 1):
            _require(isinstance(event, dict), "Correction event must be an object")
            _check_seal(event)
            _require(event.get("schema") == EVENT_SCHEMA and type(event.get("revision")) is int
                     and event["revision"] == index, "Correction event revision order is invalid")
            instant = _timestamp(event.get("created_at"))
            _require(last_time is None or instant >= last_time, "Correction event timestamps are out of order")
            last_time = instant
            _require(all(key in event and type(event[key]) is type(expected) and event[key] == expected
                         for key, expected in _LIMITS.items()),
                     "Correction journal cannot confer verification or execution authority")
            kind = event.get("event_type")
            if kind == "claim.add":
                _fields(event, _BASE | set(_LIMITS) | {"claim_id", "claim_type", "predicate", "scope", "basis", "dependencies"}, "Claim event")
                identity = _event_identity(event["claim_id"], "claim")
                _require(isinstance(event["claim_type"], str) and event["claim_type"] in {"estimated", "predicted"},
                         "Claims must be estimated or predicted")
                for field in ("predicate", "scope", "basis"):
                    _text(event[field], "Claim " + field)
                _dependencies(event["dependencies"], "Claim dependencies")
                _require(all(dependency in combined for dependency in event["dependencies"]),
                         "Claim refers to a missing artifact or a future claim")
                _require(identity not in combined, "Claim identity collides with a retained artifact")
                combined[identity] = {"kind": "claim", "dependencies": list(event["dependencies"])}
            elif kind == "correction.propose":
                _fields(event, _BASE | set(_LIMITS) | {"correction_id", "old_source_id", "new_source_id", "kind", "reason", "source_kind", "old_evidence_id", "new_evidence_id", "status"}, "Correction proposal event")
                identity = _event_identity(event["correction_id"], "correction")
                _text(event["kind"], "Correction kind", 128)
                _text(event["reason"], "Correction reason")
                _require(event["status"] == "proposed", "A proposal must remain proposed in history")
                old, new = restored._source_pair(event["old_source_id"], event["new_source_id"], combined)
                _require((old["source_kind"], old["evidence_id"], new["evidence_id"]) ==
                         (event["source_kind"], event["old_evidence_id"], event["new_evidence_id"]),
                         "Correction proposal source binding mismatch")
            elif kind == "correction.review":
                _fields(event, _BASE | set(_LIMITS) | {"decision_id", "correction_id", "decision", "expected_revision", "reviewer", "reason", "reviewer_identity_basis"}, "Correction review event")
                identity = _event_identity(event["decision_id"], "decision")
                _event_identity(event["correction_id"], "correction")
                _require(isinstance(event["decision"], str) and event["decision"] in {"accept", "reject"},
                         "Review decision must be accept or reject")
                _require(type(event["expected_revision"]) is int and event["expected_revision"] == index - 1,
                         "Retained review revision does not match its chronological position")
                _text(event["reviewer"], "Declared reviewer", 512)
                _text(event["reason"], "Review reason")
                _require(event["reviewer_identity_basis"] == "caller_declared_not_authenticated",
                         "Correction reviewer identity cannot be authenticated by a journal declaration")
                restored._validate_review_target(event, combined, restored._events)
            else:
                raise ValueError("Unsupported correction journal event type")
            _require(identity not in identities, "Duplicate correction journal event identity")
            identities.add(identity)
            restored._events.append(event)
        _acyclic(combined)
        return restored
