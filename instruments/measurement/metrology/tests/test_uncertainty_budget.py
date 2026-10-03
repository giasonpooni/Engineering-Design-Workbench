"""Reference tests for uncertainty_budget.

Every assertion is against a closed-form value or a published constant, not
against a previously recorded output of this code.
"""

from __future__ import annotations

import math

import pytest

from instrument_chain.uncertainty_budget import (
    Budget,
    Dist,
    TypeA,
    TypeB,
    coverage_factor,
    from_record,
)


def test_rectangular_divisor_is_sqrt3():
    c = TypeB("quantization", Dist.RECTANGULAR, half_width=0.005)
    assert c.u == pytest.approx(0.005 / math.sqrt(3))


def test_triangular_divisor_is_sqrt6():
    c = TypeB("interp", Dist.TRIANGULAR, half_width=0.006)
    assert c.u == pytest.approx(0.006 / math.sqrt(6))


def test_u_shaped_divisor_is_sqrt2():
    c = TypeB("mains_ripple", Dist.U_SHAPED, half_width=0.01)
    assert c.u == pytest.approx(0.01 / math.sqrt(2))


def test_normal_with_expanded_uncertainty_divides_by_k():
    c = TypeB("ref_mass", Dist.NORMAL, std=0.0004, k=2.0)
    assert c.u == pytest.approx(0.0002)


def test_type_a_mean_is_s_over_sqrt_n():
    a = TypeA("repeatability", s=0.02, n=25, statistic="mean")
    assert a.u == pytest.approx(0.004)
    assert a.dof == 24


def test_type_a_single_reading_is_s():
    a = TypeA("repeatability", s=0.02, n=25, statistic="single")
    assert a.u == pytest.approx(0.02)


def test_type_a_statistic_must_be_declared():
    with pytest.raises(ValueError):
        TypeA("repeatability", s=0.02, n=25, statistic="whatever")


def test_type_a_requires_two_observations():
    with pytest.raises(ValueError):
        TypeA("repeatability", s=0.02, n=1, statistic="mean")


def test_uncorrelated_combination_is_rss():
    b = Budget(
        "y",
        [
            TypeB("a", Dist.NORMAL, std=3.0),
            TypeB("b", Dist.NORMAL, std=4.0),
        ],
    )
    assert b.u_c() == pytest.approx(5.0)


def test_sensitivity_coefficient_scales_contribution():
    b = Budget("y", [TypeB("a", Dist.NORMAL, std=3.0, c=2.0)])
    assert b.u_c() == pytest.approx(6.0)


def test_full_positive_correlation_adds_linearly():
    b = Budget(
        "y",
        [
            TypeB("a", Dist.NORMAL, std=2.0),
            TypeB("b", Dist.NORMAL, std=2.0),
        ],
        correlations={("a", "b"): 1.0},
    )
    assert b.u_c() == pytest.approx(4.0)


def test_full_negative_correlation_cancels():
    b = Budget(
        "y",
        [
            TypeB("a", Dist.NORMAL, std=2.0),
            TypeB("b", Dist.NORMAL, std=2.0, c=1.0),
        ],
        correlations={("a", "b"): -1.0},
    )
    assert b.u_c() == pytest.approx(0.0, abs=1e-12)


def test_wels_equal_components_gives_n_times_dof():
    nu, n = 9, 4
    comps = [TypeA(f"c{i}", s=1.0, n=nu + 1, statistic="single") for i in range(n)]
    b = Budget("y", comps)
    assert b.dof_eff() == pytest.approx(n * nu)


def test_wels_all_type_b_gives_infinite_dof():
    b = Budget("y", [TypeB("a", Dist.RECTANGULAR, half_width=1.0)])
    assert math.isinf(b.dof_eff())


def test_wels_refuses_correlated_budget():
    b = Budget(
        "y",
        [
            TypeA("a", s=1.0, n=10, statistic="single"),
            TypeA("b", s=1.0, n=10, statistic="single"),
        ],
        correlations={("a", "b"): 0.5},
    )
    with pytest.raises(ValueError):
        b.dof_eff()


def test_k_at_infinite_dof_is_normal_quantile():
    assert coverage_factor(math.inf, 0.95) == pytest.approx(1.960)
    assert coverage_factor(math.inf, 0.99) == pytest.approx(2.576)


def test_k_at_tabulated_dof():
    assert coverage_factor(10, 0.95) == pytest.approx(2.228)
    assert coverage_factor(30, 0.95) == pytest.approx(2.042)
    assert coverage_factor(8, 0.99) == pytest.approx(3.355)


def test_k_interpolates_between_table_rows_monotonically():
    assert 2.042 > coverage_factor(35, 0.95) > 2.021


def test_expanded_uncertainty_is_k_times_uc():
    b = Budget("y", [TypeB("a", Dist.NORMAL, std=0.01)])
    assert b.U(0.95) == pytest.approx(1.960 * 0.01)


def test_empty_budget_reports_nothing():
    with pytest.raises(ValueError):
        Budget("y", []).u_c()


def test_missing_half_width_is_rejected():
    with pytest.raises(ValueError):
        TypeB("a", Dist.RECTANGULAR)


def test_missing_std_on_normal_is_rejected():
    with pytest.raises(ValueError):
        TypeB("a", Dist.NORMAL)


def test_duplicate_sources_are_rejected():
    with pytest.raises(ValueError):
        Budget(
            "y",
            [
                TypeB("a", Dist.NORMAL, std=1.0),
                TypeB("a", Dist.NORMAL, std=1.0),
            ],
        )


def test_correlation_on_unknown_component_is_rejected():
    with pytest.raises(ValueError):
        Budget("y", [TypeB("a", Dist.NORMAL, std=1.0)], correlations={("a", "ghost"): 0.5})


def test_traceability_defaults_to_none_claimed():
    b = Budget("y", [TypeB("a", Dist.NORMAL, std=1.0)])
    assert b.to_record()["traceability"] == "none_claimed"


def test_variance_shares_sum_to_one_and_rank_correctly():
    b = Budget(
        "y",
        [
            TypeB("small", Dist.NORMAL, std=1.0),
            TypeB("big", Dist.NORMAL, std=4.0),
        ],
    )
    rows = b.contributions()
    assert rows[0]["source"] == "big"
    assert sum(r["variance_share"] for r in rows) == pytest.approx(1.0)
    assert rows[0]["variance_share"] == pytest.approx(16 / 17)


def test_monte_carlo_matches_gum_for_linear_model():
    b = Budget(
        "displacement_mm",
        [
            TypeB("quantization", Dist.RECTANGULAR, half_width=0.005),
            TypeB("nonlinearity", Dist.TRIANGULAR, half_width=0.004),
            TypeB("ref_mass", Dist.NORMAL, std=0.0004, k=2.0),
        ],
    )
    mc = b.monte_carlo(n_draws=80_000, seed=7)
    assert mc["u_c"] == pytest.approx(b.u_c(), rel=0.02)


def test_monte_carlo_interval_brackets_gum_expanded_uncertainty():
    b = Budget("y", [TypeB("a", Dist.NORMAL, std=1.0)])
    mc = b.monte_carlo(n_draws=80_000, seed=3, p=0.95)
    assert mc["interval_high"] == pytest.approx(b.U(0.95), rel=0.05)
    assert mc["interval_low"] == pytest.approx(-b.U(0.95), rel=0.05)


def test_monte_carlo_u_shaped_variance_is_half_width_squared_over_two():
    b = Budget("y", [TypeB("ripple", Dist.U_SHAPED, half_width=1.0)])
    mc = b.monte_carlo(n_draws=80_000, seed=11)
    assert mc["u_c"] == pytest.approx(1.0 / math.sqrt(2), rel=0.02)


def test_record_round_trip_preserves_uc_and_k():
    b = Budget(
        "displacement_mm",
        [
            TypeA("repeatability", s=0.0031, n=50, statistic="mean"),
            TypeB("quantization", Dist.RECTANGULAR, half_width=0.005),
            TypeB("thermal_drift", Dist.RECTANGULAR, half_width=1.2e-4 * 5.0),
            TypeB("ref_mass", Dist.NORMAL, std=0.0004, k=2.0),
        ],
        unit="mm",
    )
    rec = b.to_record()
    back = from_record(rec)
    assert back.u_c() == pytest.approx(b.u_c())
    assert back.k() == pytest.approx(b.k())
    assert back.measurand == b.measurand


def test_record_rejects_foreign_schema():
    with pytest.raises(ValueError):
        from_record({"schema": "something-else-v1", "measurand": "y", "components": []})
