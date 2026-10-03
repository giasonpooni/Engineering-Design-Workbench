"""execution: the Python side of the cross-process execution boundary.

The STE execution vertical (`docs/STE_EXECUTION_VERTICAL.md`):

    OperationTrace (operations/)          -- the ledger, Phase 124-125
          |
    ExecutionSpecification (here)         -- the request: program, config, input
          |
    run_specification (here)              -- one subprocess per execution
          |
    execution-cli (crates/)               -- the Rust engine, checked not trusted
          |
    SpecificationDispatcher (here)        -- the EXISTING ActionDispatcher seam
          |
    experiment.step.run_experiment_step   -- unchanged; the sole admission path

This package writes NOTHING into EvidencePool and imports nothing from
`evidence/`. Its output re-enters the scientific architecture only as a
`DispatchedMeasurement` through the seam Phase 63 built and Phase 125
instrumented -- so evidence identity rules, the admission firewall, and
the operation ledger all apply to computed results exactly as they apply
to every other dispatch, with zero changes to any of them.
"""

from execution.commitments import (
    COMPUTATION_TAG,
    INPUT_TAG,
    OUTPUT_TAG,
    PROGRAM_TAG,
    SPECIFICATION_TAG,
    canonical,
    commit_hex,
)
from execution.engine import (
    EngineIdentityMismatch,
    EngineProtocolError,
    ExecutionRefused,
    ExecutionResult,
    default_cli_path,
    run_specification,
)
from execution.specification import PAIRWISE_ENERGY_DESCRIPTOR, ExecutionSpecification
from execution.dispatcher import SpecificationDispatcher

__all__ = [
    "COMPUTATION_TAG", "INPUT_TAG", "OUTPUT_TAG", "PROGRAM_TAG", "SPECIFICATION_TAG",
    "canonical", "commit_hex",
    "EngineIdentityMismatch", "EngineProtocolError", "ExecutionRefused", "ExecutionResult",
    "default_cli_path", "run_specification",
    "PAIRWISE_ENERGY_DESCRIPTOR", "ExecutionSpecification",
    "SpecificationDispatcher",
]
