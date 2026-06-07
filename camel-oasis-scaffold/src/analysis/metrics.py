"""Summary metrics computed from OASIS DB outputs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.analysis.db_loader import cascade_series, event_times, engagement_outcomes
from src.models.sir import fit_sir
from src.models.hawkes import fit_hawkes


@dataclass
class CascadeReport:
    n_engaged: int
    n_total: int
    sir_r0: float
    sir_final_size: float
    hawkes_branching: float
    peak_step: int


def cascade_report(db_path: Path, post_id: int = 1, population: int | None = None) -> CascadeReport:
    series = cascade_series(db_path, post_id=post_id)
    if population is None:
        s, n = engagement_outcomes(db_path, post_id)
        population = n
        n_engaged = s
    else:
        n_engaged = int(series.iloc[-1]) if len(series) else 0

    # SIR — convert cumulative engagement to instantaneous infected:
    # I(t) = engaged in last τ=3 steps (rough proxy)
    τ = 3
    cum = series.values
    inst = np.diff(np.concatenate([[0], cum]))
    I_t = np.convolve(inst, np.ones(τ), mode="full")[: len(inst)]
    sir = fit_sir(I_t, population=population, initial_infected=1)

    ev = event_times(db_path, post_id)
    hk = fit_hawkes(np.asarray(ev)) if len(ev) > 5 else None

    peak_step = int(np.argmax(I_t)) if len(I_t) else 0
    return CascadeReport(
        n_engaged=n_engaged,
        n_total=population,
        sir_r0=sir.r0,
        sir_final_size=sir.final_size,
        hawkes_branching=hk.branching if hk else float("nan"),
        peak_step=peak_step,
    )
