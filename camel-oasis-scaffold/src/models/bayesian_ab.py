"""Bayesian A/B testing + simple uplift.

For binary engagement outcomes (engaged / didn't engage), use the
Beta-Binomial conjugate prior:

    p_A ~ Beta(α0, β0)   posterior:  Beta(α0 + s_A, β0 + n_A - s_A)
    p_B ~ Beta(α0, β0)   posterior:  Beta(α0 + s_B, β0 + n_B - s_B)

We then Monte-Carlo sample (p_A, p_B) and report:
- P(B > A)            — posterior probability B wins
- E[max(0, A-B)/B]    — expected loss if we pick B and B is actually worse
- 95% HDI on uplift   — credible interval on (p_B - p_A) / p_A

For continuous outcomes (engagement count per agent), swap Beta-Binomial
for Gamma-Poisson or a Bayesian linear model — see PyMC notebook.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import beta as beta_dist


@dataclass
class BayesianABResult:
    posterior_a: tuple[float, float]   # (alpha, beta) of variant A
    posterior_b: tuple[float, float]
    p_b_beats_a: float
    expected_loss_choosing_b: float
    uplift_hdi_95: tuple[float, float]  # on (p_B - p_A) / p_A


def beta_binomial_ab(
    successes_a: int, trials_a: int,
    successes_b: int, trials_b: int,
    prior_alpha: float = 1.0, prior_beta: float = 1.0,
    n_samples: int = 200_000,
    rng: np.random.Generator | None = None,
) -> BayesianABResult:
    if rng is None:
        rng = np.random.default_rng(0)

    a_post = (prior_alpha + successes_a, prior_beta + trials_a - successes_a)
    b_post = (prior_alpha + successes_b, prior_beta + trials_b - successes_b)

    pa = beta_dist.rvs(*a_post, size=n_samples, random_state=rng)
    pb = beta_dist.rvs(*b_post, size=n_samples, random_state=rng)

    p_b_wins = float(np.mean(pb > pa))
    loss = np.maximum(pa - pb, 0)
    expected_loss = float(np.mean(loss))
    uplift = (pb - pa) / np.where(pa > 1e-9, pa, np.nan)
    hdi_lo, hdi_hi = np.nanpercentile(uplift, [2.5, 97.5])

    return BayesianABResult(
        posterior_a=a_post,
        posterior_b=b_post,
        p_b_beats_a=p_b_wins,
        expected_loss_choosing_b=expected_loss,
        uplift_hdi_95=(float(hdi_lo), float(hdi_hi)),
    )


def thompson_sample_arm(successes: list[int], trials: list[int],
                         prior_alpha: float = 1.0, prior_beta: float = 1.0,
                         rng: np.random.Generator | None = None) -> int:
    """Pick the next arm (variant index) via Thompson sampling."""
    if rng is None:
        rng = np.random.default_rng()
    draws = [
        beta_dist.rvs(prior_alpha + s, prior_beta + n - s, random_state=rng)
        for s, n in zip(successes, trials)
    ]
    return int(np.argmax(draws))
