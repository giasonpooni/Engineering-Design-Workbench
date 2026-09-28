"""Controller tests use explicit test doubles; they do NOT qualify native code."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

from ciw import simulation as s
from ciw import native_interop_contract as contract
from ciw.telemetry import digest
from ciw.session import ProtocolError


class ReferenceDouble:
    """Only the test suite can replace the approved native provider pair."""
    created = 0
    closed = 0
    failure = None
    blocker = None

    def __init__(self, binding, expected_runtime=None):
        type(self).created += 1
        self.runtime = {"test_double": "not-native-evidence"}
        if expected_runtime is not None and expected_runtime != self.runtime:
            raise ValueError("runtime differs")

    def execute(self, source):
        if self.failure == source["provider"]:
            raise RuntimeError("injected provider failure")
        if self.blocker is not None and source["provider"] == "julia":
            self.blocker.wait(3)
        output = (contract.oscillator_reference(source["payload"]) if source["provider"] == "julia"
                  else contract.force_reference(source["payload"]))
        return {"request": deepcopy(source), "output": output, "execution_id": "execution-" + uuid.uuid4().hex,
                "result_id": digest({"source": source, "test_result": output})}

    def close(self):
        type(self).closed += 1


def command(sim, **extra):
    v = sim.inspect()
    return {"command_id": "command-" + uuid.uuid4().hex, "owner_id": v["owner_id"],
            "expected_revision": v["revision"], "at_tick": v["state"]["tick"], **extra}


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.p1 = patch.object(s, "ProviderPair", ReferenceDouble)
        self.p2 = patch.object(s, "validate_step", lambda step, runtime: deepcopy(step["output"]))
        self.p1.start(); self.p2.start()
        ReferenceDouble.created = ReferenceDouble.closed = 0
        ReferenceDouble.failure = ReferenceDouble.blocker = None
        self.sim = s.Simulation({"omega_0_rad_s": 2.0, "gamma_s_inv": 0.1, "mass_kg": 1.0},
            {"tick": 0, "q_m": 1.0, "v_m_s": 0.0}, "unused", self.root / "original")

    def tearDown(self):
        ReferenceDouble.blocker = None
        self.sim.close()
        self.p1.stop(); self.p2.stop(); self.temp.cleanup()

    def checkpoint(self):
        receipt = self.sim.checkpoint()
        return s.read_checkpoint(self.sim.directory / receipt["filename"]), receipt["checkpoint_id"]

    def test_persistent_provider_pair_across_advances(self):
        identity = self.sim.inspect()["model_id"]
        for _ in range(4):
            self.sim.mutate("advance", command(self.sim, ticks=30))
        self.assertEqual(ReferenceDouble.created, 1)
        self.assertEqual(self.sim.inspect()["state"]["tick"], 120)
        self.assertEqual(self.sim.inspect()["model_id"], identity)

    def test_reference_chunk_invariance(self):
        initial = self.sim.inspect()["state"]
        for _ in range(10):
            self.sim.mutate("advance", command(self.sim, ticks=12))
        source = s._trajectory_source(self.sim._cp["model"], initial, {"ticks": 120})
        expected = contract.oscillator_reference(source["payload"])
        self.assertAlmostEqual(self.sim.inspect()["state"]["q_m"], expected["q_m"][-1], places=13)
        self.assertAlmostEqual(self.sim.inspect()["state"]["v_m_s"], expected["v_m_s"][-1], places=13)

    def test_impulse_is_an_event_not_a_model_change(self):
        before = self.sim.inspect()
        after = self.sim.mutate("impulse", command(self.sim, impulse_n_s=0.5))
        self.assertEqual(after["model_id"], before["model_id"])
        self.assertEqual(after["state"]["tick"], 0)
        self.assertEqual(after["state"]["v_m_s"], 0.5)
        self.assertAlmostEqual(after["observables"]["energy_j"] - before["observables"]["energy_j"], 0.125)

    def test_duplicate_command_executes_only_once(self):
        payload = command(self.sim, ticks=12)
        first = self.sim.mutate("advance", payload)
        self.assertEqual(first, self.sim.mutate("advance", payload))
        self.assertEqual(self.sim.inspect()["revision"], 1)
        with self.assertRaises(ValueError):
            self.sim.mutate("advance", {**payload, "ticks": 24})

    def test_stale_revision_and_tick_refused_without_mutation(self):
        p = command(self.sim, ticks=12)
        self.sim.mutate("advance", p)
        p["command_id"] = "command-" + uuid.uuid4().hex
        with self.assertRaisesRegex(ProtocolError, "Refresh"):
            self.sim.mutate("advance", p)
        self.assertEqual(self.sim.inspect()["revision"], 1)

    def test_provider_failure_keeps_last_committed_state(self):
        before = self.sim.inspect()
        ReferenceDouble.failure = "cpp"
        with self.assertRaises(RuntimeError):
            self.sim.mutate("advance", command(self.sim, ticks=12))
        self.assertEqual(self.sim.inspect()["state"], before["state"])
        self.assertEqual(self.sim.inspect()["revision"], 0)
        self.assertEqual(self.sim.inspect()["status"], "failed")
        failure = s.read_checkpoint(next(self.sim.directory.glob("failure-*.json")))
        self.assertEqual(len(failure["completed_native_steps"]), 1)
        self.assertIs(failure["state_committed"], False)

    def test_disk_failure_cannot_publish_new_state(self):
        before = self.sim.inspect()
        with patch.object(s, "publish", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.sim.mutate("advance", command(self.sim, ticks=12))
        self.assertEqual(before["state"], self.sim.inspect()["state"])
        self.assertEqual(self.sim.inspect()["status"], "failed")

    def test_concurrent_mutation_refuses_but_inspection_stays_responsive(self):
        gate = threading.Event(); ReferenceDouble.blocker = gate
        payload = command(self.sim, ticks=12)
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(self.sim.mutate, "advance", payload)
            for _ in range(100):
                if self.sim.inspect()["status"] == "advancing": break
                time.sleep(.01)
            with self.assertRaises(ProtocolError): self.sim.mutate("advance", payload)
            with self.assertRaises(ProtocolError): self.sim.checkpoint()
            self.assertEqual(self.sim.inspect()["state"]["tick"], 0)
            gate.set(); future.result(5)
        self.assertEqual(self.sim.inspect()["state"]["tick"], 12)

    def test_resume_preserves_model_state_and_fences_old_owner(self):
        self.sim.mutate("advance", command(self.sim, ticks=12))
        before = self.sim.inspect(); cp, identity = self.checkpoint()
        fresh = s.Simulation(None, None, "unused", self.root / "resumed", checkpoint=cp, expected_id=identity)
        try:
            now = fresh.inspect()
            self.assertEqual(before["state"], now["state"])
            self.assertEqual(before["model_id"], now["model_id"])
            self.assertEqual(before["simulation_id"], now["simulation_id"])
            self.assertNotEqual(before["owner_id"], now["owner_id"])
            p = command(fresh, ticks=12); p["owner_id"] = before["owner_id"]
            with self.assertRaises(ProtocolError): fresh.mutate("advance", p)
            fresh.mutate("advance", command(fresh, ticks=12))
            receipt = fresh.checkpoint()
            view = s.inspect_checkpoint(s.read_checkpoint(fresh.directory / receipt["filename"]))
            self.assertEqual(view["state"]["tick"], 24)
        finally: fresh.close()

    def test_restart_cannot_reuse_a_historical_command_id(self):
        payload = command(self.sim, ticks=12)
        self.sim.mutate("advance", payload)
        cp, identity = self.checkpoint()
        self.sim.close()
        fresh = s.Simulation(None, None, "unused", self.root / "fresh-ids", checkpoint=cp, expected_id=identity)
        try:
            request = command(fresh, ticks=12)
            request["command_id"] = payload["command_id"]
            before = fresh.inspect()
            with self.assertRaisesRegex(ProtocolError, "pre-restart"):
                fresh.mutate("advance", request)
            self.assertEqual(fresh.inspect(), before)
            fresh.checkpoint()
        finally:
            fresh.close()

    def test_rehashed_boolean_authority_and_numeric_configuration_refuse(self):
        cp, _ = self.checkpoint()
        for field, key, value in (("authority", "may_authorize", 0), ("configuration", "sample_rate_hz", 120.0)):
            altered = deepcopy(cp)
            altered[field][key] = value
            altered.pop("checkpoint_id")
            altered = s._seal(altered, "checkpoint_id")
            with self.subTest(field=field), self.assertRaises(ValueError):
                s.inspect_checkpoint(altered)

    def test_restart_requires_external_identity_and_same_runtime(self):
        cp, identity = self.checkpoint()
        with self.assertRaises(ValueError): s.Simulation(None, None, "unused", self.root / "no-pin", checkpoint=cp)
        with self.assertRaises(ValueError): s.inspect_checkpoint(cp, "sha256:" + "0"*64)
        cp["runtime"] = {"other": "runtime"}; cp.pop("checkpoint_id"); cp = s._seal(cp, "checkpoint_id")
        with self.assertRaisesRegex(ValueError, "runtime"):
            s.Simulation(None, None, "unused", self.root / "wrong", checkpoint=cp, expected_id=cp["checkpoint_id"])

    def test_inspection_never_launches_or_reruns_reference(self):
        self.sim.mutate("advance", command(self.sim, ticks=12)); cp, identity = self.checkpoint()
        with patch.object(s, "ProviderPair", side_effect=AssertionError("launched")), \
             patch.object(contract, "oscillator_reference", side_effect=AssertionError("oracle rerun")):
            self.assertEqual(s.inspect_checkpoint(cp, identity)["state"]["tick"], 12)

    def test_rehashed_state_and_source_swaps_refused(self):
        self.sim.mutate("advance", command(self.sim, ticks=12)); cp, _ = self.checkpoint()
        for field in ("after", "before"):
            altered = deepcopy(cp); altered["events"][0][field]["q_m"] += .1
            e = altered["events"][0]; e.pop("event_id"); altered["events"][0] = s._seal(e, "event_id")
            altered.pop("checkpoint_id"); altered = s._seal(altered, "checkpoint_id")
            with self.assertRaises(ValueError): s.inspect_checkpoint(altered)

    def test_invalid_requests_never_start_providers(self):
        for invalid in (True, 0, 121, 1.5, "12"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.sim.mutate("advance", command(self.sim, ticks=invalid))
        for invalid in (True, float("nan"), 2, "1"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.sim.mutate("impulse", command(self.sim, impulse_n_s=invalid))
        self.assertEqual(self.sim.inspect()["revision"], 0)
        self.assertEqual(self.sim.inspect()["status"], "ready")

    def test_snapshot_detaches_and_close_does_not_change_model(self):
        original = self.sim.inspect(); original["state"]["q_m"] = 9
        self.assertEqual(self.sim.inspect()["state"]["q_m"], 1)
        self.sim.close()
        with self.assertRaises(ValueError): self.sim.mutate("advance", command(self.sim, ticks=12))
        self.assertEqual(self.sim.inspect()["status"], "closed")

    def test_one_owner_per_output_directory(self):
        with self.assertRaises(FileExistsError):
            s.Simulation(None, None, "unused", self.sim.directory)

    def test_existing_session_protocol_is_extended_not_replaced(self):
        from ciw.simulation_session import SimulationSession
        from ciw.instruments import make_demo_run
        session = SimulationSession(make_demo_run(), self.root / "session")
        session.attach_simulation(self.sim)
        def ask(kind, payload):
            return session.handle({"protocol_version": 1, "request_id": uuid.uuid4().hex,
                                   "type": kind, "payload": payload})
        self.assertEqual(ask("simulation.inspect", {})["type"], "response")
        self.assertEqual(ask("session.get", {})["payload"]["simulation"]["model_id"], self.sim.inspect()["model_id"])
        self.assertEqual(ask("operation.list", {})["type"], "response")
        self.assertEqual(ask("simulation.advance", {"code": "anything"})["type"], "error")
        with self.assertRaises(ValueError): session.attach_simulation(self.sim)


if __name__ == "__main__": unittest.main()
