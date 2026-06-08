# Cost Telemetry Schema (P3)

Persisted as cost_report.json alongside reports.

See models.CostReport for the frozen P0 shape:
- run_id
- local_tokens, api_tokens
- estimated_cost_usd
- local_model, api_model
- notes

The split local/API is emitted by the ask/run paths (hybrid router + workforce).

Local model identifiers now include backend provider and model, e.g.:
- `local:mlx:mlx-qwen`
- `local:ollama:llama3.1:8b`
- `local:lmstudio:qwen2.5-7b-instruct`
- `local:turnover:turnover-local-14b`

AC6 requires the split and dollar estimate.
