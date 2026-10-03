from instrument_chain.bench import Session
from instrument_chain.digest import evidence_commitment, observation_digest, verify_evidence_commitment
from instrument_chain.manifest import load_assembly
from pathlib import Path

import pytest

DECL = Path(__file__).resolve().parents[1] / "declarations" / "assembly_v1.toml"


@pytest.fixture
def assembly():
    return load_assembly(DECL)


def test_observation_digest_is_stable(assembly):
    obs = Session(assembly, "sess-digest").step(200.0)
    first = observation_digest(obs)
    assert first == observation_digest(obs)
    assert len(first) == 64
    envelope = evidence_commitment(obs)
    assert verify_evidence_commitment(envelope) == first
    envelope["digest"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        verify_evidence_commitment(envelope)


def test_digest_changes_when_the_record_changes(assembly):
    session = Session(assembly, "sess-digest-2")
    a = session.step(200.0)
    b = session.step(400.0)
    assert observation_digest(a) != observation_digest(b)
    session.connected = False
    missing = session.step(400.0)
    assert missing.raw is None
    assert observation_digest(missing) != observation_digest(b)
