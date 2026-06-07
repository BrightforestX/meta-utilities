"""TDD for scripts/measure_research_metrics.py (Phase 3).

Parses sample report for:
- citation pass rate (heuristic: urls + [n] refs / estimated claims)
- recall % (sim: overlap with prior text keywords)
- token reduction (real via context-forge compress + tiktoken stats if avail)

Run: python -m pytest tests/test_research_metrics.py -q --tb=line
"""

import sys
import json
from pathlib import Path

# portable path to scripts (no install)
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# The module under test (will fail until impl)
from measure_research_metrics import measure_report, _heuristic_cite_count, _simple_recall


SAMPLE_REPORT = """
# Deep Research Report

## Findings
- Adoption of Weaviate BYOV reached 42% in 2026 [1] https://example.com/weaviate
- Token reduction via Context Forge + turbovec was 65% (verified in docs/turbovec-integration.md)
- See prior plan work for ratchet.

Citations: https://acme.com/phase0 https://meta-utilities/docs/gap-analysis.md
"""

SAMPLE_PRIOR = "Weaviate BYOV and turbovec RAG in context-forge for deep research token wins and Phase 0 work."


def test_heuristic_cite_count():
    n = _heuristic_cite_count(SAMPLE_REPORT)
    assert n >= 3, f"expected several cites, got {n}"


def test_simple_recall_overlap():
    rec = _simple_recall(SAMPLE_REPORT, SAMPLE_PRIOR)
    assert 0.0 <= rec <= 1.0
    assert rec > 0.1, "should recall some overlap on weaviate/turbovec keywords"


def test_measure_report_full(tmp_path):
    # writes a temp report, measures with prior, exercises compress path
    rep = tmp_path / "sample_report.md"
    rep.write_text(SAMPLE_REPORT, encoding="utf-8")
    pri = tmp_path / "prior.md"
    pri.write_text(SAMPLE_PRIOR, encoding="utf-8")

    metrics = measure_report(str(rep), prior_path=str(pri), use_compress=True)
    assert isinstance(metrics, dict)
    assert "citation_pass_rate" in metrics
    assert 0.0 <= metrics["citation_pass_rate"] <= 1.0
    assert "recall_sim" in metrics
    assert "token_stats" in metrics or "orig_tokens" in metrics
    assert metrics.get("report_chars", 0) > 0
    # self-dogfood note
    assert "context_forge" in str(metrics).lower() or "compress" in str(metrics).lower()


if __name__ == "__main__":
    # direct run support
    test_heuristic_cite_count()
    test_simple_recall_overlap()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        test_measure_report_full(Path(td))
    print("TDD PASS: research metrics script")
