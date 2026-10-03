"""§21 tests 17-18: simulation and neural candidates cannot bypass
validation -- the feedback loop's only exit into canonical state is
validate_candidate."""

import ast as pyast
import inspect

from backends.neural.interface import BeliefState
from backends.simulation.interface import CandidateNextState
from core.canonical.delta import CandidateChange
from core.canonical.validation import ValidationError
from core.canonical.version import ProvenanceInfo, Version
from runtime import feedback_loop
from runtime.feedback_loop import submit_neural_belief, submit_simulation_candidate


def test_feedback_loop_has_no_alternate_route_to_minting_a_version():
    """The behavioral tests below prove valid/invalid candidates are
    handled correctly *through* validate_candidate, but nothing
    previously checked that this module has no OTHER way to produce a
    Version -- e.g. by importing make_version or create_genesis_version
    directly and constructing one itself, bypassing validation entirely.
    A regression here would not fail any behavioral test (a bypass could
    still return a Version that looks correct for the happy path) -- it
    would only be caught by a structural check like this one, mirroring
    the same pattern already used for validation.py and the backends."""
    source = inspect.getsource(feedback_loop)
    tree = pyast.parse(source)
    imported_names = set()
    for node in pyast.walk(tree):
        if isinstance(node, pyast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, pyast.Import):
            imported_names.update(alias.name for alias in node.names)

    assert "make_version" not in imported_names
    assert "create_genesis_version" not in imported_names
    assert "validate_candidate" in imported_names


def _candidate(genesis_version, new_value, source):
    provenance = ProvenanceInfo(author=source, transaction_id="tx-sim", source=source)
    change = CandidateChange(
        path="fields.mass.value", operation="replace", old_value=10, new_value=new_value, provenance=provenance
    )
    return CandidateNextState(
        based_on_version=genesis_version.id, proposed_changes=(change,), provenance=provenance
    )


def test_simulation_candidate_is_accepted_only_through_validation(sample_schema, genesis_version):
    candidate = _candidate(genesis_version, 55, "simulation")
    result = submit_simulation_candidate(
        sample_schema, genesis_version.state, candidate, "tx-sim", "2026-08-22T00:02:00Z"
    )
    assert isinstance(result, Version)
    assert result.state.fields["mass"].value == 55
    assert result.parent == genesis_version.id


def test_simulation_candidate_violating_constraints_is_rejected_not_applied(sample_schema, genesis_version):
    # sample_schema declares fields.mass with FieldConstraints(min=0); a
    # simulation proposing a negative mass must be rejected, not silently
    # written into canonical state.
    candidate = _candidate(genesis_version, -5, "simulation")
    result = submit_simulation_candidate(
        sample_schema, genesis_version.state, candidate, "tx-sim-bad", "2026-08-22T00:02:00Z"
    )
    assert isinstance(result, list)
    assert all(isinstance(e, ValidationError) for e in result)
    assert genesis_version.state.fields["mass"].value == 10  # untouched


def test_neural_belief_is_accepted_only_through_validation(sample_schema, genesis_version):
    candidate = _candidate(genesis_version, 61, "neural:demo_model")
    belief = BeliefState(candidate=candidate, confidence=0.9)
    result = submit_neural_belief(sample_schema, genesis_version.state, belief, "tx-neural", "2026-08-22T00:03:00Z")
    assert isinstance(result, Version)
    assert result.state.fields["mass"].value == 61


def test_neural_belief_violating_constraints_is_rejected_not_applied(sample_schema, genesis_version):
    candidate = _candidate(genesis_version, -1, "neural:demo_model")
    belief = BeliefState(candidate=candidate, confidence=0.4)
    result = submit_neural_belief(
        sample_schema, genesis_version.state, belief, "tx-neural-bad", "2026-08-22T00:03:00Z"
    )
    assert isinstance(result, list)
    assert all(isinstance(e, ValidationError) for e in result)
    assert genesis_version.state.fields["mass"].value == 10
