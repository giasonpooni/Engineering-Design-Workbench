"""Public UI gate with a labelled reference double; not native qualification."""
import argparse
import asyncio
from pathlib import Path
import sys
from unittest.mock import patch
from copy import deepcopy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_persistent_simulation import godot_roundtrip
from test_persistent_simulation import ReferenceDouble
from ciw import simulation as s

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--godot', type=Path, required=True)
p.add_argument('--output-dir', type=Path, required=True)
args = p.parse_args()
args.output_dir.mkdir(parents=True, exist_ok=False)
with patch.object(s, 'ProviderPair', ReferenceDouble), patch.object(s, 'validate_step', lambda step, runtime: deepcopy(step['output'])):
    sim = s.Simulation({'omega_0_rad_s': 2.0, 'gamma_s_inv': .1, 'mass_kg': 1.0},
        {'tick': 0, 'q_m': 1.0, 'v_m_s': 0.0}, 'test-double', args.output_dir / 'simulation')
    try:
        print(asyncio.run(godot_roundtrip(sim, args.godot, args.output_dir)))
    finally:
        sim.close()
