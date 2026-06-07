# CAMEL-OASIS Deep-Research & Agent Simulation: Technical Dossier

> Audience: Claude Certified Architect building a deep-research + agent-based simulation system on Apple M4 MacBook.

---

## 1. OASIS: Open Agent Social Interaction Simulations

### 1.1 Installation and Imports

```bash
pip install camel-oasis
```

Core namespace imports ([OASIS Quickstart](https://docs.oasis.camel-ai.org/quickstart)):

```python
import oasis
from oasis import (
    ActionType, LLMAction, ManualAction,
    generate_reddit_agent_graph,
    generate_twitter_agent_graph,
)
from camel.models import ModelFactory
from camel.types import ModelPlatformType, ModelType
```

### 1.2 `oasis.make` — Environment Constructor

```python
env = oasis.make(
    agent_graph=agent_graph,                   # AgentGraph object
    platform=oasis.DefaultPlatformType.REDDIT, # or .TWITTER
    database_path="./data/simulation.db",
)
```

`DefaultPlatformType` has two values: `REDDIT` and `TWITTER`. The platform choice determines which recommendation algorithm is active: Reddit uses the hot-score algorithm; Twitter/X uses the interest+recency algorithm with TwHIN-BERT embeddings ([OASIS arXiv v4](https://arxiv.org/html/2411.11581v4)).

### 1.3 `generate_reddit_agent_graph`

```python
agent_graph = await generate_reddit_agent_graph(
    profile_path="./data/reddit/user_data_36.json",
    model=openai_model,           # single model, or list for load-balancing
    available_actions=available_actions,
)
```

### 1.4 `generate_twitter_agent_graph`

The Twitter variant accepts the same arguments but reads CSV profile files and accepts a **list of models** for distributed inference ([OASIS Twitter Interview cookbook](https://docs.oasis.camel-ai.org/cookbooks/twitter_interview)):

```python
from oasis import generate_twitter_agent_graph

models = [vllm_model_1, vllm_model_2]   # scheduling round-robins across list

agent_graph = await generate_twitter_agent_graph(
    profile_path="data/twitter_dataset/anonymous_topic_200_1h/False_Business_0.csv",
    model=models,
    available_actions=available_actions,
)
env = oasis.make(
    agent_graph=agent_graph,
    platform=oasis.DefaultPlatformType.TWITTER,
    database_path=db_path,
)
```

### 1.5 Environment Lifecycle

```python
await env.reset()           # registers all agents (SIGNUP actions), seeds initial state

# Timestep 1 — manual seeding
actions_t1 = {}
actions_t1[env.agent_graph.get_agent(0)] = [
    ManualAction(action_type=ActionType.CREATE_POST,
                 action_args={"content": "Narrative seed post"}),
]
await env.step(actions_t1)

# Timestep 2 — LLM-driven
actions_t2 = {
    agent: LLMAction()
    for _, agent in env.agent_graph.get_agents()
}
await env.step(actions_t2)

await env.close()           # flushes write-ahead log and closes DB connection
```

`env.step()` accepts a `dict[Agent, LLMAction | ManualAction | list[ManualAction]]`. Agents absent from the dict take no action that timestep.

### 1.6 `ActionType` Enum — Full Catalogue

([OASIS Actions docs](https://docs.oasis.camel-ai.org/key_modules/actions))

| ActionType | Description | Key `action_args` |
|---|---|---|
| `SIGNUP` | Register agent (auto, during `reset`) | `username`, `name`, `bio` |
| `CREATE_POST` | New post | `content: str` |
| `LIKE_POST` / `UNLIKE_POST` | Upvote / remove upvote | `post_id: int` |
| `DISLIKE_POST` / `UNDO_DISLIKE_POST` | Downvote / remove | `post_id: int` |
| `REPORT_POST` | Flag post | `post_id`, `report_reason` |
| `REPOST` | Retweet equivalent | `post_id: int` |
| `QUOTE_POST` | Retweet with comment | `post_id`, `quote_content` |
| `CREATE_COMMENT` | Comment on post | `post_id`, `content` |
| `LIKE_COMMENT` / `UNLIKE_COMMENT` | Comment vote | `comment_id: int` |
| `DISLIKE_COMMENT` / `UNDO_DISLIKE_COMMENT` | Comment downvote | `comment_id: int` |
| `FOLLOW` / `UNFOLLOW` | Social graph edge | `followee_id: int` |
| `MUTE` / `UNMUTE` | Hide without unfollow | `mutee_id: int` |
| `SEARCH_POSTS` | Keyword/post/user search | `query: str` |
| `SEARCH_USER` | User search | `query: str` |
| `TREND` | Fetch trending content | `{}` |
| `REFRESH` | Pull recommendation feed | `{}` |
| `DO_NOTHING` | No-op pass | `{}` |
| `PURCHASE_PRODUCT` | E-commerce extension | `product_name`, `purchase_num` |
| `INTERVIEW` | Researcher-initiated poll | `prompt: str` (manual only) |
| `CREATE_GROUP` / `JOIN_GROUP` / `LEAVE_GROUP` | Groups | `group_name` / `group_id` |
| `SEND_TO_GROUP` / `LISTEN_FROM_GROUP` | Group messaging | `group_id`, `message` |

**Critical**: `INTERVIEW` must **not** be included in `available_actions` — it is researcher-only and should always be issued as a `ManualAction`.

### 1.7 `LLMAction` and `ManualAction`

```python
@dataclass
class ManualAction:
    action_type: ActionType
    action_args: Dict[str, Any]
```

`LLMAction()` is an empty sentinel: the platform routes the agent's LLM to observe its feed, reason about the context in the system+user prompt (including agent profile and recent posts), and pick an action autonomously.

### 1.8 Profile JSON Format — Reddit (`user_data_36.json`)

Based on the generation script and paper ([OASIS GitHub](https://github.com/camel-ai/oasis)):

```json
[
  {
    "user_id": 1,
    "username": "alice_techie",
    "name": "Alice Johnson",
    "bio": "Software engineer, ML enthusiast, coffee addict.",
    "activity_level": 0.72,
    "interests": ["machine learning", "open source", "coffee"],
    "gender": "female",
    "age": 28,
    "location": "San Francisco, CA",
    "following": [2, 5, 9],
    "followers": [3, 7]
  },
  ...
]
```

**Required fields**: `user_id` (int), `username` (str), `name` (str), `bio` (str).

**Optional fields** (all used during simulation): `activity_level` (0–1 float, controls how often the Time Engine activates the agent), `interests` (list of strings, used by TwHIN-BERT for interest-based recommendations), `gender`, `age`, `location`, `following` (list of user_ids, pre-seeds the follow graph), `followers`.

**Twitter profile format**: CSV with columns `user_id`, `username`, `bio`, `following_count`, `followers_count`, and `posts` (recent posts JSON for seeding the recommendation context). The CSV path is passed directly to `generate_twitter_agent_graph`.

### 1.9 Recommendation Systems

([OASIS arXiv Appendix D](https://arxiv.org/html/2411.11581v4))

**Reddit hot-score** (default for `DefaultPlatformType.REDDIT`):

\[
h = \log_{10}\bigl(\max(|u - d|, 1)\bigr) + \operatorname{sign}(u-d) \cdot \frac{t - t_0}{45000}
\]

where \(u\) = upvotes, \(d\) = downvotes, \(t\) = Unix epoch submission time, \(t_0 = 1134028003\). Posts are ranked by \(h\); top-\(k\) are cached in the `rec` table.

**Twitter interest-based** (default for `DefaultPlatformType.TWITTER`):

\[
\text{Score} = R \cdot F \cdot S
\]

- \(R = \ln\!\left(\frac{271.8 - (t_\text{current} - t_\text{created})}{100}\right)\) — recency
- \(F = \max\!\left(1, \log_{1000}(\text{fan\_count}+1)\right)\) — creator reach
- \(S = \cos(E_p, E_u)\) — cosine similarity of TwHIN-BERT post embedding \(E_p\) to user profile embedding \(E_u\)

The recommendation system also supports **OpenAI embedding models** as a drop-in for TwHIN-BERT (added in a later release). Selection is implicit via the `platform` parameter to `oasis.make()`; there is no separate `rec_sys` parameter in the public API.

### 1.10 SQLite Output Schema

([OASIS arXiv Appendix D.2](https://arxiv.org/html/2411.11581v4))

The output `.db` file is a standard SQLite database. Six logical entity groups:

**`user`**
| Column | Type | Notes |
|---|---|---|
| `user_id` | INTEGER PK | |
| `agent_id` | INTEGER | Maps to in-memory agent object |
| `user_name` | TEXT | |
| `name` | TEXT | |
| `bio` | TEXT | |
| `created_at` | REAL | Unix timestamp |
| `num_followings` | INTEGER | Denormalized counter |
| `num_followers` | INTEGER | Denormalized counter |

**`post`**
| Column | Type |
|---|---|
| `post_id` | INTEGER PK |
| `user_id` | INTEGER FK→user |
| `content` | TEXT |
| `created_at` | REAL |
| `num_likes` | INTEGER |
| `num_dislikes` | INTEGER |

**`comment`** — `comment_id`, `post_id`, `user_id`, `content`, `created_at`

**`like`** — `like_id`, `user_id`, `post_id`, `created_at`

**`dislike`** — `dislike_id`, `user_id`, `post_id`, `created_at`

**`comment_like`** / **`comment_dislike`** — per-comment reaction tables with analogous columns

**`follow`** — `follower_id`, `followee_id`, `created_at`

**`mute`** — `muter_id`, `mutee_id`, `created_at`

**`trace`** — the most analytically rich table:
| Column | Type | Notes |
|---|---|---|
| `user_id` | INTEGER | |
| `created_at` | REAL | |
| `action` | TEXT | Enum name string |
| `info` | TEXT | JSON blob of action_args and result |

Every agent action is appended to `trace`, including `DO_NOTHING`. Useful for: reconstructing information cascades, computing action-sequence patterns, measuring temporal spread rates.

**`rec`** — `user_id`, `post_id` — recommendation cache populated at each timestep.

**Pandas pipeline example**:

```python
import sqlite3
import pandas as pd

con = sqlite3.connect("./data/reddit_simulation.db")
posts    = pd.read_sql("SELECT * FROM post ORDER BY created_at", con)
trace    = pd.read_sql("SELECT * FROM trace", con)
follows  = pd.read_sql("SELECT * FROM follow", con)
# Cascade depth: join trace on CREATE_COMMENT/REPOST to parent post
cascades = trace[trace["action"].isin(["CREATE_COMMENT","REPOST"])].copy()
```

### 1.11 Plugging in a Custom Local Model

OASIS uses CAMEL's `ModelFactory` internally. Replace the OpenAI model with any OpenAI-compatible endpoint ([CAMEL Models docs](https://docs.camel-ai.org/key_modules/models)):

```python
from camel.models import ModelFactory
from camel.types import ModelPlatformType

# Ollama
local_model = ModelFactory.create(
    model_platform=ModelPlatformType.OLLAMA,
    model_type="qwen2.5:14b",
    url="http://localhost:11434/v1",
    model_config_dict={"temperature": 0.6},
)

# mlx-lm server
mlx_model = ModelFactory.create(
    model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
    model_type="mlx-community/Qwen2.5-14B-Instruct-4bit",
    url="http://localhost:8080/v1",
    api_key="mlx",   # arbitrary non-empty string
    model_config_dict={"temperature": 0.6},
)

agent_graph = await generate_reddit_agent_graph(
    profile_path="./data/reddit/user_data_36.json",
    model=local_model,
    available_actions=available_actions,
)
```

For multi-server load-balancing (Twitter), pass a list:

```python
agent_graph = await generate_twitter_agent_graph(
    profile_path="...",
    model=[local_model_1, local_model_2],
    available_actions=available_actions,
)
```

### 1.12 Scaling Tips for 100–1000 Agent Runs

- **Async concurrency**: `env.step()` fires all LLM calls concurrently within the event loop. The bottleneck on a local model is GPU/ANE throughput, not Python.
- **Batch size**: Start with 36–200 agents (the bundled `user_data_36.json` is the reference). For 1000 agents, pre-generate profiles using the `generator/reddit/user_generate.py` script with GPT-4o-mini ($0.002/profile).
- **Available action pruning**: Reducing `available_actions` to 6–8 items shortens the prompt, cuts tokens, and speeds up inference ~20%.
- **Memory pressure**: With a 7B/4-bit model running on 16 GB unified memory, run no more than ~4 concurrent LLM requests. Use `asyncio.Semaphore` to cap concurrency.
- **Timestep granularity**: Each `env.step()` is one logical time unit. For Reddit hot-score recency, use the scale-factor time mapping so earlier actions in a timestep get lower timestamps.
- **SQLite WAL mode**: Enable `PRAGMA journal_mode=WAL;` on the database to allow concurrent reads during simulation.
- **Checkpoint frequency**: Call `await env.close()` only at the end; intermediate progress is flushed automatically.

---

## 2. CAMEL Workforce + Auto-Research

### 2.1 Workforce Class

([CAMEL Workforce docs](https://docs.camel-ai.org/key_modules/workforce))

```python
from camel.societies.workforce import Workforce

workforce = Workforce(
    description="Deep Research Team",
    coordinator_agent=coordinator,    # ChatAgent: assigns subtasks to workers
    task_agent=task_planner,          # ChatAgent: decomposes main task
    new_worker_agent=None,            # Template agent for dynamic worker spawning
    graceful_shutdown_timeout=15.0,
    task_timeout_seconds=120.0,
    share_memory=False,               # True → SingleAgentWorkers share memory store
    use_structured_output_handler=True,  # Enables non-native-JSON models
)
```

**Processing flow**:
1. `task_agent` breaks the `Task` into self-contained subtasks.
2. `coordinator_agent` assigns each subtask to the most suitable registered worker (by matching worker description to subtask).
3. Workers execute in parallel where dependency graph allows.
4. Results flow back; `coordinator_agent` composes the final answer.

```python
from camel.tasks import Task

result = workforce.process_task(
    Task(content="Research and summarize the effect of AI on labor markets.")
)
print(result.result)
```

### 2.2 Adding Workers

```python
from camel.agents import ChatAgent
from camel.toolkits import SearchToolkit, BrowserToolkit, CodeExecutionToolkit

# Search worker
search_agent = ChatAgent(
    system_message="You search the web and retrieve relevant information.",
    tools=SearchToolkit().get_tools(),
    model=coordinator_model,
)
workforce.add_single_agent_worker(
    description="Searches the web for factual information and news",
    worker=search_agent,
)

# Analyst worker (code execution)
analyst_agent = ChatAgent(
    system_message="You analyze data and write Python analysis code.",
    tools=CodeExecutionToolkit(sandbox="subprocess").get_tools(),
    model=analyst_model,
)
workforce.add_single_agent_worker(
    description="Runs Python code for data analysis and statistical computation",
    worker=analyst_agent,
)

# Role-playing worker (debate / adversarial review)
workforce.add_role_playing_worker(
    description="Critically reviews and stress-tests research findings",
    assistant_role_name="Devil's Advocate",
    user_role_name="Research Lead",
    assistant_agent_kwargs=dict(
        system_message="Challenge every claim with counter-evidence."
    ),
    user_agent_kwargs=dict(
        system_message="Defend the research findings rigorously."
    ),
    chat_turn_limit=5,
)
```

### 2.3 Auto-Research Pipeline Pattern

A four-stage planner → search → analyst → writer pattern:

```python
from camel.models import ModelFactory
from camel.types import ModelPlatformType, ModelType
from camel.agents import ChatAgent
from camel.societies.workforce import Workforce
from camel.toolkits import SearchToolkit, BrowserToolkit, FileWriteToolkit

# Heavy coordinator → use cloud model for planning quality
coordinator_model = ModelFactory.create(
    model_platform=ModelPlatformType.ANTHROPIC,
    model_type=ModelType.CLAUDE_SONNET_4_5,
)
# Bulk workers → local model
local_model = ModelFactory.create(
    model_platform=ModelPlatformType.OLLAMA,
    model_type="qwen2.5:14b",
    url="http://localhost:11434/v1",
)

workforce = Workforce(
    description="Automated research and report generation",
    coordinator_agent=ChatAgent(
        system_message="Decompose research tasks and assign them optimally.",
        model=coordinator_model,
    ),
    task_agent=ChatAgent(
        system_message="Break complex research goals into concrete subtasks.",
        model=coordinator_model,
    ),
)

# Stage 1 — Searcher
workforce.add_single_agent_worker(
    description="Searches and retrieves web sources, articles, and papers",
    worker=ChatAgent(
        tools=SearchToolkit().get_tools(),
        model=local_model,
    ),
)
# Stage 2 — Browser / content extractor
workforce.add_single_agent_worker(
    description="Reads and extracts content from specific URLs",
    worker=ChatAgent(
        tools=BrowserToolkit().get_tools(),
        model=local_model,
    ),
)
# Stage 3 — Analyst
workforce.add_single_agent_worker(
    description="Synthesizes sources, runs statistical analysis, checks consistency",
    worker=ChatAgent(
        tools=CodeExecutionToolkit(sandbox="subprocess").get_tools(),
        model=local_model,
    ),
)
# Stage 4 — Writer
workforce.add_single_agent_worker(
    description="Writes structured Markdown research reports and saves to file",
    worker=ChatAgent(
        tools=FileWriteToolkit().get_tools(),
        model=coordinator_model,   # writing quality benefits from stronger model
    ),
)

result = workforce.process_task(Task(content="..."))
```

### 2.4 OWL vs Plain Workforce

[OWL (Optimized Workforce Learning)](https://github.com/camel-ai/owl) is a **research framework built on top of CAMEL Workforce** ([OWL arXiv](https://arxiv.org/abs/2505.23885)). The paper architecture introduces the same Planner / Coordinator / Worker triad as CAMEL Workforce, plus an RL training loop (OWL) that optimizes a domain-agnostic 32B planner using real-world feedback, achieving 69.7% on GAIA benchmark and outperforming OpenAI Deep Research (+2.34%).

**When to use OWL repo**: If you want OWL's pre-tuned benchmark-optimized prompts, the bundled enhanced toolkits (browser automation, multimodal document parsing), and the GAIA evaluation harness. The OWL repo ships a customized fork of CAMEL in `owl/camel/` with patches for benchmark stability.

**When to use plain Workforce**: For production simulation pipelines where you control the model selection, want minimal dependencies, and need tight integration with OASIS (which uses the same CAMEL `ChatAgent` internally). Plain Workforce is more stable for custom tool injection and per-agent model assignment. **Recommended** for this use case.

---

## 3. Mathematical Models for OASIS Simulation Output

### 3.1a Information / Narrative Spread

#### SIR / SEIR Compartmental Models

Fit to cumulative-engagement time series (total likes + reposts vs. timestep).

**Continuous ODE form** (SIR):

\[
\frac{dS}{dt} = -\beta SI, \quad
\frac{dI}{dt} = \beta SI - \gamma I, \quad
\frac{dR}{dt} = \gamma I
\]

where \(S\) = susceptible (not yet engaged), \(I\) = infected (actively spreading), \(R\) = recovered (saw content, disengaged). \(\beta\) = transmission rate, \(\gamma\) = recovery rate. Fit \(\beta, \gamma\) via nonlinear least squares to cumulative engagement curve from `post` + `like` + `comment` tables.

**SEIR** adds an exposed compartment \(E\) (agent saw content but hasn't acted):

\[
\frac{dE}{dt} = \beta SI - \sigma E, \quad
\frac{dI}{dt} = \sigma E - \gamma I
\]

\(\sigma\) = rate of transition from exposed to infectious.

**Discrete stochastic form** (suitable for small networks):

At each timestep, for each \(S\)–\(I\) pair connected by a follow edge, \(S \to I\) with probability \(\beta\); each \(I\) node \(\to R\) with probability \(\gamma\). Extract the adjacency from the `follow` table and engagement from `trace`.

```python
import networkx as nx
import pandas as pd
import sqlite3
from scipy.integrate import odeint
from scipy.optimize import curve_fit
import numpy as np

con = sqlite3.connect("./data/simulation.db")
trace = pd.read_sql("SELECT * FROM trace ORDER BY created_at", con)
likes = trace[trace["action"] == "LIKE_POST"]
cum_likes = likes.groupby(pd.cut(likes["created_at"], bins=50)).size().cumsum().values

def sir_ode(y, t, beta, gamma):
    S, I, R = y
    N = S + I + R
    return [-beta*S*I/N, beta*S*I/N - gamma*I, gamma*I]

# Fit with curve_fit around numerical ODE solution
```

#### Independent Cascade (IC) and Linear Threshold (LT) Models

**IC**: Each activated node \(u\) makes one attempt to activate each neighbor \(v\) with probability \(p_{uv}\) (set to `num_likes_post / max_likes` or learned from `trace`). Propagates in discrete rounds.

**LT**: Node \(v\) activates when \(\sum_{u \in \text{active neighbors}} w_{uv} \geq \theta_v\), where \(\theta_v\) is drawn uniformly from \([0,1]\) and \(w_{uv}\) is the normalized influence weight.

Both models operate on the NetworkX graph built from `follow`:

```python
follows = pd.read_sql("SELECT * FROM follow", con)
G = nx.from_pandas_edgelist(follows, "follower_id", "followee_id", create_using=nx.DiGraph())
# IC simulation: networkx has no built-in; use ndlib or implement directly
```

Use [`ndlib`](https://ndlib.readthedocs.io/) for IC/LT/SIR on NetworkX graphs.

#### Hawkes Self-Exciting Point Process

Models retweet/comment cascades where each event raises the probability of future events.

**Conditional intensity** ([tick library](https://x-datainitiative.github.io/tick/modules/hawkes.html)):

\[
\lambda^*(t) = \mu + \sum_{t_i < t} \phi(t - t_i)
\]

where \(\mu\) is the background rate, and \(\phi(t) = \alpha e^{-\beta t}\) is the exponential kernel (self-excitation). Each comment or repost event at \(t_i\) contributes a decaying intensity boost.

**Python libraries**:
- [`tick`](https://x-datainitiative.github.io/tick/modules/hawkes.html): `tick.hawkes.HawkesExpKern`, fits \(\mu, \alpha, \beta\) via maximum likelihood. Supports multivariate Hawkes for cross-topic spillover.
- [`PyHawkes`](https://github.com/slinderman/pyhawkes): Bayesian network Hawkes process; estimates latent connectivity between agent clusters.
- [`stmorse/hawkes`](https://github.com/stmorse/hawkes): Lightweight `MHP` class for univariate/multivariate Hawkes; `P.EM(ahat, mhat, w)` for EM-based parameter estimation.

```python
# tick example
from tick.hawkes import HawkesExpKern
# Extract comment timestamps for a specific post
post_events = trace[trace["action"] == "CREATE_COMMENT"].copy()
timestamps = [post_events["created_at"].values]   # list of arrays

learner = HawkesExpKern(decays=1.0)
learner.fit(timestamps)
print(learner.baseline, learner.adjacency)  # mu, alpha
```

#### Bass Diffusion Model

Simpler alternative for aggregate adoption with no network structure:

\[
\frac{dN}{dt} = \left(p + q \frac{N(t)}{M}\right)\bigl(M - N(t)\bigr)
\]

\(p\) = coefficient of innovation (external influence), \(q\) = coefficient of imitation (peer pressure), \(M\) = total potential adopters. Fit to cumulative engagement curve using `scipy.optimize.curve_fit`. Works well when the OASIS network is dense or recommendation-driven (hot-score flattens network effects).

---

### 3.1b Market / Opinion Dynamics

#### Deffuant–Weisbuch Bounded-Confidence Model

([arXiv bounded-confidence DW](https://arxiv.org/html/2605.20418v2))

Agents \(i, j\) are chosen at random. If \(|x_i(t) - x_j(t)| < c\):

\[
x_i(t+1) = x_i(t) + \mu \bigl(x_j(t) - x_i(t)\bigr)
\]
\[
x_j(t+1) = x_j(t) + \mu \bigl(x_i(t) - x_j(t)\bigr)
\]

Otherwise opinions are unchanged. Parameters: \(c \in [0,1]\) (confidence bound), \(\mu \in (0, 0.5]\) (compromise rate). In OASIS context, initialize \(x_i\) from sentiment of each agent's posts (VADER/TextBlob on `post.content` and `trace.info`), run DW on the OASIS follower graph, compare to empirical opinion shift.

#### Hegselmann–Krause (HK) Model

Simultaneous update: each agent averages all opinions within distance \(\varepsilon\):

\[
x_i(t+1) = \frac{1}{|I(i, x(t))|} \sum_{j \in I(i,x(t))} x_j(t)
\]

where \(I(i, x(t)) = \{j : |x_j(t) - x_i(t)| \leq \varepsilon\}\). Converges to opinion clusters; cluster count is a proxy for polarization.

#### DeGroot Consensus

Linear update: \(\mathbf{x}(t+1) = W \mathbf{x}(t)\) where \(W\) is a row-stochastic influence matrix built from the OASIS `follow` table (normalize rows). Converges to consensus if \(W\) is primitive. Useful as a baseline.

#### Friedkin–Johnsen Model

Adds stubbornness \(s_i \in [0,1]\) — each agent is anchored to their initial opinion:

\[
x_i(t+1) = (1 - s_i) \sum_j T_{ij} x_j(t) + s_i x_i(0)
\]

([Friedkin-Johnsen model](https://rf.mokslasplius.lt/friedkin-johnsen-model/)). Reaches stable disagreement rather than consensus. Set \(s_i\) from agent profile `stubbornness` field or infer from low `FOLLOW`/`LIKE` rate in `trace`.

#### Voter Model

At each step, each agent copies the opinion of a random neighbor. Absorbs into consensus in finite time on finite graphs. The **noisy voter model** adds a mutation rate \(\eta\): with probability \(\eta\), adopt a random opinion. Steady-state polarization \(\propto 1/\eta\).

#### Polarization Metrics

```python
import numpy as np
from scipy.stats import kurtosis

# x = array of agent opinion scores at final timestep
bimodality_coeff = (kurtosis(x, fisher=False) + 3) / (
    (kurtosis(x, fisher=False) + 3) + 3 * ((len(x)-1)**2 / ((len(x)-2)*(len(x)-3)))
)  # BC > 0.555 indicates bimodal distribution

# Polarization index (variance of opinions normalized by max)
polarization_idx = np.var(x) / 0.25   # max variance of [0,1] bounded opinions = 0.25

# Graph modularity (community structure)
import networkx as nx
communities = nx.community.greedy_modularity_communities(G.to_undirected())
modularity = nx.community.modularity(G.to_undirected(), communities)
```

---

### 3.1c Marketing / A/B Scenario Testing

#### Bayesian A/B Testing — Beta-Binomial Conjugate

Prior: \(\theta \sim \text{Beta}(\alpha_0, \beta_0)\), typically \(\alpha_0=\beta_0=1\) (uniform).

After observing \(k\) conversions in \(n\) trials:

\[
\theta | \text{data} \sim \text{Beta}(\alpha_0 + k,\; \beta_0 + n - k)
\]

**Expected Loss decision rule** (Stucchio / VWO framework): ship variant \(B\) when:

\[
\mathcal{L}(B) = \mathbb{E}\bigl[\max(\theta_A - \theta_B, 0)\bigr] < \epsilon_\text{threshold}
\]

where expectation is over posterior samples. Monte-Carlo estimate:

```python
import numpy as np
from scipy.stats import beta

def expected_loss(alpha_a, beta_a, alpha_b, beta_b, n_samples=100_000):
    samples_a = beta.rvs(alpha_a, beta_a, size=n_samples)
    samples_b = beta.rvs(alpha_b, beta_b, size=n_samples)
    loss_a = np.mean(np.maximum(samples_b - samples_a, 0))  # cost of shipping A
    loss_b = np.mean(np.maximum(samples_a - samples_b, 0))  # cost of shipping B
    return loss_a, loss_b
```

Ship the variant with lower expected loss once `min(loss_a, loss_b) < 0.01`.

#### Causal Uplift Modeling — Meta-Learners

([EconML metalearners docs](https://www.pywhy.org/EconML/spec/estimation/metalearners.html))

Map OASIS "treatment" to exposure to a seeded narrative (agents in the exposed group saw `ManualAction CREATE_POST` of the seed post in their recommendation feed).

```python
from econml.metalearners import TLearner, SLearner, XLearner
from econml.dr import DRLearner
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier

# Features: agent profile attributes (age, interests encoded, activity_level)
# Outcome Y: total engagement (likes + comments) after k timesteps
# Treatment T: 1 if agent was seeded with narrative, 0 otherwise

T_est = TLearner(models=GradientBoostingRegressor())
T_est.fit(Y, T, X=X_features)
cate_t = T_est.effect(X_features)

X_est = XLearner(
    models=GradientBoostingRegressor(),
    propensity_model=GradientBoostingClassifier(),
)
X_est.fit(Y, T, X=X_features)
cate_x = X_est.effect(X_features)

# DR-Learner: doubly robust, most robust to model misspecification
dr_est = DRLearner(
    model_regression=GradientBoostingRegressor(),
    model_propensity=GradientBoostingClassifier(),
    model_final=GradientBoostingRegressor(),
)
dr_est.fit(Y, T, X=X_features)
cate_dr = dr_est.effect(X_features)
```

`pip install econml`

#### Difference-in-Differences (DiD) and Synthetic Control

For simulated counterfactuals: run two OASIS simulations with identical seeds except for the "treatment" (e.g., a seed post in one run). Extract engagement by agent group over time. Apply DiD:

\[
\hat{\tau}^\text{DiD} = (\bar{Y}^\text{treat}_\text{post} - \bar{Y}^\text{treat}_\text{pre}) - (\bar{Y}^\text{control}_\text{post} - \bar{Y}^\text{control}_\text{pre})
\]

For synthetic control, use `pysyncon` or `SparseSC`:

```bash
pip install pysyncon
```

#### Multi-Armed Bandit — Thompson Sampling

Adaptive scenario allocation across multiple seed narratives:

```python
import numpy as np

class ThompsonBandit:
    def __init__(self, n_arms):
        self.alpha = np.ones(n_arms)  # prior successes + 1
        self.beta  = np.ones(n_arms)  # prior failures + 1

    def select(self):
        return np.argmax(np.random.beta(self.alpha, self.beta))

    def update(self, arm, reward):  # reward ∈ {0, 1}
        self.alpha[arm] += reward
        self.beta[arm]  += 1 - reward

bandit = ThompsonBandit(n_arms=5)  # 5 narrative variants
for episode in range(num_timesteps):
    arm = bandit.select()
    # Run OASIS timestep with seed narrative = arm
    # Measure engagement (0/1 or normalize to [0,1])
    bandit.update(arm, reward)
```

---

## 4. Hybrid Inference on Apple M4

### 4.1 MLX Framework — Model Sizing Guide

MLX uses **unified memory** (CPU + GPU share the same pool). The entire model must fit; exceeding RAM causes thrashing. ([Apple Silicon MLX inference optimization](https://branch8.com/posts/apple-silicon-mlx-llm-inference-optimization-tutorial))

Rule of thumb: 4-bit quantized model ≈ 0.5 GB per billion parameters; 8-bit ≈ 1 GB/B.

| Unified RAM | Usable for LLM (leave ~4 GB for OS) | 4-bit models that fit |
|---|---|---|
| 16 GB | ~12 GB | 7B–8B (e.g., Qwen2.5-7B, Llama-3.2-8B) |
| 24 GB | ~20 GB | Up to 14B–16B (Qwen2.5-14B, Gemma-3-12B) |
| 36 GB | ~32 GB | Up to 32B (Qwen3-32B, Llama-3.3-30B) |
| 48 GB | ~44 GB | Up to 32B at 8-bit; Qwen3-30B-A3B MoE |
| 64 GB | ~60 GB | Up to 70B at 4-bit (Llama-3.3-70B) |

**Recommended quantizations** ([branch8.com benchmark](https://branch8.com/posts/apple-silicon-mlx-llm-inference-optimization-tutorial)):
- **4-bit, group-size 64**: Best speed-to-quality for agent bulk inference. Retains ~97.3% of full-precision MMLU score at 3.8× memory reduction.
- **8-bit, group-size 32**: Near-lossless; use for the Workforce coordinator/planner where reasoning quality matters.
- Avoid 3-bit: noticeable degradation on multi-step reasoning.

### 4.2 `mlx_lm.server` — OpenAI-Compatible Endpoint

([mlx-lm SERVER.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md))

```bash
# Install
pip install mlx-lm

# Serve (starts on localhost:8080)
mlx_lm.server --model mlx-community/Qwen2.5-14B-Instruct-4bit

# Quantize from HuggingFace first if needed
python -m mlx_lm.convert \
  --hf-path Qwen/Qwen2.5-14B-Instruct \
  --mlx-path ./models/qwen2.5-14b-4bit \
  --quantize --q-bits 4 --q-group-size 64
```

**Supported endpoints**: `POST /v1/chat/completions`, `GET /v1/models`. Accepts `messages`, `temperature`, `top_p`, `max_tokens`, `stream`, `stop`, `repetition_penalty`, `logit_bias`, `draft_model` (speculative decoding).

**Connect from CAMEL**:

```python
mlx_model = ModelFactory.create(
    model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
    model_type="mlx-community/Qwen2.5-14B-Instruct-4bit",
    url="http://localhost:8080/v1",
    api_key="mlx",
    model_config_dict={"temperature": 0.7, "max_tokens": 512},
)
```

**Performance**: ~38 tokens/s on M4 Max (4-bit 8B); ~18 tokens/s on M4 Pro 24GB (4-bit 8B) ([Reddit Ollama M4 benchmark](https://www.reddit.com/r/ollama/comments/1j0by7r/tested_local_llms_on_a_maxed_out_m4_macbook_pro/)).

### 4.3 Ollama on M4

Ollama exposes an OpenAI-compatible endpoint at `http://localhost:11434/v1`.

```bash
# Install: https://ollama.com/download
brew install ollama

# Pull model
ollama pull qwen2.5:14b       # ~9 GB (4-bit GGUF)
ollama pull qwen3:14b         # ~9 GB
ollama pull llama3.3:latest   # ~43 GB — needs 48 GB+ RAM

# Serve (background, auto-starts on install)
ollama serve
```

CAMEL integration ([CAMEL Models docs](https://docs.camel-ai.org/key_modules/models)):

```python
ollama_model = ModelFactory.create(
    model_platform=ModelPlatformType.OLLAMA,
    model_type="qwen2.5:14b",
    url="http://localhost:11434/v1",
    model_config_dict={"temperature": 0.6},
)
```

Ollama uses GGUF format by default (llama.cpp backend), which may be marginally slower than MLX for long-generation tasks on Apple Silicon but supports more quantization variants (`Q4_K_M`, `Q6_K`, `Q8_0`).

### 4.4 LM Studio

[LM Studio](https://lmstudio.ai/) provides a GUI for model management and exposes `http://localhost:1234/v1`. Supports both MLX and GGUF. Connect via `ModelPlatformType.OPENAI_COMPATIBLE_MODEL` with `url="http://localhost:1234/v1"`. Best for non-engineer team members who need a GUI. For programmatic simulation pipelines, prefer Ollama or mlx-lm.server for headless operation.

### 4.5 Recommended Models (2025–2026) for Agent Simulation

| Model | Size | Tool Use | Rationale |
|---|---|---|---|
| **Qwen2.5-14B-Instruct** (4-bit) | ~9 GB | ★★★★★ | Best-in-class tool calling at <14B; fits 16 GB; fast on M4; CAMEL officially tested on Qwen2 |
| **Qwen3-14B** (4-bit) | ~9 GB | ★★★★★ | Successor with thinking mode; stronger multi-step reasoning; 119-language support; officially recommends MLX, Ollama ([Qwen3 blog](https://qwenlm.github.io/blog/qwen3/)) |
| **Llama-3.3-8B-Instruct** (4-bit) | ~5 GB | ★★★★ | Smallest reliable tool-caller; fits any M4; good baseline for 1000-agent OASIS runs where throughput > quality |

For the **Workforce coordinator/planner** running cloud-side: Claude Sonnet 4.5 or GPT-4o — their structured output and multi-step reasoning quality justifies the API cost at low call volume.

### 4.6 Hybrid Pattern — Per-Agent Model Assignment

Assign cheap local models to OASIS simulation agents and a premium cloud model to the Workforce coordinator ([CAMEL Workforce docs — Worker with Specific Model](https://docs.camel-ai.org/key_modules/workforce)):

```python
from camel.models import ModelFactory
from camel.types import ModelPlatformType, ModelType

# Bulk simulation agents — local 14B on M4
bulk_model = ModelFactory.create(
    model_platform=ModelPlatformType.OLLAMA,
    model_type="qwen2.5:14b",
    url="http://localhost:11434/v1",
    model_config_dict={"temperature": 0.7},
)

# Research Workforce coordinator — Claude via API
coordinator_model = ModelFactory.create(
    model_platform=ModelPlatformType.ANTHROPIC,
    model_type=ModelType.CLAUDE_SONNET_4_5,
)

# Writer — Claude (structured output quality matters)
writer_model = coordinator_model

# OASIS simulation uses bulk_model
agent_graph = await generate_reddit_agent_graph(
    profile_path="./data/reddit/user_data_36.json",
    model=bulk_model,
    available_actions=available_actions,
)

# CAMEL Workforce uses premium model for planner + writer
workforce = Workforce(
    description="Post-simulation research analyst",
    coordinator_agent=ChatAgent(model=coordinator_model, ...),
    task_agent=ChatAgent(model=coordinator_model, ...),
)
workforce.add_single_agent_worker(
    description="Runs statistical analysis on OASIS SQLite output",
    worker=ChatAgent(model=bulk_model, tools=CodeExecutionToolkit().get_tools()),
)
workforce.add_single_agent_worker(
    description="Writes final research report with citations",
    worker=ChatAgent(model=writer_model, tools=FileWriteToolkit().get_tools()),
)
```

This pattern routes ~95% of token volume (OASIS agents) through the local model at $0 marginal cost, while keeping Workforce planning (low-volume, high-complexity) on Claude.

---

## 5. Reproducibility and Experiment Management

### 5.1 Seeding LLM-Driven Simulations

LLM responses are non-deterministic even at `temperature=0` due to floating-point non-determinism in GPU operations. Practical reproducibility strategy:

1. **Seed the agent graph construction**: set `random.seed(42)` and `numpy.random.seed(42)` before `generate_reddit_agent_graph()` to fix profile loading order and initial follow graph.
2. **Fix `temperature=0`** for agents (eliminates sampling randomness; does not eliminate hardware/ordering non-determinism).
3. **Record all LLM outputs**: the `trace.info` JSON field captures each agent's reasoning and action. Replay mode can reconstruct a simulation from a `trace` dump without re-querying the LLM.
4. **Hash the profile file**: include `sha256(user_data_*.json)` in your run metadata.
5. **Accept stochastic variation**: for statistical conclusions, run 5–10 independent seeds and report mean ± std across seeds rather than single-run results.

### 5.2 DVC + MLflow Integration

Use DVC for data versioning (profile JSONs, output `.db` files) and MLflow for run metadata and metrics.

```bash
pip install dvc mlflow

# Initialize
dvc init && git init
dvc add data/reddit/user_data_1000.json
git add data/reddit/user_data_1000.json.dvc .gitignore
git commit -m "Add agent profiles v1"
dvc remote add -d storage s3://my-bucket/oasis-data  # or local
```

```python
import mlflow
import dvc.api

data_url = dvc.api.get_url(path="data/reddit/user_data_1000.json", rev="v1")

mlflow.set_experiment("oasis-narrative-spread")
with mlflow.start_run(run_name="reddit-100agents-seed42"):
    mlflow.log_params({
        "n_agents": 100,
        "n_timesteps": 20,
        "model": "qwen2.5:14b",
        "seed": 42,
        "data_version": "v1",
        "data_url": data_url,
    })
    # ... run simulation ...
    mlflow.log_metrics({
        "final_cascade_size": cascade_size,
        "peak_active_agents": peak_active,
        "polarization_index": pol_idx,
        "modularity": modularity,
    })
    mlflow.log_artifact("./data/reddit_simulation.db")
```

Weights & Biases is an alternative:

```python
import wandb
wandb.init(project="oasis-sim", config={...})
wandb.log({"cascade_size": v, "step": t})
wandb.finish()
```

### 5.3 SQLite → Pandas/Polars Analysis Pipeline

```python
import sqlite3
import pandas as pd
import polars as pl  # pip install polars — faster for 100k+ rows

con = sqlite3.connect("./data/reddit_simulation.db")

# Polars for large datasets
posts   = pl.read_database("SELECT * FROM post", con)
trace   = pl.read_database("SELECT * FROM trace", con)
follows = pl.read_database("SELECT * FROM follow", con)

# Cascade reconstruction
reposts = trace.filter(pl.col("action").is_in(["REPOST", "CREATE_COMMENT"]))
cascade_sizes = (
    reposts
    .join(posts.select(["post_id","user_id","created_at"]), on=...)
    .group_by("post_id")
    .agg(pl.count("user_id").alias("cascade_depth"))
    .sort("cascade_depth", descending=True)
)

# Time series of engagement
engagement_ts = (
    trace
    .filter(pl.col("action").is_in(["LIKE_POST","CREATE_COMMENT","REPOST"]))
    .group_by_dynamic("created_at", every="1i")   # 1 simulation step
    .agg(pl.count().alias("events"))
)
```

For `.db` files >1 GB, consider exporting to Parquet:

```python
# pandas
df = pd.read_sql("SELECT * FROM trace", con)
df.to_parquet("trace.parquet", index=False)
```

---

## Appendix: Quick Reference

### OASIS `oasis.make()` full signature

```python
env = oasis.make(
    agent_graph: AgentGraph,
    platform: DefaultPlatformType,       # REDDIT | TWITTER
    database_path: str,
)
```

### CAMEL `ModelFactory.create()` full signature

```python
model = ModelFactory.create(
    model_platform: ModelPlatformType,
    model_type: str | ModelType,
    url: str | None = None,              # for local / compatible endpoints
    api_key: str | None = None,
    model_config_dict: dict | None = None,
)
```

### M4 Model Fit Quick Reference

| M4 Model | RAM | Recommended OASIS model |
|---|---|---|
| MacBook Air M4 | 16 GB | Qwen2.5-7B-4bit or Llama-3.2-8B-4bit |
| MacBook Pro M4 Pro | 24 GB | Qwen2.5-14B-4bit or Qwen3-14B-4bit |
| MacBook Pro M4 Max | 36–48 GB | Qwen3-32B-4bit or Qwen2.5-32B-4bit |
| MacBook Pro M4 Max | 64 GB | Llama-3.3-70B-4bit |

---

*Sources compiled 2025–2026. All code is illustrative; pin versions in production.*
