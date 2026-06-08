# camel-oasis-deepresearch

A research scaffold that combines **CAMEL-OASIS** social simulations, the **CAMEL Workforce**
auto-research multi-agent pattern, and classical **mathematical models** (epidemiological,
opinion-dynamics, causal) to produce defensible answers to "what would happen if…?" questions.

Designed to run on an **Apple M4 MacBook** with a hybrid inference setup:
- **Local (MLX or Ollama)** for the bulk of OASIS agents — cheap, private, parallel.
- **Frontier API (Claude Sonnet / GPT)** for the Workforce planner + coordinator — quality where it matters.

---

## Architecture

```
                        ┌──────────────────────────────────────────┐
                        │  CAMEL Workforce  (auto-research)        │
                        │  ┌────────────┐  ┌──────────────┐        │
   user question  ───▶  │  │  Planner   │─▶│ Coordinator  │        │
                        │  └────────────┘  └──────┬───────┘        │
                        │                         │                │
                        │   ┌────────────────┬────┴─────┬────────┐ │
                        │   ▼                ▼          ▼        ▼ │
                        │ Literature     Scenario    Math      Report
                        │ Worker         Designer    Analyst   Writer
                        │   │               │           │        │  │
                        └───┼───────────────┼───────────┼────────┼──┘
                            │               │           │        │
                            ▼               ▼           ▼        ▼
                       web search      OASIS sim    fit SIR/    final
                       arxiv, docs     (camel-      Hawkes/     markdown
                                       oasis)       Deffuant    + figs

                       Models routed per-agent:
                         • bulk OASIS agents  → local MLX (Qwen3-8B)
                         • Workforce planner  → Claude Sonnet 4.6
                         • Math analyst       → Claude Sonnet 4.6
```

## What's inside

```
camel-oasis-scaffold/
├── configs/                  # YAML for scenarios + model routing
│   ├── models.yaml           # Local + API model definitions
│   └── scenarios/
│       ├── info_spread.yaml
│       ├── opinion_dynamics.yaml
│       └── marketing_ab.yaml
├── src/
│   ├── camel_sim/             # Multi-scenario service: schemas, actions, runner, Modal hooks
│   ├── model_factory.py      # Build CAMEL ChatAgent models from configs/models.yaml
│   ├── scenarios/
│   │   ├── info_spread.py    # OASIS sim: a seed post, observe cascade
│   │   ├── opinion_dynamics.py
│   │   └── marketing_ab.py
│   ├── models/               # Math models fit to OASIS outputs
│   │   ├── sir.py            # SIR / SEIR compartmental fit
│   │   ├── hawkes.py         # Self-exciting point process
│   │   ├── bounded_confidence.py   # Deffuant + Hegselmann–Krause
│   │   └── bayesian_ab.py    # Beta-Binomial A/B + uplift
│   ├── auto_research/
│   │   ├── workforce.py      # The Workforce wiring
│   │   ├── workers.py        # Specialized worker factories
│   │   └── prompts.py        # System prompts for each role
│   ├── analysis/
│   │   ├── db_loader.py      # OASIS SQLite -> pandas
│   │   └── metrics.py        # polarization, cascade size, R-eff, etc.
│   └── cli.py                # `python -m src.cli run info_spread`
├── notebooks/
│   ├── 01_oasis_walkthrough.ipynb
│   ├── 02_fit_sir_hawkes.ipynb
│   └── 03_workforce_auto_research.ipynb
├── scripts/
│   ├── setup_mlx.sh          # Install MLX + pull a quantized model
│   ├── setup_ollama.sh
│   └── serve_local.sh        # Start mlx_lm.server on localhost:8080
├── examples/
│   └── multi_scenarios.json  # Editable CAMEL multi-scenario batch example
├── data/                     # OASIS profile JSONs + simulation .db outputs
├── pyproject.toml
└── README.md
```

## Quick start (Apple M4)

```bash
# 1. Python env
uv venv .venv --python=3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

# 2. Stand up a local OpenAI-compatible endpoint
#    Option A: MLX (Apple-native, fastest on M-series)
./scripts/setup_mlx.sh         # pulls Qwen3-8B-Instruct-4bit
./scripts/serve_local.sh       # mlx_lm.server --host 127.0.0.1 --port 8080

#    Option B: Ollama
./scripts/setup_ollama.sh      # `ollama pull qwen3:8b`

# 3. Frontier API for the planner
export ANTHROPIC_API_KEY=sk-...
# or: export OPENAI_API_KEY=sk-...

# 4. Run a scenario end-to-end
python -m src.cli run info_spread --agents 200 --steps 30
python -m src.cli analyze info_spread --fit sir hawkes

# 5. Auto-research a question
python -m src.cli ask "If we seed a narrative on Reddit with 5 popular accounts vs 50 small ones, which spreads further and why?"
```

See `notebooks/` for step-by-step walkthroughs.

## CAMEL multi-scenario service

The `src.camel_sim` package implements the CAMEL-AI multi-scenario service
shape used for scheduling, research, negotiation, and social-dynamics runs.
It has two execution paths:

- `local`: deterministic, dependency-light action execution for fast CLI checks.
- `camel`: CAMEL `ChatAgent` + `FunctionTool` execution using configured model
  backends, including optional Modal/SGLang endpoints.

Create and run an editable scenario batch locally:

```bash
python -m src.cli multi-scenario-example --output data/multi_scenarios.json
python -m src.cli multi-scenario examples/multi_scenarios.json \
  --execution-mode local \
  --output-dir data/camel_sim_results
```

From the co-located MCP/CLI wrapper:

```bash
cd ../mcp-servers/scenario-research
uv run scenario-research multi-run ../../camel-oasis-scaffold/examples/multi_scenarios.json
```

For Modal/SGLang deployment, install the optional extra and run the Modal
entrypoint:

```bash
uv pip install -e ".[modal,parquet]"
modal run src.camel_sim.modal_app --scenario-file examples/multi_scenarios.json
```

## Why this stack

- **OASIS** gives you a real social-platform simulator (Twitter/Reddit-like) with up to 1M LLM agents, recommendation systems, and a 23-action space — far more realistic than rolling your own ABM. [paper](https://arxiv.org/abs/2411.11581)
- **CAMEL Workforce** decomposes "research a question end-to-end" into Planner → Coordinator → specialized Workers, beating OpenAI Deep Research on GAIA in the OWL paper. [paper](https://arxiv.org/abs/2505.23885)
- **Mathematical models** on top of the raw simulation traces give you parameter estimates (R₀, branching factor, polarization index) that are interpretable and comparable across scenario variants — which an LLM summary alone cannot deliver.
- **Hybrid inference** keeps cost manageable: an M4 with 24+ GB unified memory can run a Q4-quantized 8B model fast enough for hundreds of concurrent OASIS agents, while the small number of "thinking" calls in the Workforce go to a frontier model.
