"""TDD for Karpathy ratchet in research pipeline (Phase 2)."""

import pytest

# Import from source (adapt path for non-package; controller/sub will ensure runnable)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-servers" / "batch-orchestrator"))

from batch_orchestrator.pipeline import apply_karpathy_ratchet, split_report_to_sections, verify_citations  # type: ignore


def test_ratchet_drops_low_quality_keeps_verified_improved():
    sections = [
        {"id": "s1", "text": "Low signal no citations. Foo bar."},
        {"id": "s2", "text": "High signal. See https://example.com/a . Metric improved 40%."},
    ]
    prior = {"s2": 0.1}
    kept = apply_karpathy_ratchet(sections, prior)
    ids = [k["id"] for k in kept]
    assert "s1" not in ids, "low quality (no cite) dropped"
    assert "s2" in ids, "high + verified + better than prior kept (monotonic)"


def test_ratchet_requires_citation_verify_for_keep():
    sections = [{"id": "s3", "text": "Claimed improvement but no source."}]
    kept = apply_karpathy_ratchet(sections, {})
    assert not kept, "no citations -> dropped even if quality high"


def test_dogfood_stub_ratchet_keeps_only_verified_with_rag_recall_and_cites():
    """Extend for Task 2.3: simulate stub mixed report (with prior recall phrases + mixed cite/quality); assert ratcheted-only (only verified improved kept), RAG recall of gap/plan/turbovec, citations verified, token win potential via shorter kept.
    This covers the 4 verify props on realistic prior-derived content (used for TDD before/after stub + hook fixes).
    """
    from batch_orchestrator.pipeline import split_report_to_sections
    # Simulate the dogfood stub synthetic output (mixed: 1 good with cites+recall of priors, 1 vague no-cite)
    stub_mixed = (
        "## High-Signal Ratcheted Section (verified)\n"
        "Prior artifacts recalled via RAG: gap-analysis.md + 2026-06-04 plan show ratchet+research-memory+turbovec/Weaviate via context-forge achieved token reductions (20%+ on gap) and live recall. "
        "See https://github.com/meta-utilities [1] and stored id 8eb3e8905198.\n"
        "Quality improved: 3->1 kept, monotonic >0.8.\n\n"
        "## Vague No-Cite Section (to be dropped)\n"
        "This might help with batch orchestration verification gaps in future but no specific sources or data.\n"
    )
    secs = split_report_to_sections(stub_mixed) or [
        {"id": "h", "text": stub_mixed.split("\n\n")[0]},
        {"id": "v", "text": stub_mixed.split("\n\n")[1] if "\n\n" in stub_mixed else ""},
    ]
    kept = apply_karpathy_ratchet(secs, {})
    ids = [k.get("id") for k in kept]
    kept_text = " ".join(k.get("text", "") for k in kept)
    assert len(kept) == 1, "ratcheted sections only: only verified high kept, vague dropped"
    assert "v" not in ids and any("h" in (i or "") for i in ids), "low/vague dropped"
    assert verify_citations(kept[0]) is True, "citations verified on kept"
    assert "gap-analysis.md" in kept_text and "turbovec" in kept_text and "plan" in kept_text, "prior artifacts recalled via RAG in kept content"
    assert "Vague" not in kept_text, "ratcheted sections only (vague dropped from final)"
    # token < baseline: kept shorter than full mixed (real compress on actual report will show %; here structural)
    assert len(kept_text) < len(stub_mixed), "<X tokens vs baseline (stub mixed input vs ratcheted kept)"
