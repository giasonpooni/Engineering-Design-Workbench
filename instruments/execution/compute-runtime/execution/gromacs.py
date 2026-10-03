"""GROMACS workloads: real scientific computations behind the STE seam.

Three workloads, three descriptors, one shared grompp->mdrun->energy
pipeline (stage 4 widened this module from the original single-point
calculation):

    ste.gromacs.single-point-energy.v1   one Potential value (stage 1)
    ste.gromacs.trajectory-energy.v1     a short deterministic MD
                                         trajectory; output = the full
                                         per-frame Potential series
    ste.gromacs.energy-minimization.v1   steepest-descent relaxation of
                                         a structured input; output =
                                         the convergence series PLUS the
                                         minimized structure

Original module docstring (still accurate for the shared machinery):

Runs `gmx grompp` -> `gmx mdrun` (nsteps=0) -> `gmx energy` over a
caller-supplied system and reports the potential energy -- through the
SAME `ExecutionSpecification` / `ExecutionResult` types and the same
identity discipline as the Rust engine, so a GROMACS computation and a
native-kernel computation are the same KIND of object to everything
downstream.

The dimension mapping (and why it is honest):

    program        the workload descriptor: engine name+version line and
                   the full topology bytes -- WHAT would be computed
    configuration  the .mdp bytes -- the parameters GOVERNING the run
    input          the .gro bytes -- the system the run is OVER

WHERE THIS SITS ON THE TRUST SPECTRUM -- weaker than the Rust engine,
and stated rather than blurred. The Rust engine echoes every identity
and is recomputed against (`execution/engine.py`); GROMACS knows nothing
of our identities, so every identity here is computed BY THIS MODULE
from bytes it holds. The coupling between the descriptor and gmx's
actual behavior is DECLARED (the descriptor's version line is trusted to
name the binary that ran -- verified against `gmx --version` output at
descriptor-build time, but nothing binds the binary at run time). This
is the native bytes-vs-behavior gap plus an external process. What the
workload still gains from the substrate: content-addressed request and
computation identities, refusal semantics, the operation ledger at the
dispatch seam, and an empirical repeat-determinism check in its tests.

DETERMINISM SCOPE: same binary, same machine -- exercised by running
twice and comparing computation identities. Bit-identical results ACROSS
machines are NOT claimed (this is floating-point code; the build pins
double precision and no SIMD, which helps and is not a proof). The
output bytes are gmx's OWN text for the energy value, taken verbatim
from the .xvg -- no float re-formatting on our side that could
introduce a second source of divergence.

COMPUTATION != MEASUREMENT applies with full force: a computed argon
pair energy is a computation about a model system. Nothing here measured
anything, and the dispatch declaration downstream says `simulation:`.
"""

from __future__ import annotations

import pathlib
import subprocess
import tempfile
from typing import Optional

from execution.commitments import COMPUTATION_TAG, OUTPUT_TAG, canonical_u32, commit_hex
from execution.engine import EngineProtocolError, ExecutionResult
from execution.specification import ExecutionSpecification

GROMACS_DESCRIPTOR_HEADER = b"ste.gromacs.single-point-energy.v1"
GROMACS_TRAJECTORY_HEADER = b"ste.gromacs.trajectory-energy.v1"
GROMACS_MINIMIZATION_HEADER = b"ste.gromacs.energy-minimization.v1"
_TOPOLOGY_MARKER = b"\n[topology]\n"

#: Fault exit codes for the stages of a run. A failed stage HALTS the
#: execution (no output, no computation identity); it is never papered
#: over with a zero energy.
FAULT_GROMPP = 10
FAULT_MDRUN = 11
FAULT_ENERGY = 12
FAULT_PARSE = 13


def gmx_version_line(gmx_path: pathlib.Path) -> str:
    """The one line of `gmx --version` output naming the version."""
    proc = subprocess.run(
        [str(gmx_path), "-quiet", "--version"], capture_output=True, timeout=60
    )
    for line in proc.stdout.decode(errors="replace").splitlines():
        if line.startswith("GROMACS version"):
            return line.strip()
    raise EngineProtocolError(f"{gmx_path} did not report a GROMACS version")


def gromacs_program_descriptor(
    version_line: str, topology: bytes, header: bytes = GROMACS_DESCRIPTOR_HEADER
) -> bytes:
    """Build the program bytes for a GROMACS workload.

    The engine version is part of the PROGRAM, not incidental metadata:
    two GROMACS versions are two programs, exactly as two backend
    versions are two proofs (Phase 126 §8). The header names WHICH
    GROMACS workload this is -- single-point, trajectory, minimization
    -- because they have different output semantics and are therefore
    different programs even over the same topology."""
    return header + b"\n" + version_line.encode("utf-8") + _TOPOLOGY_MARKER + topology


def _split_descriptor(program: bytes, header: bytes) -> bytes:
    head, marker, topology = program.partition(_TOPOLOGY_MARKER)
    if not head.startswith(header) or not marker:
        raise EngineProtocolError(f"not a {header.decode()} program descriptor")
    return topology


def run_gromacs_specification(
    spec: ExecutionSpecification,
    gmx_path: pathlib.Path,
    workdir: Optional[pathlib.Path] = None,
) -> ExecutionResult:
    """Run one GROMACS single-point energy evaluation of `spec`.

    Every invocation is a fresh working directory and a fresh set of
    processes; nothing persists between runs. The occurrence field is 0
    with the same per-invocation meaning as the Rust CLI's."""
    topology = _split_descriptor(spec.program, GROMACS_DESCRIPTOR_HEADER)

    def _result(status, exit_code, output=None, detail=None):
        output_identity = None
        computation_identity = None
        if output is not None:
            output_identity = commit_hex(OUTPUT_TAG, [output])
            computation_identity = commit_hex(
                COMPUTATION_TAG,
                [
                    bytes.fromhex(spec.program_identity()),
                    bytes.fromhex(spec.input_identity()),
                    bytes.fromhex(output_identity),
                    canonical_u32(exit_code),
                ],
            )
        return ExecutionResult(
            specification=spec, specification_identity=spec.identity(),
            program_identity=spec.program_identity(), input_identity=spec.input_identity(),
            engine_occurrence=0, status=status, exit_code=exit_code,
            output=output, output_identity=output_identity,
            computation_identity=computation_identity, detail=detail,
        )

    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        base = pathlib.Path(tmp)
        (base / "system.top").write_bytes(topology)
        (base / "conf.gro").write_bytes(spec.input_payload)
        (base / "run.mdp").write_bytes(spec.configuration)

        def _gmx(args, stdin=None):
            return subprocess.run(
                [str(gmx_path), "-quiet", *args], cwd=base, input=stdin,
                capture_output=True, timeout=300,
            )

        grompp = _gmx(["grompp", "-f", "run.mdp", "-c", "conf.gro",
                       "-p", "system.top", "-o", "run.tpr", "-maxwarn", "2"])
        if grompp.returncode != 0:
            return _result("halted", FAULT_GROMPP,
                           detail=grompp.stderr.decode(errors="replace")[-400:])
        mdrun = _gmx(["mdrun", "-s", "run.tpr", "-deffnm", "run", "-nt", "1"])
        if mdrun.returncode != 0:
            return _result("halted", FAULT_MDRUN,
                           detail=mdrun.stderr.decode(errors="replace")[-400:])
        energy = _gmx(["energy", "-f", "run.edr", "-o", "energy.xvg"],
                      stdin=b"Potential\n")
        if energy.returncode != 0:
            return _result("halted", FAULT_ENERGY,
                           detail=energy.stderr.decode(errors="replace")[-400:])

        data_lines = [
            line for line in (base / "energy.xvg").read_text().splitlines()
            if line and not line.startswith(("#", "@"))
        ]
        if len(data_lines) != 1 or len(data_lines[0].split()) != 2:
            return _result("halted", FAULT_PARSE,
                           detail=f"unexpected xvg shape: {data_lines[:2]!r}")
        # gmx's own text for the value, verbatim -- our one canonical
        # output encoding for this workload, with no re-formatting.
        potential_text = data_lines[0].split()[1]
        output = b"potential_kj_per_mol " + potential_text.encode("ascii")
        return _result("completed", 0, output=output)


def _run_series_workload(
    spec: ExecutionSpecification,
    gmx_path: pathlib.Path,
    header: bytes,
    output_builder,
    workdir: Optional[pathlib.Path] = None,
) -> ExecutionResult:
    """Shared grompp -> mdrun -> energy pipeline for the stage-4
    workloads. `output_builder(data_lines, base)` turns the xvg data
    lines (verbatim text) and the run directory into the workload's
    canonical output bytes -- each descriptor commits to its own output
    encoding, so the builder is per-workload by design."""
    topology = _split_descriptor(spec.program, header)

    def _result(status, exit_code, output=None, detail=None):
        output_identity = None
        computation_identity = None
        if output is not None:
            output_identity = commit_hex(OUTPUT_TAG, [output])
            computation_identity = commit_hex(
                COMPUTATION_TAG,
                [
                    bytes.fromhex(spec.program_identity()),
                    bytes.fromhex(spec.input_identity()),
                    bytes.fromhex(output_identity),
                    canonical_u32(exit_code),
                ],
            )
        return ExecutionResult(
            specification=spec, specification_identity=spec.identity(),
            program_identity=spec.program_identity(), input_identity=spec.input_identity(),
            engine_occurrence=0, status=status, exit_code=exit_code,
            output=output, output_identity=output_identity,
            computation_identity=computation_identity, detail=detail,
        )

    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        base = pathlib.Path(tmp)
        (base / "system.top").write_bytes(topology)
        (base / "conf.gro").write_bytes(spec.input_payload)
        (base / "run.mdp").write_bytes(spec.configuration)

        def _gmx(args, stdin=None):
            return subprocess.run(
                [str(gmx_path), "-quiet", *args], cwd=base, input=stdin,
                capture_output=True, timeout=600,
            )

        grompp = _gmx(["grompp", "-f", "run.mdp", "-c", "conf.gro",
                       "-p", "system.top", "-o", "run.tpr", "-maxwarn", "2"])
        if grompp.returncode != 0:
            return _result("halted", FAULT_GROMPP,
                           detail=grompp.stderr.decode(errors="replace")[-400:])
        mdrun = _gmx(["mdrun", "-s", "run.tpr", "-deffnm", "run", "-nt", "1"])
        if mdrun.returncode != 0:
            return _result("halted", FAULT_MDRUN,
                           detail=mdrun.stderr.decode(errors="replace")[-400:])
        energy = _gmx(["energy", "-f", "run.edr", "-o", "energy.xvg"],
                      stdin=b"Potential\n")
        if energy.returncode != 0:
            return _result("halted", FAULT_ENERGY,
                           detail=energy.stderr.decode(errors="replace")[-400:])

        data_lines = [
            line for line in (base / "energy.xvg").read_text().splitlines()
            if line and not line.startswith(("#", "@"))
        ]
        if not data_lines:
            return _result("halted", FAULT_PARSE, detail="energy.xvg carried no data lines")
        try:
            output = output_builder(data_lines, base)
        except FileNotFoundError as missing:
            return _result("halted", FAULT_PARSE, detail=f"expected artifact missing: {missing}")
        return _result("completed", 0, output=output)


def run_gromacs_trajectory_specification(
    spec: ExecutionSpecification,
    gmx_path: pathlib.Path,
    workdir: Optional[pathlib.Path] = None,
) -> ExecutionResult:
    """A short deterministic MD trajectory (A1 / Target E).

    Output bytes: `gmx-energy-series kJ/mol\\n` + every per-frame
    Potential line from the .xvg, verbatim -- the trajectory's energy
    evolution IS the result, not just its endpoint. Everything about the
    trust spectrum, determinism scope (same binary, same machine) and
    COMPUTATION != MEASUREMENT from the single-point runner applies
    unchanged."""

    def build(data_lines, _base):
        return b"gmx-energy-series kJ/mol\n" + "\n".join(data_lines).encode("ascii")

    return _run_series_workload(spec, gmx_path, GROMACS_TRAJECTORY_HEADER, build, workdir)


def run_gromacs_minimization_specification(
    spec: ExecutionSpecification,
    gmx_path: pathlib.Path,
    workdir: Optional[pathlib.Path] = None,
) -> ExecutionResult:
    """Steepest-descent energy minimization (A3): a structured scientific
    input (a perturbed lattice) relaxed to a structured numerical output.

    Output bytes:

        gmx-minimization v1\\n
        [energy-series]\\n     the per-step Potential convergence series
        ...\\n
        [minimized-structure]\\n
        ...                    run.gro WITHOUT its title line (the atom
                               count, atom records and box vectors; the
                               title is presentation, not result)
    """

    def build(data_lines, base):
        structure_lines = (base / "run.gro").read_text().splitlines()[1:]
        return (
            b"gmx-minimization v1\n[energy-series]\n"
            + "\n".join(data_lines).encode("ascii")
            + b"\n[minimized-structure]\n"
            + "\n".join(structure_lines).encode("ascii")
        )

    return _run_series_workload(spec, gmx_path, GROMACS_MINIMIZATION_HEADER, build, workdir)
