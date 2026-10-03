"""Stage 8 locks -- warrant reuse without warrant trust.

The cache contains BYTES, not trust: every hit goes through the backend
verifier before anything downstream sees "verified", and this file pins
that empirically -- the host binary is instrumented (a logging shim in
front of the real nexus host) so the tests can assert WHICH subcommands
actually ran, not just what the records claim.

Proof budget: 4 real Nexus proofs total (reuse test 1, corruption test
2, cross-process producer 1) plus cheap verifies; everything else is
proof-free.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

from campaign.driver import CampaignPoint, make_campaign_pool, run_campaign
from campaign.policy import (
    VerificationLane,
    VerificationPolicy,
    WarrantRecord,
    policy_runner,
)
from campaign.warrant_cache import WarrantCache, statement_key
from execution.engine import default_cli_path
from execution.proving import default_nexus_host_path
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR,
    PAIRWISE_ENERGY_DESCRIPTOR,
    ExecutionSpecification,
    encode_heat_input,
)
from operations.trace import FAILED, SUCCEEDED, OperationTrace

pytestmark = pytest.mark.skipif(
    not default_cli_path().exists(),
    reason="execution engine not built; environment gap",
)

REPO = pathlib.Path(__file__).resolve().parent.parent
NEXUS_ELF = REPO / "zk" / "artifacts" / "nexus-heat.elf"
RISC0_ELF = REPO / "zk" / "artifacts" / "risc0-heat.elf"
NEXUS_OK = default_nexus_host_path().exists() and NEXUS_ELF.exists()

SPEC_A = ExecutionSpecification(
    HEAT_DIFFUSION_DESCRIPTOR, b"",
    encode_heat_input(50, [0, 700_000, 1_000_000, 700_000, 0, 0]),
)


def _peak(candidate, result):
    finals = [int.from_bytes(result.output[a:a + 8], "little", signed=True)
              for a in range(0, len(result.output), 8)]
    return {"property": candidate.property, "value": max(finals), "unit": "fixed_point_mk"}


BAD_SPEC = ExecutionSpecification(HEAT_DIFFUSION_DESCRIPTOR, b"", b"bad")


def _campaign(runner, n_points=1, prepend_failure=False):
    pool, doc = make_campaign_pool(["rod-A"])
    trace = OperationTrace()
    points = [
        CampaignPoint("rod-A", "peak_temperature", SPEC_A, _peak, runner=runner)
        for _ in range(n_points)
    ]
    if prepend_failure:
        points.insert(0, CampaignPoint(
            "rod-A", "peak_temperature", BAD_SPEC, _peak, runner=runner))
    report = run_campaign(pool, doc.id, trace, points)
    return pool, trace, report


def _instrumented_nexus(tmp_path):
    """A shim in front of the real nexus host that logs each subcommand
    (`prove` / `verify`) before exec'ing the real binary -- the empirical
    record of what the backend was actually asked to do."""
    log = tmp_path / "host-calls.log"
    shim = tmp_path / "nexus-shim"
    shim.write_text(
        f"#!/bin/bash\necho \"$1\" >> {log}\n"
        f"exec {default_nexus_host_path()} \"$@\"\n"
    )
    shim.chmod(0o755)
    return shim, log


def _single_lane_policy(shim):
    lanes = {"nexus": VerificationLane("nexus", shim)}
    policy = VerificationPolicy(routine="nexus", independent=None, heavyweight=None)
    return policy, lanes


# -- section 1/5: the statement key is exactly the statement -----------------------------------------


def test_statement_key_discriminates_exactly_the_statement():
    """Same (backend, artifact, specification) -> the SAME key, always
    (the deliberate 'collision' that makes reuse possible); any change
    to any component -> a different key (identity-based invalidation)."""
    key = statement_key("nexus", NEXUS_ELF, SPEC_A)
    same = ExecutionSpecification(
        HEAT_DIFFUSION_DESCRIPTOR, b"",
        encode_heat_input(50, [0, 700_000, 1_000_000, 700_000, 0, 0]),
    )
    assert statement_key("nexus", NEXUS_ELF, same) == key

    # different backend name, everything else identical
    assert statement_key("risc0", NEXUS_ELF, SPEC_A) != key
    # different guest artifact, same spec and backend
    assert statement_key("nexus", RISC0_ELF, SPEC_A) != key
    # different input
    other_input = ExecutionSpecification(
        HEAT_DIFFUSION_DESCRIPTOR, b"",
        encode_heat_input(51, [0, 700_000, 1_000_000, 700_000, 0, 0]),
    )
    assert statement_key("nexus", NEXUS_ELF, other_input) != key
    # different configuration
    other_config = ExecutionSpecification(
        HEAT_DIFFUSION_DESCRIPTOR, b"cfg", SPEC_A.input_payload
    )
    assert statement_key("nexus", NEXUS_ELF, other_config) != key
    # different program descriptor
    other_program = ExecutionSpecification(
        PAIRWISE_ENERGY_DESCRIPTOR, b"", SPEC_A.input_payload
    )
    assert statement_key("nexus", NEXUS_ELF, other_program) != key


def test_cache_stores_bytes_content_addressed_and_isolates_backends(tmp_path):
    """Proof-free mechanics: lookup on a missing key is None (a MISS is
    'no warrant', distinct from 'invalid warrant'); the artifact id is
    sha256 of the bytes; `invalidate` is the one explicit mutation; and
    a warrant stored under one backend's key is structurally invisible
    to another backend's request."""
    cache = WarrantCache(tmp_path / "cache")
    assert cache.lookup("no-such-key") is None

    artifact = cache.store("k1", b"proof-bytes", "nexus", "spec-id")
    assert artifact == hashlib.sha256(b"proof-bytes").hexdigest()
    hit = cache.lookup("k1")
    assert hit is not None and hit.artifact_intact
    assert hit.backend == "nexus" and hit.recorded_artifact_sha256 == artifact
    # content addressing: same bytes -> same artifact identity, any key
    assert cache.store("k2", b"proof-bytes", "nexus", "spec-id") == artifact

    cache.invalidate("k1")
    assert cache.lookup("k1") is None
    assert cache.lookup("k2") is not None, "invalidation touches ONE key"

    # backend isolation at the key level
    k_nexus = statement_key("nexus", NEXUS_ELF, SPEC_A)
    k_risc0 = statement_key("risc0", NEXUS_ELF, SPEC_A)
    cache.store(k_nexus, b"nexus-proof", "nexus", SPEC_A.identity())
    assert cache.lookup(k_risc0) is None, (
        "a nexus warrant can never be RETRIEVED for a risc0 request")


def test_backend_isolation_all_pairs_and_filename_blindness(tmp_path):
    """Every backend pair is key-isolated -- over one shared ELF (only
    the backend name differs) and over the real per-backend artifacts
    (both differ). And the key sees BYTES, never filenames: the same
    artifact under any name keys identically; different bytes under the
    same name key differently."""
    sp1_elf = REPO / "zk" / "artifacts" / "sp1-heat.elf"
    for elf in (NEXUS_ELF, RISC0_ELF, sp1_elf):
        if not elf.exists():
            pytest.skip("registry artifacts not built; environment gap")

    # same ELF, three backend names -> three keys
    same_elf = {b: statement_key(b, NEXUS_ELF, SPEC_A)
                for b in ("nexus", "risc0", "sp1")}
    assert len(set(same_elf.values())) == 3

    # the real (backend, artifact) statements -> three keys
    real = {
        statement_key("nexus", NEXUS_ELF, SPEC_A),
        statement_key("risc0", RISC0_ELF, SPEC_A),
        statement_key("sp1", sp1_elf, SPEC_A),
    }
    assert len(real) == 3

    # a warrant stored under any one backend is invisible to the others
    cache = WarrantCache(tmp_path / "cache")
    cache.store(statement_key("nexus", NEXUS_ELF, SPEC_A),
                b"nexus-proof", "nexus", SPEC_A.identity())
    assert cache.lookup(statement_key("risc0", RISC0_ELF, SPEC_A)) is None
    assert cache.lookup(statement_key("sp1", sp1_elf, SPEC_A)) is None
    assert cache.lookup(statement_key("risc0", NEXUS_ELF, SPEC_A)) is None
    assert cache.lookup(statement_key("sp1", NEXUS_ELF, SPEC_A)) is None

    # filename blindness: same bytes, any name -> the SAME statement
    renamed = tmp_path / "totally-different-name.bin"
    renamed.write_bytes(NEXUS_ELF.read_bytes())
    assert statement_key("nexus", renamed, SPEC_A) == same_elf["nexus"]
    # different bytes, same name -> a DIFFERENT statement
    impostor = tmp_path / "impostor" / NEXUS_ELF.name
    impostor.parent.mkdir()
    impostor.write_bytes(RISC0_ELF.read_bytes())
    assert statement_key("nexus", impostor, SPEC_A) != same_elf["nexus"]


# -- sections 4, 7, 12: reuse skips PROVING, never verification --------------------------------------


@pytest.mark.skipif(not NEXUS_OK, reason="nexus not built; environment gap")
def test_hit_skips_proving_but_never_verification(tmp_path):
    """A failed execution followed by three identical campaign points
    through one cache: 4 occurrences (1 FAILED + 3 SUCCEEDED),
    1 observation, 1 stored artifact -- and the instrumented host shows
    `prove` ran EXACTLY once while `verify` ran on every dispatch. The
    failed execution never reaches a lane, so it can neither earn a
    VerifiedExecution nor manufacture a cached warrant. Evidence is
    invariant across no-cache / miss / hit."""
    shim, log = _instrumented_nexus(tmp_path)
    policy, lanes = _single_lane_policy(shim)
    cache = WarrantCache(tmp_path / "cache")

    # baseline: no verification at all
    _, _, plain = _campaign(None, n_points=3, prepend_failure=True)

    warrants: list[WarrantRecord] = []
    pool, trace, report = _campaign(
        policy_runner(policy, tmp_path, warrants, lanes=lanes, cache=cache),
        n_points=3, prepend_failure=True,
    )
    assert report.successes == 3 and report.failures == 1
    assert len(trace.occurrences()) == 4, "every run is a distinct occurrence"
    assert trace.state_of(0) == FAILED, "the failed execution is ON the trace"
    assert all(trace.state_of(i) == SUCCEEDED for i in (1, 2, 3))
    assert report.unique_evidence == 1, "three successes, ONE observation"
    assert len(warrants) == 3, "the failed execution produced NO warrant record"

    assert [w.cache for w in warrants] == ["miss+stored", "hit", "hit"]
    assert all(w.outcome == "verified" for w in warrants)
    assert len({w.proof_identity for w in warrants}) == 1, "one reusable warrant"

    calls = log.read_text().split()
    assert calls.count("prove") == 1, "proving happened exactly once"
    assert calls.count("verify") == 3, "verification happened on EVERY dispatch"

    # section 12: the cache moved no evidence
    assert plain.observation_ids == report.observation_ids

    # one artifact on disk, content-addressed
    key = statement_key("nexus", NEXUS_ELF, SPEC_A)
    hit = cache.lookup(key)
    assert hit is not None and hit.artifact_intact
    entries = [p for p in (tmp_path / "cache").iterdir() if p.is_dir()]
    assert len(entries) == 1 and entries[0].name == key
    assert cache.lookup(statement_key("nexus", NEXUS_ELF, BAD_SPEC)) is None, (
        "a failed execution manufactured no cached warrant")

    # warrant/cache vocabulary never reaches the observation
    observation = pool.get_observation(report.observation_ids[0])
    text = repr(observation.content) + observation.extraction_method
    for token in ("cache", "warrant", "proof", "nexus", "hit"):
        assert token not in text, f"{token!r} leaked into evidence"


# -- section 14: the corruption experiment (mandatory) -----------------------------------------------


@pytest.mark.skipif(not NEXUS_OK, reason="nexus not built; environment gap")
def test_corrupted_warrant_fails_closed_and_regeneration_is_explicit(tmp_path):
    """Corrupt the stored proof artifact, then: (a) a hit STILL goes to
    the verifier, fails, and the dispatch fails -- no VerifiedExecution,
    no automatic repair, the corrupted entry left in place as the record
    of what happened; (b) only `regenerate_invalid=True` -- an explicit,
    recorded policy decision -- invalidates the entry and proves afresh;
    (c) the replacement is a clean hit afterwards."""
    shim, log = _instrumented_nexus(tmp_path)
    policy, lanes = _single_lane_policy(shim)
    cache = WarrantCache(tmp_path / "cache")

    # populate: one real proof, stored
    seed: list[WarrantRecord] = []
    _, _, populate = _campaign(
        policy_runner(policy, tmp_path, seed, lanes=lanes, cache=cache))
    assert populate.successes == 1 and seed[0].cache == "miss+stored"

    # flip one byte in the stored artifact
    key = statement_key("nexus", NEXUS_ELF, SPEC_A)
    proof = tmp_path / "cache" / key / "proof.bin"
    raw = bytearray(proof.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    proof.write_bytes(bytes(raw))
    assert not cache.lookup(key).artifact_intact

    # (a) hit -> verify -> FAIL -> dispatch FAILS; nothing regenerated
    warrants: list[WarrantRecord] = []
    pool, trace, report = _campaign(
        policy_runner(policy, tmp_path, warrants, lanes=lanes, cache=cache))
    assert report.successes == 0 and report.failures == 1
    assert "PolicyVerificationError" in report.failure_kinds[0]
    assert trace.state_of(0) == FAILED
    assert [w.cache for w in warrants] == ["hit-invalid"]
    assert warrants[0].outcome == "failed"
    assert "cached warrant failed verification" in warrants[0].error
    assert "intact=False" in warrants[0].error
    assert cache.lookup(key) is not None, "no silent repair, no silent eviction"
    assert log.read_text().split().count("prove") == 1, (
        "the invalid hit triggered NO proving")

    # (b) explicit regeneration: invalidation is ON the record
    warrants2: list[WarrantRecord] = []
    pool2, trace2, report2 = _campaign(
        policy_runner(policy, tmp_path, warrants2, lanes=lanes, cache=cache,
                      regenerate_invalid=True))
    assert report2.successes == 1
    assert [w.cache for w in warrants2] == [
        "hit-invalid", "invalidated", "regenerated+stored"]
    assert [w.outcome for w in warrants2] == ["failed", "invalidated", "verified"]
    assert cache.lookup(key).artifact_intact, "the replacement is clean"
    assert log.read_text().split().count("prove") == 2

    # (c) and the replacement serves clean hits again
    warrants3: list[WarrantRecord] = []
    _, _, report3 = _campaign(
        policy_runner(policy, tmp_path, warrants3, lanes=lanes, cache=cache))
    assert report3.successes == 1
    assert [w.cache for w in warrants3] == ["hit"]
    assert log.read_text().split().count("prove") == 2, "still no new proving"


# -- sections 10/11: warrants survive process boundaries ---------------------------------------------


_PRODUCER = """
import json, pathlib, sys
sys.path.insert(0, {repo!r})
from campaign.warrant_cache import WarrantCache, statement_key
from execution.engine import run_specification
from execution.proving import default_nexus_host_path, prove_and_verify_result
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR, ExecutionSpecification, encode_heat_input)

spec = ExecutionSpecification(
    HEAT_DIFFUSION_DESCRIPTOR, b"",
    encode_heat_input(50, [0, 700_000, 1_000_000, 700_000, 0, 0]))
elf = pathlib.Path({repo!r}) / "zk" / "artifacts" / "nexus-heat.elf"
native = run_specification(spec)
proved = prove_and_verify_result(
    native, spec, pathlib.Path({workdir!r}) / "producer-proof.bin",
    default_nexus_host_path(), elf)
cache = WarrantCache(pathlib.Path({cache_root!r}))
key = statement_key("nexus", elf, spec)
artifact = cache.store(key, pathlib.Path(proved.proof_path).read_bytes(),
                       "nexus", spec.identity())
print(json.dumps({{"key": key, "artifact": artifact,
                   "proof_identity": proved.proof_identity}}))
"""

_CONSUMER = """
import json, pathlib, sys
sys.path.insert(0, {repo!r})
from campaign.warrant_cache import WarrantCache, statement_key
from execution.engine import run_specification
from execution.proving import verify_existing_proof
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR, ExecutionSpecification, encode_heat_input)

spec = ExecutionSpecification(
    HEAT_DIFFUSION_DESCRIPTOR, b"",
    encode_heat_input(50, [0, 700_000, 1_000_000, 700_000, 0, 0]))
elf = pathlib.Path({repo!r}) / "zk" / "artifacts" / "nexus-heat.elf"
native = run_specification(spec)
cache = WarrantCache(pathlib.Path({cache_root!r}))
key = statement_key("nexus", elf, spec)
hit = cache.lookup(key)
assert hit is not None, "cross-process lookup missed"
fields = verify_existing_proof(
    native, spec, hit.proof_path, pathlib.Path({shim!r}), elf)
print(json.dumps({{"key": key, "outcome": fields["outcome"],
                   "proof_identity": fields.get("proof_identity"),
                   "intact": hit.artifact_intact}}))
"""


@pytest.mark.skipif(not NEXUS_OK, reason="nexus not built; environment gap")
def test_warrant_reuse_crosses_process_boundaries(tmp_path):
    """A producer PROCESS proves and stores; a separate consumer PROCESS
    -- sharing only the cache directory -- hits, re-verifies through an
    instrumented host, and never proves. The warrant is a portable
    artifact, not process state."""
    shim, log = _instrumented_nexus(tmp_path)
    cache_root = tmp_path / "shared-cache"

    producer = subprocess.run(
        [sys.executable, "-c", _PRODUCER.format(
            repo=str(REPO), workdir=str(tmp_path), cache_root=str(cache_root))],
        capture_output=True, cwd=REPO, timeout=600,
    )
    assert producer.returncode == 0, producer.stderr.decode(errors="replace")[-500:]
    produced = json.loads(producer.stdout.decode().strip().splitlines()[-1])

    consumer = subprocess.run(
        [sys.executable, "-c", _CONSUMER.format(
            repo=str(REPO), cache_root=str(cache_root), shim=str(shim))],
        capture_output=True, cwd=REPO, timeout=600,
    )
    assert consumer.returncode == 0, consumer.stderr.decode(errors="replace")[-500:]
    consumed = json.loads(consumer.stdout.decode().strip().splitlines()[-1])

    assert consumed["key"] == produced["key"]
    assert consumed["outcome"] == "verified"
    assert consumed["intact"] is True
    # the consumer's host ran verify only -- the shim log has no `prove`
    calls = log.read_text().split()
    assert calls.count("verify") == 1 and calls.count("prove") == 0
