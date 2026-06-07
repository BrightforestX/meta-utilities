"""TDD tests for Karpathy ratchet + critic/verifier in deep research pipeline.

Write test first (expect fail on missing funcs), then impl in pipeline.py.
"""

from batch_orchestrator.pipeline import (
    apply_karpathy_ratchet,
    verify_citations,
    compute_quality,
    split_report_to_sections,
    load_program,
    CRITIC_PROMPT,
)


def test_verify_citations_heuristic():
    good = "Key result from [1] https://example.com/foo and prior work (Smith 2024)."
    bad = "This is a vague claim without any sources or urls attached."
    assert verify_citations(good) is True
    assert verify_citations(bad) is False
    assert verify_citations("") is False


def test_compute_quality_heuristic():
    high = """## Finding: Adoption rates
- 42% CAGR in EU (source [1])
- Compared to US 18% [https://nist.gov]
- 3 bullets of data
"""
    low = "Vague sentence here."
    assert compute_quality(high) > 0.6
    assert compute_quality(low) < 0.4
    assert 0.0 <= compute_quality("") <= 1.0


def test_apply_karpathy_ratchet_drops_low_keeps_high_verified():
    """Core ratchet: only keep on verifiable improvement (monotonic)."""
    sections = [
        {"id": "low1", "text": "Vague opinion without sources or data points at all."},
        {"id": "high1", "text": "## Result\n- Metric improved 37% (verified [1] https://acme.com/report)\n- Cross checked vs baseline Q3."},
        {"id": "med1", "text": "Some data but no citation urls or refs: sales up last year."},
    ]
    prior = {}  # first pass, threshold 0
    kept = apply_karpathy_ratchet(sections, prior)
    ids = [s["id"] for s in kept]
    assert "high1" in ids, "high-signal verified should be kept"
    assert "low1" not in ids, "low quality no-cite must be dropped"
    # med may or not depending on exact heuristic; but ratchet should not keep below prior if set
    assert len(kept) >= 1


def test_apply_karpathy_ratchet_monotonic_only():
    """If prior metric exists and new quality not strictly > , drop even if verified."""
    section = {"id": "s1", "text": "## OK\nData from https://ok.com [1]"}
    # assume prior has higher or equal
    prior = {"s1": 0.95}
    kept = apply_karpathy_ratchet([section], prior)
    assert len(kept) == 0, "ratchet must be strict monotonic improve only"


def test_split_report_to_sections_headings_and_fallback():
    draft = """# Main

## Executive Summary
This is the high-level overview with enough content to pass size filters and demonstrate split.

## Detailed Findings
- Bullet one with https://cite.com [42]
- Another.

Some trailing text without header.
"""
    secs = split_report_to_sections(draft)
    assert len(secs) >= 2
    assert any("Executive" in s.get("text", "") or "executive" in s.get("id", "") for s in secs)
    assert all("id" in s and "text" in s for s in secs)
    # fallback chunk test
    long_no_head = "para1\n\npara2\n\npara3\n\npara4\n\n" * 5
    chunks = split_report_to_sections(long_no_head)
    assert len(chunks) >= 1


def test_load_program_file_ref_and_inline(tmp_path):
    prog = tmp_path / "prog.md"
    prog.write_text("You are persistent: always cite primary sources. Never fabricate.", encoding="utf-8")
    # file: ref
    loaded = load_program(f"file:{prog.name}", tmp_path)
    assert "primary sources" in loaded
    # inline pass-thru
    direct = load_program("Always do X. Never Y.", tmp_path)
    assert direct == "Always do X. Never Y."
    # missing
    missing = load_program("file:does-not-exist.md", tmp_path)
    assert missing == ""


def test_critic_prompt_exists_and_mentions_verdict():
    assert CRITIC_PROMPT
    assert "VERDICT" in CRITIC_PROMPT or "KEEP" in CRITIC_PROMPT
    assert "citation" in CRITIC_PROMPT.lower() or "gap" in CRITIC_PROMPT.lower()


def test_dogfood_stub_in_deep_research_returns_controllable_mixed_for_ratchet(monkeypatch):
    """TDD extend: stub in providers (for 2.3 full pipeline feasibility) must return synthetic with recall phrases + mixed cite quality so ratchet keeps only good cited.
    Run before impl to see, then after providers edit.
    """
    import os
    import asyncio
    from batch_orchestrator import providers as prov
    monkeypatch.setenv("BATCH_DOGFOOD_STUB", "1")
    res = asyncio.run( prov.run_deep_research("test meta-utilities gap topic", "openai") )
    assert res.get("error") is None
    report = res.get("report", "")
    assert "gap-analysis.md" in report or "turbovec" in report, "stub must include prior RAG recall phrases"
    assert "https" in report, "stub must include verified cites"
    # the vague part present in full stub output (ratchet will drop later)
    assert "Vague" in report or "low" in report.lower() or len(report) > 100
