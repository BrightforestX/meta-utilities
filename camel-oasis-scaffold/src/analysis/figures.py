"""P1 gap: figures.py

Stub for generating report figures (cascade png, polarization, uplift).
In real runs the scaffold notebooks or analysis emit pngs; this provides the contract surface.
"""
from __future__ import annotations

from pathlib import Path


def make_cascade_plot(db_path: Path, out_png: Path) -> Path:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    # Placeholder: in real would use matplotlib on db_loader cascade_series
    out_png.write_text("PNG PLACEHOLDER for cascade")
    return out_png


def make_uplift_plot(ab_db: Path, out_png: Path) -> Path:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_png.write_text("PNG PLACEHOLDER for uplift")
    return out_png
