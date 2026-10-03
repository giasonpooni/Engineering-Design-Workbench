"""Phase 68: the deterministic demo (`python -m workbench.demo`) is
reproducible and exercises a real, complete residual loop through the
production APIs -- not a fabricated transcript."""

from workbench.demo import run_demo


def test_demo_is_deterministic_across_runs():
    state_a = run_demo()
    state_b = run_demo()
    assert state_a.session.state.id == state_b.session.state.id
    assert [s.id for s in state_a.session.state_history] == [s.id for s in state_b.session.state_history]


def test_demo_produces_a_real_two_cycle_residual_loop():
    state = run_demo()
    assert len(state.assessments) == 2
    first, second = state.assessments
    assert first.observed_value == 90.0
    assert first.residual is None  # honestly undetermined -- no prior sample
    assert second.observed_value == 100.0
    assert second.residual == 10.0  # 100 - 90
    assert len(state.session.state_history) == 3  # empty -> after y=90 -> after y=100
