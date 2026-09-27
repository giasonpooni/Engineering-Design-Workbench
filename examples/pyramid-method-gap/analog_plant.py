"""Declared continuous affine plant for the pyramid-method-gap sample.

A(theta) = A0 + theta A1, theta in [0, 1]. State x = (c, m, g) is a
dimensionless deviation from a declared operating point x=0. Matrices are
declared teaching objects, not identified from census, logs, or corpora.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

A0 = np.array(
    [
        [-0.15, 0.05, 0.00],
        [0.00, -0.40, 0.10],
        [0.00, 0.00, -0.80],
    ],
    dtype=float,
)
A1 = np.array(
    [
        [0.35, 0.25, 0.05],
        [0.10, 0.55, 0.35],
        [0.00, 0.05, 0.20],
    ],
    dtype=float,
)
Q = np.eye(3)

STATE_NAMES = ["c", "m", "g"]
# Declared initial deviation for host trajectories (same x0 on A(0) and A(1)).
DEFAULT_X0 = np.array([0.55, 0.35, 0.20], dtype=float)
RENDER_SCHEMA = "pyramid-method-gap.analog-render.v0"


def plant(theta: float) -> np.ndarray:
    if not 0.0 <= float(theta) <= 1.0:
        raise ValueError("theta must lie in [0, 1]")
    return A0 + float(theta) * A1


def spectral_abscissa(A: np.ndarray) -> float:
    return float(np.max(np.real(np.linalg.eigvals(A))))


def solve_continuous_lyapunov_P(A: np.ndarray, Q_mat: np.ndarray = Q) -> np.ndarray:
    """Solve A^T P + P A = -Q for symmetric P (host Kronecker form; no scipy)."""
    n = A.shape[0]
    K = np.kron(np.eye(n), A.T) + np.kron(A.T, np.eye(n))
    P = np.linalg.solve(K, (-Q_mat).reshape(-1)).reshape(n, n)
    return 0.5 * (P + P.T)


def certificate_on_A0() -> np.ndarray:
    """Common quadratic from continuous Lyapunov on A0 only, Q=I."""
    return solve_continuous_lyapunov_P(A0, Q)


def decrease_matrix(A: np.ndarray, P: np.ndarray) -> np.ndarray:
    return A.T @ P + P @ A


def max_eig_symmetric(M: np.ndarray) -> float:
    return float(np.max(np.real(np.linalg.eigvalsh(0.5 * (M + M.T)))))


def quadratic_V(x: np.ndarray, P: np.ndarray) -> float:
    x = np.asarray(x, dtype=float).reshape(3)
    return float(x @ P @ x)


def evaluate(theta: float, P: np.ndarray | None = None) -> dict:
    """Host analog evaluation for one theta under a common P."""
    if P is None:
        P = certificate_on_A0()
    A = plant(theta)
    alpha = spectral_abscissa(A)
    M = decrease_matrix(A, P)
    maxeig_m = max_eig_symmetric(M)
    return {
        "theta": float(theta),
        "alpha": alpha,
        "hurwitz": alpha < 0.0,
        "maxeig_M": maxeig_m,
        "decrease_definite": maxeig_m < 0.0,
    }


def rk4_trajectory(
    A: np.ndarray,
    x0: np.ndarray,
    t_end: float = 8.0,
    dt: float = 0.05,
) -> np.ndarray:
    """Integrate dx/dt = A x with classical RK4; returns (N, 3) retained points."""
    x = np.asarray(x0, dtype=float).reshape(3).copy()
    steps = max(int(round(t_end / dt)), 1)
    out = np.empty((steps + 1, 3), dtype=float)
    out[0] = x
    for i in range(steps):
        k1 = A @ x
        k2 = A @ (x + 0.5 * dt * k1)
        k3 = A @ (x + 0.5 * dt * k2)
        k4 = A @ (x + dt * k3)
        x = x + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        out[i + 1] = x
    return out


def ellipsoid_mesh(P: np.ndarray, level: float, n_u: int = 24, n_v: int = 16) -> dict:
    """Triangle mesh for {x : x^T P x = level}. Host-only; Godot must not recompute P."""
    evals, evecs = np.linalg.eigh(0.5 * (P + P.T))
    # P positive definite under teaching plant; guard anyway.
    evals = np.maximum(evals, 1e-12)
    radii = np.sqrt(float(level) / evals)
    R = evecs @ np.diag(radii)

    vertices: list[list[float]] = []
    for i in range(n_v + 1):
        phi = np.pi * i / n_v  # 0 .. pi
        for j in range(n_u):
            theta = 2.0 * np.pi * j / n_u
            local = np.array(
                [
                    np.sin(phi) * np.cos(theta),
                    np.sin(phi) * np.sin(theta),
                    np.cos(phi),
                ],
                dtype=float,
            )
            vertices.append((R @ local).tolist())

    indices: list[int] = []
    for i in range(n_v):
        for j in range(n_u):
            jn = (j + 1) % n_u
            a = i * n_u + j
            b = i * n_u + jn
            c = (i + 1) * n_u + j
            d = (i + 1) * n_u + jn
            indices.extend([a, c, b, b, c, d])

    return {"vertices": vertices, "indices": indices, "level": float(level)}


def build_analog_render(
    P: np.ndarray,
    plsr_label: str = "HOST_ANALOG_ONLY",
    x0: np.ndarray | None = None,
    strip_count: int = 21,
) -> dict:
    """Host-computed presentation artifact for the Godot Analog tab."""
    if x0 is None:
        x0 = DEFAULT_X0
    x0 = np.asarray(x0, dtype=float).reshape(3)

    vertices = [evaluate(t, P) for t in (0.0, 0.5, 1.0)]
    strip = [evaluate(float(t), P) for t in np.linspace(0.0, 1.0, strip_count)]

    traj_renewal = rk4_trajectory(plant(0.0), x0)
    traj_gap = rk4_trajectory(plant(1.0), x0)
    V_renewal = [quadratic_V(p, P) for p in traj_renewal]
    V_gap = [quadratic_V(p, P) for p in traj_gap]

    # Level set that comfortably contains the teaching trajectories.
    peak_V = max(max(V_renewal), max(V_gap), quadratic_V(x0, P))
    level = float(max(peak_V * 1.35, 0.25))
    mesh = ellipsoid_mesh(P, level)

    n = min(len(traj_renewal), len(traj_gap))
    selected = 0
    playback = []
    for i in range(n):
        playback.append(
            {
                "index": i,
                "x_renewal": traj_renewal[i].tolist(),
                "x_gap": traj_gap[i].tolist(),
                "V_renewal": V_renewal[i],
                "V_gap": V_gap[i],
            }
        )

    return {
        "schema": RENDER_SCHEMA,
        "state_names": list(STATE_NAMES),
        "P": P.tolist(),
        "x0": x0.tolist(),
        "ellipsoid_level": level,
        "vertex_table": vertices,
        "strip_samples": strip,
        "trajectories": {
            "renewal": {
                "theta": 0.0,
                "label": "A(0) renewal",
                "points": traj_renewal.tolist(),
                "V": V_renewal,
            },
            "gap": {
                "theta": 1.0,
                "label": "A(1) gap",
                "points": traj_gap.tolist(),
                "V": V_gap,
            },
        },
        "ellipsoid": mesh,
        "selected_sample_index": selected,
        "selected_theta": 0.0,
        "playback_samples": playback,
        "V_at_sample": {
            "index": selected,
            "V_renewal": V_renewal[selected],
            "V_gap": V_gap[selected],
            "V": V_renewal[selected],
        },
        "claim_scope": "computational-integrity-only",
        "may_authorize": False,
        "runtime_status": plsr_label,
        "plsr_status": plsr_label,
        "note": (
            "Presentation artifact only. Meshes and trajectories are host-computed; "
            "Godot must not recompute A or P. Cards read numeric fields from this JSON."
        ),
    }


def analog_draft_declaration(P: np.ndarray, results: list[dict]) -> dict:
    """Draft declaration JSON. Analog-draft only; may_authorize stays false."""
    return {
        "schema": "pyramid-method-gap.analog-draft.v0",
        "may_authorize": False,
        "claim_scope": "computational-integrity-only",
        "plant": {
            "form": "A(theta)=A0+theta*A1",
            "theta_domain": [0.0, 1.0],
            "state": ["c", "m", "g"],
            "A0": A0.tolist(),
            "A1": A1.tolist(),
            "note": "Declared matrices; not identified from census, logs, or corpora.",
        },
        "certificate": {
            "kind": "common_quadratic_on_A0",
            "Q": Q.tolist(),
            "P": P.tolist(),
            "note": "Conservative common P from continuous Lyapunov on A0 only.",
        },
        "host_evaluations": results,
        "runtime_status": "HOST_ANALOG_ONLY",
    }


def write_draft(path: Path, draft: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(draft, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_render(path: Path, render: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(render, indent=2, sort_keys=True) + "\n", encoding="utf-8")
