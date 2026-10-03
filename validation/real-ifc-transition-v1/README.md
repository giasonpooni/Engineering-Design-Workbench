# Retained IFC transition qualification

This directory retains the final development execution of both IFC cases and
their verified transition envelopes. The public buildingSMART model is refused;
the bounded synthetic room reaches authority review without state admission.
See `docs/REAL_IFC_TRANSITION.md` for the applicability limits and reproduction
commands.

`qualification.json` records the installed-wheel test result: 338 passed, zero
failures, errors or skips. The installed modules' 16-file closure matched the
development source before the native executions. Each execution bundle retains
that closure, its inputs, native audit, native execution and reproduction bytes.
The wheel digest identifies the exact tested build; the package can be rebuilt
from this branch and the workflow retains its wheel.

The experiment ran before this patch was committed. Accordingly,
`experiment-summary.json` records the parent commit and correctly sets
`execution_source_matches_commit` to false. Its source closure identifies the
executed implementation; that flag must not be interpreted as a clean checkout
attestation. The CI workflow repeats the executions at its checked-out commit
and retains platform-specific reports.

Phase timings are single-run diagnostics. The original source observation is
synthetic, not a field measurement. Digests and retained provider output do not
authenticate an imported execution's author or prove physical validity.
