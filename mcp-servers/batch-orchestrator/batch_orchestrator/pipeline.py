"""Multi-stage deep research pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from batch_orchestrator.models import Job, PipelineDepth, Provider, ReasoningEffort

DEPTH_CONFIG: dict[PipelineDepth, dict[str, int | ReasoningEffort]] = {
    "simple": {"max_subagents": 1, "reasoning_effort": "medium"},
    "comparative": {"max_subagents": 3, "reasoning_effort": "high"},
    "deep": {"max_subagents": 5, "reasoning_effort": "high"},
}

TRIAGE_PROMPT = """You are a research triage agent. Given the user's research query, produce:
1. A one-sentence classification (simple fact / comparative / deep research)
2. 2-3 clarifying scope bullets (audience, timeframe, geography if relevant)
3. A precise research brief (3-5 sentences) optimized for subagent fan-out

Query:
{query}

Respond in markdown with sections: Classification, Scope, Research Brief."""

INSTRUCTION_BUILDER_PROMPT = """Rewrite this research brief into {num_subagents} non-overlapping sub-queries.
Each sub-query must have explicit boundaries (topic, region, or subtopic ownership).
Return ONLY a numbered list, one sub-query per line.

Research brief:
{brief}
"""

SYNTHESIS_PROMPT = """You are a research synthesis agent. Merge the following sub-reports into one
comprehensive markdown report. Deduplicate overlapping facts, note conflicts explicitly,
and preserve citation URLs where present.

Original query: {query}

Sub-reports:
{reports}

Produce: Executive Summary, Detailed Findings, Key Sources, Open Questions."""

REFLECTION_PROMPT = """Review this research draft against the original query. List any knowledge gaps
(unanswered sub-questions, low-confidence claims). If gaps exist, suggest up to 2 follow-up queries.
If the draft is sufficient, respond with exactly: COMPLETE

Original query: {query}

Draft:
{draft}
"""


@dataclass
class PipelinePlan:
    job_id: str
    query: str
    depth: PipelineDepth
    max_subagents: int
    triage_provider: Provider
    fanout_provider: Provider
    synthesis_provider: Provider
    reasoning_effort: ReasoningEffort
    sub_queries: list[str]


def resolve_pipeline_config(job: Job) -> tuple[int, ReasoningEffort]:
    cfg = DEPTH_CONFIG.get(job.depth, DEPTH_CONFIG["comparative"])
    max_agents = min(job.max_subagents, int(cfg["max_subagents"]))
    effort = cfg["reasoning_effort"]
    if isinstance(effort, str):
        effort = effort  # type: ignore[assignment]
    return max_agents, effort  # type: ignore[return-value]


def build_triage_prompt(query: str, program: str = "") -> str:
    prog = f"Persistent program instructions:\n{program}\n\n---\n\n" if program else ""
    return (prog + TRIAGE_PROMPT).format(query=query)


def build_instruction_prompt(brief: str, num_subagents: int, program: str = "") -> str:
    prog = f"Persistent program instructions:\n{program}\n\n---\n\n" if program else ""
    return (prog + INSTRUCTION_BUILDER_PROMPT).format(brief=brief, num_subagents=num_subagents)


def parse_sub_queries(text: str, max_count: int) -> list[str]:
    lines = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Strip leading numbering like "1." or "1)"
        cleaned = line.lstrip("0123456789.) ").strip()
        if cleaned:
            lines.append(cleaned)
    return lines[:max_count] if lines else [text.strip()]


def build_synthesis_prompt(query: str, reports: list[str], program: str = "") -> str:
    prog = f"Persistent program instructions:\n{program}\n\n---\n\n" if program else ""
    combined = "\n\n---\n\n".join(
        f"### Sub-report {i + 1}\n{r}" for i, r in enumerate(reports)
    )
    return (prog + SYNTHESIS_PROMPT).format(query=query, reports=combined)


def build_reflection_prompt(query: str, draft: str, program: str = "") -> str:
    prog = f"Persistent program instructions:\n{program}\n\n---\n\n" if program else ""
    return (prog + REFLECTION_PROMPT).format(query=query, draft=draft)


def build_sub_research_prompt(sub_query: str, main_query: str = "", program: str = "") -> str:
    """Build the instruction given to each parallel deep_research subagent in a pipeline.
    Includes explicit note that controller will dispatch reviewers after report, and ratchet rules.
    """
    prog_block = f"Persistent program instructions (follow always):\n{program}\n\n---\n\n" if program else ""
    return (
        f"{prog_block}"
        f"You are a specialist researcher in a multi-stage pipeline.\n"
        f"Main research intent: {main_query or 'the user query'}\n\n"
        f"Subtask (your sole responsibility): {sub_query}\n\n"
        f"Instructions:\n"
        f"- Produce a self-contained deep research report on ONLY your subtask.\n"
        f"- Use the same output format as top-level: markdown with Executive Summary / Detailed Findings / Key Sources / Open Questions where applicable.\n"
        f"- Include explicit citations (URLs, [n] refs, or named sources) for all non-trivial claims.\n"
        f"- After your report, the controller will dispatch critic/verifier reviewers and apply Karpathy ratchet: ONLY sections that are citation-verified AND strictly higher quality than any prior version will be kept in the final output. Low-signal or un-cited content will be dropped.\n"
        f"- Prioritize verifiable, high-signal, defensible findings over volume."
    )


def extract_brief_from_triage(triage_text: str) -> str:
    """Extract research brief section from triage output."""
    if "## Research Brief" in triage_text:
        parts = triage_text.split("## Research Brief", 1)
        return parts[1].strip() if len(parts) > 1 else triage_text
    if "Research Brief" in triage_text:
        parts = triage_text.split("Research Brief", 1)
        return parts[1].strip().lstrip(":").strip()
    return triage_text


def is_reflection_complete(reflection_text: str) -> bool:
    return "COMPLETE" in reflection_text.upper() and len(reflection_text.strip()) < 200


def parse_followup_queries(reflection_text: str, max_queries: int = 2) -> list[str]:
    if is_reflection_complete(reflection_text):
        return []
    lines = []
    for line in reflection_text.split("\n"):
        line = line.strip().lstrip("-*0123456789.) ").strip()
        if line and len(line) > 20 and "COMPLETE" not in line.upper():
            lines.append(line)
    return lines[:max_queries]


# --- Phase 2: Critic / Verifier + Karpathy Ratchet additions ---

CRITIC_PROMPT = """You are a strict research critic and citation verifier (in the spirit of Karpathy's "only keep verifiable improvements").
Review the provided report SECTION for:
- Presence of explicit citations (URLs, [n] style refs, (Author Year), or "source:" markers)
- Signal density: concrete metrics, comparisons, multiple evidence bullets, named entities
- Gaps, unsupported claims, low-confidence hedges ("probably", "may"), or vague generalizations
- Overall defensibility for downstream use in client-facing or decision-grade report

At end of review output exactly one line:
VERDICT: [KEEP|REVISE|DROP]  CONFIDENCE: <0.0-1.0>  REASON: <<=20 words>

If citations present + high signal (at least one metric or comparison + 2+ bullets), lean KEEP with conf >=0.7
If no citations or pure opinion/vague: DROP
If mixed but fixable: REVISE

Section to review:
{section}

Original research intent (for context):
{intent}
"""


def build_critic_prompt(section: str, intent: str = "") -> str:
    return CRITIC_PROMPT.format(section=section, intent=intent or "general research query")


def verify_citations(section: str | dict) -> bool:
    """Heuristic citation verifier (no LLM call to keep cheap/fast).
    Accepts str or {'text': ...} section dict.
    """
    text = section.get("text", section) if isinstance(section, dict) else section
    if not text or not isinstance(text, str):
        return False
    t = text.lower()
    # urls
    if "http://" in t or "https://" in t:
        return True
    # bracket refs [1], (1), [n]
    import re
    if re.search(r"\[\d+\]", text) or re.search(r"\(\d+\)", text):
        return True
    # common markers (tightened to avoid false-positive on "no citations" etc; require colon or full phrase)
    if any(k in t for k in ("source:", "sources:", "citations:", "citation:", "according to ", "per ", "ref:", "cited in ")):
        return True
    # doi or arxiv hint
    if "doi.org" in t or "arxiv.org" in t or "10." in t[:100]:
        return True
    return False


def compute_quality(section: str | dict) -> float:
    """Heuristic quality score 0.0-1.0 (len + bullets + citations + keywords).
    No LLM for speed in ratchet (can be swapped for stub LLM later).
    """
    text = section.get("text", section) if isinstance(section, dict) else section
    if not text or not isinstance(text, str):
        return 0.0
    score = 0.0
    n = len(text)
    # length signal (cap)
    score += min(n / 1200.0, 0.35)
    # bullets / structure
    bullets = text.count("\n- ") + text.count("\n* ") + text.count("\n  - ")
    score += min(bullets * 0.08, 0.25)
    # has citation bonus
    if verify_citations(text):
        score += 0.25
    # concrete keywords (metrics, comparisons, numbers)
    import re
    nums = len(re.findall(r"\b\d+[%x]?\b", text))
    score += min(nums * 0.03, 0.15)
    if any(w in text.lower() for w in (" vs ", "compared to", "improved", "reduced", "increased", "cagr", "by ", "%")):
        score += 0.05
    # headings add structure
    if re.search(r"(?m)^#{2,3}\s", text):
        score += 0.05
    return max(0.0, min(1.0, round(score, 3)))


def split_report_to_sections(draft: str) -> list[dict]:
    """Split synthesized draft into sections for per-section ratchet/critic.
    Prefers markdown ##/### headers; falls back to para chunks.
    Returns list of {"id": slug, "text": content}
    """
    import re
    sections: list[dict] = []
    if not draft or not draft.strip():
        return sections
    # Primary: split on level-2/3 headers, keep header+following content
    parts = re.split(r"(?m)^(##{1,2} .+)$", draft)
    if len(parts) > 1:
        for i in range(1, len(parts), 2):
            header = parts[i].strip()
            body = parts[i + 1].strip() if (i + 1) < len(parts) else ""
            sec_text = (header + "\n" + body).strip()
            if len(sec_text) > 25:  # drop tiny fragments only
                sid = re.sub(r"[^a-z0-9_]+", "_", header.lower().strip("# ").strip())[:64]
                sections.append({"id": sid or f"sec_{len(sections)}", "text": sec_text})
    if sections:
        return sections
    # Fallback: chunk by ~3 paragraphs or 600 char blocks
    paras = [p.strip() for p in re.split(r"\n{2,}", draft) if p.strip()]
    for i in range(0, len(paras), 3):
        chunk = "\n\n".join(paras[i : i + 3])
        if len(chunk) > 10:  # allow small for fallback coverage; real use has headers or longer
            sections.append({"id": f"chunk_{len(sections)}", "text": chunk})
    return sections


def load_program(program_ref: str, base_dir: Path) -> str:
    """Load persistent program instructions (for a job).
    Supports:
      - "file:foo/bar/program.md" relative to base_dir (manifest dir)
      - plain text (returned as-is)
      - "" or None -> ""
    Mirrors expand_file_refs style but specific for program.md style persistent guidance.
    """
    if not program_ref:
        return ""
    ref = str(program_ref).strip()
    if ref.startswith("file:"):
        rel = ref[5:].strip()
        p = (base_dir / rel).resolve()
        if p.exists() and p.is_file():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                return ""
        return ""
    # treat as literal instructions
    return ref


def apply_karpathy_ratchet(
    report_sections: list[dict | str], prior_metrics: dict[str, float] | None = None
) -> list[dict]:
    """Karpathy ratchet: only retain sections that are citation-verified AND strictly higher quality than prior (or >0 on first pass).
    Monotonic non-decreasing quality only. Low-signal or unverified sections are dropped.
    This is the "only keep on verifiable improve" gate.
    """
    if prior_metrics is None:
        prior_metrics = {}
    kept: list[dict] = []
    for s in report_sections:
        sec = s if isinstance(s, dict) else {"id": f"auto_{hash(s) % 10000}", "text": str(s)}
        if verify_citations(sec) and compute_quality(sec) > prior_metrics.get(sec.get("id", ""), 0.0):
            kept.append(sec)
    return kept


# research-memory persist hook (now live for 2.3 dogfood via installed CLI + direct _impl; portable uv tool)
def maybe_store_ratchet_citation_graph(kept_sections: list[dict], run_id: str | None = None) -> None:
    """Store ratchet-kept citation graph / sections to research-memory for live RAG recall.
    Uses `research-memory store` CLI (installed via uv tool in verification) for robustness (no async/import/loop issues).
    Called from engine after each ratchet pass inside deep_research_pipeline (sub + final + post-reflect).
    This makes "prior artifacts recalled via RAG" true for the 2.3 pipeline output itself (plus priors pre-stored).
    """
    if not kept_sections:
        return
    try:
        import tempfile
        import subprocess
        from pathlib import Path as _P
        # Build a compact artifact md+json for the kept (ratcheted sections only + cites extracted)
        citations = []
        lines = ["# Ratchet Citation Graph (Task 2.3 dogfood pipeline output)", f"run_id: {run_id}", ""]
        for sec in kept_sections:
            txt = sec.get("text", "") if isinstance(sec, dict) else str(sec)
            import re
            urls = re.findall(r"https?://\S+|\[[^\]]+\]\([^)]+\)|id [0-9a-f]{12}", txt)
            citations.extend(urls)
            lines.append("## Kept Section")
            lines.append(txt[:2000])
            lines.append("")
        content = "\n".join(lines)
        tags = ["batch", "ratchet", "citations", "meta-utilities", "2.3-dogfood", "live-rag"]
        with tempfile.TemporaryDirectory() as td:
            art = _P(td) / "ratchet-kept.md"
            art.write_text(content, encoding="utf-8")
            # Use the CLI (post `uv tool install -e mcp-servers/research-memory` in verify); it calls _impl
            cmd = ["research-memory", "store", "--artifact", str(art), "--tags", ",".join(tags)]
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=30)
            # also try to surface for logs
            print(f"[maybe_store] research-memory store succeeded: {out[:300]}")
    except Exception as e:
        # best effort; if CLI not in PATH yet or other, ratchet still succeeds standalone (no fab)
        print(f"[maybe_store] research-memory persist skipped (will still have ratcheted report): {e}")
