"""The Stage 6 scientific execution campaign -- a REAL run, not a fixture.

Heat-diffusion parameter sweep (initial condition x grid size), repeats,
one altered input, a proved subset under BOTH backends, a GROMACS
trajectory extension, and a failure campaign -- all through ONE
EvidencePool and ONE OperationTrace via the unchanged seam.

Prints the numbers Stage 6's report requires. Run:
    STE_GMX_BIN=... python3 scripts/stage6_campaign.py
"""

import os
import pathlib
import struct
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from campaign.driver import CampaignPoint, make_campaign_pool, run_campaign
from execution.engine import run_specification
from execution.gromacs import (
    GROMACS_TRAJECTORY_HEADER, gmx_version_line, gromacs_program_descriptor,
    run_gromacs_trajectory_specification,
)
from execution.proving import (
    default_guest_elf_path, default_heat_guest_elf_path, default_host_path,
    default_nexus_heat_guest_elf_path, default_nexus_host_path,
    default_risc0_heat_guest_elf_path, default_risc0_host_path, proved_runner,
)
from execution.specification import (
    HEAT_DIFFUSION_DESCRIPTOR, ExecutionSpecification, encode_heat_input,
)
from operations.trace import FAILED, REJECTED, SUCCEEDED, OperationTrace

OUT = pathlib.Path(os.environ.get("STE_CAMPAIGN_DIR", "/tmp/ste-campaign"))
OUT.mkdir(parents=True, exist_ok=True)


def heat_spec(steps, values):
    return ExecutionSpecification(
        HEAT_DIFFUSION_DESCRIPTOR, b"", encode_heat_input(steps, list(values))
    )


def peak(candidate, result):
    finals = [int.from_bytes(result.output[a:a + 8], "little", signed=True)
              for a in range(0, len(result.output), 8)]
    return {"property": candidate.property, "value": max(finals), "unit": "fixed_point_mk"}


def profile(kind, n):
    if kind == "hot-center":
        return [0] * (n // 2) + [1_000_000] + [0] * (n - n // 2 - 1)
    if kind == "hot-left":
        return [1_000_000, 800_000] + [0] * (n - 2)
    return [int(1_000_000 * i / (n - 1)) for i in range(n)]  # gradient


def main():
    points = []
    keys = set()

    # -- Target A: the sweep (native, unproved) -------------------------------
    for kind in ("hot-center", "hot-left", "gradient"):
        for n in (6, 12, 24):
            key = f"rod-{kind}-n{n}"
            keys.add(key)
            points.append(CampaignPoint(
                formulation=key, property_name="peak_temperature",
                spec=heat_spec(200, profile(kind, n)), interpret=peak,
            ))

    # -- Targets B/G: spec A three times, then altered input B ----------------
    SPEC_A = heat_spec(50, [0, 700_000, 1_000_000, 700_000, 0, 0])
    keys.add("rod-A")
    for _ in range(3):
        points.append(CampaignPoint("rod-A", "peak_temperature", SPEC_A, peak))
    SPEC_B = heat_spec(50, [0, 700_000, 1_000_001, 700_000, 0, 0])
    keys.add("rod-B")
    points.append(CampaignPoint("rod-B", "peak_temperature", SPEC_B, peak))

    # -- Targets D/E: the proved subset, both backends, same spec A -----------
    sp1 = proved_runner(OUT, host_path=default_host_path(),
                        elf_path=default_heat_guest_elf_path())
    nexus = proved_runner(OUT, host_path=default_nexus_host_path(),
                          elf_path=default_nexus_heat_guest_elf_path())
    points.append(CampaignPoint("rod-A", "peak_temperature", SPEC_A, peak,
                                runner=sp1, label="sp1"))
    points.append(CampaignPoint("rod-A", "peak_temperature", SPEC_A, peak,
                                runner=nexus, label="nexus"))
    if default_risc0_host_path().exists() and default_risc0_heat_guest_elf_path().exists():
        risc0 = proved_runner(OUT, host_path=default_risc0_host_path(),
                              elf_path=default_risc0_heat_guest_elf_path())
        points.append(CampaignPoint("rod-A", "peak_temperature", SPEC_A, peak,
                                    runner=risc0, label="risc0"))
    # two more Nexus proofs over sweep members (proof-vs-evidence dedup)
    for kind, n in (("hot-center", 6), ("hot-left", 6)):
        points.append(CampaignPoint(
            f"rod-{kind}-n{n}", "peak_temperature",
            heat_spec(200, profile(kind, n)), peak, runner=nexus, label="nexus"))

    # -- Target H: GROMACS trajectory extension (external, unverified) --------
    gmx = os.environ.get("STE_GMX_BIN")
    if gmx and pathlib.Path(gmx).exists():
        import functools
        version = gmx_version_line(pathlib.Path(gmx))
        topology = pathlib.Path("tests/test_execution_stage4.py")  # reuse fixture text
        top = b"""[ defaults ]\n1 2 yes 0.5 0.5\n\n[ atomtypes ]\nAr 18 39.948 0.0 A 0.3401 0.978638\n\n[ moleculetype ]\nAR 1\n\n[ atoms ]\n1 Ar 1 AR AR 1 0.0 39.948\n\n[ system ]\nArgon pair\n[ molecules ]\nAR 2\n"""
        mdp = b"integrator = md\nnsteps = 100\ndt = 0.002\nnstenergy = 20\ncutoff-scheme = Verlet\ncoulombtype = Cut-off\nvdwtype = Cut-off\nrlist = 1.0\nrcoulomb = 1.0\nrvdw = 1.0\ngen-vel = no\n"
        prog = gromacs_program_descriptor(version, top, GROMACS_TRAJECTORY_HEADER)

        def gro_pair(x2):
            return (f"Argon pair\n    2\n    1AR     AR    1   1.000   1.000   1.000\n"
                    f"    2AR     AR    2   {x2:.3f}   1.000   1.000\n"
                    f"   3.00000   3.00000   3.00000\n").encode()

        def final_potential(candidate, result):
            last = result.output.decode().splitlines()[-1]
            return {"property": candidate.property,
                    "value": float(last.split()[1]), "unit": "kJ/mol"}

        runner = functools.partial(run_gromacs_trajectory_specification,
                                   gmx_path=pathlib.Path(gmx))
        for i, x2 in enumerate((1.38, 1.45, 1.60)):
            key = f"argon-pair-x{i}"
            keys.add(key)
            points.append(CampaignPoint(
                key, "final_potential",
                ExecutionSpecification(prog, mdp, gro_pair(x2)),
                final_potential, runner=runner, label="external-unverified"))

    # -- Target F: the failure campaign ---------------------------------------
    keys.update({"rod-fail-envelope", "rod-fail-exec", "rod-fail-verify",
                 "rod-fail-reject", "rod-fail-malformed"})
    # 1. unsupported specification through the proved path
    points.append(CampaignPoint(
        "rod-fail-envelope", "peak_temperature",
        ExecutionSpecification(b"no guest implements this", b"", b""),
        peak, runner=sp1, label="fail-unsupported"))
    # 2. execution failure (malformed kernel input)
    points.append(CampaignPoint(
        "rod-fail-exec", "peak_temperature",
        ExecutionSpecification(HEAT_DIFFUSION_DESCRIPTOR, b"", b"bad"),
        peak, label="fail-execution"))
    # 3. verification failure: a lying engine is caught by recomputation
    lying = OUT / "lying-engine"
    honest = run_specification(SPEC_A)
    tampered = honest.computation_identity[:-1] + (
        "0" if honest.computation_identity[-1] != "0" else "1")
    lying.write_text(
        "#!/bin/sh\ncat > /dev/null\nprintf 'ste-execution-result v1\\n'\n"
        f"printf 'spec {honest.specification_identity}\\n'\n"
        f"printf 'program {honest.program_identity}\\n'\n"
        f"printf 'input {honest.input_identity}\\n'\n"
        "printf 'occurrence 0\\nstatus completed\\nexit_code 0\\n'\n"
        f"printf 'output {honest.output.hex()}\\n'\n"
        f"printf 'output_id {honest.output_identity}\\n'\n"
        f"printf 'computation {tampered}\\n'\n")
    lying.chmod(0o755)

    def lying_runner(spec):
        return run_specification(spec, cli_path=lying)

    points.append(CampaignPoint("rod-fail-verify", "peak_temperature", SPEC_A,
                                peak, runner=lying_runner, label="fail-verification"))
    # 4. downstream evidence rejection (wrong property)
    points.append(CampaignPoint(
        "rod-fail-reject", "peak_temperature", SPEC_A,
        lambda c, r: {"property": "not_the_requested_property", "value": 1, "unit": "x"},
        label="fail-rejected"))
    # 5. malformed output interpretation
    points.append(CampaignPoint(
        "rod-fail-malformed", "peak_temperature", SPEC_A,
        lambda c, r: {"property": c.property,
                      "value": struct.unpack("<Q", r.output[:3])[0], "unit": "x"},
        label="fail-malformed"))

    # -- run ------------------------------------------------------------------
    pool, doc = make_campaign_pool(sorted(keys))
    trace = OperationTrace()
    fingerprints_before = len(pool.fingerprint_history())
    t0 = time.monotonic()
    report = run_campaign(pool, doc.id, trace, points)
    wall = time.monotonic() - t0

    proofs = sorted(OUT.glob("proof-*"))
    states = [trace.state_of(o.occurrence) for o in trace.occurrences()]
    print("=== STE STAGE 6 CAMPAIGN ===")
    print(f"specifications        : {len({p.spec.identity() for p in points})}")
    print(f"executions (points)   : {report.executions}")
    print(f"successes             : {report.successes}")
    print(f"failures              : {report.failures}  {report.failure_kinds}")
    print(f"observations admitted : {len(report.observation_ids)}")
    print(f"unique evidence ids   : {report.unique_evidence}")
    print(f"trace occurrences     : {len(trace.occurrences())}")
    print(f"trace transitions     : {sum(len(trace.transitions_of(o.occurrence)) for o in trace.occurrences())}")
    print(f"occurrence states     : SUCCEEDED={states.count(SUCCEEDED)} "
          f"FAILED={states.count(FAILED)} REJECTED={states.count(REJECTED)}")
    print(f"evidence fingerprint growth: {len(pool.fingerprint_history()) - fingerprints_before} steps")
    print(f"proof artifacts       : {len(proofs)}  "
          f"({sum(p.stat().st_size for p in proofs)/1e6:.2f} MB total)")
    for p in proofs:
        print(f"    {p.name}  {p.stat().st_size/1e3:.0f} kB")
    print(f"campaign wall time    : {wall:.1f}s")
    slowest = sorted(zip(report.seconds_per_point, [p.label for p in points]))[-5:]
    print(f"slowest points        : {[(f'{s:.1f}s', l) for s, l in slowest]}")


if __name__ == "__main__":
    main()
