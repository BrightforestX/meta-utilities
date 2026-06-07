"""Bounded-confidence opinion-dynamics models.

- Deffuant–Weisbuch (pairwise):
      if |x_i - x_j| < ε:   x_i' = x_i + μ (x_j - x_i),  x_j' = x_j + μ (x_i - x_j)

- Hegselmann–Krause (full-mixing):
      x_i' = mean({ x_j : |x_i - x_j| < ε })

These are used to *forward-simulate* the opinion trajectories implied by
fitted ε (confidence bound) and μ (convergence rate), then compared to the
trajectories observed in OASIS. ε and μ are fit by grid search minimizing
distributional distance (Wasserstein-1) at each timestep.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import wasserstein_distance


@dataclass
class BCFit:
    epsilon: float
    mu: float
    distance: float  # mean Wasserstein-1 across timesteps


def simulate_deffuant(x0: np.ndarray, epsilon: float, mu: float, steps: int,
                       rng: np.random.Generator | None = None) -> np.ndarray:
    """Return opinion matrix shape (steps+1, N)."""
    if rng is None:
        rng = np.random.default_rng(0)
    N = len(x0)
    history = np.zeros((steps + 1, N))
    history[0] = x0
    x = x0.copy()
    for t in range(1, steps + 1):
        i, j = rng.integers(0, N, size=2)
        if i != j and abs(x[i] - x[j]) < epsilon:
            xi, xj = x[i], x[j]
            x[i] = xi + mu * (xj - xi)
            x[j] = xj + mu * (xi - xj)
        history[t] = x
    return history


def simulate_hk(x0: np.ndarray, epsilon: float, steps: int) -> np.ndarray:
    N = len(x0)
    history = np.zeros((steps + 1, N))
    history[0] = x0
    x = x0.copy()
    for t in range(1, steps + 1):
        new_x = np.empty_like(x)
        for i in range(N):
            neighbors = x[np.abs(x - x[i]) < epsilon]
            new_x[i] = neighbors.mean() if len(neighbors) else x[i]
        x = new_x
        history[t] = x
    return history


def fit_deffuant(observed: np.ndarray, eps_grid=None, mu_grid=None,
                  n_sims: int = 5) -> BCFit:
    """`observed` shape (T, N). We grid-search ε, μ to minimize mean
    Wasserstein-1 between simulated and observed marginal distributions
    at each timestep (averaged over `n_sims` stochastic replicates)."""
    if eps_grid is None:
        eps_grid = np.linspace(0.05, 0.5, 10)
    if mu_grid is None:
        mu_grid = np.linspace(0.1, 0.5, 5)
    T, N = observed.shape
    best = BCFit(epsilon=np.nan, mu=np.nan, distance=np.inf)

    for eps in eps_grid:
        for mu in mu_grid:
            dists = []
            for s in range(n_sims):
                rng = np.random.default_rng(s)
                sim = simulate_deffuant(observed[0], eps, mu, T - 1, rng=rng)
                d = np.mean([wasserstein_distance(sim[t], observed[t]) for t in range(T)])
                dists.append(d)
            mean_d = float(np.mean(dists))
            if mean_d < best.distance:
                best = BCFit(epsilon=eps, mu=mu, distance=mean_d)
    return best


def polarization_index(opinions: np.ndarray) -> float:
    """Bimodality coefficient — high ⇒ two camps; low ⇒ consensus.
    BC = (skew^2 + 1) / (kurtosis + 3*(n-1)^2 / ((n-2)*(n-3)))
    Values > 0.555 indicate bimodality (Pfister et al., 2013).
    """
    from scipy.stats import skew, kurtosis
    n = len(opinions)
    if n < 4:
        return float("nan")
    s = skew(opinions, bias=False)
    k = kurtosis(opinions, fisher=False, bias=False)
    return (s ** 2 + 1) / (k + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))
