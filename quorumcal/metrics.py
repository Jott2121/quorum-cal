"""Pure math for panel calibration. No I/O in this module — ever."""
from __future__ import annotations

from dataclasses import dataclass
import math
import random

# one-sided z for the small set of confidences we support
_Z = {0.9: 1.2815515655, 0.95: 1.6448536270, 0.99: 2.3263478740}


def wilson_upper(k: int, n: int, confidence: float = 0.9) -> float:
    """One-sided Wilson score upper bound for a binomial proportion k/n."""
    if n <= 0 or k < 0 or k > n:
        raise ValueError(f"need 0 <= k <= n with n > 0, got k={k} n={n}")
    z = _Z[confidence]
    p = k / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return min(1.0, (center + margin) / denom)


def empirical_quantile(values: list[float], p: float) -> float:
    """Conservative (upper) empirical quantile: the ceil(p*n)-th smallest value."""
    if not values:
        raise ValueError("empirical_quantile needs at least one value")
    if not 0.0 < p <= 1.0:
        raise ValueError(f"p must be in (0, 1], got {p}")
    ordered = sorted(values)
    idx = math.ceil(p * len(ordered)) - 1
    return ordered[max(0, idx)]


def pairwise_phi(a: list[int], b: list[int]) -> float | None:
    """Phi coefficient between two aligned binary vectors.

    Zero-variance vectors make phi UNDEFINED and we return None — the earlier
    0.0 convention masked unidentified dependence as measured independence
    (cross-model review 2026-07-21). Callers must count undefined pairs."""
    if len(a) != len(b):
        raise ValueError(f"vectors must align, got {len(a)} vs {len(b)}")
    n11 = sum(1 for x, y in zip(a, b) if x == 1 and y == 1)
    n10 = sum(1 for x, y in zip(a, b) if x == 1 and y == 0)
    n01 = sum(1 for x, y in zip(a, b) if x == 0 and y == 1)
    n00 = sum(1 for x, y in zip(a, b) if x == 0 and y == 0)
    denom = math.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    if denom == 0:
        return None
    return (n11 * n00 - n10 * n01) / denom


def mean_pairwise_phi(vectors: list[list[int]]) -> tuple[float, int, int]:
    """(rho_bar over DEFINED pairs, total pairs, undefined pairs).

    rho_bar is 0.0 when no pair is defined — with n_undefined == n_pairs the
    caller can see that dependence is unidentified, not measured-zero."""
    if len(vectors) < 2:
        raise ValueError("need at least two judges")
    phis = [
        pairwise_phi(vectors[i], vectors[j])
        for i in range(len(vectors))
        for j in range(i + 1, len(vectors))
    ]
    defined = [p for p in phis if p is not None]
    rho = sum(defined) / len(defined) if defined else 0.0
    return rho, len(phis), len(phis) - len(defined)


def n_eff(n_judges: int, rho_bar: float) -> float:
    """Kish design-effect effective independent vote count.

    Negative rho_bar is clamped to 0 (N_eff never exceeds N: anticorrelated
    errors are luck, not independence you can bank)."""
    rho = max(0.0, rho_bar)
    return n_judges / (1 + (n_judges - 1) * rho)


def bootstrap_n_eff(vectors: list[list[int]], iters: int = 2000, seed: int = 0,
                    alpha: float = 0.1) -> tuple[float, float]:
    """Bootstrap CI for N_eff: resample task columns with replacement, alpha/2
    and 1-alpha/2 empirical quantiles of the resampled N_eff distribution.

    N_eff and rho_bar computed straight from `vectors` are bare points; the
    pre-committed gate needs an interval, not a point estimate."""
    n_judges = len(vectors)
    n_tasks = len(vectors[0]) if vectors else 0
    rng = random.Random(seed)
    samples = []
    for _ in range(iters):
        idx = [rng.randrange(n_tasks) for _ in range(n_tasks)]
        resampled = [[v[i] for i in idx] for v in vectors]
        rho, _pairs, _undef = mean_pairwise_phi(resampled)
        samples.append(n_eff(n_judges, rho))
    samples.sort()
    lo = empirical_quantile(samples, alpha / 2)
    hi = empirical_quantile(samples, 1 - alpha / 2)
    return (lo, hi)


_VERDICTS = frozenset({"endorse", "reject", "abstain", "error"})
_LABELS = frozenset({"valid", "invalid"})
ERROR_GUARD_FRACTION = 0.05


@dataclass(frozen=True)
class PanelMetrics:
    n_judges: int
    n_tasks_total: int
    n_tasks_used: int
    n_tasks_error: int
    error_guard_tripped: bool
    e_delta: float
    u_epsilon: float
    per_judge_wrong_rate: list[float]
    per_judge_wrong_upper: list[float]
    rho_bar: float
    n_phi_pairs: int
    n_phi_undefined: int
    n_effective: float
    q_min: int
    q_max: int
    feasible: bool
    wrong_vectors: list[list[int]]


def panel_metrics(rows: list[tuple[str, list[str]]],
                  delta: float = 0.1, epsilon: float = 0.1) -> PanelMetrics:
    if not rows:
        raise ValueError("no rows")
    n_judges = len(rows[0][1])
    for label, verdicts in rows:
        if label not in _LABELS:
            raise ValueError(f"bad label {label!r}")
        if len(verdicts) != n_judges:
            raise ValueError("ragged verdict rows")
        for v in verdicts:
            if v not in _VERDICTS:
                raise ValueError(f"bad verdict {v!r}")

    used = [(lb, vs) for lb, vs in rows if "error" not in vs]
    n_error = len(rows) - len(used)
    if not used:
        raise ValueError("every row contains an error verdict")

    endorse_counts = [sum(1 for v in vs if v == "endorse")
                      for lb, vs in used if lb == "invalid"]
    # Liveness counts NON-ENDORSEMENTS on valid tasks: a reject withholds
    # endorsement exactly like an abstain, so both block a quorum of q
    # (abstain-only counting overstated q_max — cross-model review 2026-07-21).
    nonendorse_counts = [sum(1 for v in vs if v != "endorse")
                         for lb, vs in used if lb == "valid"]
    e_delta = empirical_quantile([float(c) for c in endorse_counts], 1 - delta) \
        if endorse_counts else 0.0
    u_epsilon = empirical_quantile([float(c) for c in nonendorse_counts], 1 - epsilon) \
        if nonendorse_counts else 0.0

    def wrong(label: str, verdict: str) -> int:
        if label == "invalid" and verdict == "endorse":
            return 1
        if label == "valid" and verdict == "reject":
            return 1
        return 0

    vectors = [[wrong(lb, vs[j]) for lb, vs in used] for j in range(n_judges)]
    n_used = len(used)
    rates = [sum(v) / n_used for v in vectors]
    uppers = [wilson_upper(sum(v), n_used) for v in vectors]
    rho, n_pairs, n_undef = mean_pairwise_phi(vectors)

    q_min = math.floor(e_delta) + 1
    q_max = n_judges - math.ceil(u_epsilon)
    return PanelMetrics(
        n_judges=n_judges,
        n_tasks_total=len(rows),
        n_tasks_used=n_used,
        n_tasks_error=n_error,
        error_guard_tripped=n_error / len(rows) > ERROR_GUARD_FRACTION,
        e_delta=e_delta,
        u_epsilon=u_epsilon,
        per_judge_wrong_rate=rates,
        per_judge_wrong_upper=uppers,
        rho_bar=rho,
        n_phi_pairs=n_pairs,
        n_phi_undefined=n_undef,
        n_effective=n_eff(n_judges, rho),
        q_min=q_min,
        q_max=q_max,
        feasible=q_min <= q_max,
        wrong_vectors=vectors,
    )
