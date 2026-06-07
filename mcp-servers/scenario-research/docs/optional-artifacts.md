# Optional / Extended Tier (P2, non-blocking)

- DVC + remote for pipeline reproducibility (dvc.yaml stages for scenarios + fits).
- EconML / causalml for richer uplift beyond the P0 bayesian_ab.
- Experiment tracking (mlflow, wandb) - opt-in.
- Ollama fallbacks if MLX unavailable on the host.

These are registered as extras in pyproject and never block core delivery or CI.
See plan "p1-artifacts-optional-tier" and "p6-optimization-nonblocking".
