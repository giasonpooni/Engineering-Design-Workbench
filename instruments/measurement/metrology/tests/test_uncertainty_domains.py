"""Adversarial domains and scale/cancellation references for uncertainty budgets."""

import json
import math
from fractions import Fraction
from pathlib import Path
import tomllib

import numpy as np
import pytest

from instrument_chain.uncertainty_budget import (
    Budget, Dist, TypeA, TypeB, coverage_factor, from_record,
)


def normal(source, std=1.0, **kwargs):
    return TypeB(source, Dist.NORMAL, std=std, **kwargs)


@pytest.mark.parametrize("value", [-1.0, math.nan, math.inf, -math.inf, True, "1", 10**1000])
def test_standard_deviations_refuse_invalid_values(value):
    with pytest.raises(ValueError):
        normal("a", value)
    with pytest.raises(ValueError):
        TypeA("a", s=value, n=10, statistic="single")


@pytest.mark.parametrize("dist", [Dist.RECTANGULAR, Dist.TRIANGULAR, Dist.U_SHAPED])
@pytest.mark.parametrize("value", [-1.0, math.nan, math.inf, True, "1"])
def test_half_width_domain(dist, value):
    with pytest.raises(ValueError):
        TypeB("a", dist, half_width=value)


@pytest.mark.parametrize("n", [True, 1, 2.5, 2.0, math.nan, math.inf, "10", 10**1000])
def test_type_a_count_is_finite_integer_not_boolean(n):
    with pytest.raises(ValueError):
        TypeA("a", s=1.0, n=n, statistic="mean")


@pytest.mark.parametrize("c", [math.nan, math.inf, -math.inf, True, "1"])
def test_sensitivity_coefficient_domain(c):
    with pytest.raises(ValueError):
        normal("a", c=c)
    with pytest.raises(ValueError):
        TypeA("a", s=1.0, n=10, statistic="mean", c=c)


@pytest.mark.parametrize("k", [0, -1, math.nan, math.inf, True, "1"])
def test_divisor_domain(k):
    with pytest.raises(ValueError):
        normal("a", k=k)


@pytest.mark.parametrize("dof", [0, -1, math.nan, -math.inf, True, "1"])
def test_degrees_of_freedom_domain(dof):
    with pytest.raises(ValueError):
        normal("a", dof=dof)
    with pytest.raises(ValueError):
        coverage_factor(dof)


def test_positive_infinite_dof_and_zero_uncertainty_are_explicitly_supported():
    component = normal("a", 0.0, dof=math.inf, c=-2)
    assert component.u == 0
    budget = Budget("y", [component])
    assert budget.u_c() == budget.U() == 0
    assert math.isinf(budget.dof_eff())


@pytest.mark.parametrize("rho", [-2, 2, math.nan, math.inf, -math.inf, True, "0.1"])
def test_correlation_coefficients_have_a_strict_domain(rho):
    with pytest.raises(ValueError):
        Budget("y", [normal("a"), normal("b")], {("a", "b"): rho})


def test_individually_valid_coefficients_can_form_an_indefinite_matrix():
    with pytest.raises(ValueError, match="positive semidefinite"):
        Budget("y", [normal(name) for name in "abc"],
               {("a", "b"): -0.9, ("a", "c"): -0.9, ("b", "c"): -0.9})


def test_reverse_conflicts_and_invalid_self_correlations_are_not_ignored():
    with pytest.raises(ValueError, match="reverse"):
        Budget("y", [normal("a"), normal("b")], {("a", "b"): 0.2, ("b", "a"): 0.3})
    with pytest.raises(ValueError, match="self"):
        Budget("y", [normal("a")], {("a", "a"): 0.0})
    budget = Budget("y", [normal("a")], {("a", "a"): 1.0})
    assert budget.uncorrelated
    assert budget.u_c() == 1.0


@pytest.mark.parametrize("rho", [-1.0, 1.0])
def test_valid_singular_correlations_with_zero_uncertainty_are_supported(rho):
    budget = Budget("y", [normal("a", 0), normal("b", 3)], {("a", "b"): rho})
    assert budget.u_c() == 3


def test_singular_three_component_matrix_and_component_permutation():
    components = [normal(name, 2) for name in "abc"]
    correlations = {("a", "b"): -0.5, ("a", "c"): -0.5, ("b", "c"): -0.5}
    assert Budget("y", components, correlations).u_c() == 0
    assert Budget("y", components[::-1], correlations).u_c() == 0


@pytest.mark.parametrize("scale", [1e-200, 1.0, 1e200])
def test_signed_sensitivities_and_scale_invariance(scale):
    budget = Budget("y", [normal("a", 3 * scale, c=-1), normal("b", 4 * scale)],
                    {("a", "b"): 0.5, ("b", "a"): 0.5})
    assert budget.u_c() == pytest.approx(math.sqrt(13) * scale, rel=1e-14, abs=0)
    budget.components.reverse()
    assert budget.u_c() == pytest.approx(math.sqrt(13) * scale, rel=1e-14, abs=0)


@pytest.mark.parametrize("small", [1e-100, 1e-200, 5e-324])
def test_large_singular_cancellation_does_not_erase_a_tiny_independent_term(small):
    budget = Budget("y", [normal("a", 1e200), normal("b", 1e200, c=-1), normal("c", small)],
                    {("a", "b"): 1.0})
    assert budget.u_c() == small


def test_variance_overflow_and_underflow_are_avoided_when_standard_uncertainty_fits():
    large = Budget("y", [normal("a", 1e308), normal("b", 1e308)])
    assert large.u_c() == pytest.approx(math.sqrt(2) * 1e308)
    assert sum(row["variance_share"] for row in large.contributions()) == pytest.approx(1)
    small = Budget("y", [normal("a", 1e-200), normal("b", 2e-200)])
    assert small.u_c() == pytest.approx(math.sqrt(5) * 1e-200, rel=1e-14, abs=0)
    finite_dof = Budget("y", [TypeA(name, s=1e200, n=10, statistic="single") for name in "ab"])
    assert finite_dof.dof_eff() == pytest.approx(18)


def test_unrepresentable_result_and_component_products_refuse():
    with pytest.raises(ValueError, match="overflow"):
        Budget("y", [normal("a", 1e308, c=2)]).u_c()
    with pytest.raises(ValueError, match="overflow"):
        Budget("y", [normal("a", 1e308), normal("b", 1e308)], {("a", "b"): 1}).u_c()
    with pytest.raises(ValueError, match="overflow"):
        normal("a", 1e308, k=1e-308).u
    with pytest.raises(ValueError, match="underflow"):
        normal("a", 5e-324, k=2).u
    with pytest.raises(ValueError, match="underflow"):
        normal("a", 1e-300, c=1e-300).contribution
    with pytest.raises(ValueError, match="overflow"):
        Budget("y", [normal("a", 1e308)]).U()


@pytest.mark.parametrize("operation", [
    lambda b: b.u_c(), lambda b: b.uncorrelated, lambda b: b.dof_eff(),
    lambda b: b.k(), lambda b: b.U(), lambda b: b.contributions(),
    lambda b: b.to_record(), lambda b: b.to_json(), lambda b: b.monte_carlo(32),
])
def test_mutating_the_correlation_model_cannot_bypass_validation(operation):
    budget = Budget("y", [normal("a"), normal("b")])
    budget.correlations["a", "b"] = -2
    with pytest.raises(ValueError):
        operation(budget)


def test_mutating_component_container_is_revalidated():
    budget = Budget("y", [normal("a")])
    budget.components.append(normal("a"))
    with pytest.raises(ValueError, match="duplicate"):
        budget.to_record()
    budget.components = [object()]
    with pytest.raises(ValueError, match="TypeA or TypeB"):
        budget.u_c()


def test_record_loader_does_not_silently_drop_duplicate_correlations():
    budget = Budget("y", [normal("a"), normal("b")])
    record = budget.to_record()
    record["correlations"] = [{"a": "a", "b": "b", "r": 0.2}, {"a": "a", "b": "b", "r": 0.3}]
    with pytest.raises(ValueError, match="duplicate"):
        from_record(record)
    record["correlations"][1] = {"a": "b", "b": "a", "r": 0.3}
    with pytest.raises(ValueError, match="reverse"):
        from_record(record)


def test_record_loader_rejects_unknown_component_types_and_non_numeric_dof():
    record = Budget("y", [normal("a")]).to_record()
    record["components"][0]["type"] = "invented"
    with pytest.raises(ValueError, match="component type"):
        from_record(record)
    record["components"][0]["type"] = "B"
    record["components"][0]["dof"] = "10"
    with pytest.raises(ValueError):
        from_record(record)


def test_valid_record_shape_and_roundtrip_are_unchanged():
    budget = Budget("y", [normal("a", 2), normal("b", 3, c=-1)], {("a", "b"): 0.5})
    record = budget.to_record()
    assert set(record) == {"schema", "measurand", "unit", "components", "correlations", "combination",
                           "u_c", "dof_eff", "p", "k", "U", "contributions", "traceability"}
    assert from_record(record).to_record() == record


@pytest.mark.parametrize("components,correlations", [
    ([normal("a", 0.0)], {}),
    ([normal("a"), normal("b")], {("a", "b"): -1.0}),
])
def test_zero_combined_uncertainty_has_null_not_zero_variance_ratios(components, correlations):
    budget = Budget("y", components, correlations)
    assert budget.u_c() == 0.0
    record = budget.to_record()
    assert record["schema"] == "uncertainty-budget-v2"
    assert all(row["variance_share"] is None for row in record["contributions"])
    assert '"variance_share": null' in budget.to_json()


def test_legacy_declarations_load_and_new_records_explicitly_use_v2():
    legacy = Budget("y", [normal("a"), normal("b")], {("a", "b"): -1}).to_record()
    legacy["schema"] = "uncertainty-budget-v1"
    for row in legacy["contributions"]:
        row["variance_share"] = 0.0
    loaded = from_record(legacy).to_record()
    assert loaded["schema"] == "uncertainty-budget-v2"
    assert loaded["u_c"] == 0
    assert loaded["contributions"][0]["variance_share"] is None
    assert legacy["schema"] == "uncertainty-budget-v1"  # Reader leaves source untouched.


def test_correlated_diagonal_ratios_are_not_claimed_to_sum_to_one():
    budget = Budget("y", [normal("a"), normal("b")], {("a", "b"): -.9})
    shares = [row["variance_share"] for row in budget.contributions()]
    assert shares == pytest.approx([5, 5])


@pytest.mark.parametrize("schema", [None, "unknown", "uncertainty-budget-v3", 1])
def test_unknown_record_schema_is_refused(schema):
    record = Budget("y", [normal("a")]).to_record()
    record["schema"] = schema
    with pytest.raises(ValueError, match="schema"):
        from_record(record)


def test_accepted_numpy_scalars_serialize_without_changing_python_integer_declarations():
    budget = Budget("y", [TypeA("a", np.float32(2), np.int64(10), "single", c=np.float32(-1)),
                           normal("b", np.float32(3), k=np.float32(1), dof=np.float32(9))],
                    {("a", "b"): np.float32(.5)})
    record = json.loads(budget.to_json())
    assert record["components"][0]["n"] == 10
    assert from_record(record).to_record() == record
    plain = Budget("y", [normal("a", 3, c=2)]).to_record()
    assert type(plain["components"][0]["std"]) is int
    assert type(plain["components"][0]["c"]) is int
    fractional = Budget("y", [normal("a", Fraction(1, 3), c=Fraction(-2, 3))])
    assert json.loads(fractional.to_json())["components"][0]["std"] == float(Fraction(1, 3))


def test_real_declarations_that_underflow_float64_are_refused():
    with pytest.raises(ValueError, match="underflow"):
        normal("a", Fraction(1, 10**1000))
    with pytest.raises(ValueError, match="underflow"):
        normal("a", Fraction(-1, 10**1000))


def test_package_and_wire_versions_are_consistent():
    import instrument_chain

    metadata = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert instrument_chain.__version__ == metadata["project"]["version"] == "0.2.0"
    assert instrument_chain.BUDGET_SCHEMA == "uncertainty-budget-v2"


@pytest.mark.parametrize("count,p", [(True, .95), (1, .95), (2.5, .95), (32, math.nan),
                                      (32, 0), (32, 1), (2, .95)])
def test_monte_carlo_sampling_and_interval_domains(count, p):
    with pytest.raises(ValueError):
        Budget("y", [normal("a")]).monte_carlo(n_draws=count, p=p)


def test_monte_carlo_zero_width_and_large_representable_output():
    zero = Budget("y", [TypeB("a", Dist.TRIANGULAR, half_width=0)])
    assert zero.monte_carlo(100)["u_c"] == 0
    big = Budget("y", [normal("a", 1e200)])
    assert math.isfinite(big.monte_carlo(1000)["u_c"])


def test_monte_carlo_refuses_nonfinite_samples():
    with np.errstate(over="ignore", invalid="ignore"):
        with pytest.raises(ValueError, match="overflow"):
            Budget("y", [normal("a", 1e308)]).monte_carlo(1000)


@pytest.mark.parametrize("p", [math.nan, math.inf, True, "0.95", 0, 1])
def test_record_probability_domain(p):
    with pytest.raises(ValueError):
        Budget("y", [normal("a"), normal("b")], {("a", "b"): .5}).to_record(p)
