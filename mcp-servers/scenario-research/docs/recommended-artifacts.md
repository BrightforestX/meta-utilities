# Recommended Artifact Tier (P1, ~25 GB target)

These are non-blocking for P0 but required for full quality (planner, PyMC uplift, reference material).

- Qwen3-14B 4-bit model (~8.5 GB) for planner/escalation quality (swap in configs/models.yaml or serve script).
- JupyterLab + PyMC (for notebooks/04_uplift_pymc.ipynb Bayesian uplift).
- Read-only clones of reference repos (oasis, camel, owl) for paper fidelity and future alignment.

Disk budget notes (from plan):
- Minimum viable (P0): ~10 GB
- Recommended (P1): ~25 GB
- Optional extended (P2): up to ~40 GB + Linux extras

See also the root plan and the package bootstrap.sh output for exact commands.
