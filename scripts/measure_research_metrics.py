#!/usr/bin/env python3
"""
Simple metrics for deep research outputs (citation pass rate, recall proxy, token reduction).
TDD: see tests/ or run on sample report.

Leverages compress-output.py for token stats (from context-forge, no dup).
Usage:
  python scripts/measure_research_metrics.py --report batch-results/synth-with-rag.json --prior-tokens 8000
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Portable: try relative to META or script
SCRIPT_DIR = Path(__file__).parent
COMPRESS = SCRIPT_DIR.parent / "skills" / "context-forge" / "scripts" / "compress-output.py"

def count_citations(text: str) -> int:
    urls = len(re.findall(r"https?://\S+", text))
    refs = len(re.findall(r"\[[0-9]+\]", text))
    return max(urls, refs)


# Aliases + extended API for TDD test + direct use in dogfood
_heuristic_cite_count = count_citations


def _simple_recall(report: str, prior: str) -> float:
    """Simple recall sim: fraction of significant keywords from prior that appear in report."""
    import re
    stop = {"the", "and", "for", "with", "this", "that", "from", "into", "about", "prior", "work"}
    kws = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", prior) if w.lower() not in stop]
    if not kws:
        return 0.0
    rlower = report.lower()
    hits = sum(1 for k in set(kws) if k in rlower)
    return hits / max(1, len(set(kws)))


def measure_report(
    report_path: str | None = None,
    *,
    text: str | None = None,
    prior_path: str | None = None,
    use_compress: bool = True,
) -> dict[str, Any]:
    """Programmatic API used by tests and dogfood. Returns metrics dict with citation_pass_rate, recall_sim, token stats."""
    if text is not None:
        report = text
    elif report_path:
        p = Path(report_path)
        if p.suffix == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
            report = data.get("report") or data.get("text") or str(data)
        else:
            report = p.read_text(encoding="utf-8")
    else:
        raise ValueError("provide report_path or text")

    cites = _heuristic_cite_count(report)
    total_claims = max(1, len(re.findall(r"\b[A-Z][^.]{20,}\.", report)))
    pass_rate = min(1.0, cites / max(1, total_claims / 3))

    prior_text = ""
    if prior_path:
        prior_text = Path(prior_path).read_text(encoding="utf-8")
    recall = _simple_recall(report, prior_text) if prior_text else 0.0

    # tokens + compress (real)
    orig_tokens = max(1, len(report) // 4)
    comp_tokens = orig_tokens
    ratio = 1.0
    stats_str = ""
    if use_compress and COMPRESS.exists():
        try:
            import subprocess
            # call with --stats; parse stderr for compressed tokens
            res = subprocess.run(
                [sys.executable, str(COMPRESS), "--stats", "--max-tokens", "4000"],
                input=report,
                capture_output=True,
                text=True,
                timeout=30,
            )
            for line in (res.stderr or "").splitlines():
                if "Compressed:" in line and "tokens" in line:
                    try:
                        comp_tokens = int(line.split("tokens")[0].split()[-1].replace(",", ""))
                    except Exception:
                        pass
            if "Saved:" in (res.stderr or ""):
                stats_str = (res.stderr or "").split("Saved:")[-1].splitlines()[0].strip()
        except Exception:
            pass
    token_reduction = ((orig_tokens - comp_tokens) / orig_tokens * 100.0) if orig_tokens else 0.0

    m = {
        "citation_pass_rate": round(pass_rate, 3),
        "citations_found": cites,
        "recall_sim": round(recall, 3),
        "orig_tokens": orig_tokens,
        "comp_tokens": comp_tokens,
        "token_reduction_pct": round(token_reduction, 1),
        "token_stats": stats_str or f"orig~{orig_tokens} comp~{comp_tokens}",
        "report_chars": len(report),
        "ratchet_note": "see pipeline critic/ratchet output",
    }
    if use_compress and COMPRESS.exists():
        m["context_forge_used"] = True
    return m

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", help="path to report json or .md")
    ap.add_argument("--text", help="inline report text (for tests/dogfood)")
    ap.add_argument("--prior", help="prior text or path for recall sim")
    ap.add_argument("--prior-tokens", type=int, default=0)
    ap.add_argument("--recall-hits", type=int, default=0, help="proxy from search_prior or semantic")
    args = ap.parse_args()

    if args.text:
        m = measure_report(text=args.text, prior_path=args.prior, use_compress=True)
    elif args.report:
        m = measure_report(report_path=args.report, prior_path=args.prior, use_compress=True)
    else:
        ap.error("need --report or --text")

    # merge legacy fields for compat
    m.setdefault("recall_proxy_hits", args.recall_hits)
    print(json.dumps(m, indent=2))

if __name__ == "__main__":
    main()
