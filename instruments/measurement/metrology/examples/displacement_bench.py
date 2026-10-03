"""First increment on the laptop: one assembly, one bidirectional pass, one log."""

import json
from pathlib import Path

from instrument_chain.bench import Session, run_bidirectional_pass
from instrument_chain.digest import evidence_commitment
from instrument_chain.manifest import default_assembly_path, load_assembly
from instrument_chain.receiver import replay
from instrument_chain.transport import Outbox

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "results" / "displacement_bench.jsonl"
COMMITMENTS = ROOT / "results" / "displacement_commitments.jsonl"


def main() -> None:
    assembly = load_assembly(default_assembly_path())
    if LOG.exists():
        LOG.unlink()
    session = Session(assembly, "bench-2026-09-16", outbox=Outbox())
    raws = [0.0, 200.0, 400.0, 600.0, 800.0, 600.0, 400.0, 200.0, 0.0]
    records = run_bidirectional_pass(session, raws, LOG)
    print(f"assembly {assembly.assembly_id} v{assembly.version}")
    print(f"calibration {assembly.calibration.id}  y = {assembly.calibration.theta[0]} * (raw - {assembly.calibration.theta[1]})")
    for obs in records:
        print(
            f"{obs.sequence:02d}  raw={obs.raw} {obs.raw_unit}  "
            f"indicated={obs.indicated} {obs.indicated_unit}  "
            f"acq={obs.quality.acquisition.value}  id={obs.observation_id}"
        )
    COMMITMENTS.parent.mkdir(parents=True, exist_ok=True)
    COMMITMENTS.write_text(
        "".join(json.dumps(evidence_commitment(obs), sort_keys=True) + "\n" for obs in records),
        encoding="utf-8",
    )
    print(f"replayable records: {len(replay(LOG))} -> {LOG}")
    print(f"evidence commitments: {COMMITMENTS}")


if __name__ == "__main__":
    main()
