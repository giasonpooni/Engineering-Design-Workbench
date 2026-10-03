"""The molecular/crystal campaign -- real structures through every layer.

Structures: water (x3, the repeated structure), methane, a moved-atom
water (the changed structure), FCC argon, rock salt, a strained FCC
cell, and an argon trimer through GROMACS. Warrants: water's pairwise
statement on BOTH Nexus and SP1 (one computation, two independent
warrants), methane and moved-water on Nexus -- manufactured concurrently
by the stage-9 prefetcher, reused by the campaign through the stage-8
cache with mandatory re-verification. Rg and crystal points run native
(their kernels have no guests yet -- refused attributably, so their
points are honestly 'unproved'). Evidence is asserted invariant against
an unproved baseline of the same points.
"""

import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from campaign.driver import CampaignPoint, make_campaign_pool, run_campaign
from campaign.policy import VerificationPolicy, WarrantRecord, default_lanes, policy_runner
from campaign.prefetch import prefetch_warrants
from campaign.warrant_cache import WarrantCache
from execution.gromacs import (
    gmx_version_line,
    gromacs_program_descriptor,
    run_gromacs_specification,
)
from execution.specification import ExecutionSpecification
from operations.trace import FAILED, REJECTED, SUCCEEDED, OperationTrace
from structures.gromacs_bridge import argon_topology, molecule_to_gro
from structures.library import FCC_ARGON, METHANE, ROCK_SALT, WATER
from structures.lowering import (
    crystal_to_lattice_spec,
    molecule_to_pairwise_spec,
    molecule_to_rg_spec,
)
from structures.molecule import Atom, Molecule
from structures.crystal import CrystalStructure

OUT = pathlib.Path(os.environ.get("STE_CAMPAIGN_DIR", "/tmp/ste-structural"))
OUT.mkdir(parents=True, exist_ok=True)

MOVED_WATER = Molecule((WATER.atoms[0], Atom("H", 77, 0, 59), WATER.atoms[2]))
STRAINED_ARGON = CrystalStructure(
    lattice=((527, 0, 0), (0, 526, 0), (0, 0, 526)), sites=FCC_ARGON.sites)
ARGON_TRIMER = Molecule((Atom("Ar", 0, 0, 0), Atom("Ar", 380, 0, 0),
                         Atom("Ar", 190, 329, 0)))

STRUCTURES = {
    "water": WATER, "methane": METHANE, "water-moved": MOVED_WATER,
    "fcc-argon": FCC_ARGON, "rock-salt": ROCK_SALT,
    "fcc-strained": STRAINED_ARGON, "argon-trimer": ARGON_TRIMER,
}


def scaled_energy(candidate, result):
    value = int.from_bytes(result.output, "little", signed=True) // 10**12
    return {"property": candidate.property, "value": value, "unit": "1e12_energy_units"}


def rg2(candidate, result):
    value = int.from_bytes(result.output, "little", signed=True)
    return {"property": candidate.property, "value": value, "unit": "pm2"}


def lattice_volume(candidate, result):
    value = int.from_bytes(result.output[:16], "little", signed=True) // 10**6
    return {"property": candidate.property, "value": value, "unit": "1e6_pm3"}


def gmx_potential(candidate, result):
    text = result.output.decode().split()
    return {"property": candidate.property,
            "value": int(float(text[1]) * 1000), "unit": "milli_kj_per_mol"}


def find_gmx():
    import shutil
    candidate = os.environ.get("STE_GMX_BIN")
    if candidate and pathlib.Path(candidate).exists():
        return pathlib.Path(candidate)
    for name in ("gmx_d", "gmx"):
        found = shutil.which(name)
        if found:
            return pathlib.Path(found)
    return None


def build_points(dual_runner, nexus_runner, gmx, gmx_runner):
    """The campaign points; runners None => unproved native engine."""
    water_pairwise = molecule_to_pairwise_spec(WATER)
    points = []
    for _ in range(3):  # the repeated structure
        points.append(CampaignPoint("water", "pair_energy", water_pairwise,
                                    scaled_energy, runner=dual_runner, label="dual-backend"))
    points.append(CampaignPoint("methane", "pair_energy",
                                molecule_to_pairwise_spec(METHANE),
                                scaled_energy, runner=nexus_runner, label="nexus"))
    points.append(CampaignPoint("water-moved", "pair_energy",
                                molecule_to_pairwise_spec(MOVED_WATER),
                                scaled_energy, runner=nexus_runner, label="nexus"))
    points.append(CampaignPoint("water", "radius_of_gyration",
                                molecule_to_rg_spec(WATER), rg2, label="unproved"))
    for key, crystal in (("fcc-argon", FCC_ARGON), ("rock-salt", ROCK_SALT),
                         ("fcc-strained", STRAINED_ARGON)):
        points.append(CampaignPoint(key, "lattice_volume",
                                    crystal_to_lattice_spec(crystal),
                                    lattice_volume, label="unproved"))
    if gmx is not None:
        mdp = (b"integrator = md\nnsteps = 0\ncutoff-scheme = Verlet\n"
               b"coulombtype = Cut-off\nvdwtype = Cut-off\n"
               b"rlist = 1.0\nrcoulomb = 1.0\nrvdw = 1.0\n")
        descriptor = gromacs_program_descriptor(gmx_version_line(gmx), argon_topology(3))
        spec = ExecutionSpecification(
            program=descriptor, configuration=mdp,
            input_payload=molecule_to_gro(ARGON_TRIMER, (3000, 3000, 3000)))
        points.append(CampaignPoint("argon-trimer", "gmx_potential", spec,
                                    gmx_potential, runner=gmx_runner, label="external-gromacs"))
    return points


def main():
    gmx = find_gmx()
    cache = WarrantCache(OUT / "warrant-cache")
    lanes = default_lanes()

    dual_policy = VerificationPolicy(routine="nexus", independent="sp1",
                                     heavyweight=None, independent_rate_bp=10000)
    nexus_policy = VerificationPolicy(routine="nexus", independent=None, heavyweight=None)

    # stage-9 prefetch: manufacture every planned warrant concurrently
    # (workers=2: the SP1 water proof overlaps the Nexus proofs)
    t0 = time.monotonic()
    pre_dual = prefetch_warrants(dual_policy, [molecule_to_pairwise_spec(WATER)],
                                 cache, OUT, lanes=lanes, max_workers=2)
    pre_nexus = prefetch_warrants(
        nexus_policy,
        [molecule_to_pairwise_spec(METHANE), molecule_to_pairwise_spec(MOVED_WATER)],
        cache, OUT, lanes=lanes, max_workers=2)
    prefetch_wall = time.monotonic() - t0

    warrants: list[WarrantRecord] = []
    dual_runner = policy_runner(dual_policy, OUT, warrants, lanes=lanes, cache=cache)
    nexus_runner = policy_runner(nexus_policy, OUT, warrants, lanes=lanes, cache=cache)
    gmx_runner = (lambda spec: run_gromacs_specification(spec, gmx)) if gmx else None

    pool, doc = make_campaign_pool(sorted(STRUCTURES))
    trace = OperationTrace()
    t0 = time.monotonic()
    report = run_campaign(pool, doc.id, trace,
                          build_points(dual_runner, nexus_runner, gmx, gmx_runner))
    campaign_wall = time.monotonic() - t0

    # evidence baseline: identical points, no verification anywhere
    plain_pool, plain_doc = make_campaign_pool(sorted(STRUCTURES))
    plain = run_campaign(plain_pool, plain_doc.id, OperationTrace(),
                         build_points(None, None, gmx, gmx_runner))

    states = [trace.state_of(o.occurrence) for o in trace.occurrences()]
    hits = [w for w in warrants if w.cache == "hit"]
    by_cache = {}
    for w in warrants:
        by_cache[w.cache] = by_cache.get(w.cache, 0) + 1
    specs = {p.spec.identity() for p in build_points(None, None, gmx, gmx_runner)}

    print("=== STE STRUCTURAL CAMPAIGN ===")
    print(f"structures             : {len(STRUCTURES)} "
          f"({', '.join(sorted(STRUCTURES))})")
    for name, structure in sorted(STRUCTURES.items()):
        print(f"    {name:13} {structure.identity()[:16]}")
    print(f"prefetch               : dual planned {pre_dual.planned} proved {pre_dual.proved}; "
          f"nexus planned {pre_nexus.planned} proved {pre_nexus.proved}; "
          f"wall {prefetch_wall:.1f}s "
          f"(proof time {pre_dual.proving_seconds + pre_nexus.proving_seconds:.1f}s)")
    print(f"campaign               : executions {report.executions}  successes {report.successes}  "
          f"failures {report.failures} {report.failure_kinds}")
    print(f"unique statements      : {len(specs)} specs")
    print(f"observations/unique    : {len(report.observation_ids)}/{report.unique_evidence}  "
          f"occurrences {len(trace.occurrences())} "
          f"(S={states.count(SUCCEEDED)} F={states.count(FAILED)} R={states.count(REJECTED)})")
    print(f"warrants by cache state: {by_cache}")
    water_warrants = {(w.backend, w.outcome) for w in warrants
                      if w.spec_identity == molecule_to_pairwise_spec(WATER).identity()}
    print(f"water's warrants       : {sorted(water_warrants)} -- one computation, two proof systems")
    print(f"campaign wall          : {campaign_wall:.1f}s  "
          f"(hit re-verification {sum(w.seconds for w in hits):.1f}s over {len(hits)} hits)")
    print(f"evidence fingerprints  : {len(pool.fingerprint_history())}")
    assert plain.observation_ids == report.observation_ids, "warrants moved evidence"
    print("evidence invariance    : verified campaign == unproved baseline -- CONFIRMED")


if __name__ == "__main__":
    main()
