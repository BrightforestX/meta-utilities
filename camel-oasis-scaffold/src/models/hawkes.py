"""Univariate Hawkes self-exciting point-process fit for cascade analysis.

Models the rate of new comments/reposts on a seed post as

    λ(t) = μ + Σ_{t_i < t}  α · exp(-β (t - t_i))

The branching factor n* = α / β is the expected number of children per event;
n* < 1 ⇒ subcritical (cascade dies out), n* >= 1 ⇒ supercritical (unbounded
expected growth, before any exhaustion).

Implementation uses an exponential-kernel MLE — no tick dependency, since
`tick` is brittle on Apple Silicon. For multivariate or non-parametric
kernels, swap in `tick.hawkes`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize


@dataclass
class HawkesFit:
    mu: float       # baseline intensity
    alpha: float    # jump size
    beta: float     # decay rate
    branching: float  # n* = alpha / beta
    log_lik: float


def _hawkes_neg_log_lik(theta, events, T):
    log_mu, log_alpha, log_beta = theta
    mu, alpha, beta = np.exp(log_mu), np.exp(log_alpha), np.exp(log_beta)

    if len(events) == 0:
        return mu * T

    # Recursive computation of R_i = sum_{j<i} exp(-beta * (t_i - t_j))
    R = np.zeros(len(events))
    for i in range(1, len(events)):
        R[i] = np.exp(-beta * (events[i] - events[i - 1])) * (1 + R[i - 1])

    log_intensity = np.log(mu + alpha * R)
    integral = mu * T + (alpha / beta) * np.sum(1 - np.exp(-beta * (T - events)))
    return -(np.sum(log_intensity) - integral)


def fit_hawkes(event_times: np.ndarray, T: float | None = None) -> HawkesFit:
    """Fit an exp-kernel Hawkes to a 1-D array of event times (sorted)."""
    events = np.sort(np.asarray(event_times, dtype=float))
    if T is None:
        T = float(events[-1]) if len(events) else 1.0

    res = minimize(
        _hawkes_neg_log_lik,
        x0=np.log([0.1, 0.5, 1.0]),
        args=(events, T),
        method="Nelder-Mead",
        options={"xatol": 1e-6, "fatol": 1e-6, "maxiter": 5000},
    )
    mu, alpha, beta = np.exp(res.x)
    return HawkesFit(
        mu=mu, alpha=alpha, beta=beta,
        branching=alpha / beta, log_lik=-res.fun,
    )
