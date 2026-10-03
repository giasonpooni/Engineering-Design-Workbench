"""Optional simulation extension of the existing NET Session and WebSocket server.

The same Workbench, protocol validation, selection and legacy operations remain
in use. Simulation checkpoints are separate explicit artifacts, not recordings.
"""
from __future__ import annotations

import argparse
import asyncio
import uuid
from pathlib import Path

from .cli import print_json, request_remote
from .instruments import make_demo_run
from .server import run_server
from .session import Session, _keys, ProtocolError
from .simulation import Simulation, inspect_checkpoint, read_checkpoint


class SimulationSession(Session):
    def attach_simulation(self, simulation):
        if getattr(self, "simulation", None) is not None:
            raise ValueError("This Session already owns a simulation")
        self.simulation = simulation

    def snapshot(self, evaluated_at=None):
        value = super().snapshot(evaluated_at)
        if getattr(self, "simulation", None) is not None:
            value["simulation"] = self.simulation.inspect()
        return value

    def _dispatch(self, kind, payload):
        if not kind.startswith("simulation."):
            return super()._dispatch(kind, payload)
        sim = getattr(self, "simulation", None)
        if sim is None:
            raise ProtocolError("not_initialized", "The operator has not initialized a simulation")
        if kind == "simulation.inspect":
            _keys(payload, set())
            return sim.inspect()
        if kind == "simulation.checkpoint":
            _keys(payload, set())
            return sim.checkpoint()
        if kind in {"simulation.advance", "simulation.impulse"}:
            return sim.mutate(kind.split(".")[1], payload)
        raise ProtocolError("unknown_operation", "Unknown simulation operation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("serve", "headless"):
        p = commands.add_parser(name)
        p.add_argument("--binding", type=Path, required=True)
        p.add_argument("--output-dir", type=Path, required=True)
        p.add_argument("--checkpoint", type=Path)
        p.add_argument("--expected-checkpoint-id")
        if name == "serve":
            p.add_argument("--port", type=int, default=8765)
        else:
            p.add_argument("--batches", type=int, default=4)
    p = commands.add_parser("inspect")
    p.add_argument("checkpoint", type=Path)
    p.add_argument("--expected-checkpoint-id")
    for name in ("status", "advance", "impulse", "checkpoint"):
        p = commands.add_parser(name)
        p.add_argument("--url", default="ws://127.0.0.1:8765")
        if name == "advance":
            p.add_argument("--ticks", type=int, required=True)
        if name == "impulse":
            p.add_argument("--impulse-n-s", type=float, required=True)
    args = parser.parse_args()
    if args.command == "inspect":
        print_json(inspect_checkpoint(read_checkpoint(args.checkpoint), args.expected_checkpoint_id))
        return
    if args.command in {"status", "advance", "impulse", "checkpoint"}:
        async def remote():
            if args.command in {"status", "checkpoint"}:
                kind = "inspect" if args.command == "status" else "checkpoint"
                return await request_remote(args.url, "simulation." + kind, {}, timeout_s=210)
            current = await request_remote(args.url, "simulation.inspect", {})
            if current["type"] != "response":
                return current
            value = current["payload"]
            payload = {"command_id": "command-" + uuid.uuid4().hex, "owner_id": value["owner_id"],
                       "expected_revision": value["revision"], "at_tick": value["state"]["tick"]}
            payload.update({"ticks": args.ticks} if args.command == "advance"
                           else {"impulse_n_s": args.impulse_n_s})
            return await request_remote(args.url, "simulation." + args.command, payload, timeout_s=210)
        print_json(asyncio.run(remote()))
        return
    if args.checkpoint and not args.expected_checkpoint_id:
        parser.error("Restart requires --expected-checkpoint-id from your retained artifact selection")
    if args.command == "headless" and not 0 <= args.batches <= 100:
        parser.error("Headless batches must be in 0..100")
    # Same fixed reference model for headless and interactive operation.
    sim = Simulation({"omega_0_rad_s": 2.0, "gamma_s_inv": 0.1, "mass_kg": 1.0},
                     {"tick": 0, "q_m": 1.0, "v_m_s": 0.0}, args.binding,
                     args.output_dir / "simulation", checkpoint=read_checkpoint(args.checkpoint) if args.checkpoint else None,
                     expected_id=args.expected_checkpoint_id)
    try:
        if args.command == "headless":
            for _ in range(args.batches):
                current = sim.inspect()
                sim.mutate("advance", {"command_id": "command-" + uuid.uuid4().hex,
                    "owner_id": current["owner_id"], "expected_revision": current["revision"],
                    "at_tick": current["state"]["tick"], "ticks": 120})
            print_json({"simulation": sim.inspect(), "checkpoint": sim.checkpoint()})
        else:
            # The legacy recording is an independent synthetic reference, not live state.
            session = SimulationSession(make_demo_run(), args.output_dir)
            session.attach_simulation(sim)
            asyncio.run(run_server(session, args.port, "127.0.0.1"))
    finally:
        try:
            sim.checkpoint()
        finally:
            sim.close()


if __name__ == "__main__":
    main()
