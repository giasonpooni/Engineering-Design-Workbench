"""SpecificationDispatcher: computed results enter through the EXISTING seam.

This is deliberately an `ActionDispatcher` (experiment/interface.py) and
nothing more. The STE diagram's RESULT STATE -> EVIDENCE ADMISSION edge
already exists in this codebase: `experiment.step.run_experiment_step`
takes what a dispatcher returns, admits the Record, and hands the
semantic facts to `materials.results` -- the sole semantic write
boundary -- while the Phase 125 instrumentation records the operation.
Building a second path from execution to evidence would mean a second
admission route; reusing the seam means zero changes to EvidencePool,
zero changes to evidence identity, and every existing firewall applying
to computed results automatically.

What crosses the seam is a `DispatchedMeasurement` whose
`extraction_method` declares `simulation:` -- the one prefix of the
epistemic classifier that asserts NO external-world event occurred
(Phase 120). A checked native execution is exactly that: a computation
happened; nothing was measured. The declaration is still a declaration
(Phase 119: not a witness); what is BETTER here than a scripted fixture
is only that this layer independently recomputed every identity of the
computation it is reporting.

EXECUTION IDENTITY != EVIDENCE IDENTITY, held structurally: the content
mapping this dispatcher emits is built by the caller's `interpret`
function from the computation's OUTPUT -- the specification, occurrence
number, and computation identity ride along in the RECORD's raw content
(structural bookkeeping, Phase 44's distinction), never in the
Observation's semantic content. Re-running the same specification
therefore admits a byte-identical Observation with the SAME evidence id:
execution history does not contaminate reproducible evidence identity.
`tests/test_execution_dispatcher.py` proves that by running the loop
twice in two sessions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Optional

from experiment.interface import DispatchedMeasurement
from materials.candidates import ActionCandidate

from execution.engine import ExecutionResult, run_specification
from execution.specification import ExecutionSpecification


@dataclass(frozen=True)
class SpecificationDispatcher:
    """Dispatch = build the specification for the chosen candidate, run
    it through the checked engine, interpret the output into semantic
    content. A halted or refused execution raises -- the Phase 125 seam
    records the dispatch as FAILED, and no measurement is fabricated
    from a run that produced no output."""

    spec_for: Callable[[ActionCandidate], ExecutionSpecification]
    interpret: Callable[[ActionCandidate, ExecutionResult], Mapping[str, object]]
    extracted_at: str
    cli_path: Optional[Path] = field(default=None)
    #: How to execute a specification. Defaults to the checked Rust
    #: engine; `execution.gromacs.run_gromacs_specification` (partially
    #: applied with its gmx path) is the external-process alternative.
    #: Whatever runs, the SAME result shape comes back and the SAME
    #: seam carries it onward -- backends are substitutable below this
    #: line without anything downstream knowing.
    runner: Optional[Callable[[ExecutionSpecification], ExecutionResult]] = field(default=None)

    def dispatch(self, candidate: ActionCandidate) -> DispatchedMeasurement:
        spec = self.spec_for(candidate)
        if self.runner is not None:
            result = self.runner(spec)
        else:
            result = run_specification(spec, cli_path=self.cli_path)
        if result.status != "completed":
            raise RuntimeError(
                f"execution halted (exit {result.exit_code}) for candidate "
                f"{candidate.id!r}: {result.detail} -- no output, no measurement"
            )
        content = self.interpret(candidate, result)
        return DispatchedMeasurement(
            content=content,
            record_locator=(
                f"execution:{result.specification_identity[:16]}"
                f":{result.computation_identity[:16]}"
            ),
            record_raw_content=(
                "ste-execution v1\n"
                f"specification {result.specification_identity}\n"
                f"program {result.program_identity}\n"
                f"input {result.input_identity}\n"
                f"engine_occurrence {result.engine_occurrence}\n"
                f"exit_code {result.exit_code}\n"
                f"output_id {result.output_identity}\n"
                f"computation {result.computation_identity}\n"
            ),
            extracted_at=self.extracted_at,
            extraction_method="simulation:deterministic_native_execution",
        )
