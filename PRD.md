How can I design a multi step deep research agent using multiple deep research apis and synthesis agents?
Completed 10 steps
Now I have comprehensive material to write a thorough response. Let me compile this into a detailed answer.

Here's a comprehensive guide to designing a multi-step deep research agent that federates across multiple deep research APIs and uses specialized synthesis agents. Given your background with MCP, Mastra, and TypeScript-native stacks, I'll frame this at a systems-architect level.

Why Multi-Step, Multi-Source
A single-API, single-step research call is essentially augmented RAG — it fetches once, summarizes, and stops. Deep research requires something fundamentally different: adaptive, iterative exploration where each discovery shapes the next query. Anthropic's internal evaluation shows that a multi-agent research system outperformed a single Claude Opus 4 agent by 90.2% on breadth-first research tasks, and that token usage alone explains 80% of performance variance on hard research benchmarks. Together AI's Open Deep Research similarly found that multi-step search significantly improves accuracy over one-shot retrieval on multi-hop questions.

The Four-Layer Architecture
The most production-proven pattern, validated across Anthropic, OpenAI, mcp-agent, and GPT Researcher, is a layered stack:

Layer 1 — Query Intelligence (Triage & Enrichment)
Before any API call, a lightweight "pre-flight" tier processes the raw query:

Triage Agent — classifies query complexity (simple fact vs. comparative vs. deep research), decides if clarification is needed, and routes accordingly

Clarification Agent — asks 2–3 structured follow-up questions to elicit scope, audience, and output format before committing to expensive API calls

Instruction Builder Agent — rewrites the clarified query into a precise research brief: explicit tables requested, language, source priorities, structured output format

The OpenAI cookbook's four-agent pipeline (triage → clarify → instruction_builder → research) is a well-tested scaffold for this tier. Critically, using a cheap/fast model (e.g., gpt-4o-mini) here and reserving the large reasoning model for actual research reduces cost by 60–70%.

Layer 2 — Orchestrated Fan-Out (Parallel Research APIs)
This is where the multi-source federation happens. The orchestrator decomposes the research brief into parallel sub-queries and fans them out across heterogeneous APIs simultaneously:

API	Strengths	Best for
OpenAI o3-deep-research	Multi-hop reasoning, long-form synthesis	Complex analytical questions 
Perplexity Sonar	Real-time web with citations baked in	News, current events, market data 
Exa	Semantic/neural search, finding similar content	Research papers, niche documents 
Tavily	Fast, relevance-scored results, freshness	Broad surveys, agentic RAG pipelines 
Firecrawl / Jina	Deep single-URL extraction	Digging into a specific document or page 
Anthropic's research system found that spinning up 3–5 subagents in parallel cut research time by up to 90% for complex queries versus sequential execution. Each subagent needs an explicit objective, output format, tool constraints, and non-overlapping task boundaries — without this, subagents duplicate searches, as Anthropic found when two agents independently investigated the same supply-chain period.

Fan-out pattern in pseudocode (TypeScript/Mastra):

typescript
const subQueries = await planner.decompose(researchBrief, { maxSubAgents: 5 });

const results = await Promise.all(
  subQueries.map(sq => researchWorker.run({
    query: sq.query,
    apiPriority: sq.domain,  // e.g. "academic" → Exa, "news" → Perplexity
    maxSearches: sq.complexity === "deep" ? 15 : 5,
  }))
);
Layer 3 — Synthesis Agents (Merge, Deduplicate, Conflict-Resolve)
Raw fan-out results need three synthesis passes before they're trustworthy:

3a. Source Aggregator / Deduplicator
Performs semantic deduplication across API results — the same fact sourced from Perplexity, Tavily, and Exa produces three entries but one finding. Use an embedding-based similarity threshold (cosine > 0.92) or an LLM judge pass to collapse duplicates while preserving citation provenance.

3b. Conflict Resolution Agent
When sub-agents return contradictory findings (e.g., different revenue figures for the same company), a specialized critic agent should:

Identify the conflict explicitly ("Source A says X, Source B says Y")

Apply provenance-weighted trust (primary source > aggregator > blog)

Either flag for human review or adjudicate based on date recency and source authority

The "Team of Rivals" architecture formalizes this: rather than majority voting, use hierarchical veto authority where a critic can reject an output entirely and trigger a retry loop. This outperforms consensus voting for correctness in high-stakes domains.

3c. Synthesis / Report Writer Agent
A strong long-context model (e.g., Claude Opus 4, Gemini 2.5 Flash, or DeepSeek-V3) receives the deduplicated, conflict-resolved findings and writes the final artifact. The Together AI Open Deep Research assigns a dedicated "report writer" role specifically because the synthesis task requires a different capability profile than retrieval.

Layer 4 — Evaluation & Reflection
This layer closes the loop with a self-reflection step that determines whether to continue researching or finalize:

Gap Detector — after synthesis, an LLM evaluates whether any knowledge gaps remain (unanswered sub-questions, low-confidence claims). Inspired by Self-Reflection techniques

Quality Judge — LLM-as-judge scores the draft on: factual accuracy, citation accuracy, completeness, and source quality (primary vs. SEO farm)

Replan Trigger — if the gap detector or quality judge fail, the orchestrator re-enters the fan-out layer with new queries targeting the gaps

Anthropic found that a simple plan → execute → verify → replan loop outperformed complex adaptive workflows with external memory and mode-switching. The mcp-agent creator confirmed the same: 3 iterations of "simpler architecture wins" over increasingly complex orchestration.

State Management & Resilience
Agents are stateful and errors compound — a single tool failure mid-run can derail an entire research session if not handled properly.

Key patterns:

Checkpointing — Serialize the entire agent state (context, progress, accumulated findings) at each phase boundary. LangGraph's built-in checkpointer or Mastra's workflow persistence enables resuming from the exact failure point rather than restarting

External memory / knowledge bank — Subagent results should write to a shared external store (filesystem artifact or vector DB), passing only lightweight references to the orchestrator. This prevents the "game of telephone" where long outputs get garbled through the coordinator

Budget tracking — Track tokens, time, and API cost per sub-agent. Implement a "beast mode" fallback that generates the best possible answer from accumulated knowledge if budget is exhausted

Deterministic plan verification — Before executing LLM-generated plans, run code-based validation: check that referenced MCP servers exist, task dependency graph is acyclic, agents are available. A bad plan caught deterministically is far cheaper than a failed execution

Prompt Engineering That Actually Matters
These aren't cosmetic — they're the difference between an agent that works and one that spirals:

XML-tagged modular prompts — Use <objective>, <task_boundaries>, <output_format>, <tools> sections. Reduces hallucinations and clearly scopes each agent's responsibility

Explicit effort scaling — Embed rules like "simple fact: 1 agent, 3–10 searches; comparative: 2–4 agents, 10–15 each; deep research: 5+ agents with divided responsibilities"

Start broad, then narrow — Prompt subagents to begin with short, broad queries before drilling down. Agents naturally default to overly-specific queries that return zero results

Extended thinking / interleaved reasoning — Use Claude's extended thinking mode as a scratchpad for the orchestrator to plan subagent assignments, and interleaved thinking for subagents to evaluate result quality before issuing the next search

TypeScript-Native Implementation Stack
Given your Mastra + MCP stack:

Orchestration: Mastra workflows with .branch() for conditional routing between research depth tiers; handles the step-based flow without needing graph theory semantics

MCP servers: Wrap each research API (Tavily, Perplexity, Exa, OpenAI deep research) as individual MCP servers — the Deep Orchestrator in mcp-agent proves this is sufficient without needing specialized research tooling

State: Use Mastra's built-in persistence or SurrealDB (given your familiarity) for cross-session memory and checkpoint storage

Model routing: Use a fast model (gpt-4o-mini, claude-haiku) for triage/clarification, a mid-tier model for summarization/deduplication, and a large reasoning model only for planning and synthesis

Streaming: OpenAI's Runner.run_streamed() and Claude's streaming APIs let you surface intermediate progress (active searches, current subagent count) to the UI in real time

Production Failure Modes to Pre-Empt
Drawn from Anthropic, mcp-agent, and published multi-agent research:

Subagent task collision — Without explicit non-overlapping task descriptions, two agents will duplicate the same searches. Assign region/time/subtopic ownership explicitly.

Context window exhaustion — Subagents should write full outputs to filesystem artifacts and return only summaries + references to the orchestrator.

Error propagation cascades — Early misinterpretation (e.g., wrong fiscal year assumption) compounds through all downstream steps. Require subagents to state assumptions explicitly so the synthesis agent can cross-check them.

SEO content bias — LLM agents disproportionately surface highly-ranked content farms over authoritative but low-ranked sources (academic PDFs, primary databases). Add explicit heuristics to prefer primary and domain-authoritative sources.

Overspawning — Without complexity scaling rules, the orchestrator will spawn 50 subagents for a simple question. Embed hard caps and scaling tiers in the orchestrator prompt.

Rainbow deployments for stateful agents — When updating prompts or tools on a live system, running agents may be mid-execution. Use version-tagged deployments that keep old agent logic active for in-flight sessions.

Prepared by Deep Research
Do any of these apis have a batch api to save on inference?
Completed 2 steps
Here's the quick breakdown — the answer varies meaningfully by API:

Batch API Support by Provider
API	Batch Support	Discount	Notes
Anthropic Claude	✅ GA	50% off input + output	Up to 10,000 requests per batch, processed within 24 hours 
OpenAI o3-deep-research	✅ Supported	50% off input + output	Explicitly listed on the v1/batch endpoint; $10→$5 input, $40→$20 output 
Perplexity Sonar / Sonar Deep Research	❌ No batch API	None	Per-request pricing only ($5/1K requests + token costs); no async batch endpoint 
Tavily	❌ No batch API	None	Standard REST, per-call pricing; no documented batch mode 
Exa	❌ No batch API	None	Per-call pricing only
Practical Implications for Your Research Agent
Where batch actually saves money: The two most expensive steps in a multi-step research pipeline are the synthesis/report-writer pass (large output, Claude Opus or GPT-o3) and any offline evaluation/quality-judge pass. Both are non-time-sensitive — perfect batch candidates.

Use Claude Message Batches API for your synthesis agent, quality judge, and deduplication passes. At 50% off, Claude Opus 4 goes from ~$15/MTok input to ~$7.50/MTok.

Use OpenAI Batch API for o3-deep-research sub-queries that don't need real-time results — the 24-hour window works fine for nightly research pipelines or background report generation.

Prompt caching is a complementary lever — OpenAI caches o3-deep-research inputs at $2.50/MTok (vs $10 standard), which compounds nicely when you have a large shared system prompt across many subagent calls.

Perplexity and Tavily are inherently real-time (they're doing live web search), so a batch model doesn't really apply — you want their freshness. Route those only when you need current data, and batch the LLM-heavy reasoning and synthesis steps instead.

Prepared by Deep Research
Does grok build or any other frontier models support batch mode for any kinds of inference? Give me the full table/matrix
Completed 4 steps
Here's the full matrix across all major frontier providers:

Batch API Support — Full Matrix
Provider / Model	Batch API	Discount	Max Batch Size	SLA / Window	Notes
Anthropic Claude	✅ GA	50% off input + output	10,000 requests	24 hrs	Via v1/messages/batches; also available through AWS Bedrock 
OpenAI (GPT-4o, o3, o3-deep-research)	✅ GA	50% off input + output	50,000 requests / 100MB	24 hrs	All text models supported; v1/batch endpoint 
Google Gemini (2.5 Pro, 2.5 Flash, etc.)	✅ GA	50% off input + output	Large jobs (no stated cap)	24 hrs	Python SDK; launched mid-2025 
xAI Grok (Grok 4.3, Grok Build 0.1, etc.)	✅ GA	20–50% off (model-dependent)	Up to 25MB per request	24 hrs	Launched Feb 2026; applies to text/language models only — image/video billed at standard rates 
Mistral (all la Plateforme models)	✅ GA	50% off input + output	1M ongoing requests/workspace	~mins–hrs	Available since Nov 2024; also via AWS Bedrock 
Together AI (DeepSeek-R1, Llama 4, Qwen3, etc.)	✅ GA	50% off	50,000 requests / 100MB	Not specified	15 models at launch; separate rate limits from real-time pool 
AWS Bedrock (Claude, Llama, Mistral, Nova, Titan)	✅ GA	50% off on-demand	Varies by model	24 hrs	Unified batch across hosted providers; separate rate pool 
Cohere (Command A, Command R+, etc.)	✅ GA	Not publicly stated	Not stated	Not stated	v2/batches endpoint exists; enterprise/Model Vault pricing is instance-based 
Perplexity Sonar / Sonar Deep Research	❌ None	—	—	—	Real-time web search only; per-request pricing 
Exa	❌ None	—	—	—	Per-call REST only
Tavily	❌ None	—	—	—	Per-call REST only 
Key Takeaways
Grok Build specifically — the fast agentic coding model you might use for code-gen subtasks — does support the batch API at the 20–50% discount tier, though the exact percentage varies by model and you'd need to check the per-model toggle in xAI's pricing dashboard. Image and video generation on xAI are excluded from the batch discount regardless.

The 50% discount is effectively an industry standard for all the major LLM providers now — Anthropic, OpenAI, Google, Mistral, and Together AI all landed on the same number. It reflects the economics of asynchronous batching: providers can schedule jobs during off-peak compute and pass the savings on.

For your research pipeline specifically, the non-real-time synthesis, deduplication, quality-judge, and report-writer passes are all prime batch candidates. The real-time constraint only applies to the Perplexity/Tavily/Exa search fetch layer — everything downstream of that can be batched.

Prepared by Deep Research
Show me how to turn on batch mode for all of these and any other ways to save on tokens
Completed 7 steps
Here's the full code cookbook for every provider that supports batch mode, plus all the other token-saving levers.

Enabling Batch Mode: Provider-by-Provider
Anthropic Claude
Claude's batch API uses POST /v1/messages/batches with up to 100,000 requests per batch and a 256MB limit. The response polling checks processing_status until it's no longer in_progress.

typescript
// TypeScript (using OpenAI-compatible SDK via Anthropic SDK)
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();

const batch = await client.messages.batches.create({
  requests: [
    {
      custom_id: "synthesis-001",
      params: {
        model: "claude-opus-4-5",
        max_tokens: 4096,
        system: "You are a research synthesis agent...",
        messages: [{ role: "user", content: researchFindings }],
      },
    },
    {
      custom_id: "quality-judge-001",
      params: {
        model: "claude-sonnet-4-5",
        max_tokens: 512,
        messages: [{ role: "user", content: draftReport }],
      },
    },
  ],
});

// Poll for completion
let result = await client.messages.batches.retrieve(batch.id);
while (result.processing_status === "in_progress") {
  await new Promise((r) => setTimeout(r, 5000));
  result = await client.messages.batches.retrieve(batch.id);
}

// Stream results
for await (const entry of await client.messages.batches.results(batch.id)) {
  if (entry.result.type === "succeeded") {
    console.log(entry.custom_id, entry.result.message.content);
  }
}
OpenAI (o3, o3-deep-research, GPT-4o)
OpenAI uses a JSONL file upload pattern — prep your requests as a .jsonl, upload it, then create the batch job.

typescript
import OpenAI from "openai";
import fs from "fs";

const client = new OpenAI();

// 1. Write JSONL
const requests = subAgentQueries.map((q, i) => ({
  custom_id: `research-${i}`,
  method: "POST",
  url: "/v1/responses",
  body: {
    model: "o3-deep-research",
    input: [
      { role: "system", content: "You are a deep research agent..." },
      { role: "user", content: q },
    ],
    max_output_tokens: 8192,
  },
}));

fs.writeFileSync("batch.jsonl", requests.map(JSON.stringify).join("\n"));

// 2. Upload & create batch
const file = await client.files.create({
  file: fs.createReadStream("batch.jsonl"),
  purpose: "batch",
});

const batch = await client.batches.create({
  input_file_id: file.id,
  endpoint: "/v1/responses",
  completion_window: "24h",
});

// 3. Poll
let b = await client.batches.retrieve(batch.id);
while (b.status !== "completed") {
  await new Promise((r) => setTimeout(r, 10_000));
  b = await client.batches.retrieve(batch.id);
}

// 4. Download results
const content = await client.files.content(b.output_file_id!);
const lines = (await content.text()).trim().split("\n").map(JSON.parse);
Google Gemini
Gemini supports both inline requests (< 20MB) and JSONL file upload. It also supports OpenAI-compatible batch calls.

python
from google import genai
from google.genai import types

client = genai.Client()

# Inline for small batches
batch_job = client.batches.create(
    model="gemini-2.5-flash",
    src=[
        {"contents": [{"parts": [{"text": synthesis_prompt}], "role": "user"}]},
        {"contents": [{"parts": [{"text": judge_prompt}], "role": "user"}]},
    ],
    config={"display_name": "research-synthesis-batch"},
)

# Poll
import time
while True:
    job = client.batches.get(name=batch_job.name)
    if job.state.name in ("JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED"):
        break
    time.sleep(10)

# Download
result_bytes = client.files.download(file=job.dest.file_name)
for line in result_bytes.decode().splitlines():
    print(line)
Or via the OpenAI compatibility layer (handy if you already have OpenAI batch code):

python
from openai import OpenAI

# Just swap base_url — same code as OpenAI batch
gemini_client = OpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)
batch = gemini_client.batches.create(
    input_file_id=batch_input_file_id,
    endpoint="/v1/chat/completions",
    completion_window="24h",
)
xAI Grok (unique: supports MCP tools in batch)
Grok's batch API is notably different — it uses a create → add → poll → retrieve flow rather than JSONL upload, and uniquely supports MCP servers and web_search tools inside batch requests.

typescript
import { xai } from "@ai-sdk/xai";
// Or use the native SDK:
import { Client } from "xai_sdk"; // Python

// TypeScript via raw fetch (most ergonomic for TS)
const BASE = "https://api.x.ai/v1";
const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${process.env.XAI_API_KEY}`,
};

// 1. Create batch container
const { batch_id } = await fetch(`${BASE}/batches`, {
  method: "POST",
  headers,
  body: JSON.stringify({ name: "research-synthesis" }),
}).then((r) => r.json());

// 2. Add requests (can include MCP tools!)
await fetch(`${BASE}/batches/${batch_id}/requests`, {
  method: "POST",
  headers,
  body: JSON.stringify({
    batch_requests: subQueries.map((q, i) => ({
      batch_request_id: `req-${i}`,
      batch_request: {
        responses: {
          model: "grok-4.3",
          tools: [
            { type: "web_search" },
            // Can even call your MCP servers:
            { type: "mcp", server_label: "my-tool", server_url: "https://..." },
          ],
          input: [{ role: "user", content: q }],
        },
      },
    })),
  }),
});

// 3. Poll
let done = false;
while (!done) {
  await new Promise((r) => setTimeout(r, 5000));
  const { state } = await fetch(`${BASE}/batches/${batch_id}`, { headers }).then((r) => r.json());
  done = state.num_pending === 0;
}

// 4. Fetch paginated results
const { results } = await fetch(`${BASE}/batches/${batch_id}/results?limit=100`, { headers }).then((r) => r.json());
Or JSONL upload (max 200MB / 50,000 requests):

text
{"custom_id":"s1","method":"POST","url":"/v1/chat/completions","body":{"model":"grok-4.3","messages":[{"role":"user","content":"Synthesize..."}]}}
{"custom_id":"s2","method":"POST","url":"/v1/responses","body":{"model":"grok-4.3","tools":[{"type":"web_search"}],"input":[{"role":"user","content":"Search for..."}]}}
Mistral
Straightforward JSONL upload with the mistralai Python client:

python
from mistralai import Mistral
import json

client = Mistral(api_key=MISTRAL_API_KEY)

# Write JSONL
with open("batch.jsonl", "w") as f:
    for i, prompt in enumerate(synthesis_prompts):
        f.write(json.dumps({
            "custom_id": f"synth-{i}",
            "body": {
                "model": "mistral-large-latest",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2048,
            }
        }) + "\n")

# Upload & create
with open("batch.jsonl", "rb") as f:
    file = client.files.upload(file={"file_name": "batch.jsonl", "content": f})

job = client.batch.jobs.create(
    input_files=[file.id],
    model="mistral-large-latest",
    endpoint="/v1/chat/completions",
    metadata={"project": "deep-research"},
)

# Poll
import time
while job.status in ("QUEUED", "RUNNING"):
    time.sleep(5)
    job = client.batch.jobs.get(job_id=job.id)

# Download
result = client.files.download(file_id=job.output_file)
for line in result.decode().splitlines():
    print(json.loads(line))
Beyond Batch: All Token-Saving Levers
Strategy	Savings	Best Applied To	Notes
Batch API	50% off all tokens	Synthesis, judge, dedup passes	Requires 24hr SLA tolerance 
Prompt Caching (Claude)	90% off cached input tokens	Large shared system prompts	5-min TTL default; use cache_control: {"type":"ephemeral"} 
Prompt Caching (OpenAI)	50% off input tokens	System prompt prefix > 1024 tokens	Automatic — no code change needed 
Prompt Caching (Gemini)	50% off input (explicit cache)	Long shared context across many calls	1hr TTL default; pay small storage fee 
Model routing	20–60%	Triage/clarify/dedup → cheap model	GPT-4o-mini at $0.15/MTok vs $10 for o3 
Semantic caching	15–30%	Repeated/similar queries	LLM gateway (LiteLLM, Helicone) dedupes semantically identical prompts 
Structured output / tight schemas	10–25%	Any classification/extraction	Forces concise output; eliminates verbose hedging text
max_tokens budget caps	Variable	All agents	Hard cap per subagent prevents runaway output costs
The highest-leverage combo for a research agent: batch the synthesis/judge pass (50% off) + prompt-cache the shared system prompt across all subagent calls (90% off those tokens on Claude). Together these can cut total inference spend by 60–80% on a pipeline where the system prompt is large and synthesis is non-time-sensitive.

Prepared by Deep Research
Are there any open source projects that will allow me to submit a queue of reports with an associated ontology?

Yes — several open-source projects support this pattern, though it splits into two camps: report-generation agents (queue of research reports) and ontology-guided extraction systems (schema-bound knowledge). The strongest fit combines both. Here's what's available.

Best Matches for Queue + Ontology
Project	Queue/Batch Reports	Ontology/Schema Support	Stack	License
GPT Researcher	✅ Via task queue (Amazon SQS pattern documented) 
⚠️ Partial — custom report formats, no native ontology	Python, LangGraph + AG2 multi-agent 
Apache 2.0
OneKE (zjunlp)	✅ Dockerized, batch extraction from web/PDF	✅ Native schema-guided — you supply the schema/ontology, agents extract to it 
Python, multi-agent	Open source 
LangChain Open Deep Research	✅ Configurable, section-by-section parallel	⚠️ Structured output config, BYO schema via models	LangGraph, BYO models/MCP 
MIT
Generative Ontology (DSPy)	⚠️ Multi-agent pipeline	✅ Pydantic schemas as executable ontology constraining LLM generation via DSPy signatures 
Python, DSPy	Research/open
ODKE+ (Apple)	✅ Production-grade, millions of facts	✅ Ontology-guided open-domain extraction 
Research system	Paper (limited code)
How to Combine Them
The cleanest architecture for your goal — submit a queue of report requests, each bound to an ontology — is to layer GPT Researcher (or LangChain's Open Deep Research) for the research/synthesis loop on top of a schema-guided extractor:

OneKE is the closest single-project fit. It's explicitly designed for schema-guided knowledge extraction across domains, runs dockerized (so queueing is trivial), uses a collaborative multi-agent approach, and includes a user-customizable knowledge base. You define the ontology/schema, and the agents extract conforming knowledge from web sources and PDFs. This maps directly to your TypeDB/SurrealDB ontology work.

For the report-generation layer, GPT Researcher produces 5-6 page reports in PDF/Docx/Markdown and its architecture explicitly anticipates a message queue (SQS) distributing requests to worker processes — exactly the queue-of-reports pattern you described. You'd wrap each queued job with an ontology/schema parameter and pass it to a OneKE extraction step post-synthesis.

If you want ontology-constrained generation rather than post-hoc extraction, the Generative Ontology approach encodes your domain ontology as executable Pydantic schemas that constrain LLM output via DSPy signatures. This is appealing given your formal-methods background — the schema becomes a verifiable contract the generation must satisfy, rather than a validation afterthought.

Practical Recommendation
Given your SurrealDB/TypeDB and MCP background, the highest-leverage build is: a lightweight queue (Redis/SQS or even a SurrealDB live-query table) feeding worker processes, where each worker runs GPT Researcher for synthesis → OneKE for ontology-bound extraction → write entities/relations into your graph DB. OneKE's customizable knowledge base and TypeDB's schema-first model align naturally, since both treat the ontology as a first-class typed contract.

Would you prefer the ontology to constrain generation upfront (DSPy/Pydantic approach) or validate/extract after a free-form research pass (OneKE approach)? That choice determines which project becomes your core.

Prepared using Claude Opus 4.8
Is there a way to execute changes in batch outside of the cursor cloud agent api?

Yes — you have several batch-execution paths that don't touch Cursor's Cloud Agent API. The dominant pattern is headless CLI agents driven by scripts, with a few purpose-built multi-repo platforms for larger scale.

Headless CLI Agents (Most Direct)
The cleanest approach is running a coding agent in non-interactive "headless" mode from a script, iterating over a queue of tasks:

Claude Code headless mode is the strongest fit. The -p / --print flag processes a single prompt and exits, with no user interaction — purpose-built for scripting and CI/CD. You loop over a task list in bash/Python via subprocess, spinning up one invocation per change. Scope each task with --allowedTools and bound runaway loops with --max-turns.

bash
claude -p "Migrate all v1 API calls to v2 per MIGRATION.md" \
  --allowedTools "Read,Write,Edit,Grep,Glob" --max-turns 20
Claude Code's /batch command natively splits a large refactor across subagents automatically, so a single big change can fan out internally without you orchestrating it.

OpenAI Codex CLI supports local and worktree execution modes (in addition to cloud), letting you run multiple agents in parallel across different repos with no local resource conflicts — all driven outside any cloud API.

Gemini CLI runs agent-mode against a local repo for multi-step file edits directly in the terminal.

Mistral vibe and Pi Agent are minimal open-source terminal agents; Pi is explicitly designed to receive direct commands like "update all the repos here" and execute bash scripts fast with low context overhead.

Parallelism via Git Worktrees
For executing many changes concurrently on one codebase, the established pattern is Git worktrees — each agent gets an isolated copy of the repo on its own branch, works independently, then merges back. People wrap this in a shell alias/script that spins up a worktree and launches a headless agent per task, giving you true parallel batch execution locally. Claude Code's worktrees + subagents + /btw (talk to it mid-task) are built around this workflow.

Purpose-Built Multi-Repo Platforms
For change-at-scale across many repositories — closer to your enterprise/FinOps context — dedicated tools exist:

Moderne runs a multi-repo AI agent ("Moddy") integrated with OpenRewrite, executing large-scale, deterministic code transformations across entire codebases at once rather than file-by-file. This is the most robust option when changes must be auditable and applied uniformly across hundreds of repos.

Codegen and similar platforms offer API/agent-driven bulk changes as Cursor alternatives.

Recommendation for Your Setup
Given your CLI-heavy, TypeScript/Python workflow, the highest-leverage path is a task-queue script driving Claude Code headless mode, with Git worktrees for parallelism: read jobs from a queue (Redis, SQS, or a SurrealDB live-query table), spawn a worktree + claude -p invocation per job, and merge passing branches back via CI gates. If the changes are deterministic structural refactors across many repos, layer in Moderne/OpenRewrite for the recipe-based transformations and reserve the LLM agent for the judgment-heavy edits.

Are these changes mostly mechanical/structural refactors (favoring OpenRewrite recipes) or judgment-heavy edits requiring an LLM agent per task? That determines whether you lean on Moderne or a headless Claude Code queue