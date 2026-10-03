"""Reusable first-order sensitivity core for the Jacobian testbed.

This package is the importable runtime fragment. Experiments, reference
models, and reports live beside it in the repository; consuming projects
can depend on ``sensitivity`` without adopting the experiment suite.
"""

from .affine import (
    AffinePlant,
    GaussianState,
    invariant_error,
    predict,
    restore_state,
    retract,
    transform_plant,
    transform_state,
    update,
)
from .checks import (
    CheckResult,
    check_composition,
    check_coordinate_consistency,
    check_covariance_affine,
    check_derivative,
    check_metric_consistency,
)
from .composition import compose
from .coordinates import (
    MAX_CONDITION_NUMBER,
    ROUND_TRIP_TOLERANCE,
    AffineCoordinates,
    apply_input_map,
    apply_output_map,
    check_covariance_fidelity,
    check_mean_fidelity,
    push_covariance,
    transform_jacobian,
)
from .covariance import (
    CovarianceExperiment,
    first_order_covariance,
    monte_carlo_covariance,
    run_covariance_experiment,
)
from .covariance_artifact import make_covariance_artifact, validate_covariance_artifact
from .jacobian import (
    JacobianEstimate,
    finite_difference_jacobian,
    jacobian_at,
    jax_is_available,
    jvp,
    vjp,
)
from .metrics import DeclaredMetric
from .models import DifferentiableModel
from .perturbation import (
    PerturbationSweep,
    local_validity,
    perturbation_error,
    sweep_perturbation_scale,
)
from .reference_models import reference_catalogue
from .structure import local_structure, propagate_belief

__all__ = [
    "AffineCoordinates",
    "AffinePlant",
    "CheckResult",
    "CovarianceExperiment",
    "DeclaredMetric",
    "DifferentiableModel",
    "GaussianState",
    "JacobianEstimate",
    "MAX_CONDITION_NUMBER",
    "PerturbationSweep",
    "ROUND_TRIP_TOLERANCE",
    "apply_input_map",
    "apply_output_map",
    "check_composition",
    "check_coordinate_consistency",
    "check_covariance_affine",
    "check_covariance_fidelity",
    "check_derivative",
    "check_mean_fidelity",
    "check_metric_consistency",
    "compose",
    "finite_difference_jacobian",
    "first_order_covariance",
    "invariant_error",
    "jacobian_at",
    "jax_is_available",
    "jvp",
    "local_structure",
    "local_validity",
    "make_covariance_artifact",
    "monte_carlo_covariance",
    "perturbation_error",
    "predict",
    "propagate_belief",
    "push_covariance",
    "reference_catalogue",
    "restore_state",
    "retract",
    "run_covariance_experiment",
    "sweep_perturbation_scale",
    "transform_jacobian",
    "transform_plant",
    "transform_state",
    "update",
    "validate_covariance_artifact",
    "vjp",
]

__version__ = "0.1.0"
