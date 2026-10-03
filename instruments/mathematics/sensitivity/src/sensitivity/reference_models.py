"""Declared reference maps with known analytical Jacobians."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .models import DifferentiableModel

Array = NDArray[np.floating]


def affine_map(
    matrix: ArrayLike,
    offset: ArrayLike | None = None,
    *,
    name: str = "affine",
) -> DifferentiableModel:
    a = np.asarray(matrix, dtype=float)
    if a.ndim != 2:
        raise ValueError("affine matrix must be 2-D")
    b = np.zeros(a.shape[0], dtype=float) if offset is None else np.asarray(offset, dtype=float)
    if b.shape != (a.shape[0],):
        raise ValueError("offset shape must match the number of rows")

    def forward(x: Array) -> Array:
        return a @ x + b

    def jacobian(_x: Array) -> Array:
        return a.copy()

    def jax_forward(x: Array) -> Array:
        import jax.numpy as jnp
        return jnp.asarray(a) @ x + jnp.asarray(b)

    return DifferentiableModel(
        name=name,
        forward=forward,
        input_dim=a.shape[1],
        output_dim=a.shape[0],
        jacobian=jacobian,
        jax_forward=jax_forward,
        notes="affine; first-order perturbation and covariance maps are exact",
        tags=("affine", "analytical", "traceable"),
    )


def quadratic_form_gradient(*, hess: ArrayLike, grad: ArrayLike, name: str = "quadratic") -> DifferentiableModel:
    h = np.asarray(hess, dtype=float)
    g = np.asarray(grad, dtype=float)
    h = 0.5 * (h + h.T)
    if h.ndim != 2 or h.shape[0] != h.shape[1]:
        raise ValueError("H must be square")
    if g.shape != (h.shape[0],):
        raise ValueError("g must match H")

    def forward(x: Array) -> Array:
        return np.array([0.5 * float(x @ h @ x) + float(g @ x)])

    def jacobian(x: Array) -> Array:
        return (h @ x + g).reshape(1, -1)

    return DifferentiableModel(
        name=name,
        forward=forward,
        input_dim=h.shape[0],
        output_dim=1,
        jacobian=jacobian,
        notes="scalar quadratic; linear remainder is 0.5 dx^T H dx",
        tags=("quadratic", "analytical", "nonlinear"),
    )


def componentwise_exp(*, dim: int = 2, name: str = "exp") -> DifferentiableModel:
    def forward(x: Array) -> Array:
        return np.exp(x)

    def jacobian(x: Array) -> Array:
        return np.diag(np.exp(x))

    def jax_forward(x: Array) -> Array:
        import jax.numpy as jnp
        return jnp.exp(x)

    return DifferentiableModel(
        name=name,
        forward=forward,
        input_dim=dim,
        output_dim=dim,
        jacobian=jacobian,
        jax_forward=jax_forward,
        notes="componentwise exponential; holomorphic on R^n",
        tags=("nonlinear", "analytical", "holomorphic", "traceable"),
    )


def polar_from_cartesian(*, name: str = "polar") -> DifferentiableModel:
    def forward(vec: Array) -> Array:
        x, y = vec
        return np.array([np.hypot(x, y), np.arctan2(y, x)])

    def jacobian(vec: Array) -> Array:
        x, y = vec
        r2 = x * x + y * y
        r = np.sqrt(r2)
        if r2 <= 0.0:
            raise ValueError("polar Jacobian is undefined at the origin")
        return np.array([[x / r, y / r], [-y / r2, x / r2]])

    return DifferentiableModel(
        name=name,
        forward=forward,
        input_dim=2,
        output_dim=2,
        jacobian=jacobian,
        input_names=("x", "y"),
        output_names=("r", "theta"),
        notes="undefined at the origin; angle branch is atan2",
        tags=("nonlinear", "analytical", "coordinates"),
    )


def scaled_rotation(angle: float = np.pi / 5, scale: float = 1.5, *, name: str = "scaled-rotation") -> DifferentiableModel:
    c, s = np.cos(angle), np.sin(angle)
    matrix = scale * np.array([[c, -s], [s, c]])
    return affine_map(matrix, name=name)


def two_tank_mass_balance(*, name: str = "two-tank") -> DifferentiableModel:
    def forward(vec: Array) -> Array:
        m1, m2, density = vec
        return np.array([m1 + m2, density * (m1 - m2)])

    def jacobian(vec: Array) -> Array:
        return np.array([[1.0, 1.0, 0.0], [vec[2], -vec[2], vec[0] - vec[1]]])

    return DifferentiableModel(
        name=name,
        forward=forward,
        input_dim=3,
        output_dim=2,
        jacobian=jacobian,
        input_names=("m1", "m2", "density"),
        output_names=("total", "imbalance"),
        notes="illustrative plant fragment, not a closed fluid model",
        tags=("analytical", "physical-example"),
    )


def two_tank_storage(*, area: tuple[float, float] = (2.0, 1.5), name: str = "storage") -> DifferentiableModel:
    a1, a2 = (float(area[0]), float(area[1]))
    if a1 <= 0.0 or a2 <= 0.0:
        raise ValueError("tank areas must be positive")

    def forward(h: Array) -> Array:
        return np.array([a1 * h[0], a2 * h[1]])

    def jacobian(_h: Array) -> Array:
        return np.diag([a1, a2])

    return DifferentiableModel(
        name=name,
        forward=forward,
        input_dim=2,
        output_dim=2,
        jacobian=jacobian,
        input_names=("h1", "h2"),
        output_names=("m1", "m2"),
        notes="illustrative holdup map; density is absorbed into declared area",
        tags=("analytical", "fluid-example"),
    )


def two_tank_balance(*, name: str = "balance") -> DifferentiableModel:
    def forward(mass: Array) -> Array:
        return np.array([mass[0] + mass[1], mass[0] - mass[1]])

    def jacobian(_mass: Array) -> Array:
        return np.array([[1.0, 1.0], [1.0, -1.0]])

    return DifferentiableModel(
        name=name,
        forward=forward,
        input_dim=2,
        output_dim=2,
        jacobian=jacobian,
        input_names=("m1", "m2"),
        output_names=("total", "imbalance"),
        notes="linear inventory/imbalance map used by the fluid composition example",
        tags=("affine", "analytical", "fluid-example"),
    )


def two_tank_measurement(*, name: str = "gauge-totalizer") -> DifferentiableModel:
    def forward(mass: Array) -> Array:
        return np.array([mass[0], mass[0] + mass[1]])

    def jacobian(_mass: Array) -> Array:
        return np.array([[1.0, 0.0], [1.0, 1.0]])

    return DifferentiableModel(
        name=name,
        forward=forward,
        input_dim=2,
        output_dim=2,
        jacobian=jacobian,
        input_names=("m1", "m2"),
        output_names=("gauge_m1", "totalizer"),
        notes="not a plant observer; a declared measurement map for composition tests",
        tags=("affine", "analytical", "fluid-example"),
    )


def simply_supported_midspan(*, name: str = "beam-midspan") -> DifferentiableModel:
    """Central deflection delta = P L^3 / (48 EI).

    Portable construction fragment. Not GAT, not AISC capacity.
    """

    def forward(vec: Array) -> Array:
        load, length, stiffness = vec
        if stiffness <= 0.0:
            raise ValueError("EI must be positive")
        return np.array([load * length**3 / (48.0 * stiffness)])

    def jacobian(vec: Array) -> Array:
        load, length, stiffness = vec
        if stiffness <= 0.0:
            raise ValueError("EI must be positive")
        return np.array([[
            length**3 / (48.0 * stiffness),
            3.0 * load * length**2 / (48.0 * stiffness),
            -load * length**3 / (48.0 * stiffness**2),
        ]])

    return DifferentiableModel(
        name=name,
        forward=forward,
        input_dim=3,
        output_dim=1,
        jacobian=jacobian,
        input_names=("P", "L", "EI"),
        output_names=("delta",),
        notes="Euler-Bernoulli midspan formula; no shear, no support settlement",
        tags=("analytical", "construction-example", "nonlinear"),
    )


def reference_catalogue() -> dict[str, DifferentiableModel]:
    from .composition import compose

    storage = two_tank_storage()
    return {
        "affine2": affine_map([[2.0, 0.5], [0.0, 1.5]], [0.1, -0.2], name="affine2"),
        "quadratic": quadratic_form_gradient(hess=[[2.0, 0.4], [0.4, 1.2]], grad=[0.3, -0.1]),
        "exp2": componentwise_exp(dim=2),
        "polar": polar_from_cartesian(),
        "scaled-rotation": scaled_rotation(),
        "two-tank": two_tank_mass_balance(),
        "storage": storage,
        "balance": two_tank_balance(),
        "gauge-totalizer": two_tank_measurement(),
        "fluid-balance": compose([storage, two_tank_balance()], name="fluid-balance"),
        "fluid-observer": compose([storage, two_tank_measurement()], name="fluid-observer"),
        "beam-midspan": simply_supported_midspan(),
    }
