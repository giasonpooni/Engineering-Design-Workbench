"""Accepted input snapshots stay stable; the backend is an explicit test double."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from ciw import simulation as s
from test_persistent_simulation import ReferenceDouble, command


class InputIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        ReferenceDouble.failure = ReferenceDouble.blocker = None
        self.providers = patch.object(s, "ProviderPair", ReferenceDouble)
        self.validator = patch.object(s, "validate_step", lambda step, runtime: deepcopy(step["output"]))
        self.providers.start()
        self.validator.start()
        self.sim = s.Simulation({"omega_0_rad_s": 2.0, "gamma_s_inv": 0.1, "mass_kg": 1.0},
            {"tick": 0, "q_m": 1.0, "v_m_s": 0.0}, "fixture", self.root / "original")

    def tearDown(self):
        self.sim.close()
        self.providers.stop()
        self.validator.stop()
        self.temp.cleanup()

    def test_accepted_command_is_detached_from_mutable_caller_data(self):
        gate = threading.Event()
        ReferenceDouble.blocker = gate
        payload = command(self.sim, ticks=12)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.sim.mutate, "advance", payload)
            for _ in range(100):
                if self.sim.inspect()["status"] == "advancing":
                    break
                time.sleep(.01)
            payload["ticks"] = 120
            gate.set()
            self.assertEqual(future.result(5)["state"]["tick"], 12)
        receipt = self.sim.checkpoint()
        cp = s.read_checkpoint(self.sim.directory / receipt["filename"])
        self.assertEqual(cp["events"][0]["command"]["ticks"], 12)

    def test_restart_snapshots_checkpoint_before_provider_initialization(self):
        receipt = self.sim.checkpoint()
        cp = s.read_checkpoint(self.sim.directory / receipt["filename"])
        self.sim.close()
        def changing_provider(binding, expected_runtime=None):
            provider = ReferenceDouble(binding, expected_runtime)
            cp["initial_state"]["q_m"] = 9.0
            return provider
        with patch.object(s, "ProviderPair", changing_provider):
            fresh = s.Simulation(None, None, "fixture", self.root / "resumed", checkpoint=cp,
                                 expected_id=receipt["checkpoint_id"])
        try:
            self.assertEqual(fresh.inspect()["state"]["q_m"], 1.0)
            fresh.checkpoint()
        finally:
            fresh.close()


if __name__ == "__main__":
    unittest.main()
