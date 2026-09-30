from copy import deepcopy
from itertools import product
import json
import subprocess
import sys

import pytest

from ciw.control_plane import builtin_registry
from ciw.finite_preservation import (
    _evaluate, _normalise, example_specs, finite_witness_from_spec,
    require_finite_local_support, validate_finite_witness,
)
from ciw.operations.runner import seal
from ciw.representation_morphisms import registry_from_specs
from ciw.semantic_capabilities import builtin_semantic_registry


@pytest.fixture
def specimen():
    semantic = builtin_semantic_registry(builtin_registry(bind=True))
    spec, good, bad = example_specs()
    registry = registry_from_specs(spec["representations"], spec["morphisms"], semantic)
    return registry, semantic, good, bad


def test_exact_pushforward_conditional_means_and_loss(specimen):
    registry, semantic, good, _ = specimen
    value = finite_witness_from_spec(registry, semantic, good)
    r = value["results"]
    assert r["pushforward"] == {"cold": "1/2", "warm": "1/2"}
    assert r["fibres"]["cold"]["conditional_mean"] == "272"
    assert r["fibres"]["warm"]["conditional_mean"] == "292"
    assert r["expectation"] == r["conditional_expectation_integral"] == "282"
    assert r["unresolved_within_fibre_variance"] == "4"
    assert r["query_exact_on_all_declared_states"] is False
    assert r["commutativity_status"] == "PASS"
    assert require_finite_local_support(value, registry, semantic) == value


def test_equal_distributions_do_not_establish_commutativity(specimen):
    registry, semantic, _, bad = specimen
    value = finite_witness_from_spec(registry, semantic, bad)
    r = value["results"]
    assert r["intervened_distributions_equal"] is True
    assert r["commutativity_status"] == "FAIL"
    assert r["deterministic_coarse_intervention_exists_on_image"] is False
    assert len(r["fibre_conflicts"]) == 2
    assert len(r["commutativity_counterexamples"]) == 2
    with pytest.raises(ValueError, match="fails commutativity"):
        require_finite_local_support(value, registry, semantic)


def test_zero_mass_states_still_block_false_intervention(specimen):
    registry, semantic, _, bad = specimen
    bad["probabilities"] = {"cold-a": "1/2", "cold-b": "0", "warm-a": "1/2", "warm-b": "0"}
    bad["coarse_intervention"] = {"cold": "warm", "warm": "cold"}
    r = finite_witness_from_spec(registry, semantic, bad)["results"]
    assert r["intervened_distributions_equal"] is True
    assert r["commutativity_status"] == "FAIL"
    assert all(x["probability"] == "0" for x in r["commutativity_counterexamples"])
    assert r["unresolved_within_fibre_variance"] == "0"
    assert r["query_exact_on_all_declared_states"] is False


def test_zero_mass_fibre_is_not_given_a_fabricated_conditional(specimen):
    registry, semantic, good, _ = specimen
    good["probabilities"] = {"cold-a": "1/2", "cold-b": "1/2", "warm-a": "0", "warm-b": "0"}
    r = finite_witness_from_spec(registry, semantic, good)["results"]
    warm = r["fibres"]["warm"]
    assert warm["states"] == ["warm-a", "warm-b"]
    assert warm["conditional_status"] == "ZERO_MASS_UNDEFINED"
    assert warm["conditional_mean"] is None
    assert warm["conditional_variance"] is None
    assert warm["conditional_probabilities"] is None
    assert r["expectation"] == r["conditional_expectation_integral"] == "272"


def test_wrong_coarse_map_can_fail_even_when_a_valid_map_exists(specimen):
    registry, semantic, good, _ = specimen
    good["coarse_intervention"] = {"cold": "cold", "warm": "warm"}
    r = finite_witness_from_spec(registry, semantic, good)["results"]
    assert r["deterministic_coarse_intervention_exists_on_image"] is True
    assert r["commutativity_status"] == "FAIL"
    assert len(r["commutativity_counterexamples"]) == 4


def test_exact_query_on_fibres_is_separate_from_intervention(specimen):
    registry, semantic, _, bad = specimen
    bad["observable"] = {"cold-a": "1", "cold-b": "1", "warm-a": "2", "warm-b": "2"}
    r = finite_witness_from_spec(registry, semantic, bad)["results"]
    assert r["query_exact_on_all_declared_states"] is True
    assert r["unresolved_within_fibre_variance"] == "0"
    assert r["commutativity_status"] == "FAIL"


@pytest.mark.parametrize("bad_value", [True, False, 0.25, float("nan"), "NaN", "1/0", "1e-3", "1/10000000000", 10**10, {}, []])
def test_invalid_probability_inputs_refuse(specimen, bad_value):
    registry, semantic, good, _ = specimen
    good["probabilities"]["cold-a"] = bad_value
    with pytest.raises(ValueError):
        finite_witness_from_spec(registry, semantic, good)


@pytest.mark.parametrize("probability", ["-1/4", "0", "1/3"])
def test_non_probability_measure_refuses(specimen, probability):
    registry, semantic, good, _ = specimen
    good["probabilities"]["cold-a"] = probability
    with pytest.raises(ValueError, match="sum exactly to one"):
        finite_witness_from_spec(registry, semantic, good)


@pytest.mark.parametrize("name", ["projection", "fine_intervention", "coarse_intervention"])
def test_maps_must_be_total_and_closed(specimen, name):
    registry, semantic, good, _ = specimen
    good[name][next(iter(good[name]))] = "outside-the-space"
    with pytest.raises(ValueError, match="codomain"):
        finite_witness_from_spec(registry, semantic, good)


def test_incomplete_map_duplicate_state_and_resource_bound_refuse(specimen):
    registry, semantic, good, _ = specimen
    for mutation in ("missing", "duplicate", "too-many"):
        bad = deepcopy(good)
        if mutation == "missing":
            del bad["projection"]["cold-a"]
        elif mutation == "duplicate":
            bad["fine_states"].append("cold-a")
        else:
            bad["fine_states"] = [str(i) for i in range(65)]
        with pytest.raises(ValueError):
            finite_witness_from_spec(registry, semantic, bad)


def test_resealed_fake_pass_is_recomputed_and_rejected(specimen):
    registry, semantic, _, bad = specimen
    value = finite_witness_from_spec(registry, semantic, bad)
    value["results"]["commutativity_status"] = "PASS"
    value["contract_and_finite_check_pass"] = True
    with pytest.raises(ValueError, match="recomputation"):
        validate_finite_witness(seal(value), registry, semantic)


def test_registry_changes_invalidate_witness(specimen):
    registry, semantic, good, _ = specimen
    value = finite_witness_from_spec(registry, semantic, good)
    specs, _, _ = example_specs()
    specs["representations"][0]["notes"] += " revision"
    other = registry_from_specs(specs["representations"], specs["morphisms"], semantic)
    with pytest.raises(ValueError, match="registry binding"):
        validate_finite_witness(value, other, semantic)


def test_numerical_pass_does_not_add_missing_contract_authority(specimen):
    _, semantic, good, _ = specimen
    specs, _, _ = example_specs()
    specs["representations"][1]["supported_interventions"] = []
    registry = registry_from_specs(specs["representations"], specs["morphisms"], semantic)
    value = finite_witness_from_spec(registry, semantic, good)
    assert value["results"]["commutativity_status"] == "PASS"
    assert value["contract_and_finite_check_pass"] is False
    with pytest.raises(ValueError, match="lacks declared support"):
        require_finite_local_support(value, registry, semantic)


def test_wrong_representation_kind_does_not_claim_a_periodogram_witness(specimen):
    _, semantic, good, _ = specimen
    specs, _, _ = example_specs()
    specs["representations"][0]["schema_id"] = "ciw.run-channel.v1"
    registry = registry_from_specs(specs["representations"], specs["morphisms"], semantic)
    with pytest.raises(ValueError, match="finite-state-label"):
        finite_witness_from_spec(registry, semantic, good)


def test_inputs_and_results_are_detached_and_claims_remain_bounded(specimen):
    registry, semantic, good, _ = specimen
    original = deepcopy((registry, good))
    value = finite_witness_from_spec(registry, semantic, good)
    assert (registry, good) == original
    checked = validate_finite_witness(value, registry, semantic)
    checked["specification"]["observable"]["cold-a"] = "1"
    assert value["specification"]["observable"]["cold-a"] == "270"
    assert not value["claims"]["unique_inverse_inferred"]
    assert not value["claims"]["automatic_needle_authorization"]
    assert not value["claims"]["canonical_state_mutated"]


def test_exhaustive_four_state_map_space():
    # 256 fine endomorphisms x 4 coarse endomorphisms; exactly 64 commute.
    _, good, _ = example_specs()
    spec = _normalise(good)
    fine, coarse = spec["fine_states"], spec["coarse_states"]
    accepted = 0
    for images in product(fine, repeat=4):
        spec["fine_intervention"] = dict(zip(fine, images))
        for coarse_images in product(coarse, repeat=2):
            spec["coarse_intervention"] = dict(zip(coarse, coarse_images))
            r = _evaluate(spec)
            oracle = all(spec["projection"][images[i]] == spec["coarse_intervention"][spec["projection"][x]]
                         for i, x in enumerate(fine))
            assert (r["commutativity_status"] == "PASS") == oracle
            if oracle:
                accepted += 1
                assert r["intervened_distributions_equal"]
    assert accepted == 64


def test_cli_retains_counterexample_and_nonzero_exit(tmp_path):
    output = tmp_path / "demo"
    command = [sys.executable, "-m", "ciw.net", "morphism"]
    subprocess.run(command + ["finite-demo", "--output-dir", str(output)], check=True)
    for name, code in (("compatible", 0), ("incompatible", 2)):
        run = subprocess.run(command + ["finite-verify", str(output / "registry.json"),
                                       str(output / (name + "-witness.json"))], capture_output=True, text=True)
        assert run.returncode == code, run.stderr
        assert json.loads(run.stdout)["status"] == ("PASS" if code == 0 else "FAIL")
    result = output / "rechecked.json"
    run = subprocess.run(command + ["finite-check", str(output / "registry.json"),
                                   str(output / "incompatible-spec.json"), "--output", str(result)])
    assert run.returncode == 2 and result.is_file()
    assert subprocess.run(command + ["finite-demo", "--output-dir", str(output)], capture_output=True).returncode == 1
