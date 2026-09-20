"""uncertainty-budget-v2 — GUM LPU and Monte Carlo as a declared record.

Traceability is a declared string. Default is none_claimed.
The v1 declaration reader remains supported; undefined variance ratios are null
in v2 rather than zero. Evidence and observation identities are unaffected.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from enum import Enum
from fractions import Fraction
from numbers import Integral, Real
from typing import Sequence

import numpy as np

SCHEMA = "uncertainty-budget-v2"
LEGACY_SCHEMA = "uncertainty-budget-v1"


def _number(value, name: str, *, nonnegative=False, positive=False) -> float:
    """Validate declarations without coercing strings, booleans or nonfinite values."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be finite in float64") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if result == 0 and value != 0:
        raise ValueError(f"{name} underflows float64; nonzero declarations cannot become zero")
    if (positive and result <= 0) or (nonnegative and result < 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'non-negative'}")
    return result


def _text(value, name: str, *, nonempty=False) -> None:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ValueError(f"{name} must be {'a nonempty string' if nonempty else 'a string'}")


def _dof(value, name: str) -> float:
    # Positive infinity explicitly means unlimited degrees of freedom, not an
    # unavailable standard deviation. NaN and negative infinity never mean this.
    if (isinstance(value, Real) and not isinstance(value, (bool, np.bool_))
            and value == math.inf):
        return math.inf
    return _number(value, name, positive=True)


def _result(value: float, name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{name} overflowed; no nonfinite result is reported")
    return value


def _product(a: float, b: float, name: str) -> float:
    value = _result(float(a) * float(b), name)
    if value == 0 and a != 0 and b != 0:
        raise ValueError(f"{name} underflowed; a nonzero uncertainty cannot become zero")
    return value


def _native_number(value):
    """Serialize accepted reals without changing native Python int/float forms."""
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        return float(value)
    return value


class Dist(str, Enum):
    NORMAL = "normal"
    RECTANGULAR = "rectangular"
    TRIANGULAR = "triangular"
    U_SHAPED = "u_shaped"


_DIVISOR: dict[Dist, float] = {
    Dist.RECTANGULAR: math.sqrt(3.0),
    Dist.TRIANGULAR: math.sqrt(6.0),
    Dist.U_SHAPED: math.sqrt(2.0),
}

_T_TABLE: dict[float, dict[int, float]] = {
    0.95: {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
        14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
        20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042, 40: 2.021,
        50: 2.009, 60: 2.000, 100: 1.984,
    },
    0.99: {
        1: 63.657, 2: 9.925, 3: 5.841, 4: 4.604, 5: 4.032, 6: 3.707, 7: 3.499,
        8: 3.355, 9: 3.250, 10: 3.169, 12: 3.055, 15: 2.947, 20: 2.845,
        25: 2.787, 30: 2.750, 40: 2.704, 50: 2.678, 60: 2.660, 100: 2.626,
    },
}
_T_INF: dict[float, float] = {0.95: 1.960, 0.99: 2.576}


def coverage_factor(dof: float, p: float = 0.95) -> float:
    dof = _dof(dof, "effective degrees of freedom")
    p = _number(p, "coverage probability")
    if p not in _T_TABLE:
        raise ValueError(f"no t-table for p={p}; declared levels are {sorted(_T_TABLE)}")
    if dof <= 0:
        raise ValueError("effective degrees of freedom must be positive")
    table = _T_TABLE[p]
    t_inf = _T_INF[p]
    keys = sorted(table)
    if math.isinf(dof) or dof > keys[-1]:
        if math.isinf(dof):
            return t_inf
        lo = keys[-1]
        w = (1.0 / dof) / (1.0 / lo)
        return t_inf + w * (table[lo] - t_inf)
    if dof <= keys[0]:
        return table[keys[0]]
    hi = min(k for k in keys if k >= dof)
    if hi == dof:
        return table[int(dof)] if int(dof) in table else table[hi]
    lo = max(k for k in keys if k < dof)
    w = (1.0 / dof - 1.0 / hi) / (1.0 / lo - 1.0 / hi)
    return table[hi] + w * (table[lo] - table[hi])


@dataclass(frozen=True)
class TypeA:
    source: str
    s: float
    n: int
    statistic: str
    c: float = 1.0
    unit: str = ""

    def __post_init__(self) -> None:
        _text(self.source, "source", nonempty=True)
        _text(self.unit, "unit")
        if isinstance(self.n, (bool, np.bool_)) or not isinstance(self.n, Integral) or self.n < 2:
            raise ValueError(f"{self.source}: Type A needs n >= 2, got {self.n}")
        _number(self.n, f"{self.source}: sample count", positive=True)
        _number(self.s, f"{self.source}: standard deviation", nonnegative=True)
        _number(self.c, f"{self.source}: sensitivity coefficient")
        if self.statistic not in ("mean", "single"):
            raise ValueError(
                f"{self.source}: statistic must be declared as 'mean' or 'single'"
            )

    @property
    def u(self) -> float:
        value = float(self.s) / math.sqrt(self.n) if self.statistic == "mean" else float(self.s)
        if value == 0 and self.s != 0:
            raise ValueError(f"{self.source}: standard uncertainty underflowed")
        return value

    @property
    def dof(self) -> float:
        return float(self.n - 1)

    @property
    def contribution(self) -> float:
        return abs(_product(self.c, self.u, f"{self.source}: sensitivity contribution"))

    def to_dict(self) -> dict:
        return {
            "type": "A",
            "source": self.source,
            "s": _native_number(self.s),
            "n": int(self.n),
            "statistic": self.statistic,
            "c": _native_number(self.c),
            "unit": self.unit,
            "u": self.u,
            "dof": self.dof,
        }


@dataclass(frozen=True)
class TypeB:
    source: str
    dist: Dist
    half_width: float | None = None
    std: float | None = None
    k: float = 1.0
    dof: float = math.inf
    c: float = 1.0
    unit: str = ""

    def __post_init__(self) -> None:
        _text(self.source, "source", nonempty=True)
        _text(self.unit, "unit")
        _number(self.c, f"{self.source}: sensitivity coefficient")
        _number(self.k, f"{self.source}: divisor k", positive=True)
        _dof(self.dof, f"{self.source}: degrees of freedom")
        if self.std is not None:
            _number(self.std, f"{self.source}: standard deviation", nonnegative=True)
        if self.half_width is not None:
            _number(self.half_width, f"{self.source}: half_width", nonnegative=True)
        d = Dist(self.dist)
        if d is Dist.NORMAL:
            if self.std is None:
                raise ValueError(f"{self.source}: normal component needs std")
            if self.k <= 0:
                raise ValueError(f"{self.source}: divisor k must be positive")
        else:
            if self.half_width is None:
                raise ValueError(f"{self.source}: {d.value} component needs half_width")
            if self.half_width < 0:
                raise ValueError(f"{self.source}: half_width must be non-negative")

    @property
    def u(self) -> float:
        d = Dist(self.dist)
        numerator = float(self.std) if d is Dist.NORMAL else float(self.half_width)
        divisor = float(self.k) if d is Dist.NORMAL else _DIVISOR[d]
        value = _result(numerator / divisor, f"{self.source}: standard uncertainty")
        if value == 0 and numerator != 0:
            raise ValueError(f"{self.source}: standard uncertainty underflowed")
        return value

    @property
    def contribution(self) -> float:
        return abs(_product(self.c, self.u, f"{self.source}: sensitivity contribution"))

    def to_dict(self) -> dict:
        return {
            "type": "B",
            "source": self.source,
            "dist": Dist(self.dist).value,
            "half_width": _native_number(self.half_width),
            "std": _native_number(self.std),
            "k": _native_number(self.k),
            "dof": None if math.isinf(self.dof) else _native_number(self.dof),
            "c": _native_number(self.c),
            "unit": self.unit,
            "u": self.u,
        }


Component = TypeA | TypeB


@dataclass
class Budget:
    measurand: str
    components: list[Component] = field(default_factory=list)
    correlations: dict[tuple[str, str], float] = field(default_factory=dict)
    traceability: str = "none_claimed"
    unit: str = ""

    def __post_init__(self) -> None:
        self._correlation_matrix()

    def _correlation_matrix(self) -> np.ndarray:
        """Check the entire declared correlation model, including after mutation.

        Correlation is dimensionless, so the eigenvalue roundoff bound does not
        change with units or component scale. A valid singular model is allowed;
        no jitter, diagonal approximation or nearest-PSD repair is applied.
        """
        _text(self.measurand, "measurand", nonempty=True)
        _text(self.unit, "unit")
        _text(self.traceability, "traceability")
        if not isinstance(self.components, Sequence) or any(
                not isinstance(c, (TypeA, TypeB)) for c in self.components):
            raise ValueError("components must be TypeA or TypeB declarations")
        if not isinstance(self.correlations, dict):
            raise ValueError("correlations must be a dictionary of source pairs")
        names = [c.source for c in self.components]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate component sources: {sorted(dupes)}")
        for pair, rho in self.correlations.items():
            if (not isinstance(pair, tuple) or len(pair) != 2
                    or any(not isinstance(name, str) for name in pair)):
                raise ValueError("each correlation key must be a pair of source names")
            a, b = pair
            if a not in names or b not in names:
                raise ValueError(f"correlation names ({a}, {b}) for unknown components")
            rho = _number(rho, f"correlation ({a}, {b})")
            if not -1 <= rho <= 1:
                raise ValueError("correlation coefficients must lie in [-1, 1]")
            if a == b and rho != 1:
                raise ValueError("self correlation must equal 1")
            if (b, a) in self.correlations and self.correlations[b, a] != rho:
                raise ValueError("reverse correlation declarations must agree exactly")
        correlation = np.array([[self._r(a, b) for b in names] for a in names], dtype=float)
        if names:
            try:
                eigenvalues = np.linalg.eigvalsh(correlation)
            except np.linalg.LinAlgError as exc:
                raise ValueError("correlation PSD validation did not converge") from exc
            bound = 64 * np.finfo(float).eps * len(names) * max(1.0, float(np.max(np.abs(eigenvalues))))
            if not np.all(np.isfinite(eigenvalues)) or eigenvalues[0] < -bound:
                raise ValueError("full correlation matrix must be positive semidefinite")
        return correlation

    def _r(self, a: str, b: str) -> float:
        if a == b:
            return 1.0
        return self.correlations.get((a, b), self.correlations.get((b, a), 0.0))

    @property
    def uncorrelated(self) -> bool:
        self._correlation_matrix()
        return not any(a != b and v != 0.0 for (a, b), v in self.correlations.items())

    def _weighted_uncertainties(self) -> list[float]:
        return [_product(comp.c, comp.u, f"{comp.source}: sensitivity contribution")
                for comp in self.components]

    def u_c(self) -> float:
        correlation = self._correlation_matrix()
        if not self.components:
            raise ValueError("empty budget: nothing declared, so nothing is reported")
        contributions = self._weighted_uncertainties()
        # A single global scale loses tiny independent terms when large
        # correlated contributions cancel. Budgets are small: sum the quadratic
        # form exactly over the declared float64 coefficients, then take a
        # high-precision square root. This neither repairs R nor fabricates zero.
        weighted = [Fraction(value) for value in contributions]
        variance = sum((value * value for value in weighted), Fraction(0))
        for i, a in enumerate(weighted):
            for j in range(i):
                variance += 2 * a * weighted[j] * Fraction(float(correlation[i, j]))
        if variance < 0:
            raise ValueError("combined variance is negative; the declared model cannot support this result")
        if variance == 0:
            return 0.0
        with localcontext() as context:
            context.prec = 80
            value = float((Decimal(variance.numerator) / Decimal(variance.denominator)).sqrt())
        _result(value, "combined standard uncertainty")
        if value == 0:
            raise ValueError("combined standard uncertainty underflowed")
        return value

    def dof_eff(self) -> float:
        if not self.uncorrelated:
            raise ValueError(
                "Welch-Satterthwaite is declared only for uncorrelated components; "
                "this budget declares correlations"
            )
        uc = self.u_c()
        if uc == 0.0:
            return math.inf
        terms = []
        for comp, contribution in zip(self.components, self._weighted_uncertainties()):
            nu = comp.dof
            if math.isinf(nu):
                continue
            if contribution != 0:
                terms.append((contribution / uc) ** 4 / nu)
        if not terms:
            return math.inf
        denom = math.fsum(terms)
        if denom == 0:
            raise ValueError("effective degrees of freedom exceed the numerical range")
        return _result(1.0 / denom, "effective degrees of freedom")

    def k(self, p: float = 0.95) -> float:
        return coverage_factor(self.dof_eff(), p)

    def U(self, p: float = 0.95) -> float:
        return _product(self.k(p), self.u_c(), "expanded uncertainty")

    def contributions(self) -> list[dict]:
        """Diagonal ratios, not an additive decomposition when correlated.

        Cross terms are excluded. Ratios may exceed one and are None when the
        combined uncertainty is zero, since the denominator is then zero.
        """
        uc = self.u_c()
        rows = []
        for comp in self.components:
            ci = _product(comp.c, comp.u, f"{comp.source}: sensitivity contribution")
            ratio = ci / uc if uc > 0 else None
            share = _result(ratio * ratio, "variance share") if ratio is not None else None
            rows.append(
                {
                    "source": comp.source,
                    "u_i": comp.u,
                    "c_i": _native_number(comp.c),
                    "c_i_u_i": ci,
                    "variance_share": share,
                }
            )
        rows.sort(key=lambda r: abs(r["c_i_u_i"]), reverse=True)
        return rows

    def monte_carlo(self, n_draws: int = 200_000, seed: int = 0, p: float = 0.95) -> dict:
        if not self.uncorrelated:
            raise ValueError("Monte Carlo path is declared for uncorrelated components only")
        self.u_c()  # Require a nonempty, numerically representable budget first.
        if (isinstance(n_draws, (bool, np.bool_)) or not isinstance(n_draws, Integral)
                or n_draws < 2):
            raise ValueError("n_draws must be an integer >= 2")
        p = _number(p, "coverage probability")
        if not 0 < p < 1:
            raise ValueError("coverage probability must lie strictly between zero and one")
        m = int(round(p * n_draws))
        if not 1 <= m < n_draws:
            raise ValueError("coverage probability requires more draws for a nonempty interval search")
        rng = np.random.default_rng(seed)
        y = np.zeros(n_draws)
        for comp in self.components:
            if comp.u == 0:
                x = np.zeros(n_draws)
            elif isinstance(comp, TypeA):
                x = comp.u * rng.standard_t(comp.dof, n_draws)
            else:
                d = Dist(comp.dist)
                if d is Dist.NORMAL:
                    x = rng.normal(0.0, comp.u, n_draws)
                elif d is Dist.RECTANGULAR:
                    a = float(comp.half_width)
                    x = rng.uniform(-a, a, n_draws)
                elif d is Dist.TRIANGULAR:
                    a = float(comp.half_width)
                    x = rng.triangular(-a, 0.0, a, n_draws)
                else:
                    a = float(comp.half_width)
                    x = a * np.cos(rng.uniform(0.0, 2.0 * math.pi, n_draws))
            with np.errstate(over="ignore", invalid="ignore"):
                y += comp.c * x
            if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
                raise ValueError("Monte Carlo samples overflowed; no nonfinite result is reported")
        scale = float(np.max(np.abs(y)))
        ys = np.sort(y / scale if scale else y)
        widths = ys[m:] - ys[: n_draws - m]
        lo = int(np.argmin(widths))
        return {
            "n_draws": int(n_draws),
            "seed": _native_number(seed),
            "p": p,
            "u_c": _product(float(np.std(y / scale if scale else y, ddof=1)), scale, "Monte Carlo standard uncertainty"),
            "interval_low": _result(float(ys[lo]) * scale, "Monte Carlo interval"),
            "interval_high": _result(float(ys[lo + m]) * scale, "Monte Carlo interval"),
        }

    def to_record(self, p: float = 0.95) -> dict:
        p = _number(p, "coverage probability")
        if not 0 < p < 1:
            raise ValueError("coverage probability must lie strictly between zero and one")
        nu = self.dof_eff() if self.uncorrelated else None
        return {
            "schema": SCHEMA,
            "measurand": self.measurand,
            "unit": self.unit,
            "components": [c.to_dict() for c in self.components],
            "correlations": [
                {"a": a, "b": b, "r": _native_number(r)} for (a, b), r in self.correlations.items()
            ],
            "combination": "gum_lpu" if self.uncorrelated else "gum_lpu_correlated",
            "u_c": self.u_c(),
            "dof_eff": None if (nu is None or math.isinf(nu)) else nu,
            "p": p,
            "k": self.k(p) if self.uncorrelated else None,
            "U": self.U(p) if self.uncorrelated else None,
            "contributions": self.contributions(),
            "traceability": self.traceability,
        }

    def to_json(self, p: float = 0.95, **kw) -> str:
        kw.setdefault("allow_nan", False)
        return json.dumps(self.to_record(p), **kw)


def from_record(rec: dict) -> Budget:
    """Reconstruct validated v1/v2 declarations, not trust stored derived values.

    A newly serialized record uses v2. This never modifies a received artifact
    or re-labels an existing evidence identity.
    """
    if not isinstance(rec, dict) or rec.get("schema") not in (SCHEMA, LEGACY_SCHEMA):
        raise ValueError(f"expected schema {SCHEMA} or {LEGACY_SCHEMA}")
    if not isinstance(rec.get("components"), list):
        raise ValueError("record components must be an array")
    comps: list[Component] = []
    for c in rec["components"]:
        if not isinstance(c, dict) or c.get("type") not in ("A", "B"):
            raise ValueError("component type must be A or B")
        if c["type"] == "A":
            comps.append(
                TypeA(
                    source=c["source"],
                    s=c["s"],
                    n=c["n"],
                    statistic=c["statistic"],
                    c=c["c"],
                    unit=c.get("unit", ""),
                )
            )
        elif c["type"] == "B":
            comps.append(
                TypeB(
                    source=c["source"],
                    dist=Dist(c["dist"]),
                    half_width=c.get("half_width"),
                    std=c.get("std"),
                    k=c.get("k", 1.0),
                    dof=math.inf if c.get("dof") is None else c["dof"],
                    c=c["c"],
                    unit=c.get("unit", ""),
                )
            )
        else:
            raise ValueError("component type must be A or B")
    corr = {}
    declarations = rec.get("correlations", [])
    if not isinstance(declarations, list):
        raise ValueError("record correlations must be an array")
    for declaration in declarations:
        if not isinstance(declaration, dict) or set(declaration) != {"a", "b", "r"}:
            raise ValueError("correlation declaration must contain a, b and r")
        _text(declaration["a"], "correlation source", nonempty=True)
        _text(declaration["b"], "correlation source", nonempty=True)
        pair = (declaration["a"], declaration["b"])
        if pair in corr:
            raise ValueError("duplicate correlation declaration")
        corr[pair] = declaration["r"]
    return Budget(
        measurand=rec["measurand"],
        components=comps,
        correlations=corr,
        traceability=rec.get("traceability", "none_claimed"),
        unit=rec.get("unit", ""),
    )
