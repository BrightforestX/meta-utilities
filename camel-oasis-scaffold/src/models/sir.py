"""SIR / SEIR compartmental fits to information-spread cascades.

Treat each agent as Susceptible (hasn't engaged) / Infected (has reposted or
commented within the last τ steps) / Recovered (no longer actively engaging).
Fit β (transmission) and γ (recovery) to the observed S(t), I(t), R(t) curves
recovered from the OASIS SQLite trace.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.integrate import odeint
from scipy.optimize import minimize


@dataclass
class SIRFit:
    beta: float
    gamma: float
    r0: float          # basic reproduction number = beta / gamma
    final_size: float  # fraction recovered as t -> inf
    rss: float         # residual sum of squares vs observed I(t)


def _sir_rhs(y, t, beta, gamma):
    S, I, R = y
    N = S + I + R
    dS = -beta * S * I / N
    dI = beta * S * I / N - gamma * I
    dR = gamma * I
    return [dS, dI, dR]


def fit_sir(
    infected_counts: np.ndarray,
    population: int,
    initial_infected: int = 1,
    dt: float = 1.0,
) -> SIRFit:
    """Fit a deterministic SIR ODE to an infected-count time series.

    Parameters
    ----------
    infected_counts : array of I(t) at integer time points 0..T
    population      : total N (number of agents)
    """
    T = len(infected_counts)
    t_grid = np.arange(T) * dt
    I_obs = np.asarray(infected_counts, dtype=float)

    def loss(theta):
        beta, gamma = np.exp(theta)        # enforce positivity
        y0 = [population - initial_infected, initial_infected, 0]
        sol = odeint(_sir_rhs, y0, t_grid, args=(beta, gamma))
        I_pred = sol[:, 1]
        return float(np.sum((I_pred - I_obs) ** 2))

    res = minimize(loss, x0=np.log([0.3, 0.1]), method="Nelder-Mead")
    beta, gamma = np.exp(res.x)
    r0 = beta / gamma if gamma > 0 else np.inf

    # Final-size relation: 1 - s_inf = R0 * (1 - s_0) ... solve numerically
    from scipy.optimize import brentq
    s0 = (population - initial_infected) / population
    try:
        s_inf = brentq(lambda s: np.log(s / s0) + r0 * (1 - s), 1e-6, s0)
        final_size = 1 - s_inf
    except Exception:
        final_size = float("nan")

    return SIRFit(beta=beta, gamma=gamma, r0=r0, final_size=final_size, rss=res.fun)


def simulate_sir(beta: float, gamma: float, N: int, I0: int, T: int) -> np.ndarray:
    """Forward-simulate the fitted SIR for plotting overlays."""
    t = np.arange(T)
    sol = odeint(_sir_rhs, [N - I0, I0, 0], t, args=(beta, gamma))
    return sol  # shape (T, 3): S, I, R
