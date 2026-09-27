"""Proof orchestration must bind the captured statement, not mutable caller data.

Synthetic transport doubles isolate identity and lifecycle checks. They never
constitute an SP1 proof, cryptographic verification, or a physical validation.
"""
from copy import deepcopy

import pytest

from ciw import proved_heat as module
from ciw.proved_heat import ProvedHeatWorkflow
from ciw.telemetry import canonical, digest
from test_proved_heat import fake_bundle, fake_data, fake_runtime, source


def replace_caller_bundle(bundle):
    replacement_source = source()
    replacement_source.update(experiment_id="replacement-during-verification", initial_values=[0, 16, 0], steps=2)
    replacement = fake_bundle(canonical(replacement_source))
    bundle.clear()
    bundle.update(replacement)


@pytest.mark.parametrize("when", ["binding", "verification"])
def test_fresh_report_cannot_be_retargeted_by_caller_mutation(monkeypatch, when):
    workflow, bundle = ProvedHeatWorkflow(), fake_bundle()
    captured = deepcopy(bundle)
    checked = []

    def bind(*_args):
        if when == "binding":
            replace_caller_bundle(bundle)
        return None, fake_runtime(), {}

    def verify(value, _bound, retained):
        checked.append((deepcopy(value), deepcopy(retained)))
        if when == "verification":
            replace_caller_bundle(bundle)
        return {"verifier": deepcopy(retained["verifier"]), "seconds": 0.2,
                "memory": deepcopy(module.UNMEASURED_MEMORY)}

    monkeypatch.setattr(workflow, "_adapters", bind)
    monkeypatch.setattr(workflow, "_invoke", verify)
    report = workflow.verify_session(bundle, {})
    assert checked == [(source(), captured["steps"][0]["result"]["data"])]
    assert report["subject_ref"] == captured["bundle_digest"]
    assert report["result_id"] == captured["steps"][0]["result_id"]
    assert report["runtime_digest"] == digest(captured["runtimes"])
    assert bundle["bundle_digest"] != captured["bundle_digest"]


def test_fresh_report_does_not_retain_provider_owned_memory(monkeypatch):
    workflow, bundle = ProvedHeatWorkflow(), fake_bundle()
    response = {"verifier": deepcopy(bundle["steps"][0]["result"]["data"]["verifier"]),
                "seconds": 0.2, "memory": deepcopy(module.UNMEASURED_MEMORY)}
    monkeypatch.setattr(workflow, "_adapters", lambda *_: (None, fake_runtime(), {}))
    monkeypatch.setattr(workflow, "_invoke", lambda *_a, **_k: response)
    report = workflow.verify_session(bundle, {})
    expected = deepcopy(report)
    response["memory"]["scope"] = "fabricated-after-return"
    response["verifier"]["outcome"] = "failed"
    assert report == expected
    assert module._identify({k: v for k, v in report.items() if k != "verification_id"}) == report


@pytest.mark.parametrize("field", ["native", "timings", "verifier"])
def test_created_bundle_does_not_retain_provider_owned_data(monkeypatch, field):
    workflow, payload, runtime = ProvedHeatWorkflow(), fake_data(), fake_runtime()
    monkeypatch.setattr(workflow, "_adapters", lambda *_: (None, runtime, {}))
    monkeypatch.setattr(workflow, "_invoke", lambda *_a, **_k: payload)
    bundle = workflow.create_session(canonical(source()), {})
    captured = deepcopy(bundle)
    payload[field].clear()
    assert bundle == captured
    workflow._validate(bundle)


def test_created_bundle_does_not_retain_caller_owned_runtime(monkeypatch):
    workflow, runtime = ProvedHeatWorkflow(), fake_runtime()
    monkeypatch.setattr(workflow, "_adapters", lambda *_: (None, runtime, {}))
    monkeypatch.setattr(workflow, "_invoke", lambda *_a, **_k: fake_data())
    bundle = workflow.create_session(canonical(source()), {})
    captured = deepcopy(bundle)
    runtime["prover"]["sha256"] = "sha256:" + "0" * 64
    assert bundle == captured
    workflow._validate(bundle)


def test_fresh_verifier_cannot_mutate_the_checked_statement(monkeypatch):
    workflow, bundle = ProvedHeatWorkflow(), fake_bundle()
    captured = deepcopy(bundle)
    monkeypatch.setattr(workflow, "_adapters", lambda *_: (None, fake_runtime(), {}))

    def verify(_source, _bound, retained):
        response = {"verifier": deepcopy(retained["verifier"]), "seconds": 0.2,
                    "memory": deepcopy(module.UNMEASURED_MEMORY)}
        retained["native"]["values"][1] = -999
        return response

    monkeypatch.setattr(workflow, "_invoke", verify)
    with pytest.raises(ValueError, match="statement changed"):
        workflow.verify_session(bundle, {})
    assert bundle == captured


def test_replay_is_bound_to_captured_original(monkeypatch):
    workflow, bundle = ProvedHeatWorkflow(), fake_bundle()
    captured = deepcopy(bundle)
    monkeypatch.setattr(workflow, "_adapters", lambda *_: (None, fake_runtime(), {}))

    def invoke(value, _bound):
        result = fake_data(value)
        # Same numerical statement, but different original occurrence. The
        # caller must not retarget the replay receipt to that unrequested one.
        bundle.clear()
        bundle.update(fake_bundle())
        return result

    monkeypatch.setattr(workflow, "_invoke", invoke)
    replay = workflow.replay_session(bundle, {})
    assert replay["replay_receipt"]["source_bundle_digest"] == captured["bundle_digest"]
    workflow.validate_replay(captured, replay["session"], replay["replay_receipt"])


@pytest.mark.parametrize("field,value", [("outcome", "failed"), ("command", "verify-vk"),
    ("coverage", "program=true input=false output=true exit_code=true"),
    ("statement_program", "0" * 64), ("proof_identity", "0" * 64),
    ("backend", "sp1-mock v6.1.0")])
def test_fresh_rejection_cannot_be_overridden_by_retained_success(monkeypatch, field, value):
    workflow, bundle = ProvedHeatWorkflow(), fake_bundle()
    monkeypatch.setattr(workflow, "_adapters", lambda *_: (None, fake_runtime(), {}))
    rejected = deepcopy(bundle["steps"][0]["result"]["data"]["verifier"])
    rejected[field] = value
    monkeypatch.setattr(workflow, "_invoke", lambda *_a, **_k: {
        "verifier": rejected, "seconds": 0.1, "memory": deepcopy(module.UNMEASURED_MEMORY)})
    with pytest.raises(ValueError, match="Verifier"):
        workflow.verify_session(bundle, {})


@pytest.mark.parametrize("target", ["input", "output"])
def test_adversarial_fixture_rebinds_statement_not_proof_bytes(target):
    from test_proved_heat_session import rebound_statement
    original = fake_bundle()
    captured = deepcopy(original)
    tampered = rebound_statement(original, target)
    # This only tests fixture construction. No proof is authenticated here.
    ProvedHeatWorkflow()._validate(tampered)
    assert original == captured
    assert tampered["steps"][0]["result"]["data"]["proof"] == original["steps"][0]["result"]["data"]["proof"]
    assert tampered["bundle_digest"] != original["bundle_digest"]
    before = original["steps"][0]["result"]["data"]["native"]
    after = tampered["steps"][0]["result"]["data"]["native"]
    assert before[target + "_identity"] != after[target + "_identity"]


@pytest.mark.parametrize("part", ["source", "runtime"])
def test_verifier_cannot_mutate_source_or_runtime_bindings(monkeypatch, part):
    workflow, bundle, runtime = ProvedHeatWorkflow(), fake_bundle(), fake_runtime()
    monkeypatch.setattr(workflow, "_adapters", lambda *_: (None, runtime, {}))

    def verify(value, bound, retained):
        if part == "source":
            value["steps"] += 1
        else:
            bound[1]["prover"]["sha256"] = "sha256:" + "c" * 64
        return {"verifier": deepcopy(retained["verifier"]), "seconds": 0.1,
                "memory": deepcopy(module.UNMEASURED_MEMORY)}

    monkeypatch.setattr(workflow, "_invoke", verify)
    with pytest.raises(ValueError, match="changed during execution"):
        workflow.verify_session(bundle, {})
