"""Required real Julia + C++ persistent simulation qualification through SCR.

No test doubles or alternate providers are used by this entry point.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path
import subprocess
import sys
import uuid

from websockets.asyncio.server import serve
from ciw import simulation as s
from ciw import native_interop as native
from ciw import native_interop_contract as contract
from ciw.instruments import make_demo_run
from ciw.server import WorkbenchServer
from ciw.simulation_session import SimulationSession
from ciw.telemetry import canonical


def command(sim, **extra):
    v = sim.inspect()
    return {"command_id": "command-" + uuid.uuid4().hex, "owner_id": v["owner_id"],
            "expected_revision": v["revision"], "at_tick": v["state"]["tick"], **extra}


async def godot_roundtrip(sim, executable, output_dir):
    """Exercise the actual Godot scene over the existing WorkbenchServer."""
    session = SimulationSession(make_demo_run(), output_dir / "legacy-session")
    session.attach_simulation(sim)
    bridge = WorkbenchServer(session)
    project = Path(__file__).resolve().parents[1] / "godot"
    async with serve(bridge.handler, "127.0.0.1", 0, origins=[None], max_size=8*1024*1024, max_queue=4) as listener:
        port = listener.sockets[0].getsockname()[1]
        process = await asyncio.create_subprocess_exec(
            str(executable), "--headless", "--path", str(project), "--script", "res://tests/simulation_smoke.gd",
            "--", f"--simulation-url=ws://127.0.0.1:{port}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            raw, _ = await asyncio.wait_for(process.communicate(), timeout=150)
        except BaseException:
            process.kill()
            await process.wait()
            raise
        (output_dir / "godot.log").write_bytes(raw)
        if process.returncode != 0 or b"SIMULATION_GODOT_PASSED" not in raw or b"SCRIPT ERROR" in raw:
            raise RuntimeError("Godot integration failed: " + raw.decode("utf-8", "replace")[-6000:])
    # Closing the client and server connection did not close the simulation.
    if sim.inspect()["status"] != "ready":
        raise ValueError("Client disconnect changed simulation availability")
    session.save_workspace(output_dir / "legacy-session" / "workspace.json")
    return {"status": "passed", "session_id": session.session_id,
            "checks": ["same-model", "advance", "impulse", "checkpoint", "reconnect", "stale-command-refusal"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binding", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--godot", type=Path, required=True)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    sim = s.Simulation({"omega_0_rad_s": 2.0, "gamma_s_inv": 0.1, "mass_kg": 1.0},
        {"tick": 0, "q_m": 1.0, "v_m_s": 0.0}, args.binding, args.output_dir / "original")
    restored = None
    try:
        start = sim.inspect()
        pair_ids = {k: (v.stream_id, v.pipe.process.pid) for k, v in sim.providers.channels.items()}
        for _ in range(4):
            sim.mutate("advance", command(sim, ticks=12))
        for provider, channel in sim.providers.channels.items():
            if (channel.stream_id, channel.pipe.process.pid) != pair_ids[provider]:
                raise ValueError("Provider restarted between simulation batches")
        receipt = sim.checkpoint()
        cp = s.read_checkpoint(sim.directory / receipt["filename"])
        # Compare the integrated prefix against the independent full-interval analytic result.
        prefix = sim.inspect()
        oracle = contract.oscillator_reference(s._trajectory_source(cp["model"], start["state"], {"ticks": 48})["payload"])
        for key in ("q_m", "v_m_s"):
            if not math.isclose(prefix["state"][key], oracle[key][-1], rel_tol=2e-8, abs_tol=2e-8):
                raise ValueError("Chunked native trajectory failed independent reference")
        continuation = sim.mutate("advance", command(sim, ticks=12))
        for provider in ("julia", "cpp"):
            hosts = []
            steps = [cp["initial_force"]] + [step for e in cp["events"] for step in e["native_steps"]]
            for step in steps:
                if step["request"]["provider"] == provider:
                    h = native._json(native._unblob(step["transport"]["response"]))["host"]
                    hosts.append((h["process_id"], h["child_process_id"], h["occurrence"]))
            if len(hosts) < 4 or len({x[:2] for x in hosts}) != 1 or len({x[2] for x in hosts}) != len(hosts):
                raise ValueError("Retained native records do not establish persistence")
        sim.close()
        if any(ch.pipe.process.poll() is None for ch in sim.providers.channels.values()):
            raise ValueError("Closed original host was not reaped")
        restored = s.Simulation(None, None, args.binding, args.output_dir / "restored",
                                checkpoint=cp, expected_id=receipt["checkpoint_id"])
        current = restored.inspect()
        if (current["state"] != prefix["state"] or current["model_id"] != prefix["model_id"]
                or current["simulation_id"] != prefix["simulation_id"] or current["owner_id"] == prefix["owner_id"]):
            raise ValueError("Checkpoint did not preserve lineage/state and change owner occurrence")
        stale = command(restored, ticks=12); stale["owner_id"] = prefix["owner_id"]
        try:
            restored.mutate("advance", stale)
        except s.ProtocolError as exc:
            if exc.code != "stale_owner": raise
        else:
            raise ValueError("Old owner was not fenced after restart")
        now = restored.mutate("advance", command(restored, ticks=12))
        for key in ("q_m", "v_m_s"):
            if not math.isclose(now["state"][key], continuation["state"][key], rel_tol=2e-8, abs_tol=2e-8):
                raise ValueError("Restored continuation differs from uninterrupted reference")
        godot = asyncio.run(godot_roundtrip(restored, args.godot, args.output_dir))
        final = restored.checkpoint()
        checkpoint_path = restored.directory / final["filename"]
        offline = subprocess.run([sys.executable, "-m", "ciw.simulation_session", "inspect", str(checkpoint_path),
            "--expected-checkpoint-id", final["checkpoint_id"]], capture_output=True, timeout=30, check=True)
        inspected = json.loads(offline.stdout)
        if inspected["state"] != restored.inspect()["state"]:
            raise ValueError("Provider-free subprocess inspection differs")
        # A killed channel may not silently restart, advance time, or hide a partial result.
        before_failure = restored.inspect()
        restored.providers.channels["julia"].pipe.process.kill()
        restored.providers.channels["julia"].pipe.process.wait(timeout=10)
        try:
            restored.mutate("advance", command(restored, ticks=12))
        except Exception:
            if restored.inspect()["status"] != "failed": raise
        else:
            raise ValueError("Dead native provider was silently substituted")
        if restored.inspect()["state"] != before_failure["state"]:
            raise ValueError("Provider death changed committed simulation state")
        report = {"schema": "notation.persistent-simulation-qualification.v1", "outcome": "passed",
            "model_id": start["model_id"], "simulation_id": start["simulation_id"], "native_provider_streams": pair_ids,
            "checkpoint": final, "godot": godot, "runtime": cp["runtime"],
            "checks": ["same-process-multiple-batches", "distinct-native-occurrences", "analytic-prefix",
                       "checkpoint-restart", "new-owner-fencing", "continued-trajectory-agreement",
                       "provider-free-inspection", "dead-provider-fail-closed", "old-processes-reaped"],
            "scope": "bounded-synthetic-damped-oscillator-only", "physical_validation": "not_established"}
        (args.output_dir / "qualification.json").write_bytes(canonical(report))
        print(json.dumps(report, indent=2))
    finally:
        sim.close()
        if restored is not None: restored.close()


if __name__ == "__main__": main()
