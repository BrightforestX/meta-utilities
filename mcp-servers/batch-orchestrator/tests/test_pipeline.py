"""Tests for multi-stage research pipeline helpers."""

from batch_orchestrator.models import Job
from batch_orchestrator.pipeline import (
    build_instruction_prompt,
    build_reflection_prompt,
    build_sub_research_prompt,
    build_synthesis_prompt,
    build_triage_prompt,
    extract_brief_from_triage,
    is_reflection_complete,
    parse_followup_queries,
    parse_sub_queries,
    resolve_pipeline_config,
)


def test_resolve_pipeline_config_caps_subagents():
    job = Job(
        id="p",
        type="deep_research_pipeline",
        query="test",
        depth="simple",
        max_subagents=10,
    )
    max_agents, effort = resolve_pipeline_config(job)
    assert max_agents == 1
    assert effort == "medium"


def test_resolve_pipeline_config_deep():
    job = Job(
        id="p",
        type="deep_research_pipeline",
        query="test",
        depth="deep",
        max_subagents=5,
    )
    max_agents, effort = resolve_pipeline_config(job)
    assert max_agents == 5
    assert effort == "high"


def test_parse_sub_queries():
    text = "1. First topic about AI\n2. Second topic about cloud\n3. Third"
    queries = parse_sub_queries(text, max_count=2)
    assert len(queries) == 2
    assert "First topic" in queries[0]


def test_extract_brief_from_triage():
    triage = "## Classification\nSimple\n\n## Research Brief\nDo deep research on X."
    brief = extract_brief_from_triage(triage)
    assert "deep research on X" in brief


def test_reflection_complete():
    assert is_reflection_complete("COMPLETE")
    assert not is_reflection_complete("Gap: missing revenue data for Q4")


def test_parse_followup_queries():
    text = "- Investigate competitor pricing in EU\n- Review latest funding rounds"
    followups = parse_followup_queries(text)
    assert len(followups) == 2


def test_build_synthesis_prompt():
    prompt = build_synthesis_prompt("main query", ["report A", "report B"])
    assert "main query" in prompt
    assert "report A" in prompt


def test_build_prompts_accept_and_inject_program():
    prog = "PERSISTENT: cite primaries; apply ratchet."
    t = build_triage_prompt("q?", program=prog)
    i = build_instruction_prompt("brief", 2, program=prog)
    s = build_synthesis_prompt("q", ["r1"], program=prog)
    r = build_reflection_prompt("q", "draft", program=prog)
    subp = build_sub_research_prompt("subq", main_query="q", program=prog)
    for p in (t, i, s, r, subp):
        assert "PERSISTENT" in p and "ratchet" in p
    # without
    assert "PERSISTENT" not in build_triage_prompt("q?")
