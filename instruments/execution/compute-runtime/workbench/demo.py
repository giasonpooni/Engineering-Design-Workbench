"""`python -m workbench.demo` -- a deterministic, reproducible walkthrough
of the exact same command surface `workbench.cli.dispatch` exposes
interactively. No parallel implementation of any domain math: every
step below calls `workbench.cli.dispatch` (the same function `workbench.
cli.run_repl` uses for real interactive input) against a `WorkbenchState`
built the same way `workbench.cli.run_repl`'s own default builds one
(`workbench.interaction.bootstrap_default_scenario`), so this demo is a
genuine exercise of the real interface, not a re-implementation of it.

DETERMINISM: `bootstrap_default_scenario`/`WorkbenchState.observe` both
read a `clock: Callable[[], str]` for every timestamp they need
(`Document.retrieved_at`, `ExperimentalResult.extracted_at`) -- this
module supplies a small, fixed, incrementing clock instead of the real
wall clock `workbench.cli.run_repl` uses by default, so repeated runs of
this demo produce byte-for-byte identical output. Nothing about the
underlying `ModelState`/`Prediction`/`PredictionAssessment` mathematics
is touched by this -- content-addressed identity has never depended on
wall-clock time anywhere in this codebase (Phase 52 onward), and this
demo does not change that.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

from workbench.cli import dispatch
from workbench.interaction import DEFAULT_PROPERTY, WorkbenchState, bootstrap_default_scenario


def _make_fixed_clock() -> Callable[[], str]:
    counter = {"n": 0}

    def clock() -> str:
        n = counter["n"]
        counter["n"] += 1
        return f"2026-08-24T00:{n:02d}:00Z"

    return clock


def _find_tensile_strength_index(state: WorkbenchState) -> int:
    for index, candidate in enumerate(state.list_candidates()):
        if candidate.property == DEFAULT_PROPERTY:
            return index
    raise RuntimeError(f"no generated candidate targets property {DEFAULT_PROPERTY!r}")


def _run_step(state: WorkbenchState, command: str, args: List[str]) -> None:
    rendered = f"workbench> {command} {' '.join(args)}".rstrip()
    print(rendered)
    print(dispatch(state, command, args))
    print()


def run_demo() -> WorkbenchState:
    """Executes the fixed scenario: inspect -> predict -> explore a
    hypothetical -> observe two real values -> predict after each ->
    inspect history. Returns the final `WorkbenchState` so a caller
    (e.g. this module's own test) can assert on it directly rather than
    re-parsing printed text."""
    state = bootstrap_default_scenario(clock=_make_fixed_clock())
    tensile_index = _find_tensile_strength_index(state)

    steps: List[Tuple[str, List[str]]] = [
        ("status", []),
        ("candidates", []),
        ("select", [str(tensile_index + 1)]),  # workbench.cli displays/accepts candidates 1-indexed
        ("predict", []),
        ("explore", ["90"]),
        ("observe", ["90"]),
        ("predict", []),
        ("observe", ["100"]),
        ("predict", []),
        ("history", []),
    ]
    for command, args in steps:
        _run_step(state, command, args)
    return state


if __name__ == "__main__":
    run_demo()
