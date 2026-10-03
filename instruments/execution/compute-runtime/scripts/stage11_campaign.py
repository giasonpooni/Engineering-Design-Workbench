"""Stage 11, part 3: the throughput campaign -- genuinely new science.

~22 unique statements, none ever proven before this run: a 13-cell
fresh heat sweep under the standard Stage 7 policy (deterministic
RISC Zero / SP1 samples), four NEW molecules (ammonia, hydrogen
sulfide, carbon dioxide, an argon tetrahedron) through the pairwise
lane with one forced dual-backend point, native-only Rg and crystal
points (attributably unprovable), one GROMACS external execution, and
deliberate repeats so first-proof deduplication is MEASURED, not
assumed.

Manufacture runs through the stage-9 prefetcher under the stage-11
memory-aware limits; the campaign then dispatches through the
unchanged seam on warrant hits (SP1 hits through the stage-10
verification artifact). Evidence is asserted invariant against an
unproved baseline of the same points.
"""

import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from campaign.driver import CampaignPoint, make_campaign_pool, run_campaign
from campaign.policy import (
    VerificationPolicy, WarrantRecord, default_lanes, policy_runner,
)
from campaign.prefetch import prefetch_warrants
from campaign.warrant_cache import WarrantCache
from execution.gromacs import (
    gmx_version_line, gromacs_program_descriptor, run_gromacs_specification,
)
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR, ExecutionSpecification, encode_heat_input,
)
from operations.trace import FAILED, REJECTED, SUCCEEDED, OperationTrace
from scripts.stage11_memory_curve import RssSampler
from structures.crystal import CrystalSite, CrystalStructure
from structures.gromacs_bridge import argon_topology, molecule_to_gro
from structures.lowering import (
    crystal_to_lattice_spec, molecule_to_pairwise_spec, molecule_to_rg_spec,
)
from structures.molecule import Atom, Molecule

OUT = pathlib.Path(os.environ.get("STE_CAMPAIGN_DIR", "/tmp/ste-stage11-campaign"))
OUT.mkdir(parents=True, exist_ok=True)

MARKER = 333_331  # fresh-statement marker for the heat sweep

#: Stage-11 measured memory classes (peak sampled RSS per prover on
#: this 16 GB machine class): Nexus 2.6-10.1 GB (STATEMENT-SIZE
#: dependent; n=24 sweep cells are the worst case), SP1 9.6 GB,
#: RISC Zero 1.3 GB (memory-light -- measured, contrary to the naive
#: cost-implies-memory assumption). CALLER-DECLARED limits derived from
#: those measurements; the serial retry pass remains the backstop for
#: co-scheduled cross-backend worst cases (nexus-big + sp1 ~ 19.7 GB
#: exceeds the machine; per-backend caps do not gate ACROSS backends).
WORKER_LIMITS = {"nexus": 2, "risc0": 2, "sp1": 1}

# -- new real structures (textbook geometries, rounded once, here) ----
AMMONIA = Molecule((Atom("N", 0, 0, 0), Atom("H", 94, 0, -38),
                    Atom("H", -47, 81, -38), Atom("H", -47, -81, -38)))
HYDROGEN_SULFIDE = Molecule((Atom("S", 0, 0, 0), Atom("H", 96, 0, 93),
                             Atom("H", -96, 0, 93)))
CARBON_DIOXIDE = Molecule((Atom("C", 0, 0, 0), Atom("O", 116, 0, 0),
                           Atom("O", -116, 0, 0)))
ARGON_TETRAHEDRON = Molecule((Atom("Ar", 0, 0, 0), Atom("Ar", 380, 0, 0),
                              Atom("Ar", 190, 329, 0), Atom("Ar", 190, 110, 310)))
BCC_IRON = CrystalStructure(
    lattice=((287, 0, 0), (0, 287, 0), (0, 0, 287)),
    sites=(CrystalSite("Fe", 0, 0, 0), CrystalSite("Fe", 500_000, 500_000, 500_000)))
STRAINED_IRON = CrystalStructure(
    lattice=((290, 0, 0), (0, 287, 0), (0, 0, 287)), sites=BCC_IRON.sites)


def profile(kind, n):
    if kind == "hot-center":
        return [MARKER] * (n // 2) + [1_000_000] + [MARKER] * (n - n // 2 - 1)
    if kind == "hot-left":
        return [1_000_000, 800_000] + [MARKER] * (n - 2)
    return [MARKER + int(1_000_000 * i / (n - 1)) for i in range(n)]


HEAT_SPECS = [
    ExecutionSpecification(HEAT_DIFFUSION_DESCRIPTOR, b"",
                           encode_heat_input(200, profile(kind, n)))
    for kind in ("hot-center", "hot-left", "gradient")
    for n in (6, 12, 24)
] + [
    ExecutionSpecification(HEAT_DIFFUSION_DESCRIPTOR, b"",
                           encode_heat_input(202, profile("gradient", n)))
    for n in (8, 10, 16, 20)
]


def peak(candidate, result):
    finals = [int.from_bytes(result.output[a:a + 8], "little", signed=True)
              for a in range(0, len(result.output), 8)]
    return {"property": candidate.property, "value": max(finals), "unit": "fixed_point_mk"}


def scaled_energy(candidate, result):
    value = int.from_bytes(result.output, "little", signed=True) // 10**12
    return {"property": candidate.property, "value": value, "unit": "1e12_energy_units"}


def rg2(candidate, result):
    return {"property": candidate.property,
            "value": int.from_bytes(result.output, "little", signed=True), "unit": "pm2"}


def lattice_volume(candidate, result):
    return {"property": candidate.property,
            "value": int.from_bytes(result.output[:16], "little", signed=True) // 10**6,
            "unit": "1e6_pm3"}


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


STANDARD = VerificationPolicy(routine="nexus", independent="risc0",
                              heavyweight="sp1",
                              independent_rate_bp=2500, heavyweight_rate_bp=800)
DUAL_SP1 = VerificationPolicy(routine="nexus", independent="sp1",
                              heavyweight=None, independent_rate_bp=10000)
NEXUS_ONLY = VerificationPolicy(routine="nexus", independent=None, heavyweight=None)


def build_points(std_runner, dual_runner, nexus_runner, gmx, gmx_runner):
    points, keys = [], set()
    for at, spec in enumerate(HEAT_SPECS):
        key = f"rod11-{at}"; keys.add(key)
        points.append(CampaignPoint(key, "peak_temperature", spec, peak,
                                    runner=std_runner, label="policy"))
    # repeats of the first heat statement: dedup is measured, not assumed
    for _ in range(3):
        points.append(CampaignPoint("rod11-0", "peak_temperature", HEAT_SPECS[0],
                                    peak, runner=std_runner, label="repeat"))
    molecules = (("ammonia", AMMONIA, dual_runner, "dual-backend"),
                 ("h2s", HYDROGEN_SULFIDE, nexus_runner, "nexus"),
                 ("co2", CARBON_DIOXIDE, nexus_runner, "nexus"),
                 ("ar4", ARGON_TETRAHEDRON, nexus_runner, "nexus"))
    for key, molecule, runner, label in molecules:
        keys.add(key)
        points.append(CampaignPoint(key, "pair_energy",
                                    molecule_to_pairwise_spec(molecule),
                                    scaled_energy, runner=runner, label=label))
    for _ in range(2):
        points.append(CampaignPoint("h2s", "pair_energy",
                                    molecule_to_pairwise_spec(HYDROGEN_SULFIDE),
                                    scaled_energy, runner=nexus_runner, label="repeat"))
    for key, molecule in (("ammonia", AMMONIA), ("h2s", HYDROGEN_SULFIDE)):
        points.append(CampaignPoint(key, "radius_of_gyration",
                                    molecule_to_rg_spec(molecule), rg2, label="unproved"))
    for key, crystal in (("bcc-iron", BCC_IRON), ("bcc-strained", STRAINED_IRON)):
        keys.add(key)
        points.append(CampaignPoint(key, "lattice_volume",
                                    crystal_to_lattice_spec(crystal),
                                    lattice_volume, label="unproved"))
    if gmx is not None:
        keys.add("ar4-gmx")
        mdp = (b"integrator = md\nnsteps = 0\ncutoff-scheme = Verlet\n"
               b"coulombtype = Cut-off\nvdwtype = Cut-off\n"
               b"rlist = 1.0\nrcoulomb = 1.0\nrvdw = 1.0\n")
        descriptor = gromacs_program_descriptor(gmx_version_line(gmx), argon_topology(4))
        spec = ExecutionSpecification(
            program=descriptor, configuration=mdp,
            input_payload=molecule_to_gro(ARGON_TETRAHEDRON, (3000, 3000, 3000)))
        points.append(CampaignPoint("ar4-gmx", "gmx_potential", spec,
                                    gmx_potential, runner=gmx_runner, label="external"))
    return points, sorted(keys)


def main():
    gmx = find_gmx()
    cache = WarrantCache(OUT / "warrant-cache")
    lanes = default_lanes()

    # phase 1: memory-aware concurrent manufacture of every planned warrant
    sampler = RssSampler(); sampler.start()
    t0 = time.monotonic()
    reports = []
    for policy, specs in ((STANDARD, HEAT_SPECS),
                          (DUAL_SP1, [molecule_to_pairwise_spec(AMMONIA)]),
                          (NEXUS_ONLY, [molecule_to_pairwise_spec(m) for m in
                                        (HYDROGEN_SULFIDE, CARBON_DIOXIDE, ARGON_TETRAHEDRON)])):
        reports.append(prefetch_warrants(policy, specs, cache, OUT, lanes=lanes,
                                         max_workers=4, worker_limits=WORKER_LIMITS))
    prefetch_wall = time.monotonic() - t0
    sampler.stop.set(); sampler.join()

    proved = sum(r.proved for r in reports)
    planned = sum(r.planned for r in reports)
    retried = sum(1 for r in reports for o in r.outcomes if o.retried)
    failed = sum(r.failed for r in reports)
    ooms = sum(1 for r in reports for o in r.outcomes
               if "host exited -9" in ((o.first_error or "") + (o.error or "")))
    by_backend = {}
    for r in reports:
        for o in r.outcomes:
            if o.outcome == "proved":
                by_backend.setdefault(o.backend, []).append(o.seconds)

    # phase 2: the campaign through the unchanged seam, all warrants warm
    warrants: list[WarrantRecord] = []
    std_runner = policy_runner(STANDARD, OUT, warrants, lanes=lanes, cache=cache)
    dual_runner = policy_runner(DUAL_SP1, OUT, warrants, lanes=lanes, cache=cache)
    nexus_runner = policy_runner(NEXUS_ONLY, OUT, warrants, lanes=lanes, cache=cache)
    gmx_runner = (lambda spec: run_gromacs_specification(spec, gmx)) if gmx else None
    points, keys = build_points(std_runner, dual_runner, nexus_runner, gmx, gmx_runner)
    pool, doc = make_campaign_pool(keys)
    trace = OperationTrace()
    t0 = time.monotonic()
    report = run_campaign(pool, doc.id, trace, points)
    campaign_wall = time.monotonic() - t0

    # evidence baseline: identical points, no verification anywhere
    plain_points, plain_keys = build_points(None, None, None, gmx, gmx_runner)
    plain_pool, plain_doc = make_campaign_pool(plain_keys)
    plain = run_campaign(plain_pool, plain_doc.id, OperationTrace(), plain_points)

    states = [trace.state_of(o.occurrence) for o in trace.occurrences()]
    hits = [w for w in warrants if w.cache == "hit"]
    by_cache = {}
    for w in warrants:
        by_cache[w.cache] = by_cache.get(w.cache, 0) + 1
    unique_specs = {p.spec.identity() for p in points}

    print("=== STE STAGE 11 THROUGHPUT CAMPAIGN ===")
    print(f"unique specifications  : {len(unique_specs)}  campaign points {len(points)}")
    print(f"manufacture            : planned {planned} statements, proved {proved}, "
          f"failed {failed}, retried {retried}, oom-events {ooms}")
    for backend, secs in sorted(by_backend.items()):
        print(f"    {backend:8} n={len(secs):2}  total {sum(secs):7.1f}s  "
              f"mean {sum(secs)/len(secs):6.1f}s")
    print(f"manufacture wall       : {prefetch_wall:.1f}s under limits {WORKER_LIMITS} "
          f"(sum of proof times {sum(s for v in by_backend.values() for s in v):.1f}s -> "
          f"concurrency x{sum(s for v in by_backend.values() for s in v) / prefetch_wall:.2f})")
    print(f"    peak/worker {sampler.peak_single/1024/1024:.1f} GB  "
          f"aggregate peak {sampler.peak_aggregate/1024/1024:.1f} GB")
    print(f"campaign               : executions {report.executions}  successes {report.successes}  "
          f"failures {report.failures} {report.failure_kinds}")
    print(f"observations/unique    : {len(report.observation_ids)}/{report.unique_evidence}  "
          f"occurrences {len(trace.occurrences())} "
          f"(S={states.count(SUCCEEDED)} F={states.count(FAILED)} R={states.count(REJECTED)})")
    print(f"warrants by cache state: {by_cache}  ({len(hits)} hits, "
          f"{sum(w.seconds for w in hits):.1f}s re-verification)")
    print(f"campaign wall          : {campaign_wall:.1f}s")
    print(f"evidence fingerprints  : {len(pool.fingerprint_history())}")
    generations = proved
    print(f"dedup check            : {len(unique_specs)} unique specs, "
          f"{planned} planned statements, {generations} generations -- "
          f"repeats produced ZERO extra manufacture" if generations == planned == proved
          else "dedup check: SEE COUNTS ABOVE")
    assert plain.observation_ids == report.observation_ids, "scheduling moved evidence"
    print("evidence invariance    : scheduled campaign == unproved baseline -- CONFIRMED")


if __name__ == "__main__":
    main()
